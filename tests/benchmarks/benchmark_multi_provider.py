"""Performance benchmarks for multi-provider LLM system.

Measures:
- Lazy initialization overhead
- Provider registry overhead
- Query latency (local vs cloud)
- Cost tracking overhead
"""

from __future__ import annotations

import os
import statistics
import time
from typing import List

import httpx


class PerformanceBenchmark:
    """Performance benchmark runner."""

    def __init__(self, api_base: str = "http://localhost:8000", iterations: int = 10):
        """Initialize benchmark."""
        self.api_base = api_base
        self.iterations = iterations
        self.client = httpx.Client(base_url=api_base, timeout=30.0)

    def measure_latency(self, func, warmup: int = 2) -> dict:
        """Measure function latency with statistics.

        Args:
            func: Function to measure
            warmup: Number of warmup iterations

        Returns:
            Dict with min, max, mean, median, p95, p99 latencies (ms)
        """
        # Warmup
        for _ in range(warmup):
            func()

        # Measure
        latencies = []
        for _ in range(self.iterations):
            start = time.perf_counter()
            func()
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

        latencies.sort()
        return {
            "min": latencies[0],
            "max": latencies[-1],
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": latencies[int(len(latencies) * 0.95)],
            "p99": latencies[int(len(latencies) * 0.99)] if len(latencies) > 2 else latencies[-1],
            "samples": len(latencies),
        }

    def benchmark_providers_endpoint(self) -> dict:
        """Benchmark /api/providers/available endpoint."""
        print("\n📊 Benchmarking /api/providers/available...")

        def call_endpoint():
            response = self.client.get("/api/providers/available")
            assert response.status_code == 200
            return response.json()

        stats = self.measure_latency(call_endpoint)

        print(f"  Min:    {stats['min']:.2f}ms")
        print(f"  Mean:   {stats['mean']:.2f}ms")
        print(f"  Median: {stats['median']:.2f}ms")
        print(f"  P95:    {stats['p95']:.2f}ms")
        print(f"  P99:    {stats['p99']:.2f}ms")
        print(f"  Max:    {stats['max']:.2f}ms")

        # Assertion: Should be very fast (< 100ms mean)
        assert stats["mean"] < 100, f"Providers endpoint too slow: {stats['mean']:.2f}ms"

        return stats

    def benchmark_local_query(self) -> dict:
        """Benchmark local provider query latency."""
        print("\n📊 Benchmarking local provider query...")

        def call_query():
            payload = {
                "conversationId": "bench-local",
                "userId": "bench-user",
                "intent": "conversation.chat",
                "prompt": "Say: OK",
            }
            response = self.client.post("/api/query", json=payload)
            assert response.status_code == 200
            return response.json()

        stats = self.measure_latency(call_query)

        print(f"  Min:    {stats['min']:.2f}ms")
        print(f"  Mean:   {stats['mean']:.2f}ms")
        print(f"  Median: {stats['median']:.2f}ms")
        print(f"  P95:    {stats['p95']:.2f}ms")
        print(f"  P99:    {stats['p99']:.2f}ms")
        print(f"  Max:    {stats['max']:.2f}ms")

        # Assertion: Should complete in reasonable time (< 10s mean)
        assert stats["mean"] < 10000, f"Local query too slow: {stats['mean']:.2f}ms"

        return stats

    def benchmark_cloud_query(self, provider: str = "openai", model: str = "gpt-4o-mini") -> dict:
        """Benchmark cloud provider query latency."""
        print(f"\n📊 Benchmarking {provider}/{model} query...")

        enabled = os.getenv(f"ENABLE_{provider.upper()}_COLLECTIVE", "false").lower() == "true"
        if not enabled:
            print(f"  ⏭️  Skipped ({provider} not enabled)")
            return {}

        def call_query():
            payload = {
                "conversationId": f"bench-{provider}",
                "userId": "bench-user",
                "intent": "conversation.chat",
                "prompt": "Say: OK",
                "provider": provider,
                "model": model,
            }
            response = self.client.post("/api/query", json=payload)
            assert response.status_code == 200
            return response.json()

        stats = self.measure_latency(call_query, warmup=1)  # Fewer warmups for cloud

        print(f"  Min:    {stats['min']:.2f}ms")
        print(f"  Mean:   {stats['mean']:.2f}ms")
        print(f"  Median: {stats['median']:.2f}ms")
        print(f"  P95:    {stats['p95']:.2f}ms")
        print(f"  P99:    {stats['p99']:.2f}ms")
        print(f"  Max:    {stats['max']:.2f}ms")

        # Cloud should have network latency overhead
        assert stats["mean"] > 100, f"Cloud query suspiciously fast: {stats['mean']:.2f}ms"

        return stats

    def benchmark_inline_syntax_overhead(self) -> dict:
        """Benchmark inline syntax parsing overhead."""
        print("\n📊 Benchmarking inline syntax parsing overhead...")

        # Baseline: query without inline syntax
        def query_without_syntax():
            payload = {
                "conversationId": "bench-baseline",
                "userId": "bench-user",
                "intent": "conversation.chat",
                "prompt": "Say: OK",
            }
            response = self.client.post("/api/query", json=payload)
            assert response.status_code == 200

        baseline_stats = self.measure_latency(query_without_syntax)

        # With inline syntax
        def query_with_syntax():
            payload = {
                "conversationId": "bench-inline",
                "userId": "bench-user",
                "intent": "conversation.chat",
                "prompt": "@local: Say: OK",
            }
            response = self.client.post("/api/query", json=payload)
            assert response.status_code == 200

        inline_stats = self.measure_latency(query_with_syntax)

        overhead_ms = inline_stats["mean"] - baseline_stats["mean"]
        overhead_pct = (overhead_ms / baseline_stats["mean"]) * 100

        print(f"  Baseline mean:  {baseline_stats['mean']:.2f}ms")
        print(f"  Inline mean:    {inline_stats['mean']:.2f}ms")
        print(f"  Overhead:       {overhead_ms:.2f}ms ({overhead_pct:.1f}%)")

        # Overhead should be minimal (< 10ms)
        assert overhead_ms < 10, f"Inline syntax overhead too high: {overhead_ms:.2f}ms"

        return {
            "baseline": baseline_stats,
            "inline": inline_stats,
            "overhead_ms": overhead_ms,
            "overhead_pct": overhead_pct,
        }

    def run_all(self) -> dict:
        """Run all benchmarks."""
        print("=" * 60)
        print("Multi-Provider Performance Benchmarks")
        print("=" * 60)
        print(f"API Base: {self.api_base}")
        print(f"Iterations: {self.iterations}")

        results = {}

        try:
            results["providers_endpoint"] = self.benchmark_providers_endpoint()
            results["local_query"] = self.benchmark_local_query()
            results["inline_syntax_overhead"] = self.benchmark_inline_syntax_overhead()

            # Cloud benchmarks (conditional)
            if os.getenv("ENABLE_OPENAI_COLLECTIVE", "false").lower() == "true":
                results["openai_query"] = self.benchmark_cloud_query("openai", "gpt-4o-mini")

            if os.getenv("ENABLE_ANTHROPIC_COLLECTIVE", "false").lower() == "true":
                results["anthropic_query"] = self.benchmark_cloud_query(
                    "anthropic", "claude-3-5-haiku-20241022"
                )

        except Exception as e:
            print(f"\n❌ Benchmark failed: {e}")
            raise

        print("\n" + "=" * 60)
        print("✅ All benchmarks completed successfully")
        print("=" * 60)

        return results


def main():
    """Run benchmarks from command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Run multi-provider performance benchmarks")
    parser.add_argument("--api-base", default="http://localhost:8000", help="Brain API base URL")
    parser.add_argument("--iterations", type=int, default=10, help="Number of iterations per benchmark")
    args = parser.parse_args()

    benchmark = PerformanceBenchmark(api_base=args.api_base, iterations=args.iterations)
    results = benchmark.run_all()

    # Optional: Save results to JSON
    import json
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = f"benchmark_results_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n📝 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
