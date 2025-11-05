# noqa: D401
"""Placeholder client for MLX-based local models."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .config import get_routing_config


class MLXLocalClient:
    """Call out to an MLX HTTP bridge (or return stub if unavailable)."""

    def __init__(self, endpoint: Optional[str] = None) -> None:
        cfg = get_routing_config()
        self._endpoint = endpoint or cfg.mlx_endpoint.rstrip("/")

    async def generate(self, prompt: str, model: str) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self._endpoint, timeout=60) as client:
                response = await client.post(
                    "/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                    },
                )
                response.raise_for_status()
                return response.json()
        except httpx.TransportError:
            # Fallback stub to keep development loop running without MLX bridge
            return {"output": f"[mlx-unavailable] {prompt[:200]}"}


__all__ = ["MLXLocalClient"]
