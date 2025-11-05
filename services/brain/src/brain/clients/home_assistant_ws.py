# noqa: D401
"""Home Assistant WebSocket listener."""

from __future__ import annotations

import json
from typing import Awaitable, Callable
from urllib.parse import urlparse, urlunparse

import anyio
import websockets

from common.credentials import HomeAssistantCredentials


def _build_ws_url(base_http_url: str) -> str:
    parsed = urlparse(base_http_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/api/websocket", "", "", ""))


class HomeAssistantWebSocket:
    """Maintain a WebSocket connection for state updates."""

    def __init__(self, credentials: HomeAssistantCredentials) -> None:
        self._credentials = credentials

    async def listen(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Connect and forward messages to handler."""

        url = _build_ws_url(self._credentials.base_url)
        token = self._credentials.token.get_secret_value()
        async with websockets.connect(url) as websocket:
            await websocket.send(json.dumps({"type": "auth", "access_token": token}))
            auth_response = json.loads(await websocket.recv())
            if auth_response.get("type") != "auth_ok":
                raise RuntimeError(f"Home Assistant auth failed: {auth_response}")

            async for message in websocket:
                payload = json.loads(message)
                await handler(payload)

    async def run_forever(self, handler: Callable[[dict], Awaitable[None]]) -> None:
        """Reconnect loop."""

        backoff = 1.0
        while True:
            try:
                await self.listen(handler)
            except Exception:  # noqa: BLE001
                await anyio.sleep(backoff)
                backoff = min(backoff * 2, 30)


__all__ = ["HomeAssistantWebSocket"]
