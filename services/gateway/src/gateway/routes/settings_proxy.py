"""
Settings Service Proxy Routes.

Proxies settings requests to the settings service:
- /api/settings - GET/PUT user settings
- /api/settings/{section} - GET/PUT settings section
- /api/settings/voice-modes - GET/PUT custom voice modes
- /api/settings/sync - WebSocket for real-time sync
"""

from __future__ import annotations

import asyncio
import os
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
import websockets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

SETTINGS_URL = os.getenv("SETTINGS_BASE_URL", "http://settings:8450")
SETTINGS_WS_URL = SETTINGS_URL.replace("http://", "ws://").replace("https://", "wss://")


async def proxy_to_settings(request: Request, path: str = "") -> Response:
    """Proxy HTTP request to settings service."""
    url = f"{SETTINGS_URL}/api/settings{path}"

    if request.query_params:
        url += f"?{request.query_params}"

    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in ("host", "content-length")
    }

    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
            )

            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Settings service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Settings service unavailable")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Settings proxy error: {str(e)}")


@router.get("")
async def get_settings(request: Request) -> Response:
    """Proxy GET settings to settings service."""
    return await proxy_to_settings(request, "")


@router.put("")
async def update_settings(request: Request) -> Response:
    """Proxy PUT settings to settings service."""
    return await proxy_to_settings(request, "")


@router.get("/{section}")
async def get_settings_section(request: Request, section: str) -> Response:
    """Proxy GET settings section to settings service."""
    return await proxy_to_settings(request, f"/{section}")


@router.put("/{section}")
async def update_settings_section(request: Request, section: str) -> Response:
    """Proxy PUT settings section to settings service."""
    return await proxy_to_settings(request, f"/{section}")


@router.websocket("/sync")
async def settings_sync_proxy(websocket: WebSocket) -> None:
    """
    WebSocket proxy to settings service for real-time sync.

    Establishes bidirectional connection between client and settings service.
    """
    await websocket.accept()

    # Get query params for user_id
    query_string = str(websocket.query_params) if websocket.query_params else ""
    settings_ws_url = f"{SETTINGS_WS_URL}/api/settings/sync"
    if query_string:
        settings_ws_url += f"?{query_string}"

    try:
        async with websockets.connect(settings_ws_url) as settings_ws:
            async def client_to_settings():
                """Forward messages from client to settings service."""
                try:
                    while True:
                        message = await websocket.receive()

                        if message["type"] == "websocket.disconnect":
                            break

                        if "text" in message:
                            await settings_ws.send(message["text"])
                        elif "bytes" in message:
                            await settings_ws.send(message["bytes"])

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.debug("Client to settings error: %s", e)

            async def settings_to_client():
                """Forward messages from settings service to client."""
                try:
                    async for message in settings_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        elif isinstance(message, bytes):
                            await websocket.send_bytes(message)

                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.debug("Settings to client error: %s", e)

            # Run both directions concurrently
            await asyncio.gather(
                client_to_settings(),
                settings_to_client(),
                return_exceptions=True
            )

    except websockets.exceptions.WebSocketException as e:
        logger.error("Failed to connect to settings service: %s", e)
        await websocket.close(code=1011, reason="Settings service unavailable")
    except Exception as e:
        logger.error("Settings WebSocket proxy error: %s", e)
        await websocket.close(code=1011, reason=f"Proxy error: {str(e)}")
