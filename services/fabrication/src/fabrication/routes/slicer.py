"""REST API routes for G-code slicing."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from common.logging import get_logger

from ..slicer import (
    SlicerEngine,
    SliceRequest,
    SliceResponse,
    SlicingJobStatus,
    SlicingStatus,
    SupportType,
    QualityPreset,
)
from ..slicer.schemas import ProfilesResponse

LOGGER = get_logger(__name__)

router = APIRouter(prefix="/api/slicer", tags=["slicer"])

# Module-level engine instance (set by app.py on startup)
_slicer_engine: Optional[SlicerEngine] = None


def set_slicer_engine(engine: SlicerEngine) -> None:
    """Set the slicer engine instance (called from app.py)."""
    global _slicer_engine
    _slicer_engine = engine
    LOGGER.info("Slicer engine configured for routes")


def get_engine() -> SlicerEngine:
    """Get the slicer engine, raising if not configured."""
    if _slicer_engine is None:
        raise HTTPException(
            status_code=503,
            detail="Slicer engine not initialized. Check ORCASLICER_BIN_PATH configuration.",
        )
    return _slicer_engine


# =============================================================================
# Status & Availability
# =============================================================================


@router.get("/status")
async def get_slicer_status() -> dict:
    """Get slicer service status including availability.

    Returns whether OrcaSlicer is available on this system.
    Slicing requires x86_64 architecture.
    """
    engine = get_engine()
    return {
        "available": engine.is_available,
        "bin_path": str(engine.bin_path),
        "profiles_loaded": {
            "printers": len(engine.profiles.list_printers()),
            "materials": len(engine.profiles.list_materials()),
            "qualities": len(engine.profiles.list_qualities()),
        },
        "message": (
            "CuraEngine ready"
            if engine.is_available
            else "CuraEngine binary not found at configured path"
        ),
    }


# =============================================================================
# Slicing Jobs
# =============================================================================


@router.post("/slice", response_model=SliceResponse)
async def start_slicing(request: SliceRequest) -> SliceResponse:
    """Start an async slicing job.

    The job runs in the background. Poll the status URL to track progress.
    """
    engine = get_engine()

    # Check if slicer is available FIRST (most fundamental check)
    if not engine.is_available:
        raise HTTPException(
            status_code=503,
            detail=(
                "OrcaSlicer is not available on this system. "
                "Slicing requires x86_64 architecture. "
                "See /api/slicer/status for details."
            ),
        )

    # Validate input file exists
    input_path = Path(request.input_path)
    if not input_path.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Input file not found: {request.input_path}",
        )

    # Validate file type
    if input_path.suffix.lower() not in [".3mf", ".stl"]:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {input_path.suffix}. Use .3mf or .stl",
        )

    # Validate printer profile exists
    printer_profile = engine.profiles.get_printer_profile(request.config.printer_id)
    if not printer_profile:
        available = [p.id for p in engine.profiles.list_printers()]
        raise HTTPException(
            status_code=400,
            detail=f"Unknown printer: {request.config.printer_id}. Available: {available}",
        )

    # Start async slicing
    try:
        job_id = await engine.slice_async(str(input_path), request.config)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    LOGGER.info(
        "Slicing job started",
        job_id=job_id,
        input=str(input_path),
        printer=request.config.printer_id,
    )

    return SliceResponse(
        job_id=job_id,
        status=SlicingStatus.PENDING,
        status_url=f"/api/slicer/jobs/{job_id}",
    )


@router.get("/jobs/{job_id}", response_model=SlicingJobStatus)
async def get_job_status(job_id: str) -> SlicingJobStatus:
    """Get status of a slicing job.

    Poll this endpoint to track progress.
    When status is 'completed', gcode_path will contain the output file path.
    """
    engine = get_engine()

    status = engine.get_job_status(job_id)
    if not status:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found: {job_id}",
        )

    return status


@router.get("/jobs/{job_id}/download")
async def download_gcode(job_id: str) -> FileResponse:
    """Download the generated G-code file.

    Only available after job completes successfully.
    """
    engine = get_engine()

    status = engine.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if status.status != SlicingStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete. Current status: {status.status}",
        )

    gcode_path = engine.get_gcode_path(job_id)
    if not gcode_path or not gcode_path.exists():
        raise HTTPException(
            status_code=404,
            detail="G-code file not found",
        )

    return FileResponse(
        path=gcode_path,
        filename=gcode_path.name,
        media_type="application/octet-stream",
    )


@router.post("/jobs/{job_id}/upload")
async def upload_to_printer(
    job_id: str,
    printer_id: Optional[str] = Query(
        default=None,
        description="Target printer ID (defaults to job's printer_id)",
    ),
) -> dict:
    """Upload sliced G-code to a printer.

    Requires job to be completed. Uses the printer from the slicing config
    unless overridden by printer_id parameter.
    """
    engine = get_engine()

    status = engine.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if status.status != SlicingStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete. Current status: {status.status}",
        )

    gcode_path = engine.get_gcode_path(job_id)
    if not gcode_path:
        raise HTTPException(status_code=404, detail="G-code file not found")

    target_printer = printer_id or status.config.printer_id

    # TODO: Wire to printer drivers (MoonrakerDriver, BambuMqttDriver)
    # For now, return the path that would be uploaded
    LOGGER.info(
        "Upload requested",
        job_id=job_id,
        printer=target_printer,
        gcode_path=str(gcode_path),
    )

    return {
        "success": True,
        "job_id": job_id,
        "printer_id": target_printer,
        "gcode_path": str(gcode_path),
        "message": "Upload endpoint ready. Printer driver integration pending.",
    }


# =============================================================================
# Profiles
# =============================================================================


@router.get("/profiles", response_model=ProfilesResponse)
async def list_all_profiles() -> ProfilesResponse:
    """List all available slicer profiles."""
    engine = get_engine()

    return ProfilesResponse(
        printers=engine.profiles.list_printers(),
        materials=engine.profiles.list_materials(),
        qualities=engine.profiles.list_qualities(),
    )


@router.get("/profiles/printers")
async def list_printers() -> list[dict]:
    """List available printer profiles."""
    engine = get_engine()
    return [p.model_dump() for p in engine.profiles.list_printers()]


@router.get("/profiles/materials")
async def list_materials(
    printer_id: Optional[str] = Query(
        default=None,
        description="Filter materials compatible with this printer",
    ),
) -> list[dict]:
    """List available material profiles.

    Optionally filter by printer compatibility.
    """
    engine = get_engine()
    return [m.model_dump() for m in engine.profiles.list_materials(printer_id)]


@router.get("/profiles/quality")
async def list_qualities() -> list[dict]:
    """List available quality presets."""
    engine = get_engine()
    return [q.model_dump() for q in engine.profiles.list_qualities()]


@router.get("/supports")
async def list_support_types() -> list[dict]:
    """List available support structure types."""
    return [
        {"id": SupportType.NONE.value, "name": "None", "description": "No supports"},
        {
            "id": SupportType.NORMAL.value,
            "name": "Normal",
            "description": "Standard grid supports",
        },
        {
            "id": SupportType.TREE.value,
            "name": "Tree",
            "description": "Organic tree-style supports (recommended)",
        },
    ]


@router.post("/profiles/reload")
async def reload_profiles() -> dict:
    """Reload profiles from disk.

    Useful after adding or modifying profile files.
    """
    engine = get_engine()
    engine.profiles.reload()
    return {
        "success": True,
        "printers": len(engine.profiles.list_printers()),
        "materials": len(engine.profiles.list_materials()),
        "qualities": len(engine.profiles.list_qualities()),
    }
