from __future__ import annotations

from fnmatch import fnmatch
from functools import lru_cache
import json
import re
from typing import TYPE_CHECKING, Any

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


# Regex pattern to match text-based tool calls like: tool_name[ARGS]{"key": "value"}
# This handles models like Devstral that output tool calls as text instead of using API format
# The pattern captures the tool name and then uses a separate function to extract balanced JSON
_TEXT_TOOL_CALL_START_PATTERN = re.compile(r"(\w+)\[ARGS\]\{")


def _extract_balanced_json(content: str, start_pos: int) -> str | None:
    """Extract a balanced JSON object starting at start_pos (which points to '{')."""
    if start_pos >= len(content) or content[start_pos] != "{":
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start_pos, len(content)):
        char = content[i]

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

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start_pos : i + 1]

    return None


def _parse_json_tool_calls(content: str) -> list[ParsedToolCall]:
    """Parse tool calls from JSON format embedded in text.

    Handles format: { "tool_calls": [ { "name": "...", "arguments": {...} } ] }
    This is used by some models (like Devstral) that output tool calls as JSON.
    """
    tool_calls = []

    # Look for JSON objects in the content that contain tool_calls
    # Find potential JSON starts
    for i, char in enumerate(content):
        if char != "{":
            continue

        json_str = _extract_balanced_json(content, i)
        if not json_str:
            continue

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        # Check if this is a tool_calls format
        if isinstance(data, dict) and "tool_calls" in data:
            calls = data.get("tool_calls", [])
            if not isinstance(calls, list):
                continue

            for idx, call in enumerate(calls):
                if not isinstance(call, dict):
                    continue

                name = call.get("name", "")
                args = call.get("arguments", {})

                if not name:
                    continue

                # Handle case where arguments might be a string
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool_calls.append(
                    ParsedToolCall(
                        tool_name=name,
                        raw_args=args if isinstance(args, dict) else {},
                        call_id=f"json_call_{len(tool_calls)}",
                    )
                )

            # Found tool_calls, stop looking
            if tool_calls:
                return tool_calls

    return tool_calls


def _parse_text_tool_calls(content: str) -> list[ParsedToolCall]:
    """Parse tool calls from text content.

    Supports multiple formats:
    1. tool_name[ARGS]{"key": "value"} (Devstral text format)
    2. { "tool_calls": [...] } (JSON embedded format)
    """
    tool_calls = []
    idx = 0

    # First try the [ARGS] format
    for match in _TEXT_TOOL_CALL_START_PATTERN.finditer(content):
        tool_name = match.group(1)
        json_start = match.end() - 1  # Position of the '{'

        args_str = _extract_balanced_json(content, json_start)
        if args_str is None:
            continue

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        tool_calls.append(
            ParsedToolCall(
                tool_name=tool_name,
                raw_args=args,
                call_id=f"text_call_{idx}",
            )
        )
        idx += 1

    # If no [ARGS] format found, try JSON embedded format
    if not tool_calls:
        tool_calls = _parse_json_tool_calls(content)

    return tool_calls


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
        clean_message = {
            "role": message.role,
            "content": message.content,
            "reasoning_content": getattr(message, "reasoning_content", None),
        }

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

    def backfill_tool_calls(
        self, message: LLMMessage, parsed_calls: list[ParsedToolCall]
    ) -> None:
        """Backfill tool_calls on assistant message from text-based tool calls.

        When models output tool calls as text (JSON embedded or [ARGS] format),
        the assistant message has tool_calls=None. This causes issues with
        llama.cpp Jinja templates which expect:
          assistant (with tool_calls) → tool result → assistant

        This method populates the tool_calls field so the message history
        has the proper structure for subsequent LLM calls.
        """
        if message.tool_calls or not parsed_calls:
            return  # Already has tool_calls or nothing to backfill

        from kitty_code.core.types import FunctionCall, ToolCall

        message.tool_calls = [
            ToolCall(
                id=call.call_id,
                index=idx,
                type="function",
                function=FunctionCall(
                    name=call.tool_name,
                    arguments=json.dumps(call.raw_args),
                ),
            )
            for idx, call in enumerate(parsed_calls)
        ]

    def parse_message(self, message: LLMMessage) -> ParsedMessage:
        tool_calls = []

        # First try API-style tool calls (OpenAI format)
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

        # If no API tool calls found, try text-based format (Devstral/Mistral style)
        # Format: tool_name[ARGS]{"key": "value"}
        if not tool_calls and message.content:
            tool_calls = _parse_text_tool_calls(message.content)

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
