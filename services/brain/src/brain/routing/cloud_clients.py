# noqa: D401
"""Clients for cloud escalations (MCP and frontier models)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class MCPClient:
    """Minimal HTTP client for MCP-based services (e.g., Perplexity)."""

    def __init__(self, base_url: str, api_key: Optional[str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=60) as client:
            response = await client.post("/query", json=payload)
            response.raise_for_status()
            return response.json()


class FrontierClient:
    """Generic frontier client (OpenAI, Anthropic, Gemini)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def generate(self, prompt: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=60) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "system", "content": "JarvisV3 orchestration assistant."}, {"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            return response.json()


__all__ = ["MCPClient", "FrontierClient"]
