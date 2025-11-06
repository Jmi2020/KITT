"""Model Context Protocol (MCP) server framework for KITTY."""

from .server import (
    MCPServer,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
    ToolResult,
)
from .servers.cad_server import CADMCPServer

__all__ = [
    "MCPServer",
    "ToolDefinition",
    "ResourceDefinition",
    "PromptDefinition",
    "ToolResult",
    "CADMCPServer",
]
