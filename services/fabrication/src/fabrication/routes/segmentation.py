"""REST API endpoints for mesh segmentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
import io
import tempfile
import uuid
import zipfile

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import StreamingResponse
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


class UploadMeshResponse(BaseModel):
    """Response from mesh file upload."""

    success: bool
    filename: str
    container_path: str
    file_size_bytes: int
    file_type: str  # "3mf" or "stl"


# File upload constants
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("/upload", response_model=UploadMeshResponse)
async def upload_mesh_file(
    file: UploadFile = File(..., description="3MF or STL mesh file to upload")
) -> UploadMeshResponse:
    """
    Upload a 3MF or STL mesh file for segmentation.

    Files are saved to /app/artifacts/3mf/ or /app/artifacts/stl/ based on extension.
    Returns the container path for use with segmentation endpoints.

    Max file size: 100MB
    Accepted formats: .3mf, .stl
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    filename_lower = file.filename.lower()
    if filename_lower.endswith(".3mf"):
        file_type = "3mf"
        target_dir = Path("/app/artifacts/3mf")
    elif filename_lower.endswith(".stl"):
        file_type = "stl"
        target_dir = Path("/app/artifacts/stl")
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only .3mf and .stl files are accepted.",
        )

    # Ensure target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to avoid collisions
    unique_id = uuid.uuid4().hex[:8]
    safe_name = Path(file.filename).stem  # Remove extension
    # Sanitize filename (remove special chars)
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "-_")[:50]
    new_filename = f"{safe_name}_{unique_id}.{file_type}"
    target_path = target_dir / new_filename

    # Read file in chunks and check size
    total_size = 0
    try:
        with open(target_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE_BYTES:
                    # Clean up partial file
                    target_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        target_path.unlink(missing_ok=True)
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    logger.info(f"Uploaded mesh file: {target_path} ({total_size} bytes)")

    return UploadMeshResponse(
        success=True,
        filename=new_filename,
        container_path=str(target_path),
        file_size_bytes=total_size,
        file_type=file_type,
    )


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

        # Get build volume: custom > printer config > defaults
        if request.custom_build_volume:
            build_volume = request.custom_build_volume
        else:
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

        # Get build volume - custom overrides printer_id
        if request.custom_build_volume:
            build_volume = tuple(request.custom_build_volume)
            logger.info(f"Using custom build volume: {build_volume}")
        else:
            build_volume = _get_build_volume(request.printer_id)

        # Configure segmentation
        # Set wall reinforcement: use request value if specified, otherwise default to wall_thickness
        wall_reinforcement = getattr(request, 'cut_wall_reinforcement_mm', 0.0)
        if wall_reinforcement == 0.0 and request.enable_hollowing:
            # Auto-enable wall reinforcement when hollowing is enabled
            wall_reinforcement = request.wall_thickness_mm

        config = SegmentationConfig(
            build_volume=build_volume,
            wall_thickness_mm=request.wall_thickness_mm,
            enable_hollowing=request.enable_hollowing,
            hollowing_strategy=request.hollowing_strategy,
            hollowing_resolution=request.hollowing_resolution,
            joint_type=request.joint_type,
            joint_tolerance_mm=request.joint_tolerance_mm,
            max_parts=request.max_parts,
            pin_diameter_mm=request.pin_diameter_mm,
            pin_height_mm=request.pin_height_mm,
            overhang_threshold_deg=request.overhang_threshold_deg,
            cut_wall_reinforcement_mm=wall_reinforcement,
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


@router.get("/download/{job_id}")
async def download_segmented_zip(job_id: str) -> StreamingResponse:
    """
    Download all segmented parts as a ZIP file.

    Returns a ZIP archive containing all exported part files from the job.
    """
    if job_id not in _segmentation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _segmentation_jobs[job_id]
    if job["status"] != "completed" or not job.get("result"):
        raise HTTPException(status_code=400, detail="Job not completed or no result available")

    result = job["result"]

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    files_added = 0

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add individual parts
        for part in result.parts:
            part_path = Path(part.file_path)
            if part_path.exists():
                zf.write(part_path, part_path.name)
                files_added += 1
            else:
                logger.warning(f"Part file not found: {part_path}")

        # Add combined assembly if available
        if result.combined_3mf_path:
            combined_path = Path(result.combined_3mf_path)
            if combined_path.exists():
                zf.write(combined_path, combined_path.name)
                files_added += 1
            else:
                logger.warning(f"Combined assembly not found: {combined_path}")

    if files_added == 0:
        raise HTTPException(status_code=404, detail="No part files found to download")

    zip_buffer.seek(0)
    logger.info(f"Created ZIP with {files_added} parts for job {job_id[:8]}")

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="segmented_parts_{job_id[:8]}.zip"'
        },
    )


