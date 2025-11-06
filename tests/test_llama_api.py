#!/usr/bin/env python3
"""Test llama.cpp API with tool calling."""

import json
import sys
import urllib.request


def test_tool_calling_api():
    """Test that llama.cpp server accepts tools parameter."""
    print("Testing llama.cpp API with tool calling...")

    url = "http://localhost:8083/completion"

    payload = {
        "prompt": "What is the weather in Tokyo?",
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"}
                        },
                        "required": ["location"],
                    },
                },
            }
        ],
        "n_predict": 100,
        "temperature": 0.7,
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        print(f"\nSending request to {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")

        with urllib.request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))

            print("\n✅ Server accepted tools parameter!")
            print(f"\nResponse keys: {list(data.keys())}")

            # Check for content/response
            content = (
                data.get("content") or data.get("response") or data.get("completion")
            )
            if content:
                print("\nResponse content (first 200 chars):")
                print(content[:200])

                # Check if response contains tool call XML
                if "<tool_call>" in content:
                    print("\n✅ Response contains tool call XML!")
                else:
                    print(
                        "\n⚠️  Response doesn't contain tool call XML (model may need prompting)"
                    )

            return True

    except urllib.error.HTTPError as e:
        print(f"\n❌ HTTP Error: {e.code} - {e.reason}")
        print(f"Response: {e.read().decode('utf-8')}")
        return False
    except urllib.error.URLError as e:
        print(f"\n❌ URL Error: {e.reason}")
        print("Is the llama.cpp server running on port 8083?")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_tool_calling_api()
    sys.exit(0 if success else 1)
