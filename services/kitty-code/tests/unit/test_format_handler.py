"""Tests for the format handler, specifically text-based tool call handling."""

import pytest

from kitty_code.core.llm.format import (
    APIToolFormatHandler,
    ParsedToolCall,
    _parse_json_tool_calls,
    _parse_text_tool_calls,
)
from kitty_code.core.types import LLMMessage, Role


class TestTextToolCallParsing:
    """Tests for parsing text-based tool calls."""

    def test_parse_args_format(self):
        """Test parsing tool_name[ARGS]{...} format."""
        content = 'read_file[ARGS]{"path": "/tmp/test.txt"}'
        result = _parse_text_tool_calls(content)

        assert len(result) == 1
        assert result[0].tool_name == "read_file"
        assert result[0].raw_args == {"path": "/tmp/test.txt"}

    def test_parse_json_embedded_format(self):
        """Test parsing { "tool_calls": [...] } format."""
        content = '''Here is what I'll do:
{ "tool_calls": [
    { "name": "read_file", "arguments": { "path": "/tmp/test.txt" } }
] }'''
        result = _parse_text_tool_calls(content)

        assert len(result) == 1
        assert result[0].tool_name == "read_file"
        assert result[0].raw_args == {"path": "/tmp/test.txt"}

    def test_parse_json_multiple_calls(self):
        """Test parsing multiple tool calls in JSON format."""
        content = '''{ "tool_calls": [
    { "name": "read_file", "arguments": { "path": "/tmp/a.txt" } },
    { "name": "write_file", "arguments": { "path": "/tmp/b.txt", "content": "hello" } }
] }'''
        result = _parse_json_tool_calls(content)

        assert len(result) == 2
        assert result[0].tool_name == "read_file"
        assert result[1].tool_name == "write_file"

    def test_parse_json_string_arguments(self):
        """Test parsing JSON format where arguments is a string."""
        content = '''{ "tool_calls": [
    { "name": "bash", "arguments": "{\\"command\\": \\"ls\\"}" }
] }'''
        result = _parse_json_tool_calls(content)

        assert len(result) == 1
        assert result[0].tool_name == "bash"
        assert result[0].raw_args == {"command": "ls"}


class TestBackfillToolCalls:
    """Tests for backfilling tool_calls on assistant messages."""

    def test_backfill_populates_tool_calls(self):
        """Test that backfill adds tool_calls to assistant message."""
        handler = APIToolFormatHandler()
        message = LLMMessage(
            role=Role.assistant,
            content='{ "tool_calls": [{ "name": "read_file", "arguments": { "path": "/tmp/test.txt" } }] }'
        )

        # Initially no tool_calls
        assert message.tool_calls is None

        parsed_calls = [
            ParsedToolCall(
                tool_name="read_file",
                raw_args={"path": "/tmp/test.txt"},
                call_id="json_call_0",
            )
        ]

        handler.backfill_tool_calls(message, parsed_calls)

        # Now tool_calls should be populated
        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].function.name == "read_file"
        assert message.tool_calls[0].id == "json_call_0"

    def test_backfill_skips_if_already_has_tool_calls(self):
        """Test that backfill doesn't overwrite existing tool_calls."""
        from kitty_code.core.types import FunctionCall, ToolCall

        handler = APIToolFormatHandler()
        message = LLMMessage(
            role=Role.assistant,
            content="I'll read the file",
            tool_calls=[
                ToolCall(
                    id="existing_call",
                    index=0,
                    function=FunctionCall(name="write_file", arguments='{"path": "/tmp/x.txt"}'),
                )
            ],
        )

        parsed_calls = [
            ParsedToolCall(
                tool_name="read_file",
                raw_args={"path": "/tmp/test.txt"},
                call_id="json_call_0",
            )
        ]

        handler.backfill_tool_calls(message, parsed_calls)

        # Should keep existing tool_calls, not overwrite
        assert len(message.tool_calls) == 1
        assert message.tool_calls[0].id == "existing_call"
        assert message.tool_calls[0].function.name == "write_file"

    def test_backfill_skips_if_no_parsed_calls(self):
        """Test that backfill does nothing with empty parsed_calls."""
        handler = APIToolFormatHandler()
        message = LLMMessage(role=Role.assistant, content="No tools needed")

        handler.backfill_tool_calls(message, [])

        assert message.tool_calls is None

    def test_backfill_multiple_calls(self):
        """Test backfilling multiple tool calls."""
        handler = APIToolFormatHandler()
        message = LLMMessage(role=Role.assistant, content="Multiple tools")

        parsed_calls = [
            ParsedToolCall(tool_name="read_file", raw_args={"path": "/a.txt"}, call_id="call_0"),
            ParsedToolCall(tool_name="write_file", raw_args={"path": "/b.txt"}, call_id="call_1"),
            ParsedToolCall(tool_name="bash", raw_args={"command": "ls"}, call_id="call_2"),
        ]

        handler.backfill_tool_calls(message, parsed_calls)

        assert message.tool_calls is not None
        assert len(message.tool_calls) == 3
        assert message.tool_calls[0].function.name == "read_file"
        assert message.tool_calls[0].index == 0
        assert message.tool_calls[1].function.name == "write_file"
        assert message.tool_calls[1].index == 1
        assert message.tool_calls[2].function.name == "bash"
        assert message.tool_calls[2].index == 2

    def test_backfill_serializes_arguments(self):
        """Test that backfill properly serializes arguments as JSON string."""
        import json

        handler = APIToolFormatHandler()
        message = LLMMessage(role=Role.assistant, content="Test")

        parsed_calls = [
            ParsedToolCall(
                tool_name="write_file",
                raw_args={"path": "/tmp/test.txt", "content": "hello\nworld"},
                call_id="call_0",
            )
        ]

        handler.backfill_tool_calls(message, parsed_calls)

        # Arguments should be JSON string
        args_str = message.tool_calls[0].function.arguments
        args_dict = json.loads(args_str)
        assert args_dict == {"path": "/tmp/test.txt", "content": "hello\nworld"}


class TestMessageSerialization:
    """Tests that verify proper message serialization after backfill."""

    def test_serialized_message_has_tool_calls(self):
        """Test that serialized message includes tool_calls field."""
        handler = APIToolFormatHandler()
        message = LLMMessage(role=Role.assistant, content="Using tools")

        parsed_calls = [
            ParsedToolCall(
                tool_name="read_file",
                raw_args={"path": "/tmp/test.txt"},
                call_id="json_call_0",
            )
        ]

        handler.backfill_tool_calls(message, parsed_calls)

        # Serialize like GenericBackend does
        serialized = message.model_dump(exclude_none=True)

        assert "tool_calls" in serialized
        assert len(serialized["tool_calls"]) == 1
        assert serialized["tool_calls"][0]["function"]["name"] == "read_file"
