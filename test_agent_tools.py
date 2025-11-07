#!/usr/bin/env python3
"""Test script for agent with web_search and research_deep tools."""

import httpx
import json
import sys

BRAIN_URL = "http://localhost:8000"

def test_web_search():
    """Test agent with web_search tool (DuckDuckGo)."""
    print("\n=== Testing web_search tool (DuckDuckGo) ===\n")

    request_data = {
        "intent": "query.text",
        "prompt": "Use web_search to find information about llama.cpp Metal GPU optimization",
        "conversationId": "test-web-search-agent",
        "userId": "test-user",
        "verbosity": 5,
        "useAgent": True
    }

    try:
        response = httpx.post(
            f"{BRAIN_URL}/api/query",
            json=request_data,
            timeout=120.0
        )
        response.raise_for_status()
        result = response.json()

        print(f"Status: {response.status_code}")
        print(f"Tier: {result.get('routing', {}).get('tier')}")
        print(f"Confidence: {result.get('routing', {}).get('confidence')}")
        print(f"Output preview: {result.get('result', {}).get('output', '')[:200]}...")
        print(f"Metadata: {json.dumps(result.get('routing', {}).get('metadata', {}), indent=2)}")

        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_research_deep():
    """Test agent with research_deep tool (Perplexity)."""
    print("\n=== Testing research_deep tool (Perplexity) ===\n")

    request_data = {
        "intent": "query.text",
        "prompt": "Use research_deep to get comprehensive analysis of Metal vs CUDA GPU acceleration for LLM inference",
        "conversationId": "test-research-deep-agent",
        "userId": "test-user",
        "verbosity": 5,
        "useAgent": True
    }

    try:
        response = httpx.post(
            f"{BRAIN_URL}/api/query",
            json=request_data,
            timeout=120.0
        )
        response.raise_for_status()
        result = response.json()

        print(f"Status: {response.status_code}")
        print(f"Tier: {result.get('routing', {}).get('tier')}")
        print(f"Confidence: {result.get('routing', {}).get('confidence')}")
        print(f"Output preview: {result.get('result', {}).get('output', '')[:200]}...")
        print(f"Metadata: {json.dumps(result.get('routing', {}).get('metadata', {}), indent=2)}")

        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing agent with dual research tools")
    print("=" * 60)

    # Test web_search (DuckDuckGo)
    web_search_ok = test_web_search()

    # Test research_deep (Perplexity) - only if web_search succeeded
    research_deep_ok = False
    if web_search_ok:
        research_deep_ok = test_research_deep()

    print("\n" + "=" * 60)
    print(f"web_search (DuckDuckGo): {'✓ PASS' if web_search_ok else '✗ FAIL'}")
    print(f"research_deep (Perplexity): {'✓ PASS' if research_deep_ok else '✗ FAIL'}")

    sys.exit(0 if (web_search_ok and research_deep_ok) else 1)
