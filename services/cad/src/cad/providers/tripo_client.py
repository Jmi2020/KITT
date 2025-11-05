"""Client for Tripo cloud mesh generation."""

from __future__ import annotations

from typing import Dict

from common.config import settings
from common.http import http_client


class TripoClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or settings.tripo_api_key
        if not self._api_key:
            raise RuntimeError("TRIPO_API_KEY not configured")
        self._base_url = (base_url or settings.tripo_api_base).rstrip("/")

    async def image_to_mesh(self, image_url: str) -> Dict[str, str]:
        async with http_client(base_url=self._base_url, api_key=self._api_key) as client:
            response = await client.post(
                "/v2/openapi/im2tripo",
                data={"model": "default", "quality": "draft", "image_url": image_url},
            )
            response.raise_for_status()
            return response.json()
