# noqa: D401
"""Local model client wrappers."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import get_routing_config


class OllamaClient:
    """Async client for Ollama generation."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        cfg = get_routing_config()
        self._base_url = base_url or cfg.ollama_host.rstrip("/")

    async def generate(self, prompt: str, model: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60) as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            return response.json()


__all__ = ["OllamaClient"]
