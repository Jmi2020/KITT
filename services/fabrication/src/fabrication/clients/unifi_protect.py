"""Minimal UniFi Protect client for snapshots."""

from __future__ import annotations

from typing import Optional

import httpx


class UniFiProtectClient:
    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._cookies: Optional[httpx.Cookies] = None

    async def _ensure_login(self) -> None:
        if self._cookies is not None:
            return
        async with httpx.AsyncClient(verify=self._verify_ssl) as client:
            response = await client.post(
                f"{self._base_url}/api/auth/login",
                json={"username": self._username, "password": self._password},
            )
            response.raise_for_status()
            self._cookies = response.cookies

    async def get_snapshot(self, camera_id: str) -> bytes:
        await self._ensure_login()
        assert self._cookies is not None
        async with httpx.AsyncClient(verify=self._verify_ssl, cookies=self._cookies) as client:
            response = await client.get(f"{self._base_url}/api/cameras/{camera_id}/snapshot")
            response.raise_for_status()
            return response.content
