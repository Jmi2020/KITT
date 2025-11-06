"""Dynamic tool formatter for system prompt injection."""

from __future__ import annotations

from typing import Any, Dict, List


def format_tools_for_prompt(tools: List[Dict[str, Any]]) -> str:
    """Format tool definitions for inclusion in system prompt.

    Takes a list of tool definitions in JSON Schema format and formats them
    into human-readable text suitable for injection into system prompts.

    Args:
        tools: List of tool definitions with function schemas

    Returns:
        Formatted string with tool documentation

    Example:
        >>> tools = [{
        ...     "type": "function",
        ...     "function": {
        ...         "name": "generate_cad_model",
        ...         "description": "Generate a 3D CAD model from text description",
        ...         "parameters": {
        ...             "type": "object",
        ...             "properties": {
        ...                 "prompt": {
        ...                     "type": "string",
        ...                     "description": "Text description of the CAD model"
        ...                 },
        ...                 "provider": {
        ...                     "type": "string",
        ...                     "description": "CAD generation provider"
        ...                 }
        ...             },
        ...             "required": ["prompt"]
        ...         }
        ...     }
        ... }]
        >>> print(format_tools_for_prompt(tools))
        **generate_cad_model**
        Generate a 3D CAD model from text description

        Parameters:
          - prompt: string (required) - Text description of the CAD model
          - provider: string (optional) - CAD generation provider
    """
    if not tools:
        return "No tools currently available"

    formatted = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        params = func.get("parameters", {}).get("properties", {})
        required = func.get("parameters", {}).get("required", [])

        # Format parameters
        param_lines = []
        for param_name, param_def in params.items():
            param_type = param_def.get("type", "any")
            param_desc = param_def.get("description", "")
            req_marker = " (required)" if param_name in required else " (optional)"
            param_lines.append(f"  - {param_name}: {param_type}{req_marker} - {param_desc}")

        # Build tool documentation
        param_section = "\n".join(param_lines) if param_lines else "  (no parameters)"

        tool_text = f"""**{name}**
{desc}

Parameters:
{param_section}"""

        formatted.append(tool_text)

    return "\n\n".join(formatted)


def format_tools_compact(tools: List[Dict[str, Any]]) -> str:
    """Format tool definitions in compact one-line format.

    Useful for shorter prompts or when detailed parameter info isn't needed.

    Args:
        tools: List of tool definitions with function schemas

    Returns:
        Compact formatted string with tool list

    Example:
        >>> tools = [{"function": {"name": "tool1", "description": "Does thing 1"}}]
        >>> format_tools_compact(tools)
        '- tool1: Does thing 1'
    """
    if not tools:
        return "No tools available"

    lines = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        lines.append(f"- {name}: {desc}")

    return "\n".join(lines)


def get_tool_names(tools: List[Dict[str, Any]]) -> List[str]:
    """Extract tool names from tool definitions.

    Args:
        tools: List of tool definitions

    Returns:
        List of tool names
    """
    names = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name")
        if name:
            names.append(name)
    return names


__all__ = [
    "format_tools_for_prompt",
    "format_tools_compact",
    "get_tool_names",
]
