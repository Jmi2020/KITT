"""
MCP Tool Integration for Research Pipeline

Integrates existing MCP tools (web_search, Perplexity, memory) with research system.
Uses UnifiedPermissionGate for streamlined permission checks.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from enum import Enum
from collections import defaultdict, deque

from brain.research.search_cache import search_cache
from brain.research.search_dedup import deduplicate_queries, DeduplicationResult

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """Type of research tool"""
    WEB_SEARCH = "web_search"          # Free DuckDuckGo search
    RESEARCH_DEEP = "research_deep"    # Paid Perplexity research
    FETCH_WEBPAGE = "fetch_webpage"    # Fetch page content
    GET_CITATIONS = "get_citations"    # Get formatted citations
    STORE_MEMORY = "store_memory"      # Store to vector DB
    RECALL_MEMORY = "recall_memory"    # Recall from vector DB


@dataclass
class ToolExecutionContext:
    """Context for tool execution"""
    session_id: str
    user_id: str
    iteration: int
    budget_remaining: Decimal
    external_calls_remaining: int

    # Feature states (from I/O control)
    perplexity_enabled: bool = False
    offline_mode: bool = False
    cloud_routing_enabled: bool = True


@dataclass
class ToolExecutionResult:
    """Result from tool execution"""
    success: bool
    tool_name: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    # Cost tracking
    cost_usd: Decimal = Decimal("0.0")
    is_external: bool = False

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResearchToolExecutor:
    """
    Executes research tools with proper safety checks.

    Integrates:
    - MCP research server (web_search, research_deep, fetch_webpage)
    - MCP memory server (store_memory, recall_memory)
    - UnifiedPermissionGate for streamlined permission checks
    """

    def __init__(
        self,
        research_server: Any,
        memory_server: Optional[Any] = None,
        permission_gate: Optional[Any] = None,
        budget_manager: Optional[Any] = None
    ):
        """
        Initialize tool executor.

        Args:
            research_server: ResearchMCPServer instance
            memory_server: Optional MemoryMCPServer instance
            permission_gate: Optional UnifiedPermissionGate for API calls
            budget_manager: Optional BudgetManager for cost tracking
        """
        self.research_server = research_server
        self.memory_server = memory_server
        self.permission_gate = permission_gate
        self.budget = budget_manager
        # Track recent web_search queries per session to prevent duplicates / near-duplicates
        self._recent_web_queries: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5))

    async def execute(
        self,
        tool_name: ToolType,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """
        Execute a research tool with safety checks.

        Args:
            tool_name: Type of tool to execute
            arguments: Tool arguments
            context: Execution context with budget/permissions

        Returns:
            ToolExecutionResult with success status and data
        """
        # Check if tool is allowed
        if not self._is_tool_allowed(tool_name, context):
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name.value,
                error=self._get_blocked_reason(tool_name, context)
            )

        # Execute tool based on type
        try:
            if tool_name == ToolType.WEB_SEARCH:
                return await self._execute_web_search(arguments, context)

            elif tool_name == ToolType.RESEARCH_DEEP:
                return await self._execute_research_deep(arguments, context)

            elif tool_name == ToolType.FETCH_WEBPAGE:
                return await self._execute_fetch_webpage(arguments, context)

            elif tool_name == ToolType.GET_CITATIONS:
                return await self._execute_get_citations(arguments, context)

            elif tool_name == ToolType.STORE_MEMORY:
                return await self._execute_store_memory(arguments, context)

            elif tool_name == ToolType.RECALL_MEMORY:
                return await self._execute_recall_memory(arguments, context)

            else:
                return ToolExecutionResult(
                    success=False,
                    tool_name=tool_name.value,
                    error=f"Unknown tool type: {tool_name}"
                )

        except Exception as exc:
            logger.error(f"Error executing {tool_name}: {exc}")
            return ToolExecutionResult(
                success=False,
                tool_name=tool_name.value,
                error=f"Tool execution failed: {str(exc)}",
                metadata={"exception": str(exc)}
            )

    def _is_tool_allowed(self, tool_name: ToolType, context: ToolExecutionContext) -> bool:
        """Check if tool is allowed based on I/O control and budget"""

        # Check offline mode
        if context.offline_mode:
            # In offline mode, only allow free local tools
            if tool_name in [ToolType.RESEARCH_DEEP]:
                return False

        # Check cloud routing disabled
        if not context.cloud_routing_enabled:
            if tool_name in [ToolType.RESEARCH_DEEP]:
                return False

        # Check Perplexity specifically disabled
        if tool_name == ToolType.RESEARCH_DEEP and not context.perplexity_enabled:
            return False

        # Check budget for external calls
        if tool_name == ToolType.RESEARCH_DEEP:
            if context.external_calls_remaining <= 0:
                return False
            if context.budget_remaining <= Decimal("0.005"):  # Min cost for Perplexity
                return False

        return True

    def _get_blocked_reason(self, tool_name: ToolType, context: ToolExecutionContext) -> str:
        """Get reason why tool is blocked"""
        if context.offline_mode:
            return f"{tool_name.value} blocked: Offline mode enabled (I/O Control)"

        if not context.cloud_routing_enabled:
            return f"{tool_name.value} blocked: Cloud routing disabled (I/O Control)"

        if tool_name == ToolType.RESEARCH_DEEP:
            if not context.perplexity_enabled:
                return "research_deep blocked: Perplexity API disabled (I/O Control)"
            if context.external_calls_remaining <= 0:
                return "research_deep blocked: External call limit reached"
            if context.budget_remaining <= Decimal("0.005"):
                return f"research_deep blocked: Insufficient budget (${context.budget_remaining})"

        return f"{tool_name.value} blocked: Unknown reason"

    async def _execute_web_search(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Execute free web search (DuckDuckGo) with guardrails for duplication and budget."""
        query = (arguments or {}).get("query", "") or ""
        provider = (arguments or {}).get("provider", "duckduckgo") or "duckduckgo"
        session_id = context.session_id

        # Hard stop if we've already spent too many steps; force synthesis
        HARD_BUDGET = 9
        SOFT_BUDGET = 5
        if context.iteration >= HARD_BUDGET:
            return ToolExecutionResult(
                success=False,
                tool_name="web_search",
                error="Reasoning budget exhausted; synthesize with existing evidence instead of more web_search.",
                metadata={"reason": "hard_budget", "iteration": context.iteration}
            )

        # Duplicate / near-duplicate detection (require ≥3 new tokens vs recent queries)
        normalized_query = query.strip().lower()
        recent = self._recent_web_queries[session_id]
        if normalized_query:
            tokens = set(normalized_query.split())
            for prev in recent:
                if normalized_query == prev:
                    return ToolExecutionResult(
                        success=False,
                        tool_name="web_search",
                        error="Duplicate web_search blocked; change the query or synthesize.",
                        metadata={"reason": "duplicate_query", "blocked_query": query}
                    )
                # Near-duplicate: fewer than 3 novel tokens compared to previous query
                prev_tokens = set(prev.split())
                novel_tokens = tokens - prev_tokens
                if len(novel_tokens) < 3:
                    return ToolExecutionResult(
                        success=False,
                        tool_name="web_search",
                        error="Near-duplicate web_search blocked; add at least 3 new meaningful tokens or pivot to synthesis.",
                        metadata={
                            "reason": "near_duplicate_query",
                            "blocked_query": query,
                            "previous_query": prev
                        }
                    )

        # Soft budget nudge (allow call but warn caller to start synthesizing)
        metadata: Dict[str, Any] = {}
        if context.iteration >= SOFT_BUDGET:
            metadata["nudge_synthesis"] = True
            metadata["nudge_message"] = (
                "Approaching reasoning budget; prefer synthesis or a single diversified query."
            )

        # Check cache first (24h TTL)
        start_time = time.time()
        cached = await search_cache.get(query, provider)
        if cached:
            results = cached.get("results", [])
            cache_age = cached.get("cache_age", 0)
            logger.info(
                f"Cache HIT for '{query[:50]}...' (age={cache_age:.0f}s, results={len(results)})"
            )
            # Record query to prevent duplicates
            if normalized_query:
                recent.append(normalized_query)

            return ToolExecutionResult(
                success=True,
                tool_name="web_search",
                data={"results": results},
                cost_usd=Decimal("0.0"),
                is_external=False,
                metadata={
                    **metadata,
                    "cached": True,
                    "cache_age_seconds": cache_age,
                    "latency_ms": (time.time() - start_time) * 1000,
                }
            )

        # Execute search
        result = await self.research_server.execute_tool("web_search", arguments)
        latency_ms = (time.time() - start_time) * 1000

        # Cache successful results
        if result.success and result.data:
            results_to_cache = result.data.get("results", [])
            if results_to_cache:
                await search_cache.set(query, provider, results_to_cache)
                logger.debug(f"Cached {len(results_to_cache)} results for '{query[:50]}...'")

        # Record query on success (or even on attempt if we reach here)
        if normalized_query:
            recent.append(normalized_query)

        return ToolExecutionResult(
            success=result.success,
            tool_name="web_search",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Free
            is_external=False,
            metadata={
                **metadata,
                **(result.metadata or {}),
                "cached": False,
                "latency_ms": latency_ms,
            }
        )

    async def _execute_research_deep(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Execute Perplexity deep research (paid)"""

        estimated_cost = Decimal("0.005")  # $0.001-0.005 per query

        # Request permission via UnifiedPermissionGate
        if self.permission_gate:
            permission = await self.permission_gate.check_permission(
                provider="perplexity",
                estimated_cost=estimated_cost,
                context={"session_id": context.session_id}
            )

            if not permission.approved:
                # Check if we should prompt user
                if permission.prompt_user:
                    # Prompt for omega password
                    approved = await self.permission_gate.prompt_user_for_approval(permission)
                    if not approved:
                        return ToolExecutionResult(
                            success=False,
                            tool_name="research_deep",
                            error="Permission denied: User rejected Perplexity API call"
                        )
                else:
                    # Hard block (I/O Control or budget)
                    return ToolExecutionResult(
                        success=False,
                        tool_name="research_deep",
                        error=permission.reason
                    )

        # Execute tool
        result = await self.research_server.execute_tool("research_deep", arguments)

        # Extract actual cost from usage
        usage = result.data.get("usage", {}) if result.success else {}
        total_tokens = usage.get("total_tokens", 0)
        # Perplexity pricing: ~$0.001-0.005 per request
        actual_cost = Decimal("0.001") + (Decimal(str(total_tokens)) * Decimal("0.00001"))

        # Record actual cost
        if self.permission_gate and result.success:
            self.permission_gate.record_actual_cost(actual_cost, "perplexity")

        if self.budget and result.success:
            await self.budget.record_call(
                model_id="perplexity",
                cost_usd=actual_cost,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0)
            )

        return ToolExecutionResult(
            success=result.success,
            tool_name="research_deep",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=actual_cost,
            is_external=True,
            metadata=result.metadata or {}
        )

    async def _execute_fetch_webpage(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Fetch webpage content"""
        result = await self.research_server.execute_tool("fetch_webpage", arguments)

        return ToolExecutionResult(
            success=result.success,
            tool_name="fetch_webpage",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Free
            is_external=False,
            metadata=result.metadata or {}
        )

    async def _execute_get_citations(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Get formatted citations"""
        result = await self.research_server.execute_tool("get_citations", arguments)

        return ToolExecutionResult(
            success=result.success,
            tool_name="get_citations",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Free
            is_external=False,
            metadata=result.metadata or {}
        )

    async def _execute_store_memory(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Store memory to vector DB"""
        if not self.memory_server:
            return ToolExecutionResult(
                success=False,
                tool_name="store_memory",
                error="Memory server not available"
            )

        # Add session context
        arguments["conversation_id"] = context.session_id
        arguments["user_id"] = context.user_id

        result = await self.memory_server.execute_tool("store_memory", arguments)

        return ToolExecutionResult(
            success=result.success,
            tool_name="store_memory",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Local vector DB
            is_external=False,
            metadata=result.metadata or {}
        )

    async def _execute_recall_memory(
        self,
        arguments: Dict[str, Any],
        context: ToolExecutionContext
    ) -> ToolExecutionResult:
        """Recall memory from vector DB"""
        if not self.memory_server:
            return ToolExecutionResult(
                success=False,
                tool_name="recall_memory",
                error="Memory server not available"
            )

        # Add session context if not provided
        if "conversation_id" not in arguments:
            arguments["conversation_id"] = context.session_id
        if "user_id" not in arguments:
            arguments["user_id"] = context.user_id

        result = await self.memory_server.execute_tool("recall_memory", arguments)

        return ToolExecutionResult(
            success=result.success,
            tool_name="recall_memory",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Local vector DB
            is_external=False,
            metadata=result.metadata or {}
        )

    # ============ Two-Phase Search with Deduplication ============

    async def execute_searches_with_dedup(
        self,
        queries: List[str],
        context: ToolExecutionContext,
        provider: str = "duckduckgo",
        max_concurrent: int = 5,
        similarity_threshold: float = 0.7,
    ) -> Tuple[Dict[str, ToolExecutionResult], Dict[str, Any]]:
        """
        Execute multiple searches with deduplication and parallel execution.

        Two-phase approach:
        1. Collect and deduplicate queries using Jaccard similarity
        2. Execute unique queries in parallel with semaphore

        Args:
            queries: List of search queries
            context: Execution context
            provider: Search provider ID
            max_concurrent: Max concurrent requests
            similarity_threshold: Jaccard threshold for dedup

        Returns:
            Tuple of:
            - Dict mapping original query -> ToolExecutionResult
            - Dict with stats (dedup_saved, cached_count, etc.)
        """
        if not queries:
            return {}, {"dedup_saved": 0, "total_queries": 0}

        start_time = time.time()

        # Phase 1: Deduplicate queries
        dedup_result = deduplicate_queries(
            queries,
            similarity_threshold=similarity_threshold,
            max_queries=15,
        )

        unique_queries = dedup_result.unique_queries
        logger.info(
            f"Search dedup: {len(queries)} -> {len(unique_queries)} unique "
            f"(saved {dedup_result.duplicates_removed})"
        )

        # Phase 2: Execute unique queries in parallel
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_one(query: str) -> Tuple[str, ToolExecutionResult]:
            """Execute a single search with semaphore."""
            async with semaphore:
                result = await self._execute_web_search(
                    {"query": query, "provider": provider},
                    context,
                )
                return query, result

        # Execute all unique queries in parallel
        tasks = [execute_one(q) for q in unique_queries]
        results_list = await asyncio.gather(*tasks)

        # Build results dict for unique queries
        unique_results: Dict[str, ToolExecutionResult] = dict(results_list)

        # Map results back to original queries
        original_results: Dict[str, ToolExecutionResult] = {}
        cached_count = 0
        success_count = 0

        for original_query in queries:
            original_query = original_query.strip()
            if not original_query:
                continue

            canonical = dedup_result.get_canonical(original_query)

            if canonical in unique_results:
                result = unique_results[canonical]
                original_results[original_query] = result

                if result.success:
                    success_count += 1
                if result.metadata.get("cached"):
                    cached_count += 1
            else:
                # Should not happen, but handle gracefully
                original_results[original_query] = ToolExecutionResult(
                    success=False,
                    tool_name="web_search",
                    error="Query not in dedup result",
                )

        total_time_ms = (time.time() - start_time) * 1000

        stats = {
            "total_queries": len(queries),
            "unique_queries": len(unique_queries),
            "dedup_saved": dedup_result.duplicates_removed,
            "successful_queries": success_count,
            "cached_queries": cached_count,
            "total_time_ms": total_time_ms,
            "similarity_threshold": similarity_threshold,
        }

        logger.info(
            f"Parallel search complete: {success_count}/{len(unique_queries)} successful, "
            f"{cached_count} cached, {total_time_ms:.0f}ms total"
        )

        return original_results, stats
