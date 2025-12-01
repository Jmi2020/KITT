"""
KITTY Gateway - CAD Service Proxy
Proxies CAD generation requests and serves artifacts
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx


router = APIRouter(prefix="/api/cad", tags=["cad"])

CAD_BASE = os.getenv("CAD_BASE", "http://cad:8200")


@router.post("/generate")
async def generate_cad(request: Request) -> dict[str, Any]:
    """
    Generate CAD model from prompt.

    Request body:
    {
        "conversationId": "uuid",
        "prompt": "design a wall mount bracket",
        "mode": "organic",  # or "parametric"
        "imageRefs": ["1", "2"]  # optional reference image IDs
    }

    Response:
    {
        "conversationId": "uuid",
        "artifacts": [
            {
                "provider": "tripo",
                "artifactType": "stl",
                "location": "artifacts/stl/abc123.stl",
                "metadata": {
                    "glb_location": "artifacts/glb/abc123.glb",
                    "stl_location": "artifacts/stl/abc123.stl",
                    "thumbnail": "https://..."
                }
            }
        ]
    }

    Proxies to cad_service /api/cad/generate
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=180.0) as client:  # Long timeout for 3D generation
            response = await client.post(
                f"{CAD_BASE}/api/cad/generate",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"CAD service error: {e}")


@router.get("/artifacts/{subdir}/{filename}")
async def get_artifact(subdir: str, filename: str):
    """
    Serve artifact files (GLB, STL) from CAD service.

    Proxies to cad_service /api/cad/artifacts/{subdir}/{filename}
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CAD_BASE}/api/cad/artifacts/{subdir}/{filename}",
                follow_redirects=True
            )
            response.raise_for_status()

            # Determine content type
            content_type = "application/octet-stream"
            if filename.endswith(".glb"):
                content_type = "model/gltf-binary"
            elif filename.endswith(".3mf"):
                content_type = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
            elif filename.endswith(".stl"):
                content_type = "model/stl"

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Artifact not found")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"CAD service error: {e}")


@router.get("/artifacts/{filename}")
async def get_artifact_flat(filename: str):
    """
    Serve artifact files without subdirectory (fallback).
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CAD_BASE}/api/cad/artifacts/{filename}",
                follow_redirects=True
            )
            response.raise_for_status()

            content_type = "application/octet-stream"
            if filename.endswith(".glb"):
                content_type = "model/gltf-binary"
            elif filename.endswith(".3mf"):
                content_type = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
            elif filename.endswith(".stl"):
                content_type = "model/stl"

            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"'
                }
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Artifact not found")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"CAD service error: {e}")
