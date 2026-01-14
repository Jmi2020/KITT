from __future__ import annotations

from fnmatch import fnmatch
from functools import lru_cache
import json
from logging import getLogger
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kitty_code.core.tools.base import BaseTool
from kitty_code.core.types import (
    AvailableFunction,
    AvailableTool,
    LLMMessage,
    Role,
    StrToolChoice,
)

if TYPE_CHECKING:
    from kitty_code.core.config import VibeConfig
    from kitty_code.core.tools.manager import ToolManager

logger = getLogger("kitty_code")


def _extract_tool_calls_from_content(content: str) -> list[dict[str, Any]]:
    """Extract tool calls from JSON embedded in content.

    Some models (especially local ones via llama.cpp/Ollama) output tool calls
    as JSON text in the content field instead of using native function calling.
    This function parses those JSON tool calls.

    Supports multiple formats:
    1. {"tool_calls": [{"name": "...", "arguments": {...}, "id": "..."}]}
    2. [{"name": "...", "arguments": {...}}]
    3. {"name": "...", "arguments": {...}}

    Returns a list of parsed tool call dicts, or empty list if no valid JSON found.
    """
    if not content:
        return []

    # Try to find JSON in the content
    # Look for JSON object or array patterns
    json_patterns = [
        # Match JSON object starting with { and containing "tool_calls" or "name"
        r'\{[^{}]*"(?:tool_calls|name)"[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        # Match JSON array of objects
        r'\[[^[\]]*\{[^{}]*"name"[^{}]*\}[^[\]]*\]',
    ]

    # First, try to parse the entire content as JSON
    stripped = content.strip()
    try:
        data = json.loads(stripped)
        return _normalize_tool_calls_data(data)
    except json.JSONDecodeError:
        pass

    # Try to find JSON embedded in the content
    # Look for the first { that might start a tool_calls object
    for match in re.finditer(r'\{["\s]*tool_calls|\[\s*\{["\s]*name', stripped):
        start = match.start()
        # Try to parse from this position
        remaining = stripped[start:]

        # Find matching brackets
        bracket_count = 0
        in_string = False
        escape_next = False
        end_pos = 0

        for i, char in enumerate(remaining):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue

            if char in "{[":
                bracket_count += 1
            elif char in "}]":
                bracket_count -= 1
                if bracket_count == 0:
                    end_pos = i + 1
                    break

        if end_pos > 0:
            json_str = remaining[:end_pos]
            try:
                data = json.loads(json_str)
                result = _normalize_tool_calls_data(data)
                if result:
                    return result
            except json.JSONDecodeError:
                continue

    return []


def _normalize_tool_calls_data(data: Any) -> list[dict[str, Any]]:
    """Normalize various tool call JSON formats to a standard list."""
    if isinstance(data, dict):
        # Format: {"tool_calls": [...]}
        if "tool_calls" in data:
            tool_calls = data["tool_calls"]
            if isinstance(tool_calls, list):
                return tool_calls
        # Format: {"name": "...", "arguments": {...}}
        elif "name" in data:
            return [data]
    elif isinstance(data, list):
        # Format: [{"name": "...", "arguments": {...}}, ...]
        if all(isinstance(item, dict) and "name" in item for item in data):
            return data
    return []


def _is_regex_hint(pattern: str) -> bool:
    """Heuristically detect whether a pattern looks like a regex.

    - Explicit regex: starts with 're:'
    - Heuristic regex: contains common regex metachars or '.*'
    """
    if pattern.startswith("re:"):
        return True
    return bool(re.search(r"[().+|^$]", pattern) or ".*" in pattern)


@lru_cache(maxsize=256)
def _compile_icase(expr: str) -> re.Pattern | None:
    try:
        return re.compile(expr, re.IGNORECASE)
    except re.error:
        return None


def _regex_match_icase(expr: str, s: str) -> bool:
    rx = _compile_icase(expr)
    return rx is not None and rx.fullmatch(s) is not None


def _name_matches(name: str, patterns: list[str]) -> bool:
    """Check if a tool name matches any of the provided patterns.

    Supports three forms (case-insensitive):
    - Exact names (no wildcards/regex tokens)
    - Glob wildcards using fnmatch (e.g., 'serena_*')
    - Regex when prefixed with 're:'
      or when the pattern looks regex-y (e.g., 'serena.*')
    """
    n = name.lower()
    for raw in patterns:
        if not (p := (raw or "").strip()):
            continue

        match p:
            case _ if p.startswith("re:"):
                if _regex_match_icase(p.removeprefix("re:"), name):
                    return True
            case _ if _is_regex_hint(p):
                if _regex_match_icase(p, name):
                    return True
            case _:
                if fnmatch(n, p.lower()):
                    return True

    return False


def get_active_tool_classes(
    tool_manager: ToolManager, config: VibeConfig
) -> list[type[BaseTool]]:
    """Returns a list of active tool classes based on the configuration.

    Args:
        tool_manager: ToolManager instance with discovered tools
        config: VibeConfig with enabled_tools/disabled_tools settings
    """
    all_tools = list(tool_manager.available_tools().values())

    if config.enabled_tools:
        return [
            tool_class
            for tool_class in all_tools
            if _name_matches(tool_class.get_name(), config.enabled_tools)
        ]

    if config.disabled_tools:
        return [
            tool_class
            for tool_class in all_tools
            if not _name_matches(tool_class.get_name(), config.disabled_tools)
        ]

    return all_tools


class ParsedToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_name: str
    raw_args: dict[str, Any]
    call_id: str = ""


class ResolvedToolCall(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    tool_name: str
    tool_class: type[BaseTool]
    validated_args: BaseModel
    call_id: str = ""

    @property
    def args_dict(self) -> dict[str, Any]:
        return self.validated_args.model_dump()


class FailedToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_name: str
    call_id: str
    error: str


class ParsedMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_calls: list[ParsedToolCall]


class ResolvedMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    tool_calls: list[ResolvedToolCall]
    failed_calls: list[FailedToolCall] = Field(default_factory=list)


class APIToolFormatHandler:
    @property
    def name(self) -> str:
        return "api"

    def get_available_tools(
        self, tool_manager: ToolManager, config: VibeConfig
    ) -> list[AvailableTool]:
        active_tools = get_active_tool_classes(tool_manager, config)

        return [
            AvailableTool(
                function=AvailableFunction(
                    name=tool_class.get_name(),
                    description=tool_class.description,
                    parameters=tool_class.get_parameters(),
                )
            )
            for tool_class in active_tools
        ]

    def get_tool_choice(self) -> StrToolChoice | AvailableTool:
        return "auto"

    def process_api_response_message(self, message: Any) -> LLMMessage:
        clean_message = {"role": message.role, "content": message.content}

        if message.tool_calls:
            clean_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "index": tc.index,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        return LLMMessage.model_validate(clean_message)

    def parse_message(self, message: LLMMessage) -> ParsedMessage:
        tool_calls = []

        # First, try native API tool_calls field
        api_tool_calls = message.tool_calls or []
        for tc in api_tool_calls:
            if not (function_call := tc.function):
                continue
            try:
                args = json.loads(function_call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            tool_calls.append(
                ParsedToolCall(
                    tool_name=function_call.name or "",
                    raw_args=args,
                    call_id=tc.id or "",
                )
            )

        # Fallback: Parse tool calls from JSON embedded in content
        # This handles local models (llama.cpp/Ollama) that output tool calls as JSON text
        if not tool_calls and message.content:
            content_tool_calls = _extract_tool_calls_from_content(message.content)
            for tc_data in content_tool_calls:
                tool_name = tc_data.get("name", "")
                if not tool_name:
                    continue

                # Handle arguments in various formats
                raw_args = tc_data.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {}

                call_id = tc_data.get("id", "") or str(uuid4())[:8]

                tool_calls.append(
                    ParsedToolCall(
                        tool_name=tool_name,
                        raw_args=raw_args if isinstance(raw_args, dict) else {},
                        call_id=call_id,
                    )
                )

            if tool_calls:
                logger.debug(
                    "Parsed %d tool call(s) from content JSON (fallback mode)",
                    len(tool_calls),
                )

        return ParsedMessage(tool_calls=tool_calls)

    def resolve_tool_calls(
        self, parsed: ParsedMessage, tool_manager: ToolManager, config: VibeConfig
    ) -> ResolvedMessage:
        resolved_calls = []
        failed_calls = []

        active_tools = {
            tool_class.get_name(): tool_class
            for tool_class in get_active_tool_classes(tool_manager, config)
        }

        for parsed_call in parsed.tool_calls:
            tool_class = active_tools.get(parsed_call.tool_name)
            if not tool_class:
                failed_calls.append(
                    FailedToolCall(
                        tool_name=parsed_call.tool_name,
                        call_id=parsed_call.call_id,
                        error=f"Unknown tool '{parsed_call.tool_name}'",
                    )
                )
                continue

            args_model, _ = tool_class._get_tool_args_results()
            try:
                validated_args = args_model.model_validate(parsed_call.raw_args)
                resolved_calls.append(
                    ResolvedToolCall(
                        tool_name=parsed_call.tool_name,
                        tool_class=tool_class,
                        validated_args=validated_args,
                        call_id=parsed_call.call_id,
                    )
                )
            except ValidationError as e:
                failed_calls.append(
                    FailedToolCall(
                        tool_name=parsed_call.tool_name,
                        call_id=parsed_call.call_id,
                        error=f"Invalid arguments: {e}",
                    )
                )

        return ResolvedMessage(tool_calls=resolved_calls, failed_calls=failed_calls)

    def create_tool_response_message(
        self, tool_call: ResolvedToolCall, result_text: str
    ) -> LLMMessage:
        return LLMMessage(
            role=Role.tool,
            tool_call_id=tool_call.call_id,
            name=tool_call.tool_name,
            content=result_text,
        )

    def create_failed_tool_response_message(
        self, failed: FailedToolCall, error_content: str
    ) -> LLMMessage:
        return LLMMessage(
            role=Role.tool,
            tool_call_id=failed.call_id,
            name=failed.tool_name,
            content=error_content,
        )
