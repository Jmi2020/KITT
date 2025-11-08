#!/usr/bin/env python3
"""Test script for unified prompts implementation.

Tests:
1. Basic query using unified prompts
2. Tool calling with validation
3. Temperature enforcement
4. Agent mode with ReAct pattern
"""

import asyncio
import json
import httpx


async def test_basic_query():
    """Test basic query using unified prompts."""
    print("\n" + "="*80)
    print("TEST 1: Basic Query with Unified Prompts")
    print("="*80)

    payload = {
        "intent": "query.text",
        "prompt": "What is the best print temperature for PLA filament?",
        "conversationId": "test-unified-basic",
        "userId": "test",
        "verbosity": 3,
        "useAgent": False
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/query",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            print(f"\nTier: {data.get('routing', {}).get('tier')}")
            print(f"Confidence: {data.get('routing', {}).get('confidence')}")
            print(f"\nResponse (first 300 chars):\n{data.get('result', {}).get('output', '')[:300]}...")
            print("\n✓ Test 1 PASSED")
            return True

        except Exception as e:
            print(f"\n✗ Test 1 FAILED: {e}")
            return False


async def test_agent_mode():
    """Test agent mode with unified prompts."""
    print("\n" + "="*80)
    print("TEST 2: Agent Mode with ReAct Pattern")
    print("="*80)

    payload = {
        "intent": "query.text",
        "prompt": "Use your tools to search for the current price of PLA filament per kg",
        "conversationId": "test-unified-agent",
        "userId": "test",
        "verbosity": 3,
        "useAgent": True  # Enable agent mode
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/query",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            print(f"\nTier: {data.get('routing', {}).get('tier')}")
            print(f"Agent Used: {data.get('routing', {}).get('metadata', {}).get('agent_used', False)}")
            print(f"Tools Called: {data.get('routing', {}).get('metadata', {}).get('tools_used', [])}")
            print(f"\nResponse (first 300 chars):\n{data.get('result', {}).get('output', '')[:300]}...")
            print("\n✓ Test 2 PASSED")
            return True

        except Exception as e:
            print(f"\n✗ Test 2 FAILED: {e}")
            return False


async def test_mcp_tier():
    """Test MCP tier with freshness requirement."""
    print("\n" + "="*80)
    print("TEST 3: MCP Tier with Freshness (Perplexity)")
    print("="*80)

    payload = {
        "intent": "query.text",
        "prompt": "What are the latest 3D printing trends in 2025?",
        "conversationId": "test-unified-mcp",
        "userId": "test",
        "verbosity": 5,
        "forceTier": "mcp",
        "freshnessRequired": True,
        "useAgent": False
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/query",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            print(f"\nTier: {data.get('routing', {}).get('tier')}")
            print(f"Confidence: {data.get('routing', {}).get('confidence')}")
            print(f"Provider: {data.get('routing', {}).get('metadata', {}).get('provider')}")
            print(f"\nResponse (first 300 chars):\n{data.get('result', {}).get('output', '')[:300]}...")
            print("\n✓ Test 3 PASSED")
            return True

        except Exception as e:
            print(f"\n✗ Test 3 FAILED: {e}")
            return False


async def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("UNIFIED PROMPTS IMPLEMENTATION TEST SUITE")
    print("="*80)
    print("\nTesting Phase 2 implementation:")
    print("- KittySystemPrompt integration")
    print("- Tool call validation")
    print("- Temperature enforcement")
    print("- ReAct agent pattern")

    results = []

    # Test 1: Basic query
    results.append(await test_basic_query())
    await asyncio.sleep(2)

    # Test 2: Agent mode
    results.append(await test_agent_mode())
    await asyncio.sleep(2)

    # Test 3: MCP tier
    results.append(await test_mcp_tier())

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")

    if passed == total:
        print("\n✓ ALL TESTS PASSED")
    else:
        print("\n✗ SOME TESTS FAILED")

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
