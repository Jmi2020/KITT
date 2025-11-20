# noqa: D401
"""Confidence-based routing engine."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import logging

from pydantic import BaseModel

from common.config import settings
from common.db.models import RoutingTier
from common.cache import CacheRecord, SemanticCache

from ..metrics import record_decision
from ..metrics.slo import SLOCalculator
from ..logging_config import log_routing_decision, log_confidence_analysis
from ..prompts.unified import KittySystemPrompt
from .audit_store import RoutingAuditStore
from .cloud_clients import FrontierClient, MCPClient
from .config import RoutingConfig, get_routing_config
from .confidence_scorer import RoutingConfidenceScorer
from .cost_tracker import CostTracker
from .multi_server_client import MultiServerLlamaCppClient
from .ml_local_client import MLXLocalClient
from .permission import PermissionManager
from .pricing import estimate_cost
from .tool_registry import get_tools_for_prompt
from .summarizer import HermesSummarizer
from ..tools.model_config import detect_model_format
from ..usage_stats import UsageStats

# Import ReAct agent and tool MCP client
from ..agents import ReActAgent
from ..tools.mcp_client import MCPClient as ToolMCPClient
from ..conversation.safety import SafetyChecker

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
    tool_mode: str = "auto"  # Tool calling mode: "auto", "on", "off"
    allow_paid: bool = False  # Whether paid providers/tools are authorized by user
    vision_targets: Optional[List[str]] = None


@dataclass
class RoutingResult:
    output: str
    tier: RoutingTier
    confidence: float
    latency_ms: int
    cached: bool = False
    metadata: Optional[Dict[str, Any]] = None


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
        llama_client: Optional[MultiServerLlamaCppClient] = None,
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
        self._llama = llama_client or MultiServerLlamaCppClient()
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
        self._prompt_builder = KittySystemPrompt()
        self._summarizer = HermesSummarizer()
        self._confidence_scorer = RoutingConfidenceScorer()

        # Initialize tool MCP client with Perplexity integration and ReAct agent
        self._tool_mcp = tool_mcp_client or ToolMCPClient(perplexity_client=self._mcp)

        # Initialize safety checker for tool execution validation
        self._safety_checker = SafetyChecker()

        # Agent uses Q4 orchestrator for tool calling
        self._agent = ReActAgent(
            llm_client=self._llama,
            mcp_client=self._tool_mcp,
            max_iterations=10,
            model_alias="kitty-q4",
        )

    async def route(self, request: RoutingRequest) -> RoutingResult:
        cache_key = _hash_prompt(request.prompt)
        if self._cache and not request.freshness_required and not request.vision_targets:
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

        # Check for agentic routing first - agent can decide to use vision or CAD tools
        if request.use_agent:
            result = await self._invoke_agent(request)
            return await self._finalize_result(request, result, cache_key=cache_key)

        # If not using agent, run vision pipeline for simple reference gathering
        if request.vision_targets:
            logger.info("Routing vision targets: %s", ", ".join(request.vision_targets))
            pipeline_result = await self._run_vision_pipeline(request)
            if pipeline_result:
                return await self._finalize_result(request, pipeline_result, cache_key=None)

        result = await self._invoke_local(request)
        if request.force_tier == RoutingTier.local:
            return await self._finalize_result(request, result)

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
            if not request.allow_paid:
                logger.info("Paid tiers blocked: override keyword not detected.")
                if not result.metadata:
                    result.metadata = {}
                result.metadata["paid_override_required"] = True
            else:
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

        return await self._finalize_result(request, result, cache_key=cache_key)

    async def route_stream(self, request: RoutingRequest):
        """Stream query response with real-time thinking traces.

        Yields chunks in format:
        {
            "delta": str,              # Content delta
            "delta_thinking": str,     # Thinking trace delta (optional)
            "done": bool,              # Whether stream is complete
            "routing_result": RoutingResult  # Final result (only when done=True)
        }

        Note: Streaming only supports local tier routing (no escalation or caching).
        """
        # Streaming doesn't support caching or escalation
        # Only use local tier for streaming

        start = time.perf_counter()
        full_content = ""
        full_thinking = ""

        # Default to F16 (Ollama reasoner) for streaming with thinking traces
        # Q4 (llama.cpp) doesn't support streaming yet
        model_alias = request.model_hint or "kitty-f16"
        model_format = detect_model_format(model_alias)

        # Get tools based on prompt and mode
        tools = get_tools_for_prompt(request.prompt, mode=request.tool_mode)
        if not request.allow_paid:
            tools = [
                tool
                for tool in tools
                if tool.get("function", {}).get("name") not in {"research_deep"}
            ]

        final_prompt = request.prompt
        if tools:
            final_prompt = self._prompt_builder.build(
                mode="cli",
                tools=tools,
                model_format=model_format.value,
                query=request.prompt,
                freshness_required=request.freshness_required,
                vision_targets=request.vision_targets,
            )

        # Stream from llama client
        async for chunk in self._llama.generate_stream(final_prompt, model_alias):
            # Accumulate full response
            if chunk.get("delta"):
                full_content += chunk["delta"]
            if chunk.get("delta_thinking"):
                full_thinking += chunk["delta_thinking"]

            # Yield chunk to caller
            yield chunk

            # If done, construct final RoutingResult
            if chunk.get("done"):
                latency = int((time.perf_counter() - start) * 1000)

                metadata = {
                    "provider": "llamacpp",
                    "model": model_alias or self._config.llamacpp.model_alias or self._config.local_models[0],
                    "host": self._config.llamacpp.host,
                    "streaming": True,
                    "thinking_length": len(full_thinking) if full_thinking else 0,
                }

                # Use confidence scorer to calculate dynamic confidence
                confidence_result = self._confidence_scorer.score_response(
                    response_text=full_content,
                    tool_calls=[],
                    metadata=metadata,
                    prompt=request.prompt,
                )
                confidence = confidence_result.overall

                # Log routing decision
                log_routing_decision(
                    logger=logger,
                    tier="local",
                    model=metadata["model"],
                    confidence=confidence,
                    cost=_COST_BY_TIER[RoutingTier.local],
                    prompt=request.prompt,
                    response=full_content,
                    metadata=metadata,
                )

                result = RoutingResult(
                    output=full_content,
                    tier=RoutingTier.local,
                    confidence=confidence,
                    latency_ms=latency,
                    metadata=metadata,
                )

                # Record audit and usage
                self._record(request, result, cache_key=None)
                self._record_usage(result)

                # Yield final chunk with result
                yield {
                    "delta": "",
                    "delta_thinking": None,
                    "done": True,
                    "routing_result": result,
                }

    async def _invoke_local(self, request: RoutingRequest) -> RoutingResult:
        start = time.perf_counter()
        # Default to Q4 orchestrator model for tool calling
        model_alias = request.model_hint or "kitty-q4"
        model_format = detect_model_format(model_alias)

        # Get tools based on prompt and mode
        tools = get_tools_for_prompt(request.prompt, mode=request.tool_mode)
        if not request.allow_paid:
            tools = [
                tool
                for tool in tools
                if tool.get("function", {}).get("name") not in {"research_deep"}
            ]

        final_prompt = request.prompt
        if tools:
            final_prompt = self._prompt_builder.build(
                mode="cli",
                tools=tools,
                model_format=model_format.value,
                query=request.prompt,
                freshness_required=request.freshness_required,
                vision_targets=request.vision_targets,
            )

        # Pass tools to llama client
        response = await self._llama.generate(final_prompt, model_alias, tools=tools)

        # Handle tool calls if present
        tool_calls = response.get("tool_calls", [])
        if tool_calls:
            logger.info(f"Model requested {len(tool_calls)} tool calls")
            output = await self._execute_tools(
                tool_calls, request.prompt, model_alias, allow_paid=request.allow_paid
            )
        else:
            output = (
                response.get("response") or response.get("output") or response.get("completion") or ""
            )

        latency = int((time.perf_counter() - start) * 1000)

        # Calculate dynamic confidence score
        metadata = {
            "provider": "llamacpp",
            "model": model_alias
            or self._config.llamacpp.model_alias
            or self._config.local_models[0],
            "host": self._config.llamacpp.host,
            "tools_used": len(tool_calls) if tool_calls else 0,
            "stop_reason": response.get("stop_type"),
            "truncated": response.get("truncated", False),
            "raw": response.get("raw", {}),
        }

        # Use confidence scorer to calculate dynamic confidence
        confidence_result = self._confidence_scorer.score_response(
            response_text=output,
            tool_calls=tool_calls,
            metadata=metadata,
            prompt=request.prompt,
        )
        confidence = confidence_result.overall

        # Log confidence analysis if warnings exist
        if confidence_result.warnings:
            log_confidence_analysis(
                logger=logger,
                confidence=confidence,
                factors=confidence_result.factors.to_dict(),
                explanation=confidence_result.explanation,
                warnings=confidence_result.warnings,
            )

        # Extract token usage from response
        raw_response = response.get("raw", {})
        usage = raw_response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Calculate actual cost based on tokens (if available)
        if prompt_tokens > 0 or completion_tokens > 0:
            actual_cost = self._cost_tracker.record_tokens(
                tier=RoutingTier.local,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                usage_data=usage,
            )
            metadata["token_usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": actual_cost,
            }
        else:
            # Fallback to fixed cost if no token data
            actual_cost = _COST_BY_TIER[RoutingTier.local]
            self._cost_tracker.record(RoutingTier.local, actual_cost)

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="local",
            model=metadata["model"],
            confidence=confidence,
            cost=actual_cost,
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

        # Extract token usage if available
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Calculate actual cost based on tokens (if available)
        if prompt_tokens > 0 or completion_tokens > 0:
            actual_cost = self._cost_tracker.record_tokens(
                tier=RoutingTier.mcp,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                usage_data=usage,
            )
            metadata["token_usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": actual_cost,
            }
        else:
            # Fallback to fixed cost
            actual_cost = _COST_BY_TIER[RoutingTier.mcp]
            self._cost_tracker.record(RoutingTier.mcp, actual_cost)

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="mcp",
            model="perplexity",
            confidence=0.6,
            cost=actual_cost,
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

        # Extract token usage from OpenAI response
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Calculate actual cost based on tokens (if available)
        if prompt_tokens > 0 or completion_tokens > 0:
            actual_cost = self._cost_tracker.record_tokens(
                tier=RoutingTier.frontier,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                usage_data=usage,
            )
            metadata["token_usage"] = {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": actual_cost,
            }
        else:
            # Fallback to fixed cost
            actual_cost = _COST_BY_TIER[RoutingTier.frontier]
            self._cost_tracker.record(RoutingTier.frontier, actual_cost)

        # Log routing decision
        log_routing_decision(
            logger=logger,
            tier="frontier",
            model=settings.openai_model,
            confidence=0.9,
            cost=actual_cost,
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

    async def _execute_tools(
        self,
        tool_calls: list,
        original_prompt: str,
        model_alias: Optional[str],
        allow_paid: bool = False
    ) -> str:
        """Execute tool calls with safety checks and return formatted response.

        Args:
            tool_calls: List of tool call objects from model
            original_prompt: Original user prompt
            model_alias: Model alias for follow-up call
            allow_paid: Whether paid/premium tools are authorized

        Returns:
            Final response after tool execution, or error if safety check fails
        """
        tool_results = []

        for tool_call in tool_calls:
            try:
                function_name = None
                arguments: Dict[str, Any] = {}

                if hasattr(tool_call, "name"):
                    function_name = getattr(tool_call, "name")
                    arguments = getattr(tool_call, "arguments", {}) or {}
                elif isinstance(tool_call, dict):
                    if "function" in tool_call:
                        func = tool_call.get("function") or {}
                        function_name = func.get("name")
                        arguments = func.get("arguments", {}) or {}
                    else:
                        function_name = tool_call.get("name")
                        arguments = tool_call.get("arguments", {}) or {}

                if not isinstance(arguments, dict):
                    arguments = {}

                if not function_name:
                    logger.warning("Received tool call without function name: %s", tool_call)
                    continue

                # Safety check before execution
                safety_result = self._safety_checker.check_tool_execution(
                    tool_name=function_name,
                    tool_args=arguments,
                    override_provided=allow_paid
                )

                if not safety_result.approved:
                    # Tool execution blocked by safety policy
                    error_msg = f"Tool '{function_name}' blocked by safety policy: {safety_result.reason}"

                    if safety_result.requires_confirmation:
                        error_msg = (
                            f"⚠️  {function_name} requires confirmation.\n"
                            f"Hazard class: {safety_result.hazard_class}\n"
                            f"Please confirm with phrase: '{safety_result.confirmation_phrase}'"
                        )
                        logger.warning(error_msg)
                        tool_results.append({
                            "tool": function_name,
                            "error": "Confirmation required",
                            "message": error_msg
                        })
                        continue

                    if safety_result.requires_override:
                        error_msg = (
                            f"⚠️  {function_name} requires budget override.\n"
                            f"Reason: {safety_result.reason}\n"
                            f"This tool has restricted access."
                        )
                        logger.warning(error_msg)
                        tool_results.append({
                            "tool": function_name,
                            "error": "Budget override required",
                            "message": error_msg
                        })
                        continue

                    # Other safety failures
                    logger.warning(error_msg)
                    tool_results.append({
                        "tool": function_name,
                        "error": "Safety check failed",
                        "message": error_msg
                    })
                    continue

                logger.info(f"Executing tool: {function_name} with args: {arguments}")

                if function_name == "web_search":
                    # Execute web search via MCP (Perplexity)
                    if self._mcp:
                        query = arguments.get("query", "")
                        result = await self._mcp.query({"query": query})
                        tool_results.append(
                            {
                                "tool": "web_search",
                                "query": query,
                                "result": result.get("output") or result.get("text", "No results"),
                            }
                        )
                    else:
                        tool_results.append(
                            {"tool": "web_search", "error": "MCP client not available"}
                        )

                elif function_name == "generate_cad":
                    # Execute CAD generation via CAD service
                    description = arguments.get("description", "")
                    format_type = arguments.get("format", "step")
                    # TODO: Call CAD service endpoint
                    tool_results.append(
                        {
                            "tool": "generate_cad",
                            "description": description,
                            "result": f"CAD generation queued for: {description} (format: {format_type})",
                        }
                    )

                elif function_name == "reason_with_f16":
                    # Delegate to F16 reasoning engine
                    query = arguments.get("query", "")
                    context = arguments.get("context", "")

                    # Build reasoning prompt
                    reasoning_prompt = query
                    if context:
                        reasoning_prompt = f"Context:\n{context}\n\nQuestion: {query}"

                    logger.info(f"Delegating to F16 reasoning engine: {query[:100]}...")

                    # Call F16 model (no tools)
                    f16_response = await self._llama.generate(
                        reasoning_prompt,
                        model="kitty-f16",
                        tools=None
                    )
                    f16_output = (
                        f16_response.get("response")
                        or f16_response.get("output")
                        or f16_response.get("completion")
                        or "No response from F16 model"
                    )

                    tool_results.append(
                        {
                            "tool": "reason_with_f16",
                            "query": query,
                            "result": f16_output,
                        }
                    )

                else:
                    tool_results.append({"tool": function_name, "error": "Unknown tool"})

            except Exception as exc:
                logger.error(f"Tool execution failed: {exc}")
                tool_results.append(
                    {"tool": function_name if "function_name" in locals() else "unknown", "error": str(exc)}
                )

        # Format tool results for final response
        results_text = "\n\n".join(
            [
                f"Tool: {r['tool']}\nResult: {r.get('result', r.get('error', 'Unknown'))}"
                for r in tool_results
            ]
        )

        # Call model again with tool results to get final answer
        follow_up_prompt = f"""Original question: {original_prompt}

