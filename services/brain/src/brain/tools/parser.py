# noqa: D401
"""Parser for Qwen2.5 tool call format (XML + JSON)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ToolCall:
    """Structured tool call from LLM response."""

    name: str
    arguments: Dict[str, Any]
    raw_xml: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {"name": self.name, "arguments": self.arguments}


def parse_tool_calls(text: str) -> tuple[List[ToolCall], str]:
    """Extract tool calls from Qwen2.5 response.

    Qwen2.5 returns tool calls in XML format:
    <tool_call>{"name": "function_name", "arguments": {...}}</tool_call>

    Args:
        text: LLM response text potentially containing tool calls

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    tool_calls: List[ToolCall] = []

    # Pattern to match <tool_call>...</tool_call> blocks
    pattern = r"<tool_call>(.*?)</tool_call>"
    matches = re.finditer(pattern, text, re.DOTALL)

    for match in matches:
        raw_xml = match.group(0)
        json_content = match.group(1).strip()

        try:
            # Parse JSON content
            data = json.loads(json_content)

            # Extract name and arguments
            if isinstance(data, dict) and "name" in data:
                tool_call = ToolCall(
                    name=data["name"],
                    arguments=data.get("arguments", {}),
                    raw_xml=raw_xml,
                )
                tool_calls.append(tool_call)
        except json.JSONDecodeError:
            # Skip malformed tool calls
            continue

    # Remove all tool call XML from text to get remaining content
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL).strip()

    return tool_calls, cleaned_text


__all__ = ["ToolCall", "parse_tool_calls"]
