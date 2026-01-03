"""
Semantic Scholar API client for paper harvesting.

Semantic Scholar provides rich metadata including citations, references,
and related papers. Excellent for building citation graphs.

Rate Limit: 100 requests per 5 minutes (free tier without API key)
           1000 requests per 5 minutes (with free API key)
API Docs: https://api.semanticscholar.org/api-docs/
"""

import os
from typing import AsyncIterator, Optional, List, Dict, Any
from datetime import datetime
import logging

from .base import (
    AcademicSource,
    PaperMetadata,
    RateLimitConfig,
    SourcePriority,
)

logger = logging.getLogger(__name__)

S2_API_URL = "https://api.semanticscholar.org/graph/v1"
S2_PAPER_FIELDS = (
    "paperId,title,abstract,authors,year,citationCount,"
    "openAccessPdf,externalIds,venue,publicationDate"
)


class SemanticScholarSource(AcademicSource):
    """
    Semantic Scholar API client.

    Features:
    - Rich citation metadata
    - Connected papers for graph building
    - Free tier: 100 req/5min without key, 1000/5min with key
    - Author and paper relationship data

    Example usage:
        source = SemanticScholarSource(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
        async for paper in source.search("attention mechanism", max_results=50):
            print(f"{paper.title} - {paper.citations_count} citations")
    """

    def __init__(self, api_key: Optional[str] = None):
        # Rate limit depends on whether API key is provided
        # Without key: 100/5min = 0.33/sec
        # With key: 1000/5min = 3.33/sec
        rate = 3.0 if api_key else 0.33
        burst = 10 if api_key else 3

        super().__init__(
            rate_limit=RateLimitConfig(
                requests_per_second=rate,
                burst_limit=burst,
                retry_after_seconds=60.0,
            ),
            api_key=api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
            base_url=S2_API_URL,
        )

    @property
    def name(self) -> str:
        return "Semantic Scholar"

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.SEMANTIC_SCHOLAR

    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "KITT-Research-Harvester/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        categories: Optional[List[str]] = None,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search Semantic Scholar for papers.

        Args:
            query: Search query string
            max_results: Maximum results to return
            date_from: Filter by publication date (start year)
            date_to: Filter by publication date (end year)
            categories: Not used (S2 doesn't support category filtering)

        Yields:
            PaperMetadata for each matching paper
        """
        offset = 0
        limit = min(100, max_results)  # S2 max per request
        yielded = 0

        while yielded < max_results:
            await self._acquire_rate_limit()

            params: Dict[str, Any] = {
                "query": query,
                "offset": offset,
                "limit": min(limit, max_results - yielded),
                "fields": S2_PAPER_FIELDS,
            }

            # Add year range filter
            year_range = self._build_year_range(date_from, date_to)
            if year_range:
                params["year"] = year_range

            try:
                client = await self._get_client()
                response = await client.get(
                    f"{self.base_url}/paper/search",
                    params=params,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"S2 rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()

                papers = data.get("data", [])
                if not papers:
                    logger.debug(f"S2 search returned no more results at offset {offset}")
                    break

                for paper_data in papers:
                    paper = self._parse_paper(paper_data)
                    if paper:
                        yield paper
                        yielded += 1

                        if yielded >= max_results:
                            break

                offset += len(papers)

                # Check if there are more results
                total = data.get("total", 0)
                if offset >= total or len(papers) < limit:
                    break

            except Exception as e:
                logger.error(f"S2 search error: {e}")
                break

        logger.info(f"S2 search yielded {yielded} papers for query: {query[:50]}...")

    def _build_year_range(
        self,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Optional[str]:
        """Build S2 year range filter string."""
        if not date_from and not date_to:
            return None

        from_year = date_from.year if date_from else ""
        to_year = date_to.year if date_to else ""

        if from_year and to_year:
            return f"{from_year}-{to_year}"
        elif from_year:
            return f"{from_year}-"
        elif to_year:
            return f"-{to_year}"
        return None

    def _parse_paper(self, data: Dict[str, Any]) -> Optional[PaperMetadata]:
        """Parse S2 API response into PaperMetadata."""
        try:
            s2_id = data.get("paperId", "")
            if not s2_id:
                return None

            # Extract external IDs
            external_ids = data.get("externalIds") or {}
            arxiv_id = external_ids.get("ArXiv")
            doi = external_ids.get("DOI")
            pubmed_id = external_ids.get("PubMed")

            # Authors
            authors = [
                a.get("name", "") for a in data.get("authors", [])
                if a.get("name")
            ]

            # Published date
            pub_date_str = data.get("publicationDate")
            published_date = None
            if pub_date_str:
                try:
                    published_date = datetime.fromisoformat(pub_date_str)
                except ValueError:
                    # Try year only
                    year = data.get("year")
                    if year:
                        published_date = datetime(year, 1, 1)
            elif data.get("year"):
                published_date = datetime(data["year"], 1, 1)

            # PDF URL
            pdf_info = data.get("openAccessPdf") or {}
            pdf_url = pdf_info.get("url")

            # Source URL
            source_url = f"https://www.semanticscholar.org/paper/{s2_id}"

            return PaperMetadata(
                source_id=f"s2:{s2_id}",
                title=data.get("title", ""),
                abstract=data.get("abstract", "") or "",
                authors=authors,
                published_date=published_date,
                doi=doi,
                arxiv_id=arxiv_id,
                semantic_scholar_id=s2_id,
                pubmed_id=pubmed_id,
                pdf_url=pdf_url,
                source_url=source_url,
                citations_count=data.get("citationCount", 0) or 0,
                source="semantic_scholar",
            )

        except Exception as e:
            logger.error(f"Failed to parse S2 paper: {e}")
            return None

    async def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get paper by Semantic Scholar ID.

        Args:
            paper_id: S2 paper ID (e.g., "s2:abc123..." or just "abc123...")

        Returns:
            PaperMetadata or None if not found
        """
        # Strip prefix if present
        if paper_id.startswith("s2:"):
            paper_id = paper_id[3:]

        await self._acquire_rate_limit()

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/paper/{paper_id}",
                params={"fields": S2_PAPER_FIELDS},
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return self._parse_paper(response.json())

        except Exception as e:
            logger.error(f"S2 get_paper error for {paper_id}: {e}")
            return None

    async def get_full_text(self, paper: PaperMetadata) -> Optional[str]:
        """
        S2 doesn't provide full text directly.

        Returns None to indicate PDF download is needed.
        """
        return None

    async def get_citations(
        self,
        paper_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Get papers that cite the given paper.

        Args:
            paper_id: S2 paper ID
            max_results: Maximum citations to return

        Yields:
            PaperMetadata for citing papers
        """
        if paper_id.startswith("s2:"):
            paper_id = paper_id[3:]

        offset = 0
        limit = min(100, max_results)
        yielded = 0

        while yielded < max_results:
            await self._acquire_rate_limit()

            try:
                client = await self._get_client()
                response = await client.get(
                    f"{self.base_url}/paper/{paper_id}/citations",
                    params={
                        "offset": offset,
                        "limit": min(limit, max_results - yielded),
                        "fields": "citingPaper." + S2_PAPER_FIELDS.replace(",", ",citingPaper."),
                    },
                )

                if response.status_code == 429:
                    await asyncio.sleep(60)
                    continue

                response.raise_for_status()
                data = response.json()

                citations = data.get("data", [])
                if not citations:
                    break

                for citation in citations:
                    citing_paper = citation.get("citingPaper", {})
                    paper = self._parse_paper(citing_paper)
                    if paper:
                        yield paper
                        yielded += 1

                        if yielded >= max_results:
                            break

                offset += len(citations)

            except Exception as e:
                logger.error(f"S2 get_citations error: {e}")
                break

    async def get_references(
        self,
        paper_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Get papers that are cited by the given paper.

        Args:
            paper_id: S2 paper ID
            max_results: Maximum references to return

        Yields:
            PaperMetadata for referenced papers
        """
        if paper_id.startswith("s2:"):
            paper_id = paper_id[3:]

        offset = 0
        limit = min(100, max_results)
        yielded = 0

        while yielded < max_results:
            await self._acquire_rate_limit()

            try:
                client = await self._get_client()
                response = await client.get(
                    f"{self.base_url}/paper/{paper_id}/references",
                    params={
                        "offset": offset,
                        "limit": min(limit, max_results - yielded),
                        "fields": "citedPaper." + S2_PAPER_FIELDS.replace(",", ",citedPaper."),
                    },
                )

                if response.status_code == 429:
                    await asyncio.sleep(60)
                    continue

                response.raise_for_status()
                data = response.json()

                references = data.get("data", [])
                if not references:
                    break

                for reference in references:
                    cited_paper = reference.get("citedPaper", {})
                    paper = self._parse_paper(cited_paper)
                    if paper:
                        yield paper
                        yielded += 1

                        if yielded >= max_results:
                            break

                offset += len(references)

            except Exception as e:
                logger.error(f"S2 get_references error: {e}")
                break


# Required for async iteration in _build_year_range
import asyncio
