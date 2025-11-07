# noqa: D401
"""MCP client for connecting to and executing tools on MCP servers."""

from __future__ import annotations

import os
import logging
from typing import Any, Dict, List

from ..clients.home_assistant import HomeAssistantClient
from common.credentials import HomeAssistantCredentials

# Import MCP server classes
import sys
from pathlib import Path

# Add services/mcp/src to sys.path so we can import shared MCP servers
repo_root = Path(__file__).resolve().parents[5]
mcp_path = repo_root / "services" / "mcp" / "src"
if mcp_path.exists() and str(mcp_path) not in sys.path:
    sys.path.insert(0, str(mcp_path))

try:  # noqa: WPS229
    from mcp import (  # noqa: E402
        BrokerMCPServer,
        CADMCPServer,
        HomeAssistantMCPServer,
        MemoryMCPServer,
        ResearchMCPServer,
        ToolDefinition,
    )
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    BrokerMCPServer = CADMCPServer = HomeAssistantMCPServer = MemoryMCPServer = ResearchMCPServer = None  # type: ignore[assignment]
    ToolDefinition = Dict[str, Any]  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for interacting with MCP tool servers."""

    def __init__(
        self,
        cad_service_url: str | None = None,
        memory_service_url: str | None = None,
        ha_service_url: str | None = None,
        broker_url: str | None = None,
        perplexity_client: Any = None,
    ) -> None:
        """Initialize MCP client with server connections.

        Args:
            cad_service_url: Optional CAD service URL
            memory_service_url: Optional memory service URL
            ha_service_url: Optional Home Assistant service URL
            broker_url: Optional Command Broker service URL
            perplexity_client: Optional Perplexity MCP client for premium web search
        """
        # Initialize MCP servers
        self._servers: Dict[str, Any] = {}

        try:
            # Broker server
            if callable(BrokerMCPServer):
                self._servers["broker"] = BrokerMCPServer(
                    broker_url=broker_url or os.getenv("BROKER_URL", "http://broker:8777")
                )

            # CAD server
            if callable(CADMCPServer):
                self._servers["cad"] = CADMCPServer(
                    cad_service_url=cad_service_url
                    or os.getenv("CAD_SERVICE_URL", "http://cad:8000")
                )

            # Memory server
            if callable(MemoryMCPServer):
                self._servers["memory"] = MemoryMCPServer(
                    memory_service_url=memory_service_url
                    or os.getenv("MEM0_MCP_URL", "http://mem0-mcp:8765")
                )

            # Home Assistant server (needs HA client)
            if callable(HomeAssistantMCPServer):
                ha_url = ha_service_url or os.getenv("HOME_ASSISTANT_URL")
                ha_token = os.getenv("HOME_ASSISTANT_TOKEN")
                if ha_url and ha_token:
                    creds = HomeAssistantCredentials(base_url=ha_url, token=ha_token)
                    ha_client = HomeAssistantClient(credentials=creds)
                    self._servers["homeassistant"] = HomeAssistantMCPServer(ha_client=ha_client)

            # Research server with optional Perplexity integration
            if callable(ResearchMCPServer):
                self._servers["research"] = ResearchMCPServer(perplexity_client=perplexity_client)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Disabling MCP tools: %s", exc)
            self._servers.clear()

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools from all connected servers.

        Returns:
            List of tool definitions in JSON Schema format
        """
        tools = []

        for server_name, server in self._servers.items():
            for tool_def in server.list_tools():
                # Add server metadata to tool definition
                tool_schema = tool_def.to_json_schema()
                tool_schema["server"] = server_name
                tools.append(tool_schema)

        return tools

    def get_tool(self, tool_name: str) -> ToolDefinition | None:
        """Get a specific tool definition by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            ToolDefinition if found, None otherwise
        """
        for server in self._servers.values():
            tool_def = server.get_tool(tool_name)
            if tool_def:
                return tool_def

        return None

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool across all servers.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        # Find which server has this tool
        for server_name, server in self._servers.items():
            tool_def = server.get_tool(tool_name)
            if tool_def:
                # Execute tool on this server
                result = await server.execute_tool(tool_name, arguments)

                # Return result as dictionary
                return {
                    "success": result.success,
                    "data": result.data,
                    "error": result.error,
                    "metadata": {
                        **result.metadata,
                        "server": server_name,
                        "tool": tool_name,
                    },
                }

        # Tool not found
        return {
            "success": False,
            "error": f"Tool '{tool_name}' not found on any server",
            "data": None,
            "metadata": {"tool": tool_name},
        }

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a resource from the appropriate server.

        Args:
            uri: Resource URI (e.g., "cad://recent", "memory://stats")

        Returns:
            Resource data

        Raises:
            ValueError: If resource not found
        """
        # Extract server name from URI
        if "://" in uri:
            server_name = uri.split("://")[0]

            if server_name in self._servers:
                server = self._servers[server_name]
                return await server.fetch_resource(uri)

        raise ValueError(f"Resource not found: {uri}")

    def get_tools_for_prompt(self) -> List[Dict[str, Any]]:
        """Get all tools formatted for LLM prompts (JSON Schema).

        Returns:
            List of tool definitions in JSON Schema format
        """
        return self.list_tools()


__all__ = ["MCPClient"]
