"""Moonraker JSON-RPC helper."""

from __future__ import annotations

from typing import Any, Dict

import httpx


class MoonrakerClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def query_objects(self, objects: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "method": "printer.objects.query",
            "params": {"objects": objects},
            "id": 1,
        }
        async with httpx.AsyncClient(base_url=self._base_url, timeout=30) as client:
            response = await client.post("/printer/objects/query", json=payload)
            response.raise_for_status()
            return response.json()

    async def get_print_stats(self) -> Dict[str, Any]:
        result = await self.query_objects({"print_stats": ["state", "filename"]})
        return result.get("result", {}).get("status", {}).get("print_stats", {})
