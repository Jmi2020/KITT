# noqa: D401
"""Base MCP server framework following Anthropic's Model Context Protocol.

Implements the three core MCP primitives:
- Tools: Model-controlled functions that can be invoked
- Resources: Application-controlled data sources (read-only)
- Prompts: User-controlled interaction templates
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolDefinition:
    """MCP Tool definition in JSON Schema format."""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema object
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI/Anthropic-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ResourceDefinition:
    """MCP Resource definition (read-only data source)."""

    uri: str  # e.g., "cad://projects/123/artifacts"
    name: str
    description: str
    mime_type: str = "application/json"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptDefinition:
    """MCP Prompt template definition."""

    name: str
    description: str
    template: str  # Template string with {variable} placeholders
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Result from executing a tool."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPServer(ABC):
    """Base class for MCP-compliant tool servers.

    Each server implementation exposes tools, resources, and/or prompts.
    """

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self._tools: Dict[str, ToolDefinition] = {}
        self._resources: Dict[str, ResourceDefinition] = {}
        self._prompts: Dict[str, PromptDefinition] = {}

    def register_tool(self, tool: ToolDefinition) -> None:
        """Register a tool with this server."""
        self._tools[tool.name] = tool

    def register_resource(self, resource: ResourceDefinition) -> None:
        """Register a resource with this server."""
        self._resources[resource.uri] = resource

    def register_prompt(self, prompt: PromptDefinition) -> None:
        """Register a prompt template with this server."""
        self._prompts[prompt.name] = prompt

    def list_tools(self) -> List[ToolDefinition]:
        """List all tools provided by this server."""
        return list(self._tools.values())

    def list_resources(self) -> List[ResourceDefinition]:
        """List all resources provided by this server."""
        return list(self._resources.values())

    def list_prompts(self) -> List[PromptDefinition]:
        """List all prompt templates provided by this server."""
        return list(self._prompts.values())

    @abstractmethod
    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (validated against JSON Schema)

        Returns:
            ToolResult with success status and data/error
        """
        pass

    @abstractmethod
    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a resource by URI.

        Args:
            uri: Resource URI (e.g., "cad://projects/123")

        Returns:
            Resource data as dictionary
        """
        pass

    async def render_prompt(self, prompt_name: str, variables: Dict[str, Any]) -> str:
        """Render a prompt template with given variables.

        Args:
            prompt_name: Name of the prompt template
            variables: Variable values for template substitution

        Returns:
            Rendered prompt string
        """
        prompt = self._prompts.get(prompt_name)
        if not prompt:
            raise ValueError(f"Prompt '{prompt_name}' not found")

        return prompt.template.format(**variables)


__all__ = [
    "MCPServer",
    "ToolDefinition",
    "ResourceDefinition",
    "PromptDefinition",
    "ToolResult",
]
