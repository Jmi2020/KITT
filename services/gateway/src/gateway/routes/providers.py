"""Provider and model information endpoint proxy."""

from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/providers", tags=["providers"])

BRAIN_URL = os.getenv("UPSTREAM_BRAIN_URL", "http://brain:8000")


@router.get("/models")
async def get_available_models():
    """
    Proxy request to brain service for available models.

    Returns flat list of all available models for Shell page selector,
    including local (Ollama, llama.cpp) and cloud providers.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BRAIN_URL}/api/providers/models")
            response.raise_for_status()
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch models: {str(e)}")


@router.get("/available")
async def get_available_providers():
    """
    Proxy request to brain service for available providers (legacy format).

    Returns information about all configured LLM providers and their status.
    New code should use /api/providers/models instead.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BRAIN_URL}/api/providers/available")
            response.raise_for_status()
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch providers: {str(e)}")


@router.get("/models/{model_id}/card")
async def get_model_card(model_id: str):
    """
    Proxy request to brain service for model card information.

    Returns detailed model card information including:
    - Full description from HuggingFace
    - Capabilities and features
    - Technical specifications
    - Links to documentation
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BRAIN_URL}/api/providers/models/{model_id}/card")
            response.raise_for_status()
            return JSONResponse(content=response.json(), status_code=response.status_code)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch model card: {str(e)}")
