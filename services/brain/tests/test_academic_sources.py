"""
Test script for academic source clients.

Tests arXiv, PubMed (NCBI), CORE, and Semantic Scholar APIs.
"""

import asyncio
import os
import sys

# Add the brain service to path
sys.path.insert(0, "/Users/Shared/Coding/KITT/services/brain/src")

from brain.research.sources.arxiv import ArxivSource
from brain.research.sources.pubmed import PubMedSource
from brain.research.sources.core import CORESource
from brain.research.sources.semantic_scholar import SemanticScholarSource
from brain.research.sources.registry import SourceRegistry


async def test_arxiv():
    """Test arXiv API (no key required)."""
    print("\n" + "=" * 60)
    print("Testing arXiv (no API key required)")
    print("=" * 60)

    source = ArxivSource()
    query = "quantum error correction"

    print(f"Searching for: '{query}'")
    papers = []
    async for paper in source.search(query, max_results=3):
        papers.append(paper)
        print(f"\n  [{len(papers)}] {paper.title[:70]}...")
        print(f"      arXiv ID: {paper.arxiv_id}")
        print(f"      Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"      Published: {paper.published_date}")
        print(f"      PDF URL: {paper.pdf_url[:60]}..." if paper.pdf_url else "      PDF URL: None")

    print(f"\n  Total papers found: {len(papers)}")
    return len(papers) > 0


async def test_pubmed():
    """Test PubMed/NCBI API."""
    print("\n" + "=" * 60)
    print("Testing PubMed (NCBI)")
    print("=" * 60)

    api_key = os.getenv("NCBI_API_KEY", "")
    if api_key:
        print(f"  Using API key: {api_key[:8]}...")
    else:
        print("  No API key (using public rate limit: 3 req/sec)")

    source = PubMedSource(api_key=api_key if api_key else None)
    query = "CRISPR gene editing"

    print(f"Searching for: '{query}'")
    papers = []
    async for paper in source.search(query, max_results=3):
        papers.append(paper)
        print(f"\n  [{len(papers)}] {paper.title[:70]}...")
        print(f"      PubMed ID: {paper.pubmed_id}")
        print(f"      Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"      Published: {paper.published_date}")
        print(f"      DOI: {paper.doi}" if paper.doi else "      DOI: None")

    print(f"\n  Total papers found: {len(papers)}")
    return len(papers) > 0


async def test_core():
    """Test CORE API."""
    print("\n" + "=" * 60)
    print("Testing CORE")
    print("=" * 60)

    api_key = os.getenv("CORE_API_KEY", "")
    if api_key:
        print(f"  Using API key: {api_key[:8]}...")
    else:
        print("  WARNING: No API key - CORE requires an API key")
        return False

    source = CORESource(api_key=api_key)
    query = "machine learning"

    print(f"Searching for: '{query}'")
    papers = []
    try:
        async for paper in source.search(query, max_results=3):
            papers.append(paper)
            print(f"\n  [{len(papers)}] {paper.title[:70]}...")
            print(f"      CORE ID: {paper.source_id}")
            print(f"      Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"      Published: {paper.published_date}")
            print(f"      DOI: {paper.doi}" if paper.doi else "      DOI: None")

        print(f"\n  Total papers found: {len(papers)}")
        return len(papers) > 0
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


async def test_semantic_scholar():
    """Test Semantic Scholar API (works without key, just rate limited)."""
    print("\n" + "=" * 60)
    print("Testing Semantic Scholar")
    print("=" * 60)

    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key:
        print(f"  Using API key: {api_key[:8]}...")
    else:
        print("  No API key (using public rate limit: 100 req/5min)")

    source = SemanticScholarSource(api_key=api_key if api_key else None)
    query = "transformer neural networks"

    print(f"Searching for: '{query}'")
    papers = []
    try:
        async for paper in source.search(query, max_results=3):
            papers.append(paper)
            print(f"\n  [{len(papers)}] {paper.title[:70]}...")
            print(f"      S2 ID: {paper.s2_id}")
            print(f"      Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
            print(f"      Published: {paper.published_date}")
            print(f"      Citations: {paper.citations_count}")

        print(f"\n  Total papers found: {len(papers)}")
        return len(papers) > 0
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


async def test_registry():
    """Test the unified source registry."""
    print("\n" + "=" * 60)
    print("Testing Source Registry (Combined Search)")
    print("=" * 60)

    registry = SourceRegistry()

    # Register available sources
    registry.register(ArxivSource(), priority=1)

    ncbi_key = os.getenv("NCBI_API_KEY", "")
    if ncbi_key:
        registry.register(PubMedSource(api_key=ncbi_key), priority=2)

    core_key = os.getenv("CORE_API_KEY", "")
    if core_key:
        registry.register(CORESource(api_key=core_key), priority=3)

    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    registry.register(SemanticScholarSource(api_key=s2_key if s2_key else None), priority=4)

    print(f"  Registered {len(registry._sources)} sources")

    query = "reinforcement learning robotics"
    print(f"  Searching all sources for: '{query}'")

    papers = await registry.search_parallel(query, max_per_source=2, timeout=30.0)

    print(f"\n  Combined results: {len(papers)} papers")
    for i, paper in enumerate(papers[:5], 1):
        source_name = type(paper).__name__ if hasattr(paper, '__class__') else 'unknown'
        print(f"    [{i}] {paper.title[:60]}...")
        print(f"        Source: {paper.source_id[:30]}...")

    return len(papers) > 0


async def main():
    """Run all tests."""
    print("\n" + "#" * 60)
    print("# Academic Source Client Tests")
    print("#" * 60)

    # Load environment
    from dotenv import load_dotenv
    load_dotenv("/Users/Shared/Coding/KITT/.env")

    results = {}

    # Test each source
    results["arXiv"] = await test_arxiv()
    results["PubMed"] = await test_pubmed()
    results["CORE"] = await test_core()
    results["Semantic Scholar"] = await test_semantic_scholar()
    results["Registry"] = await test_registry()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for source, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {source:20} [{status}]")

    total_passed = sum(results.values())
    total_tests = len(results)
    print(f"\n  {total_passed}/{total_tests} tests passed")

    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
