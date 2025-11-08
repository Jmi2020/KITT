# noqa: D401
"""Multi-format parser for tool calls from various LLM models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .model_config import ToolCallFormat


@dataclass
class ToolCall:
    """Structured tool call from LLM response."""

    name: str
    arguments: Dict[str, Any]
    raw_xml: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {"name": self.name, "arguments": self.arguments}


def parse_tool_calls(
    text: str,
    format_type: ToolCallFormat = ToolCallFormat.QWEN_XML,
) -> tuple[List[ToolCall], str]:
    """Parse tool calls using format-specific parser.

    Args:
        text: LLM response text potentially containing tool calls
        format_type: Tool calling format to use (default: QWEN_XML for backward compatibility)

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    if format_type == ToolCallFormat.QWEN_XML:
        return _parse_qwen_xml(text)
    elif format_type == ToolCallFormat.LLAMA_JSON:
        return _parse_llama_json(text)
    elif format_type == ToolCallFormat.MISTRAL_JSON:
        return _parse_mistral_json(text)
    elif format_type == ToolCallFormat.GEMMA_FUNCTION:
        return _parse_gemma_function(text)
    else:
        # Fallback to generic XML parser
        return _parse_generic_xml(text)


def _parse_qwen_xml(text: str) -> tuple[List[ToolCall], str]:
    """Parse Qwen2.5/3 XML format: <tool_call>{"name": "...", "arguments": {...}}</tool_call>

    Args:
        text: LLM response text

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


def _parse_llama_json(text: str) -> tuple[List[ToolCall], str]:
    """Parse Llama 3.1+/3.3 Pythonic function call format.

    Llama 3.3 outputs function calls in square brackets:
    [func_name1(param1=value1, param2=value2), func_name2(param3=value3)]

    Args:
        text: LLM response text

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    import ast

    tool_calls: List[ToolCall] = []

    # Look for square bracket wrapper [...]
    bracket_pattern = r'\[(.*?)\]'
    bracket_match = re.search(bracket_pattern, text, re.DOTALL)

    if not bracket_match:
        # No bracketed tool calls found
        return [], text

    raw_full = bracket_match.group(0)
    content = bracket_match.group(1).strip()

    if not content:
        return [], text

    # Pattern to match Python-style function calls: func_name(param1=value1, param2='value2')
    # Match function calls inside the brackets
    pattern = r'(\w+)\(([^)]*)\)'

    for match in re.finditer(pattern, content):
        func_name = match.group(1)
        params_str = match.group(2).strip()
        raw_call = match.group(0)

        # Skip common Python built-ins that aren't tool calls
        if func_name in ['print', 'range', 'len', 'str', 'int', 'float', 'bool', 'list', 'dict']:
            continue

        # Parse parameters (param=value pairs)
        arguments = {}
        if params_str:
            # Split parameters by comma (outside quotes)
            param_pattern = r'(\w+)\s*=\s*([^,]+?)(?=,\s*\w+\s*=|$)'
            param_matches = re.finditer(param_pattern, params_str)

            for param_match in param_matches:
                param_name = param_match.group(1).strip()
                param_value = param_match.group(2).strip()

                # Use ast.literal_eval for safe evaluation
                try:
                    arguments[param_name] = ast.literal_eval(param_value)
                except (ValueError, SyntaxError):
                    # If literal_eval fails, keep as string (remove quotes if present)
                    if param_value.startswith(("'", '"')) and param_value.endswith(("'", '"')):
                        arguments[param_name] = param_value[1:-1]
                    else:
                        arguments[param_name] = param_value

        tool_call = ToolCall(
            name=func_name,
            arguments=arguments,
            raw_xml=raw_call,
        )
        tool_calls.append(tool_call)

    # Remove the bracketed tool calls from text
    cleaned_text = text.replace(raw_full, "").strip()

    return tool_calls, cleaned_text


def _parse_mistral_json(text: str) -> tuple[List[ToolCall], str]:
    """Parse Mistral JSON format: [TOOL_CALLS] [{"name": "...", "arguments": {...}}]

    Args:
        text: LLM response text

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    tool_calls: List[ToolCall] = []

    # Pattern to match [TOOL_CALLS] followed by JSON array
    pattern = r"\[TOOL_CALLS\]\s*(\[.*?\])"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        raw_match = match.group(0)
        json_content = match.group(1).strip()

        try:
            # Parse JSON array
            data = json.loads(json_content)

            # Extract each tool call
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item:
                        tool_call = ToolCall(
                            name=item["name"],
                            arguments=item.get("arguments", {}),
                            raw_xml=raw_match,
                        )
                        tool_calls.append(tool_call)
        except json.JSONDecodeError:
            # Skip malformed tool calls
            pass

        # Remove tool call marker from text
        cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL).strip()
    else:
        cleaned_text = text

    return tool_calls, cleaned_text


def _parse_gemma_function(text: str) -> tuple[List[ToolCall], str]:
    """Parse Gemma function format: <function_call>{"name": "...", "parameters": {...}}</function_call>

    Note: Gemma uses "parameters" instead of "arguments"

    Args:
        text: LLM response text

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    tool_calls: List[ToolCall] = []

    # Pattern to match <function_call>...</function_call> blocks
    pattern = r"<function_call>(.*?)</function_call>"
    matches = re.finditer(pattern, text, re.DOTALL)

    for match in matches:
        raw_xml = match.group(0)
        json_content = match.group(1).strip()

        try:
            # Parse JSON content
            data = json.loads(json_content)

            # Extract name and parameters (Gemma uses "parameters" not "arguments")
            if isinstance(data, dict) and "name" in data:
                tool_call = ToolCall(
                    name=data["name"],
                    arguments=data.get("parameters", {}),  # Map parameters -> arguments
                    raw_xml=raw_xml,
                )
                tool_calls.append(tool_call)
        except json.JSONDecodeError:
            # Skip malformed tool calls
            continue

    # Remove all function call XML from text to get remaining content
    cleaned_text = re.sub(pattern, "", text, flags=re.DOTALL).strip()

    return tool_calls, cleaned_text


def _parse_generic_xml(text: str) -> tuple[List[ToolCall], str]:
    """Generic XML parser for unknown models.

    Tries both <tool_call> and <function_call> patterns.

    Args:
        text: LLM response text

    Returns:
        Tuple of (list of ToolCall objects, remaining text without tool calls)
    """
    # Try Qwen XML format first
    tool_calls, cleaned_text = _parse_qwen_xml(text)

    # If no tool calls found, try Gemma function format
    if not tool_calls:
        tool_calls, cleaned_text = _parse_gemma_function(text)

    # If still no tool calls, try Mistral JSON format
    if not tool_calls:
        tool_calls, cleaned_text = _parse_mistral_json(text)

    return tool_calls, cleaned_text


__all__ = ["ToolCall", "parse_tool_calls"]
