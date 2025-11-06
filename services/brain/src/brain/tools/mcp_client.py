# noqa: D401
"""MCP client for connecting to and executing tools on MCP servers."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from services.common.src.common.clients.home_assistant import HomeAssistantClient

# Import MCP server classes
import sys
from pathlib import Path

# Add services/mcp to path so we can import the MCP servers
mcp_path = Path(__file__).parent.parent.parent.parent.parent / "mcp" / "src"
if str(mcp_path) not in sys.path:
    sys.path.insert(0, str(mcp_path))

from mcp import (  # noqa: E402
    CADMCPServer,
    HomeAssistantMCPServer,
    MemoryMCPServer,
    ToolDefinition,
)


class MCPClient:
    """Client for interacting with MCP tool servers."""

    def __init__(
        self,
        cad_service_url: str | None = None,
        memory_service_url: str | None = None,
        ha_service_url: str | None = None,
    ) -> None:
        """Initialize MCP client with server connections.

        Args:
            cad_service_url: Optional CAD service URL
            memory_service_url: Optional memory service URL
            ha_service_url: Optional Home Assistant service URL
        """
        # Initialize MCP servers
        self._servers: Dict[str, Any] = {}

        # CAD server
        self._servers["cad"] = CADMCPServer(
            cad_service_url=cad_service_url or os.getenv("CAD_SERVICE_URL", "http://cad:8000")
        )

        # Memory server
        self._servers["memory"] = MemoryMCPServer(
            memory_service_url=memory_service_url
            or os.getenv("MEM0_MCP_URL", "http://mem0-mcp:8765")
        )

        # Home Assistant server (needs HA client)
        ha_url = ha_service_url or os.getenv("HOME_ASSISTANT_URL")
        ha_token = os.getenv("HOME_ASSISTANT_TOKEN")

        if ha_url and ha_token:
            ha_client = HomeAssistantClient(base_url=ha_url, token=ha_token)
            self._servers["homeassistant"] = HomeAssistantMCPServer(ha_client=ha_client)
        else:
            # Don't add HA server if not configured
            pass

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
