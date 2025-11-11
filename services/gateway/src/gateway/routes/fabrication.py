"""
KITTY Gateway - Fabrication Service Proxy
Proxies multi-printer control requests to the fabrication service
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request, HTTPException
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
