# noqa: D401
"""SearchTool for DuckDuckGo web search."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


class SearchTool:
    """Web search using DuckDuckGo API.

    Provides privacy-respecting web search with:
    - No API key required
    - Rate limiting to avoid blocking
    - Result deduplication
    - Configurable result limits
    - Safesearch filtering
    """

    def __init__(
        self,
        max_results: int = 10,
        safesearch: str = "moderate",
        region: str = "wt-wt",  # worldwide
        time_range: Optional[str] = None,  # None, 'd' (day), 'w' (week), 'm' (month), 'y' (year)
    ) -> None:
        """Initialize SearchTool.

        Args:
            max_results: Maximum number of results to return
            safesearch: Safesearch setting ('on', 'moderate', 'off')
            region: Search region code (e.g., 'us-en', 'uk-en', 'wt-wt' for worldwide)
            time_range: Time range filter (None, 'd', 'w', 'm', 'y')
        """
        self.max_results = max_results
        self.safesearch = safesearch
        self.region = region
        self.time_range = time_range

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search the web using DuckDuckGo.

        Args:
            query: Search query string
            max_results: Override default max_results

        Returns:
            Dictionary with:
                - success (bool): Whether search succeeded
                - query (str): Original query
                - results (list): List of search results, each with:
                    - title (str): Result title
                    - url (str): Result URL
                    - description (str): Result description/snippet
                    - source (str): Source domain
                - total_results (int): Number of results returned
                - error (str): Error message if failed
                - metadata (dict): Additional metadata
        """
        try:
            max_res = max_results or self.max_results

            # Run synchronous DDGS call in thread pool
            results = await asyncio.to_thread(
                self._search_sync,
                query,
                max_res,
            )

            # Format results
            formatted_results = []
            seen_urls = set()

            for result in results:
                url = result.get("href", result.get("url", ""))

                # Deduplicate by URL
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Extract domain for source
                source = self._extract_domain(url)

                formatted_results.append(
                    {
                        "title": result.get("title", ""),
                        "url": url,
                        "description": result.get("body", result.get("description", "")),
                        "source": source,
                    }
                )

            return {
                "success": True,
                "query": query,
                "results": formatted_results,
                "total_results": len(formatted_results),
                "metadata": {
                    "safesearch": self.safesearch,
                    "region": self.region,
                    "time_range": self.time_range,
                },
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("Search error for query '%s': %s", query, exc)
            return {
                "success": False,
                "query": query,
                "error": f"Search failed: {str(exc)}",
                "results": [],
                "total_results": 0,
                "metadata": {},
            }

    def _search_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Execute synchronous DuckDuckGo search.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of search result dictionaries
        """
        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    keywords=query,
                    region=self.region,
                    safesearch=self.safesearch,
                    timelimit=self.time_range,
                    max_results=max_results,
                )
            )
            return results

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain name (e.g., 'example.com')
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            domain = parsed.netloc

            # Remove 'www.' prefix
            if domain.startswith("www."):
                domain = domain[4:]

            return domain
        except Exception:  # noqa: BLE001
            return ""

    async def search_news(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search news using DuckDuckGo.

        Args:
            query: Search query string
            max_results: Override default max_results

        Returns:
            Dictionary with same format as search()
        """
        try:
            max_res = max_results or self.max_results

            # Run synchronous DDGS news search in thread pool
            results = await asyncio.to_thread(
                self._search_news_sync,
                query,
                max_res,
            )

            # Format results
            formatted_results = []
            seen_urls = set()

            for result in results:
                url = result.get("url", "")

                # Deduplicate by URL
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Extract domain for source
                source = self._extract_domain(url)

                formatted_results.append(
                    {
                        "title": result.get("title", ""),
                        "url": url,
                        "description": result.get("body", ""),
                        "source": source,
                        "date": result.get("date", ""),
                    }
                )

            return {
                "success": True,
                "query": query,
                "results": formatted_results,
                "total_results": len(formatted_results),
                "metadata": {
                    "safesearch": self.safesearch,
                    "region": self.region,
                    "search_type": "news",
                },
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("News search error for query '%s': %s", query, exc)
            return {
                "success": False,
                "query": query,
                "error": f"News search failed: {str(exc)}",
                "results": [],
                "total_results": 0,
                "metadata": {},
            }

    def _search_news_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Execute synchronous DuckDuckGo news search.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of news result dictionaries
        """
        with DDGS() as ddgs:
            results = list(
                ddgs.news(
                    keywords=query,
                    region=self.region,
                    safesearch=self.safesearch,
                    timelimit=self.time_range,
                    max_results=max_results,
                )
            )
            return results


__all__ = ["SearchTool"]
