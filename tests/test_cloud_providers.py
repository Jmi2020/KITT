#!/usr/bin/env python3
"""Test script to verify each cloud provider works individually."""

import asyncio
import os
import sys

# Add services to path
sys.path.insert(0, "/Users/Shared/Coding/KITT/services/brain/src")
sys.path.insert(0, "/Users/Shared/Coding/KITT/services/common/src")


async def test_provider(provider: str, model: str, api_key_env: str):
    """Test a single cloud provider with a simple query."""
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"  SKIP: {api_key_env} not set")
        return False

    print(f"  API Key: {api_key[:10]}...{api_key[-4:]}")

    try:
        import litellm

        # Format model name per provider
        if provider == "openai":
            litellm_model = model
        elif provider == "perplexity":
            litellm_model = f"perplexity/{model}"
        elif provider == "gemini":
            litellm_model = f"gemini/{model}"
        else:
            litellm_model = f"{provider}/{model}"

        print(f"  Litellm model: {litellm_model}")

        result = await litellm.acompletion(
            model=litellm_model,
            messages=[
                {"role": "user", "content": "Say 'Hello from {provider}' in exactly 5 words."}
            ],
            temperature=0.7,
            max_tokens=50,
        )

        response = result.choices[0].message.content
        print(f"  Response: {response[:100]}")

        # Get usage if available
        if hasattr(result, "usage") and result.usage:
            print(f"  Tokens: {result.usage.total_tokens}")

        print(f"  SUCCESS")
        return True

    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        return False


async def main():
    print("=" * 60)
    print("Cloud Provider Test Script")
    print("=" * 60)

    # Define providers to test (December 2025 models)
    providers = [
        ("openai", "gpt-5.2", "OPENAI_API_KEY"),
        ("anthropic", "claude-sonnet-4-5", "ANTHROPIC_API_KEY"),
        ("perplexity", "sonar", "PERPLEXITY_API_KEY"),
        ("gemini", "gemini-2.5-flash", "GOOGLE_API_KEY"),
    ]

    results = {}

    for provider, model, api_key_env in providers:
        print(f"\n[{provider.upper()}] Testing {model}...")
        success = await test_provider(provider, model, api_key_env)
        results[provider] = success

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)
    for provider, success in results.items():
        status = "OK" if success else "FAILED"
        print(f"  {provider}: {status}")

    # Check if any failed
    if not all(results.values()):
        print("\nSome providers failed!")
        sys.exit(1)
    else:
        print("\nAll providers working!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
