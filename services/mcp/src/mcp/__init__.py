"""Model Context Protocol (MCP) server framework for KITTY."""

from .server import (
    MCPServer,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
    ToolResult,
)
from .servers.cad_server import CADMCPServer
from .servers.homeassistant_server import HomeAssistantMCPServer
from .servers.memory_server import MemoryMCPServer

__all__ = [
    "MCPServer",
    "ToolDefinition",
    "ResourceDefinition",
    "PromptDefinition",
    "ToolResult",
    "CADMCPServer",
    "HomeAssistantMCPServer",
    "MemoryMCPServer",
]
