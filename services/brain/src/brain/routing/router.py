# noqa: D401
"""Confidence-based routing engine."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Dict, Optional

import logging

from pydantic import BaseModel

from common.config import settings
from common.db.models import RoutingTier
from common.cache import CacheRecord, SemanticCache

from ..metrics import record_decision
from ..metrics.slo import SLOCalculator
from ..logging_config import log_routing_decision, log_confidence_analysis
from .audit_store import RoutingAuditStore
from .cloud_clients import FrontierClient, MCPClient
from .config import RoutingConfig, get_routing_config
from .cost_tracker import CostTracker
from .llama_cpp_client import LlamaCppClient
from .ml_local_client import MLXLocalClient
from .permission import PermissionManager
from .pricing import estimate_cost

# Import ReAct agent and tool MCP client
from ..agents import ReActAgent
from ..tools.mcp_client import MCPClient as ToolMCPClient

logger = logging.getLogger("brain.routing")


class RoutingRequest(BaseModel):
    conversation_id: str
    request_id: str
    prompt: str
    user_id: Optional[str] = None
    force_tier: Optional[RoutingTier] = None
    freshness_required: bool = False
    model_hint: Optional[str] = None
    use_agent: bool = False  # Enable agentic routing with tool use


@dataclass
class RoutingResult:
    output: str
    tier: RoutingTier
    confidence: float
    latency_ms: int
    cached: bool = False
    metadata: Optional[Dict[str, str]] = None


def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


_COST_BY_TIER = {
    RoutingTier.local: 0.0001,
    RoutingTier.mcp: 0.002,
    RoutingTier.frontier: 0.06,
}


class BrainRouter:
    def __init__(
        self,
        config: Optional[RoutingConfig] = None,
        llama_client: Optional[LlamaCppClient] = None,
        mlx: Optional[MLXLocalClient] = None,
        audit_store: Optional[RoutingAuditStore] = None,
        cache: Optional[SemanticCache] = None,
        mcp_client: Optional[MCPClient] = None,
        frontier_client: Optional[FrontierClient] = None,
        cost_tracker: Optional[CostTracker] = None,
        slo_calculator: Optional[SLOCalculator] = None,
        permission_manager: Optional[PermissionManager] = None,
        tool_mcp_client: Optional[ToolMCPClient] = None,
    ) -> None:
        self._config = config or get_routing_config()
        self._llama = llama_client or LlamaCppClient(self._config.llamacpp)
        self._mlx = mlx or MLXLocalClient()
        self._audit = audit_store or RoutingAuditStore()
        self._cache = cache or (SemanticCache() if settings.semantic_cache_enabled else None)
        self._mcp = mcp_client
        if not self._mcp and settings.perplexity_api_key:
            # Use perplexity_model_search if available, otherwise default to "sonar"
            model = getattr(settings, "perplexity_model_search", "sonar")
            self._mcp = MCPClient(settings.perplexity_base_url, settings.perplexity_api_key, model=model)
        self._frontier = frontier_client
        if not self._frontier and settings.openai_api_key:
            self._frontier = FrontierClient(
                settings.openai_base_url, settings.openai_api_key, settings.openai_model
            )
        self._cost_tracker = cost_tracker or CostTracker()
        self._slo_calculator = slo_calculator or SLOCalculator()
        self._permission = permission_manager or PermissionManager()

        # Initialize tool MCP client with Perplexity integration and ReAct agent
        self._tool_mcp = tool_mcp_client or ToolMCPClient(perplexity_client=self._mcp)
        self._agent = ReActAgent(
            llm_client=self._llama,
            mcp_client=self._tool_mcp,
            max_iterations=10,
        )

    async def route(self, request: RoutingRequest) -> RoutingResult:
        cache_key = _hash_prompt(request.prompt)
        if self._cache and not request.freshness_required:
            cached = self._cache.fetch(cache_key)
            if cached:
                result = RoutingResult(
                    output=cached.response,
                    tier=RoutingTier.local,
                    confidence=cached.confidence,
                    latency_ms=0,
                    cached=True,
                )
                self._audit.record(
                    conversation_id=request.conversation_id,
                    request_id=request.request_id,
                    tier=result.tier,
                    confidence=result.confidence,
                    latency_ms=result.latency_ms,
                    user_id=request.user_id,
                )
                return result

        # Check for agentic routing
        if request.use_agent:
            result = await self._invoke_agent(request)
            self._record(request, result, cache_key=cache_key)
            return result

        result = await self._invoke_local(request)
        if request.force_tier == RoutingTier.local:
            self._record(request, result)
            return result

        # Check if escalation is needed
        needs_escalation = (
            result.confidence < self._config.thresholds.local_confidence
            or request.force_tier == RoutingTier.mcp
            or request.freshness_required
        )

        # Log confidence analysis
        reason = []
        if result.confidence < self._config.thresholds.local_confidence:
            reason.append(f"low confidence ({result.confidence:.2f} < {self._config.thresholds.local_confidence})")
        if request.force_tier == RoutingTier.mcp:
            reason.append("forced MCP tier")
        if request.freshness_required:
            reason.append("freshness required")

        log_confidence_analysis(
            logger=logger,
            prompt=request.prompt,
            local_confidence=result.confidence,
            needs_escalation=needs_escalation,
            reason=" + ".join(reason) if reason else "local sufficient",
            model=result.metadata.get("model", "unknown") if result.metadata else "unknown",
        )

        if needs_escalation:
            # Try MCP first (cheaper)
            if self._mcp:
                cost_est = estimate_cost(request.prompt, "perplexity")
                reason = (
                    "low confidence"
                    if result.confidence < self._config.thresholds.local_confidence
                    else "fresh data required"
                )  # noqa: E501

                # Request permission
                approved = await self._permission.request_permission(
                    tier=RoutingTier.mcp,
                    provider="perplexity",
                    estimated_cost=cost_est,
                    reason=reason,
                    conversation_id=request.conversation_id,
                )

                if approved:
                    cloud_result = await self._invoke_mcp(request)
                    if cloud_result:
                        result = cloud_result
                        # TODO: Extract actual token count from response and update cost
                        # self._permission.record_actual_cost(actual_cost)

            # Fallback to Frontier if MCP didn't work
            if result.tier == RoutingTier.local and self._frontier:
                cost_est = estimate_cost(request.prompt, "openai")
                reason = "MCP unavailable or low quality"

                approved = await self._permission.request_permission(
                    tier=RoutingTier.frontier,
                    provider="openai",
                    estimated_cost=cost_est,
                    reason=reason,
                    conversation_id=request.conversation_id,
                )

                if approved:
                    frontier_result = await self._invoke_frontier(request)
                    if frontier_result:
                        result = frontier_result
                        # TODO: Extract actual token count from response and update cost

        self._record(request, result, cache_key=cache_key)
        return result

    async def _invoke_local(self, request: RoutingRequest) -> RoutingResult:
        start = time.perf_counter()
        model_alias = request.model_hint or (
            self._config.local_models[0] if self._config.local_models else None
        )
        response = await self._llama.generate(request.prompt, model_alias)
        latency = int((time.perf_counter() - start) * 1000)
        output = (
            response.get("response") or response.get("output") or response.get("completion") or ""
        )
        confidence = 0.85 if output else 0.0
        metadata = {
            "provider": "llamacpp",
            "model": model_alias
            or self._config.llamacpp.model_alias
            or self._config.local_models[0],
            "host": self._config.llamacpp.host,
        }

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="local",
            model=metadata["model"],
            confidence=confidence,
            cost=_COST_BY_TIER[RoutingTier.local],
            prompt=request.prompt,
            response=output,
            metadata=metadata,
        )

        return RoutingResult(
            output=output,
            tier=RoutingTier.local,
            confidence=confidence,
            latency_ms=latency,
            metadata=metadata,
        )

    async def _invoke_mcp(self, request: RoutingRequest) -> Optional[RoutingResult]:
        if not self._mcp:
            return None
        start = time.perf_counter()
        response = await self._mcp.query({"query": request.prompt})
        latency = int((time.perf_counter() - start) * 1000)
        output = response.get("output") or response.get("text") or ""
        if not output:
            return None
        metadata = {"provider": "perplexity_mcp"}

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="mcp",
            model="perplexity",
            confidence=0.6,
            cost=_COST_BY_TIER[RoutingTier.mcp],
            prompt=request.prompt,
            response=output,
            metadata=metadata,
        )

        return RoutingResult(
            output=output,
            tier=RoutingTier.mcp,
            confidence=0.6,
            latency_ms=latency,
            metadata=metadata,
        )

    async def _invoke_frontier(self, request: RoutingRequest) -> Optional[RoutingResult]:
        if not self._frontier:
            return None
        start = time.perf_counter()
        response = await self._frontier.generate(request.prompt)
        latency = int((time.perf_counter() - start) * 1000)
        choices = response.get("choices")
        if not choices:
            return None
        output = choices[0]["message"]["content"]
        metadata = {"provider": "frontier_llm", "model": settings.openai_model}

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="frontier",
            model=settings.openai_model,
            confidence=0.9,
            cost=_COST_BY_TIER[RoutingTier.frontier],
            prompt=request.prompt,
            response=output,
            metadata=metadata,
        )

        return RoutingResult(
            output=output,
            tier=RoutingTier.frontier,
            confidence=0.9,
            latency_ms=latency,
            metadata=metadata,
        )

    async def _invoke_agent(self, request: RoutingRequest) -> RoutingResult:
        """Run ReAct agent with tool use for complex queries.

        Args:
            request: Routing request

        Returns:
            RoutingResult with agent response
        """
        start = time.perf_counter()

        # Run ReAct agent
        agent_result = await self._agent.run(request.prompt)

        latency = int((time.perf_counter() - start) * 1000)

        # Format agent result as RoutingResult
        metadata = {
            "provider": "react_agent",
            "iterations": str(agent_result.iterations),
            "tools_used": str(len([s for s in agent_result.steps if s.action])),
            "success": str(agent_result.success),
        }

        if agent_result.error:
            metadata["error"] = agent_result.error

        # High confidence if agent succeeded
        confidence = 0.9 if agent_result.success else 0.5

        return RoutingResult(
            output=agent_result.answer,
            tier=RoutingTier.local,  # Agent uses local LLM + tools
            confidence=confidence,
            latency_ms=latency,
            metadata=metadata,
        )

    def _record(
        self, request: RoutingRequest, result: RoutingResult, cache_key: Optional[str] = None
    ) -> None:
        if self._cache and cache_key and not result.cached:
            self._cache.store(
                CacheRecord(
                    key=cache_key,
                    prompt=request.prompt,
                    response=result.output,
                    confidence=result.confidence,
                )
            )
        cost = _COST_BY_TIER.get(result.tier, 0.0)
        self._cost_tracker.record(result.tier, cost)
        local_ratio = self._slo_calculator.update(result.tier)
        try:
            self._audit.record(
                conversation_id=request.conversation_id,
                request_id=request.request_id,
                tier=result.tier,
                confidence=result.confidence,
                latency_ms=result.latency_ms,
                user_id=request.user_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to record routing decision: %s", exc)
        record_decision(
            tier=result.tier.value,
            latency_ms=result.latency_ms,
            cost=cost,
            local_ratio=local_ratio,
        )


__all__ = ["BrainRouter", "RoutingRequest", "RoutingResult"]
