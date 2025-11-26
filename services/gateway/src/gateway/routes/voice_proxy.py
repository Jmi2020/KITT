"""
Voice Service Proxy Routes.

Proxies voice requests to the voice service:
- /api/voice/status - Voice service status
- /api/voice/transcript - Text transcript endpoint
- /api/voice/stream - WebSocket for real-time streaming
"""

from __future__ import annotations

import asyncio
import os
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
import websockets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/voice", tags=["voice"])

VOICE_URL = os.getenv("VOICE_BASE_URL", "http://localhost:8400")
VOICE_WS_URL = VOICE_URL.replace("http://", "ws://").replace("https://", "wss://")


async def proxy_to_voice(request: Request, path: str) -> Response:
    """Proxy HTTP request to voice service."""
    url = f"{VOICE_URL}{path}"

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
        raise HTTPException(status_code=504, detail="Voice service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Voice service unavailable")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Voice proxy error: {str(e)}")


@router.get("/status")
async def voice_status(request: Request) -> Response:
    """Proxy voice status to voice service."""
    return await proxy_to_voice(request, "/api/voice/status")


@router.post("/transcript")
async def voice_transcript(request: Request) -> Response:
    """Proxy voice transcript to voice service."""
    return await proxy_to_voice(request, "/api/voice/transcript")


@router.websocket("/stream")
async def voice_stream_proxy(websocket: WebSocket) -> None:
    """
    WebSocket proxy to voice service.

    Establishes bidirectional connection between client and voice service.
    """
    await websocket.accept()

    voice_ws_url = f"{VOICE_WS_URL}/api/voice/stream"

    try:
        async with websockets.connect(voice_ws_url) as voice_ws:
            async def client_to_voice():
                """Forward messages from client to voice service."""
                try:
                    while True:
                        message = await websocket.receive()

                        if message["type"] == "websocket.disconnect":
                            break

                        if "text" in message:
                            await voice_ws.send(message["text"])
                        elif "bytes" in message:
                            await voice_ws.send(message["bytes"])

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.debug("Client to voice error: %s", e)

            async def voice_to_client():
                """Forward messages from voice service to client."""
                try:
                    async for message in voice_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        elif isinstance(message, bytes):
                            await websocket.send_bytes(message)

                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.debug("Voice to client error: %s", e)

            # Run both directions concurrently
            await asyncio.gather(
                client_to_voice(),
                voice_to_client(),
                return_exceptions=True
            )

    except websockets.exceptions.WebSocketException as e:
        logger.error("Failed to connect to voice service: %s", e)
        await websocket.close(code=1011, reason="Voice service unavailable")
    except Exception as e:
        logger.error("Voice WebSocket proxy error: %s", e)
        await websocket.close(code=1011, reason=f"Proxy error: {str(e)}")