Tool execution results:
{results_text}

Based on the tool results above, provide a comprehensive answer to the original question."""

        response = await self._llama.generate(follow_up_prompt, model_alias, tools=None)
        return (
            response.get("response") or response.get("output") or response.get("completion") or results_text
        )

    async def _invoke_agent(self, request: RoutingRequest) -> RoutingResult:
        """Run ReAct agent with tool use for complex queries.

        Args:
            request: Routing request

        Returns:
            RoutingResult with agent response
        """
        start = time.perf_counter()

        if request.vision_targets:
            logger.info(
                "Routing with vision targets: %s",
                ", ".join(request.vision_targets[:3]),
            )
        else:
            logger.info("Routing without vision targets")

        # Run ReAct agent
        agent_result = await self._agent.run(
            request.prompt,
            freshness_required=request.freshness_required,
            allow_paid=request.allow_paid,
            vision_targets=request.vision_targets,
        )

        latency = int((time.perf_counter() - start) * 1000)

        # Format agent result as RoutingResult
        metadata: Dict[str, Any] = {
            "provider": "react_agent",
            "iterations": str(agent_result.iterations),
            "tools_used": str(len([s for s in agent_result.steps if s.action])),
            "success": str(agent_result.success),
        }
        if request.vision_targets:
            metadata["vision_targets"] = request.vision_targets
        if agent_result.truncated:
            metadata["truncated"] = True
        if agent_result.stop_reason:
            metadata["stop_reason"] = agent_result.stop_reason

        if agent_result.error:
            metadata["error"] = agent_result.error
        if agent_result.steps:
            metadata["agent_steps"] = [asdict(step) for step in agent_result.steps]

        # Add confirmation information if present
        if agent_result.requires_confirmation:
            metadata["requires_confirmation"] = True
            metadata["confirmation_phrase"] = agent_result.confirmation_phrase
            metadata["pending_tool"] = agent_result.pending_tool
            metadata["pending_tool_args"] = agent_result.pending_tool_args
            metadata["hazard_class"] = agent_result.hazard_class
            metadata["confirmation_reason"] = "Tool requires user confirmation before execution"
            logger.warning(
                f"Agent requires confirmation for {agent_result.pending_tool}: {agent_result.hazard_class}"
            )

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
        if request.vision_targets:
            return
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

    def _record_usage(self, result: RoutingResult) -> None:
        provider = (result.metadata or {}).get("provider", result.tier.value)
        cost = _COST_BY_TIER.get(result.tier, 0.0)
        UsageStats.record(provider=provider, tier=result.tier.value, cost=cost)

    async def _finalize_result(
        self, request: RoutingRequest, result: RoutingResult, cache_key: Optional[str] = None
    ) -> RoutingResult:
        result = await self._maybe_summarize(result)
        self._record(request, result, cache_key=cache_key)
        self._record_usage(result)
        return result

    async def _maybe_summarize(self, result: RoutingResult) -> RoutingResult:
        if not self._summarizer.enabled:
            return result

        metadata = result.metadata or {}
        provider = metadata.get("provider")
        if provider != "react_agent":
            return result
        if metadata.get("vision_targets"):
            return result

        agent_steps = metadata.get("agent_steps") or []
        truncated = bool(metadata.get("truncated"))
        output_text = result.output or ""

        if not self._summarizer.should_summarize(
            output_len=len(output_text), truncated=truncated, has_agent_steps=bool(agent_steps)
        ):
            return result

        summary = await self._summarizer.summarize(output_text, agent_steps=agent_steps)
        if not summary:
            return result

        updated_metadata = dict(metadata)
        updated_metadata.setdefault("raw_output", output_text)
        updated_metadata["summary_provider"] = self._summarizer.alias
        updated_metadata["summary_applied"] = True

        result.output = summary
        result.metadata = updated_metadata
        UsageStats.record(provider=self._summarizer.alias, tier="local", cost=0.0)
        return result

    async def _run_vision_pipeline(self, request: RoutingRequest) -> Optional[RoutingResult]:
        if not self._tool_mcp or not request.vision_targets:
            if not self._tool_mcp:
                logger.info("Vision pipeline skipped: MCP client unavailable")
            return None

        start = time.perf_counter()
        references: List[Dict[str, Any]] = []
        tools_used = 0

        for target in request.vision_targets:
            query = target.strip()
            if not query:
                continue
            logger.info("Vision pipeline starting search for '%s'", query)

            try:
                search = await self._tool_mcp.execute_tool(
                    "image_search", {"query": query, "max_results": 8}
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vision search failed for '%s': %s", query, exc)
                continue

            tools_used += 1
            if not search.get("success"):
                continue
            images = (search.get("data") or {}).get("results") or []
            if not images:
                logger.info("Vision pipeline found 0 images for '%s'", query)
                continue

            try:
                filtered = await self._tool_mcp.execute_tool(
                    "image_filter",
                    {"query": query, "images": images, "min_score": 0.35},
                )
                tools_used += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vision filter failed for '%s': %s", query, exc)
                filtered = {"success": False}

            ranked = images
            if filtered.get("success"):
                ranked = (filtered.get("data") or {}).get("results") or images
            top_images = ranked[:3]
            if not top_images:
                continue

            stored_urls: Dict[str, str] = {}
            payload = {
                "session_id": request.conversation_id,
                "images": [
                    {
                        "id": img.get("id"),
                        "image_url": img.get("image_url"),
                        "title": img.get("title"),
                        "source": img.get("source"),
                        "caption": img.get("description"),
                    }
                    for img in top_images
                ],
            }

            try:
                stored = await self._tool_mcp.execute_tool("store_selection", payload)
                tools_used += 1
                if stored.get("success"):
                    for entry in (stored.get("data") or {}).get("stored", []):
                        stored_urls[entry.get("id")] = entry.get("download_url") or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vision storage failed for '%s': %s", query, exc)

            formatted = []
            for img in top_images:
                image_id = img.get("id")
                formatted.append(
                    {
                        "title": img.get("title") or "Image",
                        "image_url": img.get("image_url"),
                        "source": img.get("source"),
                        "download_url": stored_urls.get(image_id),
                    }
                )
            references.append({"query": query, "images": formatted})
            logger.info("Vision pipeline stored %d refs for '%s'", len(formatted), query)

        if not references:
            logger.info("Vision pipeline produced no references")
            return None

        lines: List[str] = ["Here are reference images gathered from the vision workflow:\n"]
        for ref in references:
            lines.append(f"### {ref['query']}")
            for idx, image in enumerate(ref["images"], 1):
                url = image.get("download_url") or image.get("image_url")
                title = image.get("title") or f"Image {idx}"
                source = image.get("source") or "unknown source"
                if url:
                    lines.append(f"{idx}. [{title}]({url}) — source: {source}")
                else:
                    lines.append(f"{idx}. {title} — source: {source}")
            lines.append("")

        latency = int((time.perf_counter() - start) * 1000)
        metadata = {
            "provider": "vision_pipeline",
            "vision_targets": request.vision_targets,
            "references": references,
            "tools_used": str(tools_used),
        }
        logger.info(
            "Vision pipeline returning %d reference sets in %dms",
            len(references),
            latency,
        )

        return RoutingResult(
            output="\n".join(lines).strip(),
            tier=RoutingTier.local,
            confidence=0.92,
            latency_ms=latency,
            metadata=metadata,
        )


__all__ = ["BrainRouter", "RoutingRequest", "RoutingResult"]
