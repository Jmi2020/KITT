# noqa: D401
"""Safe tool executor with permission and hazard checks."""

from __future__ import annotations

from typing import Any, Dict, Optional, Set

from common.db.models import RoutingTier

from ..routing.permission import PermissionManager
from .mcp_client import MCPClient

# Import safety workflow (optional dependency)
try:
    import sys
    from pathlib import Path

    # Add services/safety to path
    safety_path = Path(__file__).parent.parent.parent.parent.parent / "safety" / "src"
    if str(safety_path) not in sys.path:
        sys.path.insert(0, str(safety_path))

    from safety.workflows.hazard import HazardWorkflow  # type: ignore

    HAZARD_AVAILABLE = True
except ImportError:
    HazardWorkflow = None  # type: ignore
    HAZARD_AVAILABLE = False


class SafeToolExecutor:
    """Execute tools with safety checks and permission gating.

    Provides a safety layer on top of the MCP client that enforces:
    - Permission checks for tools that cost money
    - Hazard workflow verification for dangerous operations
    - Tool-specific safety policies
    """

    def __init__(
        self,
        mcp_client: MCPClient,
        permission_manager: Optional[PermissionManager] = None,
        hazard_workflow: Optional[Any] = None,
    ) -> None:
        """Initialize safe tool executor.

        Args:
            mcp_client: MCP client for tool execution
            permission_manager: Permission manager for cost approval
            hazard_workflow: Hazard workflow for dangerous operations
        """
        self._mcp = mcp_client
        self._permission = permission_manager or PermissionManager()
        self._hazard = hazard_workflow

        # Classify tools by safety level
        self._hazardous_tools: Set[str] = {
            "control_device",
            "execute_command",
        }  # Tools that may be dangerous
        self._cloud_tools: Set[str] = {"generate_cad_model"}  # Tools that may cost money
        self._free_tools: Set[str] = {
            "get_entity_state",
            "list_entities",
            "recall_memory",
            "store_memory",
            "list_commands",
            "get_command_schema",
            "web_search",
            "fetch_webpage",
            "get_citations",
            "reset_research_session",
        }  # Always allowed

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute tool with appropriate safety checks.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            user_id: User ID for permission checks
            conversation_id: Conversation ID for permission tracking

        Returns:
            Tool execution result dictionary with success, data, error, metadata
        """
        # Check for hazardous operations
        if tool_name in self._hazardous_tools:
            if not await self._check_hazard_safety(tool_name, arguments, user_id, conversation_id):
                return {
                    "success": False,
                    "data": None,
                    "error": "Hazard safety check failed - operation denied",
                    "metadata": {"tool": tool_name, "safety_check": "hazard_failed"},
                }

        # Check for tools requiring budget approval
        if tool_name in self._cloud_tools and tool_name not in self._free_tools:
            if not await self._check_permission(tool_name, conversation_id):
                return {
                    "success": False,
                    "data": None,
                    "error": "Permission denied - budget limit or user declined",
                    "metadata": {
                        "tool": tool_name,
                        "safety_check": "permission_denied",
                    },
                }

        # Execute tool via MCP client
        return await self._mcp.execute_tool(tool_name, arguments)

    async def _check_hazard_safety(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str],
        conversation_id: Optional[str],
    ) -> bool:
        """Check if hazardous tool operation is allowed.

        Args:
            tool_name: Tool name
            arguments: Tool arguments
            user_id: User ID
            conversation_id: Conversation ID

        Returns:
            True if operation is allowed, False otherwise
        """
        if not HAZARD_AVAILABLE or not self._hazard:
            # If hazard workflow not available, allow operation
            # This maintains backward compatibility
            return True

        # Handle control_device tool with special hazard checks
        if tool_name == "control_device":
            domain = arguments.get("domain", "")
            service = arguments.get("service", "")
            entity_id = arguments.get("entity_id", "")

            # Check for lock unlock operations
            if domain == "lock" and service == "unlock":
                # Require confirmation phrase for unlocking
                confirmation_phrase = arguments.get("confirmation_phrase")
                if not confirmation_phrase:
                    return False

                # Process via hazard workflow
                allowed, _response = await self._hazard.process_device_intent(
                    intent="lock.unlock",
                    device_id=entity_id,
                    zone_id=None,
                    user_id=user_id or "unknown",
                    signature=confirmation_phrase,
                )
                return allowed

        # Handle execute_command tool with command-specific checks
        if tool_name == "execute_command":
            command = arguments.get("command", "")

            # Certain commands may be hazardous based on their nature
            potentially_hazardous_commands = {
                "run_python_script",  # Arbitrary code execution
                "git_pull",  # File system modifications
                "extract_archive",  # File system modifications
            }

            if command in potentially_hazardous_commands:
                # For now, allow but this could be enhanced with hazard workflow
                # In the future, we could require confirmation for these operations
                return True

        # Other hazardous tools - allow by default unless specific rules added
        return True

    async def _check_permission(self, tool_name: str, conversation_id: Optional[str]) -> bool:
        """Check if permission is granted for cloud tool.

        Args:
            tool_name: Tool name
            conversation_id: Conversation ID for tracking

        Returns:
            True if permission granted, False otherwise
        """
        # Estimate cost based on tool
        estimated_cost = self._estimate_tool_cost(tool_name)

        # Request permission
        approved = await self._permission.request_permission(
            tier=RoutingTier.mcp,
            provider=self._get_tool_provider(tool_name),
            estimated_cost=estimated_cost,
            reason=f"{tool_name} requested by agent",
            conversation_id=conversation_id or "unknown",
        )

        return approved

    def _estimate_tool_cost(self, tool_name: str) -> float:
        """Estimate cost of tool execution.

        Args:
            tool_name: Tool name

        Returns:
            Estimated cost in USD
        """
        # Simple cost estimation - can be made more sophisticated
        cost_map = {
            "generate_cad_model": 0.05,  # Zoo API call
            "control_device": 0.0,  # Free
            "get_entity_state": 0.0,
            "list_entities": 0.0,
            "store_memory": 0.001,  # Minimal embedding cost
            "recall_memory": 0.001,
            "execute_command": 0.0,  # Free (local execution)
            "list_commands": 0.0,
            "get_command_schema": 0.0,
        }
        return cost_map.get(tool_name, 0.01)  # Default to 1 cent

    def _get_tool_provider(self, tool_name: str) -> str:
        """Get provider name for tool.

        Args:
            tool_name: Tool name

        Returns:
            Provider name
        """
        provider_map = {
            "generate_cad_model": "zoo",
            "control_device": "homeassistant",
            "get_entity_state": "homeassistant",
            "list_entities": "homeassistant",
            "store_memory": "qdrant",
            "recall_memory": "qdrant",
            "execute_command": "broker",
            "list_commands": "broker",
            "get_command_schema": "broker",
        }
        return provider_map.get(tool_name, "unknown")

    def add_hazardous_tool(self, tool_name: str) -> None:
        """Register a tool as hazardous.

        Args:
            tool_name: Tool name to mark as hazardous
        """
        self._hazardous_tools.add(tool_name)

    def add_cloud_tool(self, tool_name: str) -> None:
        """Register a tool as requiring cloud/budget approval.

        Args:
            tool_name: Tool name to mark as cloud tool
        """
        self._cloud_tools.add(tool_name)


__all__ = ["SafeToolExecutor"]
