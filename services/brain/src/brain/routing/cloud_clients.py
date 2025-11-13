# noqa: D401
"""Clients for cloud escalations (MCP and frontier models)."""

from __future__ import annotations

import json
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
            payload: Dict with 'query' key containing the user prompt.
                     Optional search parameters:
                     - search_domain_filter: List of domains to include/exclude
                     - search_recency_filter: "day", "week", "month", "year"
                     - return_images: bool - Include image results
                     - return_related_questions: bool - Include related questions

        Returns:
            Dict with 'output' key containing the response text
        """
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"} if self._api_key else {}

        # Extract prompt from payload (supports both "query" and "prompt" keys)
        prompt = payload.get("query") or payload.get("prompt", "")

        # Allow model override per-query (useful for task-specific model selection)
        model = payload.get("model", self._model)

        # Format as OpenAI chat completions request
        request_body = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        # Add Perplexity-specific search parameters if provided
        # These enhance search quality and control result sources
        search_params = {}
        if "search_domain_filter" in payload:
            search_params["search_domain_filter"] = payload["search_domain_filter"]
        if "search_recency_filter" in payload:
            search_params["search_recency_filter"] = payload["search_recency_filter"]
        if "return_images" in payload:
            search_params["return_images"] = payload["return_images"]
        if "return_related_questions" in payload:
            search_params["return_related_questions"] = payload["return_related_questions"]

        # Merge search parameters into request body
        if search_params:
            request_body.update(search_params)

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

    async def stream_query(self, payload: Dict[str, Any]):
        """Stream query responses for real-time progress.

        Args:
            payload: Same as query() method

        Yields:
            Dict chunks with partial content as they arrive

        Note:
            This is a basic streaming implementation for Perplexity API.
            Response format: {"delta": str, "done": bool}
        """
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"} if self._api_key else {}

        # Extract prompt and model
        prompt = payload.get("query") or payload.get("prompt", "")
        model = payload.get("model", self._model)

        # Build request body with streaming enabled
        request_body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True
        }

        # Add search parameters if present
        search_params = {}
        for key in ["search_domain_filter", "search_recency_filter", "return_images", "return_related_questions"]:
            if key in payload:
                search_params[key] = payload[key]
        if search_params:
            request_body.update(search_params)

        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=120) as client:
            async with client.stream("POST", "/chat/completions", json=request_body) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]  # Remove "data: " prefix
                        if data == "[DONE]":
                            yield {"delta": "", "done": True}
                            break
                        try:
                            chunk = json.loads(data)
                            content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if content:
                                yield {"delta": content, "done": False}
                        except json.JSONDecodeError:
                            continue


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
