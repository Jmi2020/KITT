"""Layered web search client used by the Research MCP server."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from duckduckgo_search import DDGS

from .providers.brave import BraveSearchClient

logger = logging.getLogger(__name__)


class SearchTool:
    """Cascade search helper (SearXNG → Brave → DuckDuckGo)."""

    def __init__(
        self,
        max_results: int = 10,
        safesearch: str = "moderate",
        region: str = "wt-wt",
        time_range: Optional[str] = None,
        searxng_url: Optional[str] = None,
        brave_api_key: Optional[str] = None,
        brave_endpoint: Optional[str] = None,
    ) -> None:
        self.max_results = max_results
        self.safesearch = safesearch
        self.region = region
        self.time_range = time_range

        self._searxng_url = searxng_url or os.getenv("SEARXNG_BASE_URL")
        self._brave_api_key = brave_api_key or os.getenv("BRAVE_SEARCH_API_KEY")
        self._brave_endpoint = (
            brave_endpoint
            or os.getenv("BRAVE_SEARCH_ENDPOINT")
            or "https://api.search.brave.com/res/v1/web/search"
        )

        self._gateway_host = os.getenv("DOCKER_HOST_GATEWAY", "host.docker.internal")
        self._inside_container = bool(os.getenv("KITTY_IN_CONTAINER") == "1" or os.path.exists("/.dockerenv"))

        if self._searxng_url:
            self._searxng_url = self._normalize_local_url(
                self._searxng_url,
                inside_container=self._inside_container,
                gateway_host=self._gateway_host,
            )

        self._brave_client: Optional[BraveSearchClient] = None

    async def search(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        """Search the web, preferring self-hosted/free options."""
        target = max_results or self.max_results

        searx = await self._search_searx(query, target)
        if searx:
            return searx

        brave = await self._search_brave(query, target)
        if brave:
            return brave

        return await self._search_duckduckgo(query, target)

    async def _search_searx(self, query: str, max_results: int) -> Optional[Dict[str, Any]]:
        if not self._searxng_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{self._searxng_url.rstrip('/')}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "language": "en",
                        "categories": "general",
                        "safesearch": 1 if self.safesearch != "off" else 0,
                        "pageno": 1,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.debug("SearXNG unavailable: %s", exc)
            return None

        hits = []
        seen = set()
        for row in payload.get("results", [])[:max_results]:
            url = row.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            hits.append(
                {
                    "title": row.get("title", ""),
                    "url": url,
                    "description": row.get("content", ""),
                    "source": self._extract_domain(url),
                }
            )

        if not hits:
            return None

        return {
            "success": True,
            "query": query,
            "results": hits,
            "total_results": len(hits),
            "metadata": {"provider": "searxng"},
        }

    async def _search_brave(self, query: str, max_results: int) -> Optional[Dict[str, Any]]:
        if not self._brave_api_key:
            return None

        if not self._brave_client:
            self._brave_client = BraveSearchClient(
                api_key=self._brave_api_key,
                endpoint=self._brave_endpoint,
                safesearch=self.safesearch,
            )

        result = await self._brave_client.search(query, max_results=max_results)
        if not result or not result.get("success") or not result.get("results"):
            return None
        return result

    async def _search_duckduckgo(self, query: str, max_results: int) -> Dict[str, Any]:
        try:
            rows = await asyncio.to_thread(self._ddg_sync, query, max_results)
        except Exception as exc:  # noqa: BLE001
            logger.error("DuckDuckGo error for '%s': %s", query, exc)
            return {
                "success": False,
                "query": query,
                "error": str(exc),
                "results": [],
                "total_results": 0,
                "metadata": {},
            }

        hits = []
        seen = set()
        for row in rows:
            url = row.get("href", row.get("url", ""))
            if not url or url in seen:
                continue
            seen.add(url)
            hits.append(
                {
                    "title": row.get("title", ""),
                    "url": url,
                    "description": row.get("body", row.get("description", "")),
                    "source": self._extract_domain(url),
                }
            )

        return {
            "success": True,
            "query": query,
            "results": hits,
            "total_results": len(hits),
            "metadata": {"provider": "duckduckgo"},
        }

    def _ddg_sync(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        with DDGS() as ddgs:
            return list(
                ddgs.text(
                    keywords=query,
                    region=self.region,
                    safesearch=self.safesearch,
                    timelimit=self.time_range,
                    max_results=max_results,
                )
            )

    def _extract_domain(self, url: str) -> str:
        try:
            domain = urlparse(url).netloc
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _normalize_local_url(
        url: Optional[str],
        *,
        inside_container: bool,
        gateway_host: str,
    ) -> Optional[str]:
        if not url or not inside_container:
            return url

        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname not in {"localhost", "127.0.0.1"}:
            return url

        port = parsed.port
        netloc = f"{gateway_host}:{port}" if port else gateway_host
        new_parsed = parsed._replace(netloc=netloc)
        return urlunparse(new_parsed)


__all__ = ["SearchTool"]
