#!/usr/bin/env python3
"""Manual test script for Perplexity API enhancements.

Tests:
1. Citations extraction from real API response
2. Token usage tracking
3. Accurate cost calculation
4. Search parameter passthrough
5. Model selection override
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root / "services" / "brain" / "src"))
sys.path.insert(0, str(repo_root / "services" / "common" / "src"))

from brain.routing.cloud_clients import MCPClient
from brain.autonomous.task_executor import TaskExecutor
from common.config import settings


async def test_basic_query():
    """Test 1: Basic query with citations extraction."""
    print("\n" + "="*70)
    print("TEST 1: Basic Query with Citations Extraction")
    print("="*70)

    client = MCPClient(
        base_url=settings.perplexity_base_url,
        api_key=settings.perplexity_api_key,
        model="sonar"
    )

    query = "What are the key properties of PETG 3D printing filament?"

    print(f"\nQuery: {query}")
    print(f"Model: sonar")
    print("\nCalling Perplexity API...")

    response = await client.query({"query": query})

    print(f"\n✅ Response received ({len(response.get('output', ''))} chars)")
    print(f"\nOutput preview:\n{response['output'][:200]}...")

    # Check raw response structure
    raw = response.get("raw", {})
    print(f"\n📊 Raw response keys: {list(raw.keys())}")

    # Check for citations
    citations = raw.get("citations", [])
    if citations:
        print(f"\n✅ Citations found at top level: {len(citations)} citations")
        print(f"First citation: {citations[0] if citations else 'N/A'}")
    else:
        print("\n⚠️  No citations at top level, checking choices metadata...")
        if "choices" in raw:
            choice_meta = raw["choices"][0].get("metadata", {})
            citations = choice_meta.get("citations", [])
            if citations:
                print(f"✅ Citations found in choices metadata: {len(citations)} citations")
            else:
                print("❌ No citations found in choices metadata either")

    # Check usage
    usage = raw.get("usage", {})
    if usage:
        print(f"\n✅ Usage data found: {usage}")
        print(f"   - Total tokens: {usage.get('total_tokens', 0)}")
        print(f"   - Input tokens: {usage.get('prompt_tokens', 0)}")
        print(f"   - Output tokens: {usage.get('completion_tokens', 0)}")
    else:
        print("\n⚠️  No usage data found in response")

    return response


async def test_cost_calculation():
    """Test 2: Token-based cost calculation."""
    print("\n" + "="*70)
    print("TEST 2: Token-Based Cost Calculation")
    print("="*70)

    # Create task executor with cost calculation method
    executor = TaskExecutor()

    # Test cost calculation for different models
    test_cases = [
        ("sonar", 10000, 0.002),  # 10k tokens at $0.20/1M = $0.002
        ("sonar-pro", 10000, 0.09),  # 10k tokens at $9/1M = $0.09
        ("sonar-reasoning", 10000, 0.03),  # 10k tokens at $3/1M = $0.03
        ("sonar-reasoning-pro", 10000, 0.05),  # 10k tokens at $5/1M = $0.05
    ]

    print("\nModel               | Tokens  | Expected Cost | Calculated Cost | Match")
    print("-"*75)

    all_passed = True
    for model, tokens, expected_cost in test_cases:
        calculated_cost = executor._calculate_perplexity_cost(tokens, model)
        match = "✅" if abs(calculated_cost - expected_cost) < 0.0001 else "❌"
        if match == "❌":
            all_passed = False

        print(f"{model:20} | {tokens:7} | ${expected_cost:13.4f} | ${calculated_cost:15.4f} | {match}")

    if all_passed:
        print("\n✅ All cost calculations accurate!")
    else:
        print("\n❌ Some cost calculations incorrect")

    return all_passed


async def test_search_parameters():
    """Test 3: Search parameter passthrough."""
    print("\n" + "="*70)
    print("TEST 3: Search Parameter Passthrough")
    print("="*70)

    client = MCPClient(
        base_url=settings.perplexity_base_url,
        api_key=settings.perplexity_api_key,
        model="sonar"
    )

    query = "Latest advances in sustainable 3D printing materials"

    payload = {
        "query": query,
        "search_domain_filter": ["edu", "gov"],
        "search_recency_filter": "month",
        "return_related_questions": True
    }

    print(f"\nQuery: {query}")
    print(f"Search params: domain_filter={payload['search_domain_filter']}, recency={payload['search_recency_filter']}")
    print("\nCalling Perplexity API with search parameters...")

    response = await client.query(payload)

    print(f"\n✅ Response received ({len(response.get('output', ''))} chars)")
    print(f"\nOutput preview:\n{response['output'][:200]}...")

    # Check if related questions are returned
    raw = response.get("raw", {})
    related_questions = raw.get("related_questions", [])
    if related_questions:
        print(f"\n✅ Related questions found: {len(related_questions)}")
        for i, q in enumerate(related_questions[:3], 1):
            print(f"   {i}. {q}")
    else:
        print("\n⚠️  No related questions in response")

    return response


async def test_model_selection():
    """Test 4: Per-query model override."""
    print("\n" + "="*70)
    print("TEST 4: Per-Query Model Selection Override")
    print("="*70)

    # Create client with default model "sonar"
    client = MCPClient(
        base_url=settings.perplexity_base_url,
        api_key=settings.perplexity_api_key,
        model="sonar"
    )

    query = "Compare injection molding vs 3D printing for production"

    # Override to use sonar-pro for this specific query
    payload = {
        "query": query,
        "model": "sonar-pro"
    }

    print(f"\nClient default model: sonar")
    print(f"Query override model: sonar-pro")
    print(f"Query: {query}")
    print("\nCalling Perplexity API with model override...")

    response = await client.query(payload)

    print(f"\n✅ Response received ({len(response.get('output', ''))} chars)")

    # Verify model used in response
    raw = response.get("raw", {})
    model_used = raw.get("model", "unknown")
    print(f"\nModel used: {model_used}")

    if "pro" in model_used.lower():
        print("✅ Model override successful!")
    else:
        print(f"⚠️  Expected sonar-pro, got {model_used}")

    return response


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("PERPLEXITY API ENHANCEMENTS - MANUAL TEST SUITE")
    print("="*70)
    print(f"\nAPI Base: {settings.perplexity_base_url}")
    print(f"API Key: {settings.perplexity_api_key[:20]}...")
    print(f"Default Model: {settings.perplexity_model_search}")

    try:
        # Test 1: Basic query with citations
        await test_basic_query()

        # Test 2: Cost calculation
        await test_cost_calculation()

        # Test 3: Search parameters
        await test_search_parameters()

        # Test 4: Model selection
        await test_model_selection()

        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
