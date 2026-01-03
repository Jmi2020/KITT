"""
Source registry for managing academic paper sources.

Provides a unified interface to search across multiple sources
with priority ordering and fallback handling.
"""

import asyncio
from typing import Dict, List, Optional, AsyncIterator, Set
from datetime import datetime
import logging
import os

from .base import AcademicSource, PaperMetadata, SourcePriority
from .arxiv import ArxivSource
from .semantic_scholar import SemanticScholarSource
from .pubmed import PubMedSource
from .core import CORESource

logger = logging.getLogger(__name__)


class SourceRegistry:
    """
    Registry for managing academic paper sources.

    Provides:
    - Unified search across multiple sources
    - Priority-based source ordering
    - Deduplication via paper IDs
    - Fallback on source failures

    Example usage:
        registry = get_source_registry()
        async for paper in registry.search_all("transformer attention", max_per_source=50):
            print(paper.title)
    """

    def __init__(self):
        self._sources: Dict[str, AcademicSource] = {}
        self._initialized = False

    def register(self, source: AcademicSource) -> None:
        """Register an academic source."""
        self._sources[source.name.lower()] = source
        logger.info(f"Registered source: {source.name} (priority: {source.priority})")

    def get(self, name: str) -> Optional[AcademicSource]:
        """Get a source by name."""
        return self._sources.get(name.lower())

    def list_sources(self) -> List[AcademicSource]:
        """List all registered sources, sorted by priority."""
        return sorted(
            self._sources.values(),
            key=lambda s: s.priority
        )

    def list_source_names(self) -> List[str]:
        """List all registered source names."""
        return [s.name for s in self.list_sources()]

    async def initialize_defaults(self) -> None:
        """Initialize default sources with API keys from environment."""
        if self._initialized:
            return

        # arXiv (no API key needed)
        self.register(ArxivSource())

        # Semantic Scholar (optional API key for higher limits)
        s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        self.register(SemanticScholarSource(api_key=s2_key))

        # PubMed (optional API key for higher limits)
        ncbi_key = os.getenv("NCBI_API_KEY")
        self.register(PubMedSource(api_key=ncbi_key))

        # CORE (optional API key)
        core_key = os.getenv("CORE_API_KEY")
        self.register(CORESource(api_key=core_key))

        self._initialized = True
        logger.info(f"Initialized {len(self._sources)} academic sources")

    async def close_all(self) -> None:
        """Close all source HTTP clients."""
        for source in self._sources.values():
            await source.close()
        logger.info("Closed all source connections")

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all sources."""
        results = {}
        for name, source in self._sources.items():
            try:
                results[name] = await source.health_check()
            except Exception as e:
                logger.warning(f"Health check failed for {name}: {e}")
                results[name] = False
        return results

    async def search_all(
        self,
        query: str,
        max_per_source: int = 50,
        sources: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        categories: Optional[List[str]] = None,
        deduplicate: bool = True,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search across all (or specified) sources.

        Args:
            query: Search query string
            max_per_source: Maximum results per source
            sources: Specific sources to search (None = all)
            date_from: Filter by publication date (start)
            date_to: Filter by publication date (end)
            categories: Category filters (source-specific)
            deduplicate: Whether to deduplicate by DOI/arXiv ID

        Yields:
            PaperMetadata from all sources, deduplicated
        """
        # Get sources to search
        if sources:
            source_list = [
                self._sources[name.lower()]
                for name in sources
                if name.lower() in self._sources
            ]
        else:
            source_list = self.list_sources()

        if not source_list:
            logger.warning("No sources available for search")
            return

        # Track seen papers for deduplication
        seen_dois: Set[str] = set()
        seen_arxiv: Set[str] = set()
        seen_s2: Set[str] = set()
        seen_pubmed: Set[str] = set()

        # Search sources in priority order
        for source in source_list:
            try:
                logger.info(f"Searching {source.name} for: {query[:50]}...")

                async for paper in source.search(
                    query=query,
                    max_results=max_per_source,
                    date_from=date_from,
                    date_to=date_to,
                    categories=categories,
                ):
                    if deduplicate:
                        # Check for duplicates
                        is_dup = False

                        if paper.doi and paper.doi in seen_dois:
                            is_dup = True
                        elif paper.arxiv_id and paper.arxiv_id in seen_arxiv:
                            is_dup = True
                        elif paper.semantic_scholar_id and paper.semantic_scholar_id in seen_s2:
                            is_dup = True
                        elif paper.pubmed_id and paper.pubmed_id in seen_pubmed:
                            is_dup = True

                        if is_dup:
                            continue

                        # Track this paper
                        if paper.doi:
                            seen_dois.add(paper.doi)
                        if paper.arxiv_id:
                            seen_arxiv.add(paper.arxiv_id)
                        if paper.semantic_scholar_id:
                            seen_s2.add(paper.semantic_scholar_id)
                        if paper.pubmed_id:
                            seen_pubmed.add(paper.pubmed_id)

                    yield paper

            except Exception as e:
                logger.error(f"Error searching {source.name}: {e}")
                # Continue with next source on failure
                continue

    async def search_parallel(
        self,
        query: str,
        max_per_source: int = 50,
        sources: Optional[List[str]] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        timeout: float = 60.0,
    ) -> Dict[str, List[PaperMetadata]]:
        """
        Search all sources in parallel.

        Unlike search_all which yields results as they come,
        this returns all results grouped by source.

        Args:
            query: Search query string
            max_per_source: Maximum results per source
            sources: Specific sources to search (None = all)
            date_from: Filter by publication date (start)
            date_to: Filter by publication date (end)
            timeout: Maximum time to wait for all sources

        Returns:
            Dict mapping source name to list of papers
        """
        # Get sources to search
        if sources:
            source_list = [
                (name, self._sources[name.lower()])
                for name in sources
                if name.lower() in self._sources
            ]
        else:
            source_list = [(s.name, s) for s in self.list_sources()]

        if not source_list:
            return {}

        async def search_source(name: str, source: AcademicSource) -> tuple[str, List[PaperMetadata]]:
            papers = []
            try:
                async for paper in source.search(
                    query=query,
                    max_results=max_per_source,
                    date_from=date_from,
                    date_to=date_to,
                ):
                    papers.append(paper)
            except Exception as e:
                logger.error(f"Error searching {name}: {e}")
            return name, papers

        # Run all searches in parallel with timeout
        tasks = [
            search_source(name, source)
            for name, source in source_list
        ]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Search timed out after {timeout}s")
            results = []

        # Process results
        output: Dict[str, List[PaperMetadata]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Search task failed: {result}")
                continue
            name, papers = result
            output[name] = papers

        return output

    async def get_paper(
        self,
        paper_id: str,
        source_hint: Optional[str] = None,
    ) -> Optional[PaperMetadata]:
        """
        Get a paper by ID, optionally with source hint.

        Args:
            paper_id: Paper ID (may include source prefix like "arxiv:")
            source_hint: Hint about which source to check first

        Returns:
            PaperMetadata or None if not found
        """
        # Parse source from ID prefix
        source_name = source_hint
        actual_id = paper_id

        if ":" in paper_id:
            prefix, actual_id = paper_id.split(":", 1)
            prefix_map = {
                "arxiv": "arxiv",
                "s2": "semantic scholar",
                "pubmed": "pubmed",
                "core": "core",
            }
            source_name = prefix_map.get(prefix.lower(), source_hint)

        # Try specific source first
        if source_name and source_name.lower() in self._sources:
            source = self._sources[source_name.lower()]
            paper = await source.get_paper(actual_id)
            if paper:
                return paper

        # Fall back to all sources
        for source in self.list_sources():
            if source_name and source.name.lower() == source_name.lower():
                continue  # Already tried
            try:
                paper = await source.get_paper(paper_id)
                if paper:
                    return paper
            except Exception as e:
                logger.debug(f"Get paper failed for {source.name}: {e}")
                continue

        return None

    async def find_by_doi(self, doi: str) -> Optional[PaperMetadata]:
        """
        Find a paper by DOI.

        Args:
            doi: Digital Object Identifier

        Returns:
            PaperMetadata or None if not found
        """
        # Semantic Scholar is best for DOI lookup
        if "semantic scholar" in self._sources:
            s2 = self._sources["semantic scholar"]
            paper = await s2.get_paper(f"DOI:{doi}")
            if paper:
                return paper

        # Fall back to search
        async for paper in self.search_all(doi, max_per_source=5):
            if paper.doi == doi:
                return paper

        return None


# Global registry instance
_registry: Optional[SourceRegistry] = None


def get_source_registry() -> SourceRegistry:
    """
    Get the global source registry singleton.

    Returns:
        SourceRegistry instance (not initialized, call initialize_defaults first)
    """
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry


async def initialize_source_registry() -> SourceRegistry:
    """
    Initialize and return the global source registry.

    This is the recommended way to get the registry for first use.

    Returns:
        Initialized SourceRegistry instance
    """
    registry = get_source_registry()
    await registry.initialize_defaults()
    return registry
