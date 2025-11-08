"""Brave Search API client."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class BraveSearchClient:
    """Client for Brave Search REST API (free tier + paid scale)."""

    def __init__(
        self,
        api_key: str,
        endpoint: str = "https://api.search.brave.com/res/v1/search",
        timeout: float = 10.0,
        safesearch: str = "moderate",
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._timeout = timeout
        self._safesearch = safesearch
        self._client = httpx.AsyncClient(timeout=timeout)

    async def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """Search Brave and normalize results."""
        headers = {"X-Subscription-Token": self._api_key}
        params = {
            "q": query,
            "url": "api",
            "count": max_results,
            "safesearch": self._safesearch,
        }

        try:
            resp = await self._client.get(self._endpoint, headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            logger.warning("Brave search failed for '%s': %s", query, exc)
            return {"success": False, "error": str(exc), "results": []}

        results = self._parse_results(payload, max_results)
        return {
            "success": True,
            "query": query,
            "results": results,
            "total_results": len(results),
            "metadata": {"provider": "brave"},
        }

    def _parse_results(self, payload: Dict[str, Any], max_results: int) -> List[Dict[str, str]]:
        docs: List[Dict[str, str]] = []
        web_results = payload.get("web", {}).get("results", [])

        for item in web_results[:max_results]:
            docs.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "source": item.get("source", ""),
                }
            )

        return docs

    async def close(self) -> None:
        await self._client.aclose()
