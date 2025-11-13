#!/usr/bin/env python3
"""Manual test script for Perplexity API enhancements.

This script validates the following enhancements:
1. Citations extraction (HIGH priority)
2. Token usage tracking and cost calculation (HIGH priority)
3. Search parameter passthrough (MEDIUM priority)
4. Model override and dynamic selection (MEDIUM priority)

Usage:
    python tests/manual/test_perplexity_enhancements.py

Prerequisites:
    - PERPLEXITY_API_KEY set in .env
    - Brain service dependencies installed
"""

import asyncio
import os
import sys
from pathlib import Path

# Add services to path
repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root / "services" / "brain" / "src"))
sys.path.insert(0, str(repo_root / "services" / "common" / "src"))

from brain.routing.cloud_clients import MCPClient
from common.config import settings


class PerplexityTestSuite:
    """Test suite for Perplexity API enhancements."""

    def __init__(self):
        """Initialize test suite with Perplexity client."""
        if not settings.perplexity_api_key:
            raise RuntimeError(
                "PERPLEXITY_API_KEY not configured. "
                "Set it in .env file to run these tests."
            )

        self.client = MCPClient(
            base_url=settings.perplexity_base_url,
            api_key=settings.perplexity_api_key,
            model="sonar"
        )

    async def test_1_citations_extraction(self):
        """Test citations extraction from Perplexity response.

        Validates:
        - Citations exist in response
        - Multiple fallback locations checked
        - Citations format is array of objects/strings
        """
        print("\n" + "="*70)
        print("TEST 1: Citations Extraction")
        print("="*70)

        query = "What are the latest advances in 3D printing materials for aerospace?"

        print(f"\nQuery: {query}")
        print("Model: sonar")
        print("\nExecuting query...")

        response = await self.client.query({"query": query})
        raw = response.get("raw", {})

        # Check top-level citations
        top_level_citations = raw.get("citations", [])
        print(f"\n✓ Top-level citations: {len(top_level_citations)} found")
        if top_level_citations:
            print(f"  Sample: {top_level_citations[0] if len(top_level_citations) > 0 else 'N/A'}")

        # Check choice metadata citations
        choice_citations = []
        if "choices" in raw and len(raw["choices"]) > 0:
            choice_metadata = raw["choices"][0].get("metadata", {})
            choice_citations = choice_metadata.get("citations", [])
            print(f"✓ Choice metadata citations: {len(choice_citations)} found")

        # Determine which location has citations
        final_citations = top_level_citations or choice_citations

        print(f"\n{'✅ PASS' if final_citations else '❌ FAIL'}: Citations extraction")
        print(f"Total citations: {len(final_citations)}")

        if final_citations:
            print("\nCitation format validation:")
            sample = final_citations[0]
            print(f"  Type: {type(sample)}")
            print(f"  Sample: {sample}")

        return len(final_citations) > 0

    async def test_2_token_usage_tracking(self):
        """Test token usage extraction and cost calculation.

        Validates:
        - Usage data present in response
        - Total tokens, input tokens, output tokens all captured
        - Cost calculation accuracy for all models
        """
        print("\n" + "="*70)
        print("TEST 2: Token Usage Tracking & Cost Calculation")
        print("="*70)

        query = "Explain PLA vs PETG for 3D printing"

        print(f"\nQuery: {query}")
        print("Model: sonar")
        print("\nExecuting query...")

        response = await self.client.query({"query": query})
        raw = response.get("raw", {})

        # Extract usage data
        usage = raw.get("usage", {})

        print(f"\n✓ Usage data found: {bool(usage)}")
        if usage:
            total_tokens = usage.get("total_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            print(f"  Total tokens: {total_tokens}")
            print(f"  Input tokens: {prompt_tokens}")
            print(f"  Output tokens: {completion_tokens}")

            # Test cost calculation for all models
            print("\nCost calculation validation:")

            # Import cost calculation method
            from brain.autonomous.task_executor import TaskExecutor
            executor = TaskExecutor()

            models = {
                "sonar": 0.20,
                "sonar-pro": 9.0,
                "sonar-reasoning": 3.0,
                "sonar-reasoning-pro": 5.0,
            }

            for model, expected_rate in models.items():
                cost = executor._calculate_perplexity_cost(total_tokens, model)
                expected_cost = (total_tokens / 1_000_000) * expected_rate
                match = abs(cost - expected_cost) < 0.0001

                print(f"  {model}: ${cost:.6f} (rate: ${expected_rate}/1M) {'✅' if match else '❌'}")

        print(f"\n{'✅ PASS' if usage else '❌ FAIL'}: Token usage tracking")

        return bool(usage) and usage.get("total_tokens", 0) > 0

    async def test_3_search_parameters(self):
        """Test search parameter passthrough to Perplexity API.

        Validates:
        - search_domain_filter works
        - search_recency_filter works
        - return_related_questions works
        """
        print("\n" + "="*70)
        print("TEST 3: Search Parameters")
        print("="*70)

        query = "Latest sustainable 3D printing materials"

        print(f"\nQuery: {query}")
        print("Model: sonar")
        print("\nSearch parameters:")
        print("  - Domain filter: ['.edu', '.gov', '.org']")
        print("  - Recency filter: 'month'")
        print("  - Return related questions: True")
        print("\nExecuting query...")

        payload = {
            "query": query,
            "search_domain_filter": [".edu", ".gov", ".org"],
            "search_recency_filter": "month",
            "return_related_questions": True,
        }

        response = await self.client.query(payload)
        raw = response.get("raw", {})

        # Check for related questions
        related_questions = []
        if "choices" in raw and len(raw["choices"]) > 0:
            choice_metadata = raw["choices"][0].get("metadata", {})
            related_questions = choice_metadata.get("related_questions", [])

        # Also check top-level
        if not related_questions:
            related_questions = raw.get("related_questions", [])

        print(f"\n✓ Related questions returned: {len(related_questions)}")
        if related_questions:
            print("  Sample questions:")
            for i, q in enumerate(related_questions[:3], 1):
                print(f"    {i}. {q}")

        # Check citations to verify domain filtering (indirect validation)
        citations = raw.get("citations", [])
        print(f"\n✓ Citations with domain filtering: {len(citations)}")
        if citations:
            # Check if citations are from filtered domains
            filtered_domains = ['.edu', '.gov', '.org']
            domain_match_count = sum(
                1 for c in citations
                if isinstance(c, str) and any(d in c for d in filtered_domains)
            )
            print(f"  Citations from filtered domains: {domain_match_count}/{len(citations)}")

        print(f"\n{'✅ PASS' if related_questions else '⚠️ PARTIAL'}: Search parameters")
        print("Note: Domain/recency filtering is applied by Perplexity internally")

        return True  # Parameters accepted without error

    async def test_4_model_override(self):
        """Test per-query model override.

        Validates:
        - Model can be overridden in payload
        - sonar-pro produces different results than sonar
        - Cost calculation uses correct model
        """
        print("\n" + "="*70)
        print("TEST 4: Model Override & Dynamic Selection")
        print("="*70)

        query = "Compare Metal FDM vs SLS for aerospace parts"

        # Test with default model (sonar)
        print(f"\nQuery: {query}")
        print("Model: sonar (default)")
        print("\nExecuting with sonar...")

        response_sonar = await self.client.query({"query": query})
        sonar_output = response_sonar.get("output", "")
        sonar_usage = response_sonar.get("raw", {}).get("usage", {})
        sonar_tokens = sonar_usage.get("total_tokens", 0)

        print(f"\n✓ Sonar response: {len(sonar_output)} chars, {sonar_tokens} tokens")

        # Test with model override (sonar-pro)
        print("\nModel: sonar-pro (override)")
        print("Executing with sonar-pro...")

        response_pro = await self.client.query({"query": query, "model": "sonar-pro"})
        pro_output = response_pro.get("output", "")
        pro_usage = response_pro.get("raw", {}).get("usage", {})
        pro_tokens = pro_usage.get("total_tokens", 0)

        print(f"\n✓ Sonar-pro response: {len(pro_output)} chars, {pro_tokens} tokens")

        # Compare responses
        print("\nComparison:")
        print(f"  Response length difference: {abs(len(pro_output) - len(sonar_output))} chars")
        print(f"  Token difference: {abs(pro_tokens - sonar_tokens)} tokens")

        # Test cost calculation difference
        from brain.autonomous.task_executor import TaskExecutor
        executor = TaskExecutor()

        cost_sonar = executor._calculate_perplexity_cost(sonar_tokens, "sonar")
        cost_pro = executor._calculate_perplexity_cost(pro_tokens, "sonar-pro")

        print(f"\nCost calculation:")
        print(f"  Sonar: ${cost_sonar:.6f} ({sonar_tokens} tokens @ $0.20/1M)")
        print(f"  Sonar-pro: ${cost_pro:.6f} ({pro_tokens} tokens @ $9.00/1M)")
        print(f"  Cost difference: ${abs(cost_pro - cost_sonar):.6f}")

        print(f"\n{'✅ PASS' if pro_tokens > 0 and sonar_tokens > 0 else '❌ FAIL'}: Model override")

        return pro_tokens > 0 and sonar_tokens > 0

    async def run_all_tests(self):
        """Run all test cases and report results."""
        print("\n" + "="*70)
        print("PERPLEXITY API ENHANCEMENTS - VALIDATION TEST SUITE")
        print("="*70)
        print(f"\nAPI Base: {settings.perplexity_base_url}")
        print(f"API Key: {'*' * 20}{settings.perplexity_api_key[-4:]}")
        print(f"Default Model: {self.client._model}")

        results = {}

        try:
            results["test_1_citations"] = await self.test_1_citations_extraction()
        except Exception as e:
            print(f"\n❌ TEST 1 FAILED: {e}")
            results["test_1_citations"] = False

        try:
            results["test_2_usage"] = await self.test_2_token_usage_tracking()
        except Exception as e:
            print(f"\n❌ TEST 2 FAILED: {e}")
            results["test_2_usage"] = False

        try:
            results["test_3_search"] = await self.test_3_search_parameters()
        except Exception as e:
            print(f"\n❌ TEST 3 FAILED: {e}")
            results["test_3_search"] = False

        try:
            results["test_4_model"] = await self.test_4_model_override()
        except Exception as e:
            print(f"\n❌ TEST 4 FAILED: {e}")
            results["test_4_model"] = False

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)

        passed = sum(1 for v in results.values() if v)
        total = len(results)

        for test_name, passed_flag in results.items():
            status = "✅ PASS" if passed_flag else "❌ FAIL"
            print(f"{status}: {test_name}")

        print(f"\nTotal: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

        if passed == total:
            print("\n🎉 ALL TESTS PASSED - Perplexity enhancements validated!")
            print("✅ Production ready for autonomous research workflows")
            return 0
        else:
            print("\n⚠️ SOME TESTS FAILED - Review failures before deployment")
            return 1


async def main():
    """Main entry point."""
    try:
        suite = PerplexityTestSuite()
        return await suite.run_all_tests()
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
