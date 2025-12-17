
from __future__ import annotations
import asyncio
import logging
import httpx
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Any

import websockets

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collective", tags=["collective"])

# KITTY uses brain service on port 8000, not agent-runtime
BASE = "http://brain:8000/api/collective"
WS_BASE = "ws://brain:8000/api/collective"


class RunReq(BaseModel):
    task: str
    pattern: Literal["pipeline", "council", "debate"] = "pipeline"
    k: int = Field(3, ge=2, le=7)
    max_steps: int = Field(8, ge=1, le=20)


class StreamRunReq(BaseModel):
    task: str
    pattern: Literal["pipeline", "council", "debate"] = "council"
    k: int = Field(3, ge=2, le=7)
    userId: Optional[str] = None
    enableSearchPhase: Optional[bool] = False
    selectedSpecialists: Optional[List[str]] = None


@router.post("/run")
async def proxy_run(req: RunReq):
    """Proxy collective meta-agent requests to brain service.

    Forwards requests to brain:8000/api/collective/run which executes
    the collective meta-agent patterns (council, debate, pipeline).

    This allows external clients to access the collective functionality
    through the gateway's public interface.
    """
    # Collective operations can take 5-20 minutes (council k=5, F16 judge, GPU-bound)
    # Use 1200s to respect GPU processing time and avoid premature timeouts
    async with httpx.AsyncClient(timeout=1200) as client:
        r = await client.post(f"{BASE}/run", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.post("/stream/start")
async def proxy_stream_start(req: StreamRunReq):
    """Start a streaming collective run.

    Creates a session that can be monitored via WebSocket.
    Returns session_id to connect via WebSocket.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/stream/start", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.websocket("/stream/{session_id}")
async def proxy_collective_stream(websocket: WebSocket, session_id: str):
    """
    WebSocket proxy to brain service for collective streaming.

    Establishes bidirectional connection between client and brain service.
    """
    await websocket.accept()

    brain_ws_url = f"{WS_BASE}/stream/{session_id}"

    try:
        async with websockets.connect(brain_ws_url) as brain_ws:
            async def client_to_brain():
                """Forward messages from client to brain service."""
                try:
                    while True:
                        message = await websocket.receive()

                        if message["type"] == "websocket.disconnect":
                            break

                        if "text" in message:
                            await brain_ws.send(message["text"])
                        elif "bytes" in message:
                            await brain_ws.send(message["bytes"])

                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.debug("Client to brain error: %s", e)

            async def brain_to_client():
                """Forward messages from brain service to client."""
                try:
                    async for message in brain_ws:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        elif isinstance(message, bytes):
                            await websocket.send_bytes(message)

                except websockets.exceptions.ConnectionClosed:
                    pass
                except Exception as e:
                    logger.debug("Brain to client error: %s", e)

            # Run both directions concurrently
            await asyncio.gather(
                client_to_brain(),
                brain_to_client(),
                return_exceptions=True
            )

    except websockets.exceptions.WebSocketException as e:
        logger.error("Failed to connect to brain service: %s", e)
        await websocket.close(code=1011, reason="Brain service unavailable")
    except Exception as e:
        logger.error("Collective WebSocket proxy error: %s", e)
        await websocket.close(code=1011, reason=f"Proxy error: {str(e)}")


@router.get("/specialists")
async def proxy_list_specialists():
    """List available specialists for collective deliberation."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/specialists")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


class CostEstimateReq(BaseModel):
    specialist_ids: List[str]
    tokens_per_proposal: int = 4000


@router.post("/specialists/estimate")
async def proxy_estimate_cost(req: CostEstimateReq):
    """Estimate cost for selected specialists."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE}/specialists/estimate", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.get("/sessions")
async def proxy_list_sessions(
    user_id: Optional[str] = Query(None, alias="userId"),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """List recent collective sessions."""
    params = {"limit": limit}
    if user_id:
        params["user_id"] = user_id
    if status:
        params["status"] = status

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/sessions", params=params)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()


@router.get("/sessions/{session_id}")
async def proxy_get_session(session_id: str):
    """Get details for a specific collective session."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/sessions/{session_id}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
