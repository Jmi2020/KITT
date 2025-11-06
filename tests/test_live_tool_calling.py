#!/usr/bin/env python3
"""Live test of llama.cpp tool calling with Qwen2.5."""

import json
import httpx

# llama.cpp server with tool calling enabled
LLAMACPP_URL = "http://localhost:8083"


def test_simple_tool_call():
    """Test basic tool calling with a simple get_weather tool."""

    # Define a simple tool
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
                            "description": "City name, e.g. 'San Francisco, CA'",
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

    # Create request
    request = {
        "messages": [
            {"role": "user", "content": "What's the weather like in San Francisco?"}
        ],
        "tools": tools,
        "temperature": 0.7,
        "max_tokens": 512,
    }

    print("=" * 80)
    print("TEST: Simple Tool Call (get_weather)")
    print("=" * 80)
    print(f"Query: {request['messages'][0]['content']}")
    print(f"Available tools: {[t['function']['name'] for t in tools]}")
    print()

    # Send request
    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{LLAMACPP_URL}/v1/chat/completions", json=request)
        response.raise_for_status()
        result = response.json()

    # Parse response
    message = result["choices"][0]["message"]
    print("Response:")
    print(json.dumps(message, indent=2))
    print()

    # Check for tool calls
    if "tool_calls" in message and message["tool_calls"]:
        print("✓ Tool call detected!")
        for tc in message["tool_calls"]:
            print(f"  Tool: {tc['function']['name']}")
            print(f"  Arguments: {tc['function']['arguments']}")
        return True
    else:
        print("✗ No tool call in response")
        if "content" in message:
            print(f"Content: {message['content']}")
        return False


def test_xml_format_parsing():
    """Test that we can parse Qwen2.5's XML tool call format."""

    # Sample response with XML tool call
    sample_response = """<tool_call>
{"name": "get_weather", "arguments": {"location": "San Francisco, CA", "unit": "fahrenheit"}}
</tool_call>"""

    print("=" * 80)
    print("TEST: XML Format Parsing")
    print("=" * 80)
    print("Sample XML:")
    print(sample_response)
    print()

    # Parse XML tool call (this is what our parser does)
    import re

    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    matches = re.findall(pattern, sample_response, re.DOTALL)

    if matches:
        print("✓ XML parsing successful!")
        for i, match in enumerate(matches, 1):
            tool_call = json.loads(match)
            print(f"  Tool Call {i}:")
            print(f"    Name: {tool_call['name']}")
            print(f"    Arguments: {tool_call['arguments']}")
        return True
    else:
        print("✗ Failed to parse XML")
        return False


def test_multi_tool_scenario():
    """Test with multiple tools available."""

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
                "description": "Search the web for information",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        },
    ]

    request = {
        "messages": [{"role": "user", "content": "Search for recent news about AI"}],
        "tools": tools,
        "temperature": 0.7,
        "max_tokens": 512,
    }

    print("=" * 80)
    print("TEST: Multiple Tools Available")
    print("=" * 80)
    print(f"Query: {request['messages'][0]['content']}")
    print(f"Available tools: {[t['function']['name'] for t in tools]}")
    print()

    with httpx.Client(timeout=30.0) as client:
        response = client.post(f"{LLAMACPP_URL}/v1/chat/completions", json=request)
        response.raise_for_status()
        result = response.json()

    message = result["choices"][0]["message"]
    print("Response:")
    print(json.dumps(message, indent=2))
    print()

    if "tool_calls" in message and message["tool_calls"]:
        tool_name = message["tool_calls"][0]["function"]["name"]
        print(f"✓ Correct tool selected: {tool_name}")
        return tool_name == "search_web"
    else:
        print("✗ No tool call")
        return False


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("LIVE TOOL CALLING TEST SUITE")
    print("=" * 80)
    print()

    results = {}

    # Test 1: XML parsing
    results["XML Parsing"] = test_xml_format_parsing()
    print()

    # Test 2: Simple tool call
    results["Simple Tool Call"] = test_simple_tool_call()
    print()

    # Test 3: Multiple tools
    results["Multiple Tools"] = test_multi_tool_scenario()
    print()

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status} - {test_name}")

    total = len(results)
    passed = sum(results.values())
    print()
    print(f"Results: {passed}/{total} tests passed")

    exit(0 if all(results.values()) else 1)
