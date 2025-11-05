"""Client for Zoo CAD API."""

from __future__ import annotations

from typing import Any, Dict

from common.config import settings
from common.http import http_client


class ZooClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key or settings.zoo_api_key
        if not self._api_key:
            raise RuntimeError("ZOO_API_KEY not configured")
        self._base_url = (base_url or settings.zoo_api_base).rstrip("/")

    async def create_model(self, name: str, prompt: str, parameters: Dict[str, Any] | None = None) -> Dict[str, Any]:
        payload = {
            "name": name,
            "prompt": prompt,
            "language": "kcl",
        }
        if parameters:
            payload["parameters"] = parameters
        async with http_client(base_url=self._base_url, api_key=self._api_key) as client:
            response = await client.post("/projects/default/models", json=payload)
            response.raise_for_status()
            return response.json()

    async def poll_status(self, status_url: str) -> Dict[str, Any]:
        async with http_client(base_url=self._base_url, api_key=self._api_key) as client:
            response = await client.get(status_url)
            response.raise_for_status()
            return response.json()
