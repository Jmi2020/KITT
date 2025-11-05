# noqa: D401
"""Home Assistant REST client."""

from __future__ import annotations

from typing import Any, Dict, Optional

from common.credentials import HomeAssistantCredentials
from common.http import http_client


class HomeAssistantClient:
    """Thin asynchronous wrapper around Home Assistant REST API."""

    def __init__(self, credentials: HomeAssistantCredentials) -> None:
        self._credentials = credentials

    async def call_service(self, domain: str, service: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call a Home Assistant domain service."""

        endpoint = f"/api/services/{domain}/{service}"
        async with http_client(
            base_url=self._credentials.base_url, bearer_token=self._credentials.token.get_secret_value()
        ) as client:
            response = await client.post(endpoint, json=data or {})
            response.raise_for_status()
            return response.json()

    async def get_states(self) -> Dict[str, Any]:
        """Return entity states."""

        async with http_client(
            base_url=self._credentials.base_url, bearer_token=self._credentials.token.get_secret_value()
        ) as client:
            response = await client.get("/api/states")
            response.raise_for_status()
            return {item["entity_id"]: item for item in response.json()}


__all__ = ["HomeAssistantClient"]
