"""
KITTY Gateway - Fabrication Service Proxy
Proxies multi-printer control requests to the fabrication service
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
import httpx


router = APIRouter(prefix="/api/fabrication", tags=["fabrication"])

FABRICATION_BASE = os.getenv("FABRICATION_BASE", "http://fabrication:8300")


@router.post("/open_in_slicer")
async def open_in_slicer(request: Request) -> dict[str, Any]:
    """
    Open STL file in appropriate slicer app (Manual Workflow).

    Workflow:
    1. Analyze STL dimensions
    2. Select optimal printer based on size and availability
    3. Launch slicer app with STL file
    4. User completes slicing and printing manually

    Printer Selection Hierarchy (Quality-First):
    - Bamboo H2D: First choice for models up to the H2D build envelope (override via H2D_BUILD_* env vars)
    - Elegoo Giga: Fallback if Bamboo busy OR large models above H2D limits (uses ORANGESTORM_GIGA_BUILD_* env vars)
    - Snapmaker Artisan: CNC or laser jobs only

    Request body:
    {
        "stl_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
        "print_mode": "3d_print",  # or "cnc", "laser"
        "force_printer": null      # optional override
    }

    Response:
    {
        "success": true,
        "printer_id": "bamboo_h2d",
        "slicer_app": "BambuStudio",
        "stl_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
        "reasoning": "Model fits Bamboo H2D (150mm ≤ 250mm)...",
        "model_dimensions": {...},
        "printer_available": true
    }

    Proxies to fabrication_service /api/fabrication/open_in_slicer
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/open_in_slicer",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        # Forward the exact error from the fabrication service
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/analyze_model")
async def analyze_model(request: Request) -> dict[str, Any]:
    """
    Analyze STL dimensions and preview printer selection.

    Does NOT launch slicer app. Use this to preview which printer
    would be selected before committing to open the slicer.

    Request body:
    {
        "stl_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
        "print_mode": "3d_print"
    }

    Response:
    {
        "dimensions": {
            "width": 150.0,
            "depth": 80.0,
            "height": 45.0,
            "max_dimension": 150.0,
            "volume": 540000.0,
            "surface_area": 45000.0,
            "bounds": [...]
        },
        "recommended_printer": "bamboo_h2d",
        "slicer_app": "BambuStudio",
        "reasoning": "Model fits Bamboo H2D...",
        "printer_available": true,
        "model_fits": true
    }

    Proxies to fabrication_service /api/fabrication/analyze_model
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/fabrication/analyze_model",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/printer_status")
async def get_printer_status() -> dict[str, Any]:
    """
    Get status of all printers.

    Returns current online/offline status and printing state for:
    - Bamboo Labs H2D (via MQTT)
    - Elegoo Giga (via Moonraker HTTP)
    - Snapmaker Artisan (assumed available - no status check in Phase 1)

    Response:
    {
        "printers": {
            "bamboo_h2d": {
                "printer_id": "bamboo_h2d",
                "is_online": true,
                "is_printing": false,
                "status": "idle",
                "bed_temp": null,
                "extruder_temp": null,
                "progress": null,
                "estimated_time_remaining": null,
                "last_updated": "2025-01-15T10:30:00"
            },
            "elegoo_giga": {...},
            "snapmaker_artisan": {...}
        }
    }

    Proxies to fabrication_service /api/fabrication/printer_status
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/fabrication/printer_status"
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


# === Mesh Segmentation Endpoints ===


@router.get("/segmentation/printers")
async def list_printers() -> list[dict[str, Any]]:
    """List available printers with build volumes for segmentation."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{FABRICATION_BASE}/api/segmentation/printers")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/segmentation/upload")
async def upload_mesh_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Upload a 3MF or STL mesh file for segmentation.

    Files are saved to the artifacts directory and the container path is returned
    for use with segmentation endpoints.

    Max file size: 100MB
    Accepted formats: .3mf, .stl
    """
    try:
        # Read file content and forward as multipart
        file_content = await file.read()
        files = {"file": (file.filename, file_content, file.content_type)}

        async with httpx.AsyncClient(timeout=120.0) as client:  # Long timeout for uploads
            response = await client.post(
                f"{FABRICATION_BASE}/api/segmentation/upload",
                files=files
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/segmentation/check")
async def check_segmentation(request: Request) -> dict[str, Any]:
    """
    Check if a mesh needs segmentation based on printer build volume.

    Request body:
    {
        "mesh_path": "/path/to/model.3mf",
        "printer_id": "bamboo_h2d"
    }
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/segmentation/check",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/segmentation/segment")
async def segment_mesh(request: Request) -> dict[str, Any]:
    """
    Segment a mesh into printable parts.

    Request body:
    {
        "mesh_path": "/path/to/model.3mf",
        "printer_id": "bamboo_h2d",
        "wall_thickness_mm": 2.0,
        "enable_hollowing": true,
        "joint_type": "dowel",
        "max_parts": 50
    }
    """
    try:
        data = await request.json()
        async with httpx.AsyncClient(timeout=300.0) as client:  # Long timeout for segmentation
            response = await client.post(
                f"{FABRICATION_BASE}/api/segmentation/segment",
                json=data
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/segmentation/jobs/{job_id}")
async def get_segmentation_job(job_id: str) -> dict[str, Any]:
    """Get status of an async segmentation job."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{FABRICATION_BASE}/api/segmentation/jobs/{job_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.post("/segmentation/segment/async")
async def segment_mesh_async(request: Request) -> dict[str, Any]:
    """
    Start async segmentation job for large models.

    Returns job ID for status polling via /segmentation/jobs/{job_id}.
    """
    try:
        body = await request.json()
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{FABRICATION_BASE}/api/segmentation/segment/async",
                json=body,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/segmentation/download/{job_id}")
async def download_segmented_zip(job_id: str):
    """
    Download all segmented parts as a ZIP file.

    Streams the ZIP file from the fabrication service.
    """
    from fastapi.responses import StreamingResponse

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/segmentation/download/{job_id}",
            )
            response.raise_for_status()

            # Stream the ZIP response
            return StreamingResponse(
                iter([response.content]),
                media_type="application/zip",
                headers=dict(response.headers),
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")


@router.get("/artifacts/{file_path:path}")
async def serve_artifact(file_path: str):
    """
    Serve artifact files (segmented 3MF/STL parts) from the fabrication service.

    Proxies file requests to the fabrication service's mounted artifacts directory.
    Used for downloading individual segmented parts and combined assemblies.
    """
    from fastapi.responses import StreamingResponse

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{FABRICATION_BASE}/api/fabrication/artifacts/{file_path}",
            )
            response.raise_for_status()

            # Determine content type based on file extension
            content_type = "application/octet-stream"
            if file_path.endswith(".3mf"):
                content_type = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
            elif file_path.endswith(".stl"):
                content_type = "application/sla"

            # Stream the file response with download disposition
            filename = file_path.split("/")[-1]
            return StreamingResponse(
                iter([response.content]),
                media_type=content_type,
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Length": str(len(response.content)),
                },
            )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Fabrication service error: {e}")
