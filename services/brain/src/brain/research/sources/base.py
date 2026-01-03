"""
Abstract base class for academic paper sources.

Provides:
- Async rate limiting with token bucket algorithm
- Pagination via async iterators
- PDF download with retries
- Error handling and fallback
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, List, Dict, Any
from datetime import datetime
from enum import IntEnum
import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)


class SourcePriority(IntEnum):
    """Priority ordering for source fallback.

    Lower values = higher priority (tried first).
    """
    ARXIV = 1        # Primary - free, comprehensive for CS/ML
    SEMANTIC_SCHOLAR = 2  # Secondary - rich metadata, citations
    PUBMED = 3       # Tertiary - biomedical focus
    CORE = 4         # Quaternary - broad open access


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for an academic source."""
    requests_per_second: float
    burst_limit: int = 1
    retry_after_seconds: float = 60.0


@dataclass
class PaperMetadata:
    """Standardized paper metadata across all sources.

    This model provides a common interface for papers regardless of
    which academic source they were harvested from.
    """
    source_id: str           # Source-specific ID (e.g., "arxiv:2301.12345")
    title: str
    abstract: str
    authors: List[str]
    published_date: Optional[datetime] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    pubmed_id: Optional[str] = None
    core_id: Optional[str] = None
    pdf_url: Optional[str] = None
    source_url: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    citations_count: int = 0
    source: str = ""  # Source name (arxiv, semantic_scholar, pubmed, core)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_id": self.source_id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "semantic_scholar_id": self.semantic_scholar_id,
            "pubmed_id": self.pubmed_id,
            "core_id": self.core_id,
            "pdf_url": self.pdf_url,
            "source_url": self.source_url,
            "categories": self.categories,
            "citations_count": self.citations_count,
            "source": self.source,
        }


class AcademicSource(ABC):
    """
    Abstract base class for academic paper sources.

    Implements:
    - Async rate limiting with token bucket algorithm
    - Pagination via async iterators
    - PDF download with retries
    - Error handling and fallback

    Subclasses must implement:
    - name: Property returning the source name
    - priority: Property returning SourcePriority
    - search: Async generator yielding PaperMetadata
    - get_paper: Retrieve a single paper by ID
    - get_full_text: Attempt to retrieve full paper text
    """

    def __init__(
        self,
        rate_limit: RateLimitConfig,
        api_key: Optional[str] = None,
        base_url: str = ""
    ):
        self.rate_limit = rate_limit
        self.api_key = api_key
        self.base_url = base_url

        # Token bucket for rate limiting
        self._tokens = float(rate_limit.burst_limit)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

        # HTTP client (created lazily)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers=self._get_default_headers(),
            )
        return self._client

    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests. Override in subclasses if needed."""
        return {
            "User-Agent": "KITT-Research-Harvester/1.0 (Academic Research)",
            "Accept": "application/json",
        }

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _acquire_rate_limit(self):
        """Acquire a rate limit token using token bucket algorithm."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill

            # Refill tokens based on elapsed time
            self._tokens = min(
                float(self.rate_limit.burst_limit),
                self._tokens + elapsed * self.rate_limit.requests_per_second
            )
            self._last_refill = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.rate_limit.requests_per_second
                logger.debug(f"{self.name}: Rate limited, waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1

    @property
    @abstractmethod
    def name(self) -> str:
        """Source name for logging and identification."""
        pass

    @property
    @abstractmethod
    def priority(self) -> SourcePriority:
        """Priority for source ordering in fallback chains."""
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        categories: Optional[List[str]] = None,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search for papers matching query.

        Yields PaperMetadata for each result, handling pagination internally.

        Args:
            query: Search query string
            max_results: Maximum number of results to return
            date_from: Filter papers published after this date
            date_to: Filter papers published before this date
            categories: Filter by category codes (source-specific)

        Yields:
            PaperMetadata for each matching paper
        """
        pass

    @abstractmethod
    async def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get full metadata for a specific paper by ID.

        Args:
            paper_id: Source-specific paper ID

        Returns:
            PaperMetadata or None if not found
        """
        pass

    @abstractmethod
    async def get_full_text(self, paper: PaperMetadata) -> Optional[str]:
        """
        Attempt to retrieve full text of paper.

        This may involve downloading and parsing a PDF, or accessing
        an API endpoint that provides full text.

        Args:
            paper: Paper metadata

        Returns:
            Full text string or None if unavailable
        """
        pass

    async def download_pdf(
        self,
        paper: PaperMetadata,
        output_path: str,
        max_retries: int = 3
    ) -> bool:
        """
        Download PDF for paper with retries.

        Args:
            paper: Paper metadata (must have pdf_url)
            output_path: Local path to save PDF
            max_retries: Maximum retry attempts

        Returns:
            True if successful, False otherwise
        """
        if not paper.pdf_url:
            logger.warning(f"No PDF URL for paper {paper.source_id}")
            return False

        for attempt in range(max_retries):
            try:
                await self._acquire_rate_limit()

                client = await self._get_client()
                response = await client.get(paper.pdf_url)
                response.raise_for_status()

                # Check content type
                content_type = response.headers.get("content-type", "")
                if "pdf" not in content_type.lower() and not paper.pdf_url.endswith(".pdf"):
                    logger.warning(
                        f"Unexpected content type for {paper.source_id}: {content_type}"
                    )

                with open(output_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"Downloaded PDF for {paper.source_id} to {output_path}")
                return True

            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"PDF download attempt {attempt+1} failed for {paper.source_id}: "
                    f"HTTP {e.response.status_code}"
                )
            except Exception as e:
                logger.warning(
                    f"PDF download attempt {attempt+1} failed for {paper.source_id}: {e}"
                )

            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return False

    async def health_check(self) -> bool:
        """
        Check if the source is available and responding.

        Returns:
            True if healthy, False otherwise
        """
        try:
            await self._acquire_rate_limit()
            client = await self._get_client()
            response = await client.get(self.base_url)
            return response.status_code < 500
        except Exception as e:
            logger.warning(f"{self.name} health check failed: {e}")
            return False
