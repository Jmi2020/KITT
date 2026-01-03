"""
arXiv API client for paper harvesting.

arXiv provides free, unrestricted access to academic papers in physics,
mathematics, computer science, and related fields.

Rate Limit: 3 requests/second (no API key required)
API Docs: https://info.arxiv.org/help/api/index.html
"""

import asyncio
import xml.etree.ElementTree as ET
from typing import AsyncIterator, Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlencode
import logging
import re

from .base import (
    AcademicSource,
    PaperMetadata,
    RateLimitConfig,
    SourcePriority,
)

logger = logging.getLogger(__name__)

ARXIV_API_URL = "http://export.arxiv.org/api/query"
ARXIV_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Common arXiv categories for AI/ML research
ARXIV_AI_CATEGORIES = [
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "cs.NE",   # Neural and Evolutionary Computing
    "stat.ML", # Machine Learning (Statistics)
]


class ArxivSource(AcademicSource):
    """
    arXiv API client.

    Features:
    - No API key required
    - Rate limit: 3 req/sec
    - Supports category filtering (cs.AI, cs.LG, etc.)
    - PDF access via arxiv.org/pdf/{id}.pdf
    - Full text via arxiv.org/abs/{id} (HTML) or PDF

    Example usage:
        source = ArxivSource()
        async for paper in source.search("transformer attention mechanism", max_results=100):
            print(paper.title)
    """

    def __init__(self):
        super().__init__(
            rate_limit=RateLimitConfig(
                requests_per_second=3.0,
                burst_limit=3,
                retry_after_seconds=10.0,
            ),
            base_url=ARXIV_API_URL,
        )

    @property
    def name(self) -> str:
        return "arXiv"

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.ARXIV

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "KITT-Research-Harvester/1.0 (Academic Research; mailto:research@kitty.local)",
            "Accept": "application/atom+xml",
        }

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        categories: Optional[List[str]] = None,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search arXiv for papers.

        Uses arXiv query syntax:
        - all:query for full-text search
        - cat:cs.AI for category filtering
        - ti:query for title search
        - abs:query for abstract search

        Args:
            query: Search query string
            max_results: Maximum results to return
            date_from: Filter by publication date (start)
            date_to: Filter by publication date (end)
            categories: arXiv categories to filter (e.g., ["cs.AI", "cs.LG"])

        Yields:
            PaperMetadata for each matching paper
        """
        # Build query string
        search_query = f"all:{query}"

        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
            search_query = f"({search_query}) AND ({cat_query})"

        start = 0
        batch_size = min(100, max_results)  # arXiv max per request is 100
        yielded = 0

        while yielded < max_results:
            await self._acquire_rate_limit()

            params = {
                "search_query": search_query,
                "start": start,
                "max_results": min(batch_size, max_results - yielded),
                "sortBy": "lastUpdatedDate",
                "sortOrder": "descending",
            }

            try:
                client = await self._get_client()
                response = await client.get(
                    self.base_url,
                    params=params,
                )
                response.raise_for_status()

                # Parse Atom XML response
                root = ET.fromstring(response.text)
                entries = root.findall("atom:entry", ARXIV_ATOM_NS)

                if not entries:
                    logger.debug(f"arXiv search returned no more results at offset {start}")
                    break

                for entry in entries:
                    paper = self._parse_entry(entry)
                    if paper:
                        # Apply date filtering
                        if date_from and paper.published_date and paper.published_date < date_from:
                            continue
                        if date_to and paper.published_date and paper.published_date > date_to:
                            continue

                        yield paper
                        yielded += 1

                        if yielded >= max_results:
                            break

                start += len(entries)

                if len(entries) < batch_size:
                    break  # No more results available

            except ET.ParseError as e:
                logger.error(f"arXiv XML parse error: {e}")
                break
            except Exception as e:
                logger.error(f"arXiv search error: {e}")
                break

        logger.info(f"arXiv search yielded {yielded} papers for query: {query[:50]}...")

    def _parse_entry(self, entry: ET.Element) -> Optional[PaperMetadata]:
        """Parse arXiv Atom entry into PaperMetadata."""
        try:
            # Extract arXiv ID from URL
            id_elem = entry.find("atom:id", ARXIV_ATOM_NS)
            arxiv_url = id_elem.text if id_elem is not None else ""
            # URL format: http://arxiv.org/abs/2301.12345v1
            arxiv_id = arxiv_url.split("/abs/")[-1] if arxiv_url else ""

            # Strip version suffix for canonical ID
            arxiv_id_base = re.sub(r"v\d+$", "", arxiv_id)

            title_elem = entry.find("atom:title", ARXIV_ATOM_NS)
            title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""

            abstract_elem = entry.find("atom:summary", ARXIV_ATOM_NS)
            abstract = abstract_elem.text.strip() if abstract_elem is not None else ""

            # Authors
            authors = []
            for author in entry.findall("atom:author", ARXIV_ATOM_NS):
                name_elem = author.find("atom:name", ARXIV_ATOM_NS)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text)

            # Published date
            published_elem = entry.find("atom:published", ARXIV_ATOM_NS)
            published_date = None
            if published_elem is not None and published_elem.text:
                try:
                    published_date = datetime.fromisoformat(
                        published_elem.text.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            # Categories
            categories = []
            for cat in entry.findall("atom:category", ARXIV_ATOM_NS):
                term = cat.get("term")
                if term:
                    categories.append(term)

            # PDF URL
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id_base}.pdf"
            source_url = f"https://arxiv.org/abs/{arxiv_id_base}"

            # DOI (if available via link)
            doi = None
            for link in entry.findall("atom:link", ARXIV_ATOM_NS):
                if link.get("title") == "doi":
                    doi_href = link.get("href", "")
                    if "doi.org/" in doi_href:
                        doi = doi_href.split("doi.org/")[-1]
                    break

            return PaperMetadata(
                source_id=f"arxiv:{arxiv_id_base}",
                title=title,
                abstract=abstract,
                authors=authors,
                published_date=published_date,
                doi=doi,
                arxiv_id=arxiv_id_base,
                pdf_url=pdf_url,
                source_url=source_url,
                categories=categories,
                source="arxiv",
            )

        except Exception as e:
            logger.error(f"Failed to parse arXiv entry: {e}")
            return None

    async def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get paper by arXiv ID.

        Args:
            paper_id: arXiv ID (e.g., "2301.12345" or "arxiv:2301.12345")

        Returns:
            PaperMetadata or None if not found
        """
        # Strip prefix if present
        if paper_id.startswith("arxiv:"):
            paper_id = paper_id[6:]

        # Strip version suffix
        paper_id = re.sub(r"v\d+$", "", paper_id)

        await self._acquire_rate_limit()

        params = {"id_list": paper_id}

        try:
            client = await self._get_client()
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            entries = root.findall("atom:entry", ARXIV_ATOM_NS)

            if entries:
                return self._parse_entry(entries[0])

            return None

        except Exception as e:
            logger.error(f"arXiv get_paper error for {paper_id}: {e}")
            return None

    async def get_full_text(self, paper: PaperMetadata) -> Optional[str]:
        """
        Get full text for an arXiv paper.

        arXiv doesn't provide full text via API. Options:
        1. Download PDF and extract text (slow, requires PDF parsing)
        2. Use abstract only (fast, limited)

        For now, this returns None to indicate that the caller should
        download the PDF and extract text using a PDF parser.

        Args:
            paper: Paper metadata

        Returns:
            None (full text extraction requires PDF download)
        """
        # Full text extraction from arXiv requires PDF download
        # This is handled by the pipeline with caching
        return None

    async def search_by_author(
        self,
        author_name: str,
        max_results: int = 50,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search for papers by a specific author.

        Args:
            author_name: Author name to search
            max_results: Maximum results

        Yields:
            PaperMetadata for matching papers
        """
        query = f'au:"{author_name}"'
        async for paper in self.search(query, max_results=max_results):
            yield paper

    async def get_recent_papers(
        self,
        categories: List[str],
        max_results: int = 100,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Get recent papers in specified categories.

        Args:
            categories: arXiv categories (e.g., ["cs.AI", "cs.LG"])
            max_results: Maximum results

        Yields:
            PaperMetadata for recent papers
        """
        # Use wildcard search with category filter
        async for paper in self.search(
            "*",
            max_results=max_results,
            categories=categories,
        ):
            yield paper
