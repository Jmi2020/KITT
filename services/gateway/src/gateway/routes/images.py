"""
KITTY Gateway - Images Service Proxy
Proxies image generation requests to the images_service
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException
import httpx


router = APIRouter(prefix="/api/images", tags=["images"])

IMAGES_BASE = os.getenv("IMAGES_BASE", "http://127.0.0.1:8089")


@router.post("/generate")
async def generate(request: Request) -> dict[str, Any]:
    """
    Enqueue an image generation job

    Proxies to images_service /api/images/generate
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=1200.0) as client:
            response = await client.post(
                f"{IMAGES_BASE}/api/images/generate",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Images service error: {e}")


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict[str, Any]:
    """
    Get status of a generation job

    Proxies to images_service /api/images/jobs/{job_id}
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{IMAGES_BASE}/api/images/jobs/{job_id}"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Images service error: {e}")


@router.get("/latest")
async def latest(limit: int = 36) -> dict[str, Any]:
    """
    List latest generated images

    Proxies to images_service /api/images/latest
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{IMAGES_BASE}/api/images/latest",
                params={"limit": limit}
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Images service error: {e}")


@router.post("/select")
async def select_image(request: Request) -> dict[str, Any]:
    """
    Select an image and return an imageRef

    Proxies to images_service /api/images/select
    Returns imageRef compatible with KITTY vision flows
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{IMAGES_BASE}/api/images/select",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Images service error: {e}")


@router.get("/stats")
async def stats() -> dict[str, Any]:
    """
    Get queue statistics

    Proxies to images_service /api/images/stats
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{IMAGES_BASE}/api/images/stats")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Images service error: {e}")
