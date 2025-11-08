#!/usr/bin/env python3
"""Test Athene V2 Agent tool calling capabilities."""

import json
import requests

def test_q4_tool_calling():
    """Test Q4 (Athene V2) server tool calling."""
    url = "http://localhost:8083/v1/chat/completions"

    payload = {
        "model": "kitty-q4",
        "messages": [
            {
                "role": "user",
                "content": "What is the current weather in San Francisco?"
            }
        ],
        "tools": [
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
                                "description": "The city and state, e.g. San Francisco, CA"
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "Temperature unit"
                            }
                        },
                        "required": ["location"]
                    }
                }
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512
    }

    print("=" * 80)
    print("Testing Athene V2 Agent Tool Calling (Q4 Server - Port 8083)")
    print("=" * 80)
    print(f"\nRequest URL: {url}")
    print(f"Prompt: {payload['messages'][0]['content']}")
    print(f"Tools available: {payload['tools'][0]['function']['name']}")
    print(f"Temperature: {payload['temperature']}")
    print("\nSending request...")

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        print("\n" + "=" * 80)
        print("RESPONSE")
        print("=" * 80)
        print(json.dumps(result, indent=2))

        # Check if tool call was made
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            message = choice.get("message", {})

            print("\n" + "=" * 80)
            print("ANALYSIS")
            print("=" * 80)

            if "tool_calls" in message:
                print(f"✓ Tool call detected!")
                print(f"  Number of tool calls: {len(message['tool_calls'])}")
                for i, tc in enumerate(message["tool_calls"]):
                    print(f"\n  Tool Call #{i+1}:")
                    print(f"    Function: {tc.get('function', {}).get('name')}")
                    print(f"    Arguments: {tc.get('function', {}).get('arguments')}")

            elif "content" in message:
                content = message["content"]
                print(f"Model response (content): {content[:200]}...")

                # Check for QWEN_XML format in content
                if "<tool_call>" in content:
                    print("\n✓ QWEN_XML format detected in content!")
                    print(f"  Raw content: {content}")
                else:
                    print("\n✗ No tool call detected (expected for weather query)")

        return result

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request failed: {e}")
        return None

def test_multi_tool_calling():
    """Test with multiple tools."""
    url = "http://localhost:8083/v1/chat/completions"

    payload = {
        "model": "kitty-q4",
        "messages": [
            {
                "role": "user",
                "content": "Search the web for the latest 3D printing materials and calculate the volume of a 10cm cube"
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "calculate_volume",
                    "description": "Calculate the volume of a cube",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "side_length": {
                                "type": "number",
                                "description": "The length of one side in cm"
                            }
                        },
                        "required": ["side_length"]
                    }
                }
            }
        ],
        "temperature": 0.0,
        "max_tokens": 512
    }

    print("\n\n" + "=" * 80)
    print("Testing Multiple Tools (Parallel Tool Calling)")
    print("=" * 80)
    print(f"\nPrompt: {payload['messages'][0]['content']}")
    print(f"Tools: web_search, calculate_volume")

    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        print("\nResponse:")
        print(json.dumps(result, indent=2))

        if "choices" in result and len(result["choices"]) > 0:
            message = result["choices"][0].get("message", {})
            if "tool_calls" in message:
                print(f"\n✓ Parallel tool calling: {len(message['tool_calls'])} tools called")
            elif "<tool_call>" in message.get("content", ""):
                print("\n✓ QWEN_XML format tool calls detected")

        return result

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Request failed: {e}")
        return None

if __name__ == "__main__":
    # Test 1: Single tool call
    result1 = test_q4_tool_calling()

    # Test 2: Multiple tools (parallel calling)
    result2 = test_multi_tool_calling()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("Athene V2 Agent tool calling test complete.")
    print("Expected format: QWEN_XML with <tool_call>{json}</tool_call> tags")
    print("Temperature: 0.0 (deterministic mode for reliable function calling)")
