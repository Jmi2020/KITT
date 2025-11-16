"""
MCP Tool Integration for Research Pipeline

Integrates existing MCP tools (web_search, Perplexity, memory) with research system.
Uses UnifiedPermissionGate for streamlined permission checks.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum

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
        """Execute free web search (DuckDuckGo)"""
        result = await self.research_server.execute_tool("web_search", arguments)

        return ToolExecutionResult(
            success=result.success,
            tool_name="web_search",
            data=result.data if result.success else {},
            error=result.error if not result.success else None,
            cost_usd=Decimal("0.0"),  # Free
            is_external=False,
            metadata=result.metadata or {}
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
