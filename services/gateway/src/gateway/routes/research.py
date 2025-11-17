"""Research API proxy router."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/research", tags=["research"])

BRAIN_BASE = "http://brain:8000"


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_research(path: str, request: Request):
    """
    Proxy all research API requests to the brain service.

    This includes:
    - Session management endpoints
    - Results endpoints
    - Findings endpoints
    - Follow-up session creation
    """
    url = f"{BRAIN_BASE}/api/research/{path}"

    # Get query parameters
    params = dict(request.query_params)

    # Get request body if present
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.json()
        except Exception:
            body = await request.body()

    # Forward the request with appropriate timeout
    # Research operations can be long-running, so use generous timeout
    timeout = httpx.Timeout(300.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        if request.method == "GET":
            response = await client.get(url, params=params)
        elif request.method == "POST":
            if isinstance(body, bytes):
                response = await client.post(url, content=body, params=params)
            else:
                response = await client.post(url, json=body, params=params)
        elif request.method == "PUT":
            if isinstance(body, bytes):
                response = await client.put(url, content=body, params=params)
            else:
                response = await client.put(url, json=body, params=params)
        elif request.method == "DELETE":
            response = await client.delete(url, params=params)
        elif request.method == "PATCH":
            if isinstance(body, bytes):
                response = await client.patch(url, content=body, params=params)
            else:
                response = await client.patch(url, json=body, params=params)

    # Return the response
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    return response.json()
