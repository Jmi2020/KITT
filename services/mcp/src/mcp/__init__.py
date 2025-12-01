"""Model Context Protocol (MCP) server framework for KITTY."""

from .server import (
    MCPServer,
    PromptDefinition,
    ResourceDefinition,
    ToolDefinition,
    ToolResult,
)
from .servers import (
    BrokerMCPServer,
    CADMCPServer,
    DiscoveryMCPServer,
    FabricationMCPServer,
    HomeAssistantMCPServer,
    MemoryMCPServer,
    ResearchMCPServer,
    VisionMCPServer,
)

__all__ = [
    "MCPServer",
    "ToolDefinition",
    "ResourceDefinition",
    "PromptDefinition",
    "ToolResult",
    "BrokerMCPServer",
    "CADMCPServer",
    "DiscoveryMCPServer",
    "FabricationMCPServer",
    "HomeAssistantMCPServer",
    "MemoryMCPServer",
    "ResearchMCPServer",
    "VisionMCPServer",
]
