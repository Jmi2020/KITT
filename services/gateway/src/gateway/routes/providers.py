"""Provider information endpoint proxy."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("/available")
async def get_available_providers():
    """
    Proxy request to brain service for available providers.

    Returns information about all configured LLM providers and their status.
    """
    brain_url = os.getenv("UPSTREAM_BRAIN_URL", "http://brain:8000")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{brain_url}/api/providers/available")
            response.raise_for_status()
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch providers: {str(e)}")
