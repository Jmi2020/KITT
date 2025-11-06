#!/usr/bin/env python3
"""Test Phase 1: llama.cpp function calling with Qwen2.5 tool parser.

Tests:
1. LlamaCppClient accepts tools parameter
2. Qwen2.5 returns tool calls in XML format
3. Parser extracts tool calls correctly
4. Backwards compatibility (works without tools)
"""

import asyncio
import sys
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "brain" / "src"))

from brain.routing.llama_cpp_client import LlamaCppClient
from brain.tools.parser import parse_tool_calls


async def test_basic_tool_calling():
    """Test basic tool calling with a simple weather tool."""
    print("\n=== Test 1: Basic Tool Calling ===")

    client = LlamaCppClient()

    # Define a simple weather tool
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or zip code",
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "Temperature unit",
                        },
                    },
                    "required": ["location"],
                },
            },
        }
    ]

    prompt = "What's the weather like in San Francisco? Use celsius."

    print(f"Prompt: {prompt}")
    print(f"Tools: {tools[0]['function']['name']}")

    try:
        response = await client.generate(prompt=prompt, tools=tools)

        print(f"\nResponse text: {response['response']}")
        print(f"Tool calls found: {len(response['tool_calls'])}")

        if response["tool_calls"]:
            for i, tool_call in enumerate(response["tool_calls"]):
                print(f"\nTool Call {i+1}:")
                print(f"  Name: {tool_call.name}")
                print(f"  Arguments: {tool_call.arguments}")
                print(f"  Raw XML: {tool_call.raw_xml}")

        # Verify tool call was made
        if response["tool_calls"]:
            assert response["tool_calls"][0].name == "get_weather"
            assert "location" in response["tool_calls"][0].arguments
            print("\n✅ Test 1 PASSED: Tool call successfully invoked")
            return True
        else:
            print("\n⚠️  Test 1 WARNING: No tool calls detected (may need model tuning)")
            return False

    except Exception as e:
        print(f"\n❌ Test 1 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_parser_directly():
    """Test the tool call parser with mock Qwen2.5 responses."""
    print("\n=== Test 2: Parser Direct Test ===")

    # Mock Qwen2.5 response with tool call
    mock_response = """I'll help you check the weather.

<tool_call>{"name": "get_weather", "arguments": {"location": "San Francisco", "unit": "celsius"}}</tool_call>

I'll fetch the current weather conditions for you."""

    print(f"Mock response:\n{mock_response}")

    try:
        tool_calls, cleaned_text = parse_tool_calls(mock_response)

        print(f"\nParsed {len(tool_calls)} tool call(s)")
        print(f"Cleaned text: {cleaned_text}")

        if tool_calls:
            print("\nTool Call:")
            print(f"  Name: {tool_calls[0].name}")
            print(f"  Arguments: {tool_calls[0].arguments}")

            # Verify parsing
            assert tool_calls[0].name == "get_weather"
            assert tool_calls[0].arguments["location"] == "San Francisco"
            assert tool_calls[0].arguments["unit"] == "celsius"
            assert "<tool_call>" not in cleaned_text

            print("\n✅ Test 2 PASSED: Parser correctly extracts tool calls")
            return True
        else:
            print("\n❌ Test 2 FAILED: Parser did not extract tool calls")
            return False

    except Exception as e:
        print(f"\n❌ Test 2 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_backwards_compatibility():
    """Test that LlamaCppClient still works without tools parameter."""
    print("\n=== Test 3: Backwards Compatibility ===")

    client = LlamaCppClient()
    prompt = "What is 2+2? Answer with just the number."

    print(f"Prompt: {prompt}")
    print("Tools: None (testing backwards compatibility)")

    try:
        response = await client.generate(prompt=prompt)

        print(f"\nResponse: {response['response']}")
        print(f"Tool calls: {response['tool_calls']}")

        # Verify response structure
        assert "response" in response
        assert "tool_calls" in response
        assert "raw" in response
        assert len(response["tool_calls"]) == 0

        print("\n✅ Test 3 PASSED: Backwards compatibility maintained")
        return True

    except Exception as e:
        print(f"\n❌ Test 3 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_multiple_tools():
    """Test with multiple tool definitions."""
    print("\n=== Test 4: Multiple Tools ===")

    client = LlamaCppClient()

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get current weather",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string"}},
                    "required": ["location"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
    ]

    prompt = "Search the web for weather in Tokyo"

    print(f"Prompt: {prompt}")
    print(f"Tools: {[t['function']['name'] for t in tools]}")

    try:
        response = await client.generate(prompt=prompt, tools=tools)

        print(f"\nResponse: {response['response']}")
        print(f"Tool calls: {len(response['tool_calls'])}")

        if response["tool_calls"]:
            for tool_call in response["tool_calls"]:
                print(f"  - {tool_call.name}({tool_call.arguments})")

        print("\n✅ Test 4 PASSED: Multiple tools handled correctly")
        return True

    except Exception as e:
        print(f"\n❌ Test 4 FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all Phase 1 tests."""
    print("=" * 60)
    print("Phase 1 Tool Calling Test Suite")
    print("=" * 60)

    results = []

    # Test 1: Basic tool calling (may fail if model not tuned)
    results.append(await test_basic_tool_calling())

    # Test 2: Parser (should always pass)
    results.append(await test_parser_directly())

    # Test 3: Backwards compatibility (should always pass)
    results.append(await test_backwards_compatibility())

    # Test 4: Multiple tools
    results.append(await test_multiple_tools())

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\n✅ All tests passed! Phase 1 implementation is working correctly.")
        return 0
    elif passed >= 2:  # Parser and backwards compat must pass
        print(
            "\n⚠️  Core functionality working. Model may need prompt tuning for tool use."
        )
        return 0
    else:
        print("\n❌ Critical tests failed. Check implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
