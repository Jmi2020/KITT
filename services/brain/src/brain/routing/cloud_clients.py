# noqa: D401
"""Clients for cloud escalations (MCP and frontier models)."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


class MCPClient:
    """Minimal HTTP client for MCP-based services (e.g., Perplexity)."""

    def __init__(self, base_url: str, api_key: Optional[str], model: str = "sonar") -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Query with OpenAI-compatible chat completions format.

        Args:
            payload: Dict with 'query' key containing the user prompt

        Returns:
            Dict with 'output' key containing the response text
        """
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"} if self._api_key else {}

        # Extract prompt from payload (supports both "query" and "prompt" keys)
        prompt = payload.get("query") or payload.get("prompt", "")

        # Format as OpenAI chat completions request
        request_body = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        async with httpx.AsyncClient(
            base_url=self._base_url, headers=headers, timeout=60
        ) as client:
            response = await client.post("/chat/completions", json=request_body)
            response.raise_for_status()
            result = response.json()

            # Extract content from OpenAI-style response
            try:
                output = result["choices"][0]["message"]["content"]
                return {"output": output, "raw": result}
            except (KeyError, IndexError):
                return {"output": "", "raw": result}


class FrontierClient:
    """Generic frontier client (OpenAI, Anthropic, Gemini)."""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def generate(self, prompt: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=headers, timeout=60
        ) as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": "KITTY orchestration assistant."},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
            return response.json()


__all__ = ["MCPClient", "FrontierClient"]
