"""REST API endpoints for mesh segmentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import tempfile

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from common.logging import get_logger

from ..config import get_printer_config
from ..segmentation import (
    MeshWrapper,
    PlanarSegmentationEngine,
    SegmentationConfig,
    JointType,
)
from ..segmentation.schemas import (
    HollowingStrategy,
    SegmentMeshRequest,
    SegmentMeshResponse,
    SegmentedPartResponse,
    CheckSegmentationRequest,
    CheckSegmentationResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/segmentation", tags=["segmentation"])

# Store for background task results
_segmentation_jobs: dict[str, dict[str, Any]] = {}


class SegmentationJobStatus(BaseModel):
    """Status of a segmentation job."""

    job_id: str
    status: str  # pending, running, completed, failed
    progress: float = 0.0
    result: Optional[SegmentMeshResponse] = None
    error: Optional[str] = None


@router.post("/check")
async def check_segmentation(request: CheckSegmentationRequest) -> CheckSegmentationResponse:
    """
    Check if a mesh needs segmentation.

    Returns analysis of mesh dimensions vs build volume.
    """
    try:
        # Load mesh (supports both 3MF and STL)
        mesh_path = Path(request.mesh_path)
        if not mesh_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.mesh_path}")

        mesh = MeshWrapper(mesh_path)

        # Get build volume from printer config or defaults
        build_volume = _get_build_volume(request.printer_id)

        # Create engine for analysis
        config = SegmentationConfig(build_volume=build_volume)
        engine = PlanarSegmentationEngine(config)

        # Check segmentation needs
        analysis = engine.check_segmentation(mesh)

        return CheckSegmentationResponse(
            needs_segmentation=analysis["needs_segmentation"],
            model_dimensions_mm=mesh.dimensions,
            build_volume_mm=build_volume,
            exceeds_by_mm=analysis["exceeds_by_mm"],
            recommended_cuts=analysis["recommended_cuts"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Check segmentation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/segment")
async def segment_mesh(request: SegmentMeshRequest) -> SegmentMeshResponse:
    """
    Segment a mesh into printable parts.

    This endpoint performs synchronous segmentation for smaller models.
    For large models, use /segment/async.
    """
    try:
        # Load mesh (supports both 3MF and STL)
        mesh_path = Path(request.mesh_path)
        if not mesh_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {request.mesh_path}")

        mesh = MeshWrapper(mesh_path)
        logger.info(f"Loaded mesh: {mesh.dimensions} mm, {mesh.volume_cm3:.1f} cm³")

        # Get build volume
        build_volume = _get_build_volume(request.printer_id)

        # Configure segmentation
        config = SegmentationConfig(
            build_volume=build_volume,
            wall_thickness_mm=request.wall_thickness_mm,
            enable_hollowing=request.enable_hollowing,
            hollowing_strategy=request.hollowing_strategy,
            joint_type=request.joint_type,
            joint_tolerance_mm=request.joint_tolerance_mm,
            max_parts=request.max_parts,
        )

        # Get output directory for exported parts
        output_dir = _get_output_directory(mesh_path)

        # Run segmentation with file export
        engine = PlanarSegmentationEngine(config)
        result = engine.segment(mesh, output_dir=str(output_dir))

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error or "Segmentation failed")

        logger.info(f"Segmentation complete: {result.num_parts} parts exported to {output_dir}")

        part_responses = [
            SegmentedPartResponse(
                index=p.index,
                name=p.name,
                dimensions_mm=p.dimensions_mm,
                volume_cm3=p.volume_cm3,
                file_path=p.file_path,
                minio_uri=p.minio_uri,
                requires_supports=p.requires_supports,
            )
            for p in result.parts
        ]

        return SegmentMeshResponse(
            success=True,
            needs_segmentation=result.needs_segmentation,
            num_parts=result.num_parts,
            parts=part_responses,
            combined_3mf_path=result.combined_3mf_path,
            combined_3mf_uri=result.combined_3mf_uri,
            hardware_required=result.hardware_required,
            assembly_notes=result.assembly_notes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Segmentation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/segment/async")
async def segment_mesh_async(
    request: SegmentMeshRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    """
    Start async segmentation job for large models.

    Returns job ID for status polling.
    """
    import uuid

    job_id = str(uuid.uuid4())

    # Initialize job status
    _segmentation_jobs[job_id] = {
        "status": "pending",
        "progress": 0.0,
        "result": None,
        "error": None,
    }

    # Start background task
    background_tasks.add_task(_run_segmentation_job, job_id, request)

    return {"job_id": job_id, "status_url": f"/api/segmentation/jobs/{job_id}"}


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str) -> SegmentationJobStatus:
    """Get status of a segmentation job."""
    if job_id not in _segmentation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _segmentation_jobs[job_id]

    return SegmentationJobStatus(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/printers")
async def list_printer_configs() -> list[dict[str, Any]]:
    """List available printer configurations with build volumes."""
    try:
        config = get_printer_config()

        printers = []
        for printer_id, printer_info in config.get("printers", {}).items():
            build_volume = printer_info.get("build_volume", [250, 250, 250])
            printers.append({
                "printer_id": printer_id,
                "name": printer_info.get("name", printer_id),
                "build_volume_mm": tuple(build_volume),
                "model": printer_info.get("model", "Unknown"),
            })

        return printers

    except Exception as e:
        logger.error(f"Failed to list printers: {e}")
        return [
            {
                "printer_id": "default",
                "name": "Default Printer",
                "build_volume_mm": (250, 250, 250),
                "model": "Generic",
            }
        ]


def _get_build_volume(printer_id: Optional[str]) -> tuple[float, float, float]:
    """Get build volume for a printer."""
    if not printer_id:
        return (250.0, 250.0, 250.0)  # Default

    try:
        config = get_printer_config()
        printer_info = config.get("printers", {}).get(printer_id)

        if printer_info and "build_volume" in printer_info:
            vol = printer_info["build_volume"]
            return (float(vol[0]), float(vol[1]), float(vol[2]))

    except Exception as e:
        logger.warning(f"Failed to get printer config for {printer_id}: {e}")

    return (250.0, 250.0, 250.0)


def _get_output_directory(source_path: Path) -> Path:
    """Get output directory for segmented parts."""
    # Create output directory next to source file
    output_dir = source_path.parent / f"{source_path.stem}_segmented"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


async def _run_segmentation_job(job_id: str, request: SegmentMeshRequest) -> None:
    """Background task for segmentation."""
    try:
        _segmentation_jobs[job_id]["status"] = "running"
        _segmentation_jobs[job_id]["progress"] = 0.1

        # Load mesh (supports both 3MF and STL)
        mesh_path = Path(request.mesh_path)
        mesh = MeshWrapper(mesh_path)
        _segmentation_jobs[job_id]["progress"] = 0.2

        # Get build volume
        build_volume = _get_build_volume(request.printer_id)

        # Get output directory for exported parts
        output_dir = _get_output_directory(mesh_path)

        # Configure and run
        config = SegmentationConfig(
            build_volume=build_volume,
            wall_thickness_mm=request.wall_thickness_mm,
            enable_hollowing=request.enable_hollowing,
            hollowing_strategy=request.hollowing_strategy,
            joint_type=request.joint_type,
            joint_tolerance_mm=request.joint_tolerance_mm,
            max_parts=request.max_parts,
        )

        engine = PlanarSegmentationEngine(config)
        _segmentation_jobs[job_id]["progress"] = 0.3

        result = engine.segment(mesh, output_dir=str(output_dir))
        _segmentation_jobs[job_id]["progress"] = 0.9

        if result.success:
            part_responses = [
                SegmentedPartResponse(
                    index=p.index,
                    name=p.name,
                    dimensions_mm=p.dimensions_mm,
                    volume_cm3=p.volume_cm3,
                    file_path=p.file_path,
                    minio_uri=p.minio_uri,
                    requires_supports=p.requires_supports,
                )
                for p in result.parts
            ]

            _segmentation_jobs[job_id]["result"] = SegmentMeshResponse(
                success=True,
                needs_segmentation=result.needs_segmentation,
                num_parts=result.num_parts,
                parts=part_responses,
                combined_3mf_path=result.combined_3mf_path,
                combined_3mf_uri=result.combined_3mf_uri,
                hardware_required=result.hardware_required,
                assembly_notes=result.assembly_notes,
            )
            _segmentation_jobs[job_id]["status"] = "completed"
        else:
            _segmentation_jobs[job_id]["error"] = result.error
            _segmentation_jobs[job_id]["status"] = "failed"

        _segmentation_jobs[job_id]["progress"] = 1.0

    except Exception as e:
        logger.exception(f"Background segmentation failed: {e}")
        _segmentation_jobs[job_id]["status"] = "failed"
        _segmentation_jobs[job_id]["error"] = str(e)