@router.get("/download-3mf/{job_id}")
async def download_combined_3mf(job_id: str) -> StreamingResponse:
    """
    Download the combined 3MF file for a segmentation job.

    This is useful for opening in external slicers like Bambu Studio.
    Returns the combined assembly 3MF file with all parts and colors.
    """
    if job_id not in _segmentation_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _segmentation_jobs[job_id]
    if job["status"] != "completed" or not job.get("result"):
        raise HTTPException(status_code=400, detail="Job not completed or no result available")

    result = job["result"]

    if not result.combined_3mf_path:
        raise HTTPException(status_code=404, detail="No combined 3MF file available")

    combined_path = Path(result.combined_3mf_path)
    if not combined_path.exists():
        raise HTTPException(status_code=404, detail="Combined 3MF file not found on disk")

    # Read file into memory
    file_content = combined_path.read_bytes()
    file_buffer = io.BytesIO(file_content)

    logger.info(f"Serving 3MF download for job {job_id[:8]}: {combined_path.name}")

    return StreamingResponse(
        file_buffer,
        media_type="application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        headers={
            "Content-Disposition": f'attachment; filename="{combined_path.name}"'
        },
    )


@router.get("/download-file")
async def download_artifact_file(path: str) -> StreamingResponse:
    """
    Download any artifact file by path.

    This endpoint allows downloading 3MF, STL, or G-code files from the
    artifacts directory. Useful for opening files in external applications
    like Bambu Studio.

    Security: Only allows files within the /app/artifacts directory.
    """
    # Security: Ensure path is within artifacts directory
    file_path = Path(path)

    # Normalize and validate path
    allowed_prefixes = ["/app/artifacts", "/app/storage"]
    is_allowed = any(str(file_path).startswith(prefix) for prefix in allowed_prefixes)

    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Only artifact files can be downloaded"
        )

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Determine media type
    suffix = file_path.suffix.lower()
    media_types = {
        ".3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        ".stl": "application/sla",
        ".gcode": "text/plain",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    # Read file
    file_content = file_path.read_bytes()
    file_buffer = io.BytesIO(file_content)

    logger.info(f"Serving artifact download: {file_path.name}")

    return StreamingResponse(
        file_buffer,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"'
        },
    )


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
        _segmentation_jobs[job_id]["progress"] = 0.05

        # Progress callback to update job status
        def on_progress(progress: float, stage: str):
            """Update job progress from engine callback."""
            _segmentation_jobs[job_id]["progress"] = progress
            logger.debug(f"Segmentation progress: {progress:.0%} - {stage}")

        # Load mesh (supports both 3MF and STL)
        mesh_path = Path(request.mesh_path)
        mesh = MeshWrapper(mesh_path)
        _segmentation_jobs[job_id]["progress"] = 0.08

        # Get build volume - custom overrides printer_id
        if request.custom_build_volume:
            build_volume = tuple(request.custom_build_volume)
        else:
            build_volume = _get_build_volume(request.printer_id)

        # Get output directory for exported parts
        output_dir = _get_output_directory(mesh_path)

        # Configure and run
        # Set wall reinforcement: use request value if specified, otherwise default to wall_thickness
        wall_reinforcement = getattr(request, 'cut_wall_reinforcement_mm', 0.0)
        if wall_reinforcement == 0.0 and request.enable_hollowing:
            # Auto-enable wall reinforcement when hollowing is enabled
            wall_reinforcement = request.wall_thickness_mm

        config = SegmentationConfig(
            build_volume=build_volume,
            wall_thickness_mm=request.wall_thickness_mm,
            enable_hollowing=request.enable_hollowing,
            hollowing_strategy=request.hollowing_strategy,
            hollowing_resolution=request.hollowing_resolution,
            joint_type=request.joint_type,
            joint_tolerance_mm=request.joint_tolerance_mm,
            max_parts=request.max_parts,
            pin_diameter_mm=request.pin_diameter_mm,
            pin_height_mm=request.pin_height_mm,
            cut_wall_reinforcement_mm=wall_reinforcement,
        )

        engine = PlanarSegmentationEngine(config)

        # Run segmentation with progress callback
        result = engine.segment(mesh, output_dir=str(output_dir), progress_callback=on_progress)

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
