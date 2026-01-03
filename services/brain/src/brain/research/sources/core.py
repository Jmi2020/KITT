"""
CORE API client for paper harvesting.

CORE aggregates open access research papers from repositories worldwide.
It provides one of the largest collections of open access articles.

Rate Limit: Free tier allows limited requests, API key recommended
API Docs: https://core.ac.uk/documentation/api
"""

import asyncio
from typing import AsyncIterator, Optional, List, Dict, Any
from datetime import datetime
import logging
import os

from .base import (
    AcademicSource,
    PaperMetadata,
    RateLimitConfig,
    SourcePriority,
)

logger = logging.getLogger(__name__)

CORE_API_URL = "https://api.core.ac.uk/v3"


class CORESource(AcademicSource):
    """
    CORE API client for open access research papers.

    Features:
    - Large collection of open access papers
    - Full text available for many papers
    - Aggregates from multiple repositories
    - Free API with key for higher limits

    Example usage:
        source = CORESource(api_key=os.getenv("CORE_API_KEY"))
        async for paper in source.search("machine learning", max_results=100):
            print(f"{paper.title} - {paper.source_url}")
    """

    def __init__(self, api_key: Optional[str] = None):
        # CORE recommends 1 request per second for free tier
        rate = 2.0 if api_key else 0.5
        burst = 5 if api_key else 2

        super().__init__(
            rate_limit=RateLimitConfig(
                requests_per_second=rate,
                burst_limit=burst,
                retry_after_seconds=60.0,
            ),
            api_key=api_key or os.getenv("CORE_API_KEY"),
            base_url=CORE_API_URL,
        )

    @property
    def name(self) -> str:
        return "CORE"

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.CORE

    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": "KITT-Research-Harvester/1.0 (Academic Research)",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
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
        Search CORE for papers.

        Args:
            query: Search query string
            max_results: Maximum results to return
            date_from: Filter by publication date (start)
            date_to: Filter by publication date (end)
            categories: Subject categories to filter by

        Yields:
            PaperMetadata for each matching paper
        """
        offset = 0
        limit = min(100, max_results)  # CORE max per request
        yielded = 0

        # Build query with filters
        search_query = query
        if date_from or date_to:
            year_filter = self._build_year_filter(date_from, date_to)
            if year_filter:
                search_query = f"({query}) AND {year_filter}"

        while yielded < max_results:
            await self._acquire_rate_limit()

            # CORE v3 uses POST for search
            body = {
                "q": search_query,
                "offset": offset,
                "limit": min(limit, max_results - yielded),
                "scroll": False,
            }

            try:
                client = await self._get_client()
                response = await client.post(
                    f"{self.base_url}/search/works",
                    json=body,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"CORE rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue

                # Handle auth errors
                if response.status_code == 401:
                    logger.error("CORE API key invalid or missing")
                    break

                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    logger.debug(f"CORE search returned no more results at offset {offset}")
                    break

                for result in results:
                    paper = self._parse_work(result)
                    if paper:
                        yield paper
                        yielded += 1

                        if yielded >= max_results:
                            break

                offset += len(results)

                # Check if more results available
                total = data.get("totalHits", 0)
                if offset >= total or len(results) < limit:
                    break

            except Exception as e:
                logger.error(f"CORE search error: {e}")
                break

        logger.info(f"CORE search yielded {yielded} papers for query: {query[:50]}...")

    def _build_year_filter(
        self,
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> Optional[str]:
        """Build CORE year range filter."""
        if not date_from and not date_to:
            return None

        if date_from and date_to:
            return f"yearPublished>={date_from.year} AND yearPublished<={date_to.year}"
        elif date_from:
            return f"yearPublished>={date_from.year}"
        elif date_to:
            return f"yearPublished<={date_to.year}"
        return None

    def _parse_work(self, data: Dict[str, Any]) -> Optional[PaperMetadata]:
        """Parse CORE API response into PaperMetadata."""
        try:
            core_id = str(data.get("id", ""))
            if not core_id:
                return None

            title = data.get("title", "")
            if not title:
                return None

            # Abstract
            abstract = data.get("abstract", "") or ""

            # Authors
            authors = []
            for author in data.get("authors", []):
                name = author.get("name", "")
                if name:
                    authors.append(name)

            # Published date
            pub_date = None
            year = data.get("yearPublished")
            if year:
                try:
                    pub_date = datetime(int(year), 1, 1)
                except (ValueError, TypeError):
                    pass

            # DOI
            doi = data.get("doi")

            # Extract other IDs from identifiers
            arxiv_id = None
            identifiers = data.get("identifiers", [])
            for ident in identifiers:
                if isinstance(ident, str) and "arxiv" in ident.lower():
                    # Extract arxiv ID from URL or identifier
                    import re
                    match = re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", ident)
                    if match:
                        arxiv_id = match.group(1)
                        break

            # PDF URL
            pdf_url = None
            download_url = data.get("downloadUrl")
            if download_url:
                pdf_url = download_url
            else:
                # Try to get from links
                links = data.get("links", [])
                for link in links:
                    if isinstance(link, dict):
                        link_type = link.get("type", "")
                        if "pdf" in link_type.lower():
                            pdf_url = link.get("url")
                            break

            # Source URL
            source_url = data.get("sourceFulltextUrls", [""])[0] if data.get("sourceFulltextUrls") else ""
            if not source_url:
                source_url = f"https://core.ac.uk/works/{core_id}"

            # Subjects/categories
            categories = data.get("subjects", [])
            if not categories:
                # Try fieldOfStudy
                field = data.get("fieldOfStudy")
                if field:
                    categories = [field]

            return PaperMetadata(
                source_id=f"core:{core_id}",
                title=title,
                abstract=abstract,
                authors=authors,
                published_date=pub_date,
                doi=doi,
                arxiv_id=arxiv_id,
                core_id=core_id,
                pdf_url=pdf_url,
                source_url=source_url,
                categories=categories[:10] if categories else [],
                source="core",
            )

        except Exception as e:
            logger.error(f"Failed to parse CORE work: {e}")
            return None

    async def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get paper by CORE ID.

        Args:
            paper_id: CORE ID (e.g., "123456789" or "core:123456789")

        Returns:
            PaperMetadata or None if not found
        """
        # Strip prefix if present
        if paper_id.startswith("core:"):
            paper_id = paper_id[5:]

        await self._acquire_rate_limit()

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/works/{paper_id}",
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return self._parse_work(response.json())

        except Exception as e:
            logger.error(f"CORE get_paper error for {paper_id}: {e}")
            return None

    async def get_full_text(self, paper: PaperMetadata) -> Optional[str]:
        """
        Get full text for a CORE paper.

        CORE provides full text for many papers via the API.

        Args:
            paper: Paper metadata

        Returns:
            Full text string or None if unavailable
        """
        if not paper.core_id:
            return None

        await self._acquire_rate_limit()

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/works/{paper.core_id}",
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            data = response.json()

            # CORE sometimes includes full text in the response
            full_text = data.get("fullText")
            if full_text:
                return full_text

            # Or it might be in fulltextIdentifier
            fulltext_url = data.get("downloadUrl")
            if fulltext_url and fulltext_url.endswith(".txt"):
                await self._acquire_rate_limit()
                text_response = await client.get(fulltext_url)
                if text_response.status_code == 200:
                    return text_response.text

            return None

        except Exception as e:
            logger.debug(f"CORE full text retrieval failed for {paper.core_id}: {e}")
            return None

    async def get_similar_papers(
        self,
        paper_id: str,
        max_results: int = 20,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Get papers similar to the given paper.

        Args:
            paper_id: CORE paper ID
            max_results: Maximum similar papers to return

        Yields:
            PaperMetadata for similar papers
        """
        if paper_id.startswith("core:"):
            paper_id = paper_id[5:]

        await self._acquire_rate_limit()

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/works/{paper_id}/similar",
                params={"limit": max_results},
            )

            if response.status_code == 404:
                return

            response.raise_for_status()
            data = response.json()

            for result in data.get("results", []):
                paper = self._parse_work(result)
                if paper:
                    yield paper

        except Exception as e:
            logger.error(f"CORE similar papers error: {e}")

    async def search_by_repository(
        self,
        repository_id: str,
        max_results: int = 100,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search for papers from a specific repository.

        Args:
            repository_id: CORE repository ID
            max_results: Maximum results to return

        Yields:
            PaperMetadata for papers in the repository
        """
        query = f"repositories.id:{repository_id}"

        async for paper in self.search(query, max_results=max_results):
            yield paper
