#!/usr/bin/env python3
"""Test Phase 1: Tool call parser standalone test.

Tests the Qwen2.5 XML tool call parser without requiring full dependencies.
"""

import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ToolCall:
    """Structured tool call from LLM response."""

    name: str
    arguments: Dict[str, Any]
    raw_xml: str

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "arguments": self.arguments}


def parse_tool_calls(text: str) -> tuple[List[ToolCall], str]:
    """Extract tool calls from Qwen2.5 response.

    Qwen2.5 returns tool calls in XML format:
    <tool_call>{"name": "function_name", "arguments": {...}}</tool_call>
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


def test_single_tool_call():
    """Test parsing a single tool call."""
    print("\n=== Test 1: Single Tool Call ===")

    mock_response = """I'll help you check the weather.

<tool_call>{"name": "get_weather", "arguments": {"location": "San Francisco", "unit": "celsius"}}</tool_call>

I'll fetch the current weather conditions for you."""

    print(f"Input:\n{mock_response[:100]}...")

    tool_calls, cleaned_text = parse_tool_calls(mock_response)

    print(f"\nParsed {len(tool_calls)} tool call(s)")
    if tool_calls:
        print(f"Tool: {tool_calls[0].name}")
        print(f"Arguments: {tool_calls[0].arguments}")
        print(f"Cleaned text contains tool_call tag: {'<tool_call>' in cleaned_text}")

        # Assertions
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "get_weather"
        assert tool_calls[0].arguments["location"] == "San Francisco"
        assert tool_calls[0].arguments["unit"] == "celsius"
        assert "<tool_call>" not in cleaned_text

        print("✅ Test 1 PASSED")
        return True
    else:
        print("❌ Test 1 FAILED: No tool calls parsed")
        return False


def test_multiple_tool_calls():
    """Test parsing multiple tool calls."""
    print("\n=== Test 2: Multiple Tool Calls ===")

    mock_response = """I'll search the web and check the weather.

<tool_call>{"name": "search_web", "arguments": {"query": "Tokyo weather"}}</tool_call>

Now let me get the actual weather data:

<tool_call>{"name": "get_weather", "arguments": {"location": "Tokyo", "unit": "celsius"}}</tool_call>

Here are the results."""

    print("Input contains 2 tool calls")

    tool_calls, cleaned_text = parse_tool_calls(mock_response)

    print(f"\nParsed {len(tool_calls)} tool call(s)")
    for i, tc in enumerate(tool_calls):
        print(f"  {i+1}. {tc.name}({tc.arguments})")

    # Assertions
    assert len(tool_calls) == 2
    assert tool_calls[0].name == "search_web"
    assert tool_calls[0].arguments["query"] == "Tokyo weather"
    assert tool_calls[1].name == "get_weather"
    assert tool_calls[1].arguments["location"] == "Tokyo"
    assert "<tool_call>" not in cleaned_text

    print("✅ Test 2 PASSED")
    return True


def test_no_tool_calls():
    """Test parsing text with no tool calls."""
    print("\n=== Test 3: No Tool Calls ===")

    mock_response = "This is a regular response without any tool calls."

    print(f"Input: {mock_response}")

    tool_calls, cleaned_text = parse_tool_calls(mock_response)

    print(f"\nParsed {len(tool_calls)} tool call(s)")
    print(f"Cleaned text: {cleaned_text}")

    # Assertions
    assert len(tool_calls) == 0
    assert cleaned_text == mock_response

    print("✅ Test 3 PASSED")
    return True


def test_malformed_tool_call():
    """Test handling malformed tool calls."""
    print("\n=== Test 4: Malformed Tool Call (Should Skip) ===")

    mock_response = """Here's a response with a malformed tool call.

<tool_call>{"name": "broken", arguments: {bad json}}</tool_call>

And a valid one:

<tool_call>{"name": "valid_tool", "arguments": {"key": "value"}}</tool_call>

Done."""

    print("Input contains 1 valid and 1 malformed tool call")

    tool_calls, cleaned_text = parse_tool_calls(mock_response)

    print(f"\nParsed {len(tool_calls)} valid tool call(s)")
    if tool_calls:
        print(f"Valid tool: {tool_calls[0].name}")

    # Assertions
    assert len(tool_calls) == 1  # Only valid one parsed
    assert tool_calls[0].name == "valid_tool"

    print("✅ Test 4 PASSED (malformed tool call skipped correctly)")
    return True


def test_complex_arguments():
    """Test parsing tool calls with complex nested arguments."""
    print("\n=== Test 5: Complex Nested Arguments ===")

    mock_response = """<tool_call>{"name": "create_task", "arguments": {"title": "Test", "metadata": {"tags": ["urgent", "bug"], "priority": 1}, "assignees": ["alice", "bob"]}}</tool_call>"""

    print("Input has nested arguments")

    tool_calls, cleaned_text = parse_tool_calls(mock_response)

    print(f"\nParsed {len(tool_calls)} tool call(s)")
    if tool_calls:
        print(f"Tool: {tool_calls[0].name}")
        print(f"Arguments: {json.dumps(tool_calls[0].arguments, indent=2)}")

        # Assertions
        assert len(tool_calls) == 1
        assert tool_calls[0].name == "create_task"
        assert tool_calls[0].arguments["title"] == "Test"
        assert tool_calls[0].arguments["metadata"]["tags"] == ["urgent", "bug"]
        assert tool_calls[0].arguments["metadata"]["priority"] == 1
        assert tool_calls[0].arguments["assignees"] == ["alice", "bob"]

        print("✅ Test 5 PASSED")
        return True
    else:
        print("❌ Test 5 FAILED")
        return False


def main():
    """Run all parser tests."""
    print("=" * 60)
    print("Phase 1 Tool Call Parser Test Suite")
    print("=" * 60)

    results = []

    results.append(test_single_tool_call())
    results.append(test_multiple_tool_calls())
    results.append(test_no_tool_calls())
    results.append(test_malformed_tool_call())
    results.append(test_complex_arguments())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ All parser tests passed! Phase 1 core functionality is working.")
        print("\nThe parser successfully:")
        print("  - Extracts single tool calls")
        print("  - Handles multiple tool calls in one response")
        print("  - Handles text without tool calls")
        print("  - Skips malformed tool calls gracefully")
        print("  - Parses complex nested arguments")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
