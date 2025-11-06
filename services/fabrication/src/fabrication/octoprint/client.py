"""OctoPrint HTTP client for heat/upload/start sequences."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import httpx


class OctoPrintClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Api-Key": api_key}

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=60
        ) as client:
            response = await client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

    async def upload_file(
        self, gcode_path: Path, select: bool = True
    ) -> Dict[str, Any]:
        files = {
            "file": (gcode_path.name, gcode_path.read_bytes(), "application/gcode")
        }
        data = {"select": str(select).lower(), "print": "false"}
        response = await self._request(
            "post", "/api/files/local", files=files, data=data
        )
        return response.json()

    async def set_tool_temperature(self, target: int) -> None:
        await self._request(
            "post",
            "/api/printer/tool",
            json={"command": "target", "targets": {"tool0": target}},
        )

    async def set_bed_temperature(self, target: int) -> None:
        await self._request(
            "post", "/api/printer/bed", json={"command": "target", "target": target}
        )

    async def start_job(self) -> None:
        await self._request("post", "/api/job", json={"command": "start"})

    async def pause_job(self, action: str = "pause") -> None:
        await self._request(
            "post", "/api/job", json={"command": "pause", "action": action}
        )

    async def get_status(self) -> Dict[str, Any]:
        response = await self._request("get", "/api/job")
        return response.json()
