"""UniFi Access API client."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from common.config import settings


class UniFiAccessClient:
    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None) -> None:
        self._base_url = (base_url or settings.unifi_access_base_url or "").rstrip("/")
        self._token = token or settings.unifi_access_token
        if not self._base_url or not self._token:
            raise RuntimeError("UniFi Access credentials not configured")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(base_url=self._base_url, headers=headers, timeout=30) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}

    async def get_user(self, email: str) -> Optional[Dict[str, Any]]:
        data = await self._request("GET", f"/api/v1/users?filter={{\"email\":\"{email}\"}}")
        entries = data.get("data", [])
        return entries[0] if entries else None

    async def get_zone_presence(self, zone_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/api/v1/zones/{zone_id}/occupancy")

    async def unlock_door(self, door_id: str, user_id: str) -> Dict[str, Any]:
        payload = {"user_id": user_id, "unlock_method": "mobile_button"}
        return await self._request("POST", f"/api/v1/doors/{door_id}/unlock", json=payload)
