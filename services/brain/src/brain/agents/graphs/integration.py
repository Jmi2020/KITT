"""
Integration layer between LangGraph router and Brain orchestrator.

Provides feature-flagged routing that can use either:
1. LangGraph-based router_graph (enhanced reasoning)
2. Traditional BrainRouter (fallback)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from common.db.models import RoutingTier

if TYPE_CHECKING:
    from brain.memory import MemoryClient
    from brain.routing.multi_server_client import MultiServerLlamaCppClient
    from brain.tools.mcp_client import MCPClient
    from brain.routing.router import RoutingRequest, RoutingResult

from .router_graph import create_router_graph

logger = logging.getLogger(__name__)


class LangGraphRoutingIntegration:
    """
    Feature-flagged integration for LangGraph-based routing.

    Falls back to traditional router if LangGraph disabled or fails.
    """

    def __init__(
        self,
        llm_client: MultiServerLlamaCppClient,
        memory_client: MemoryClient,
        mcp_client: MCPClient,
    ) -> None:
        """
        Initialize LangGraph routing integration.

        Args:
            llm_client: Multi-server llama.cpp client (PRIMARY, always local Q4/F16)
            memory_client: Memory search client
            mcp_client: MCP tool client
        """
        self.llm_client = llm_client
        self.memory_client = memory_client
        self.mcp_client = mcp_client

        # Feature flag
        self.enabled = os.getenv("BRAIN_USE_LANGGRAPH", "false").lower() == "true"

        # Rollout percentage (0-100)
        self.rollout_percent = int(os.getenv("BRAIN_LANGGRAPH_ROLLOUT_PERCENT", "0"))

        # Router graph (lazy init)
        self._router_graph = None

        if self.enabled:
            logger.info(
                f"LangGraph routing enabled (rollout: {self.rollout_percent}%)"
            )
        else:
            logger.info("LangGraph routing disabled (using traditional router)")

    async def should_use_langgraph(self, request: RoutingRequest) -> bool:
        """
        Determine if this request should use LangGraph routing.

        Args:
            request: Routing request

        Returns:
            True if should use LangGraph, False for traditional router
        """
        if not self.enabled:
            return False

        # Rollout logic (hash-based for consistency)
        if self.rollout_percent < 100:
            # Use conversation_id hash for stable A/B testing
            hash_val = hash(request.conversation_id) % 100
            if hash_val >= self.rollout_percent:
                return False

        return True

    async def route_with_langgraph(
        self, request: RoutingRequest
    ) -> RoutingResult:
        """
        Route using LangGraph router_graph.

        Args:
            request: Routing request

        Returns:
            RoutingResult compatible with existing system
        """
        # Lazy init router graph
        if self._router_graph is None:
            self._router_graph = await create_router_graph(
                llm_client=self.llm_client,
                memory_client=self.memory_client,
                mcp_client=self.mcp_client,
                max_refinements=2,
            )

        try:
            # Run router graph
            final_state = await self._router_graph.run(
                query=request.prompt,
                user_id=request.user_id or "unknown",
                conversation_id=request.conversation_id,
                request_id=request.request_id,
            )

            # Convert router graph state to RoutingResult
            return self._convert_to_routing_result(request, final_state)

        except Exception as exc:
            logger.error(f"LangGraph routing failed: {exc}", exc_info=True)
            # Return error result
            from brain.routing.router import RoutingResult

            return RoutingResult(
                output=f"Routing error: {exc}",
                confidence=0.0,
                tier=RoutingTier.LOCAL,
                request_id=request.request_id,
                conversation_id=request.conversation_id,
                cost_usd=0.0,
                latency_ms=0,
            )

    def _convert_to_routing_result(
        self, request: RoutingRequest, state: dict
    ) -> RoutingResult:
        """
        Convert router graph state to RoutingResult.

        Args:
            request: Original routing request
            state: Final router graph state

        Returns:
            RoutingResult for Brain orchestrator
        """
        from brain.routing.router import RoutingResult

        return RoutingResult(
            output=state.get("response", "No response generated"),
            confidence=state.get("confidence", 0.5),
            tier=state.get("tier_used", RoutingTier.LOCAL),
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            cost_usd=state.get("cost_usd", 0.0),
            latency_ms=state.get("latency_ms", 0),
            model_used=state.get("tier_used", RoutingTier.LOCAL).value,
            # Additional metadata from graph execution
            metadata={
                "langgraph": True,
                "complexity_score": state.get("complexity_score"),
                "nodes_executed": state.get("nodes_executed", []),
                "tools_used": list(state.get("tool_results", {}).keys()),
                "refinement_count": state.get("refinement_count", 0),
                "escalated_to_f16": state.get("escalated_to_f16", False),
            },
        )


async def create_langgraph_integration(
    llm_client: MultiServerLlamaCppClient,
    memory_client: MemoryClient,
    mcp_client: MCPClient,
) -> LangGraphRoutingIntegration:
    """
    Factory function to create LangGraph integration.

    Args:
        llm_client: Multi-server llama.cpp client (PRIMARY, always local Q4/F16)
        memory_client: Memory client
        mcp_client: MCP client

    Returns:
        Initialized integration
    """
    return LangGraphRoutingIntegration(
        llm_client=llm_client,
        memory_client=memory_client,
        mcp_client=mcp_client,
    )
