"""REST API routes for mesh orientation optimization."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, HTTPException

from common.logging import get_logger

from ..orientation import (
    OrientationOptimizer,
    AnalyzeOrientationRequest,
    AnalyzeOrientationResponse,
    ApplyOrientationRequest,
    ApplyOrientationResponse,
)

LOGGER = get_logger(__name__)

router = APIRouter(prefix="/api/orientation", tags=["orientation"])

# Module-level optimizer instance
_optimizer: Optional[OrientationOptimizer] = None


def get_optimizer() -> OrientationOptimizer:
    """Get or create the orientation optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = OrientationOptimizer(threshold_angle=45.0)
    return _optimizer


# =============================================================================
# Orientation Analysis
# =============================================================================


@router.get("/status")
async def get_orientation_status() -> dict:
    """Get orientation service status."""
    return {
        "available": True,
        "default_threshold_angle": 45.0,
        "supported_formats": ["stl", "glb", "gltf", "3mf"],
        "cardinal_orientations": 6,
    }


@router.post("/analyze", response_model=AnalyzeOrientationResponse)
async def analyze_orientations(request: AnalyzeOrientationRequest) -> AnalyzeOrientationResponse:
    """
    Analyze mesh and return ranked orientation options.

    Tests 6 cardinal orientations (Z+, Z-, X+, X-, Y+, Y-) and returns
    them ranked by overhang ratio (lower is better).

    The best orientation minimizes the surface area requiring supports.
    """
    start_time = time.time()
    optimizer = get_optimizer()

    # Update threshold if provided
    if request.threshold_angle != 45.0:
        optimizer.threshold_angle = request.threshold_angle

    try:
        orientations, mesh = optimizer.analyze_orientations(
            mesh_path=request.mesh_path,
            include_intermediate=request.include_intermediate,
        )

        dimensions = optimizer.get_mesh_dimensions(mesh)
        face_count = len(mesh.faces)
        best_id = orientations[0].id if orientations else "z_up"

        elapsed_ms = int((time.time() - start_time) * 1000)

        LOGGER.info(
            f"Orientation analysis complete: {len(orientations)} options, "
            f"best={best_id} ({orientations[0].overhang_ratio:.1%} overhang), "
            f"took {elapsed_ms}ms"
        )

        return AnalyzeOrientationResponse(
            success=True,
            original_dimensions=dimensions,
            face_count=face_count,
            orientations=orientations,
            best_orientation_id=best_id,
            analysis_time_ms=elapsed_ms,
            error=None,
        )

    except FileNotFoundError as e:
        LOGGER.error(f"Mesh file not found: {request.mesh_path}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        LOGGER.error(f"Orientation analysis failed: {e}")
        elapsed_ms = int((time.time() - start_time) * 1000)
        return AnalyzeOrientationResponse(
            success=False,
            original_dimensions=(0.0, 0.0, 0.0),
            face_count=0,
            orientations=[],
            best_orientation_id="z_up",
            analysis_time_ms=elapsed_ms,
            error=str(e),
        )


@router.post("/apply", response_model=ApplyOrientationResponse)
async def apply_orientation(request: ApplyOrientationRequest) -> ApplyOrientationResponse:
    """
    Apply selected orientation and optional scaling to mesh.

    Creates a rotated (and optionally scaled) copy of the mesh in temp storage.
    The original file is NOT modified.

    If target_height is provided, the mesh is uniformly scaled so that the
    height (Z dimension after rotation) matches the target.

    Returns the path to the oriented mesh for use in subsequent slicing.
    """
    optimizer = get_optimizer()
    scale_factor = None

    try:
        # Load the mesh
        mesh = optimizer.load_mesh(request.mesh_path)

        # Save oriented mesh (rotation is applied during save)
        oriented_path = optimizer.save_oriented_mesh(
            mesh=mesh,
            rotation_matrix=request.rotation_matrix,
            original_path=request.mesh_path,
        )

        # Load the oriented mesh to get dimensions and optionally scale
        oriented_mesh = optimizer.load_mesh(oriented_path)

        # Apply scaling if target_height is specified
        if request.target_height is not None:
            # Get current height (Z dimension) after orientation
            bounds = oriented_mesh.bounds
            current_height = bounds[1][2] - bounds[0][2]

            if current_height > 0:
                scale_factor = request.target_height / current_height
                oriented_mesh.apply_scale(scale_factor)

                # Re-save the scaled mesh
                oriented_mesh.export(oriented_path)

                LOGGER.info(
                    f"Applied scaling: factor={scale_factor:.4f}, "
                    f"target_height={request.target_height}mm"
                )

        new_dims = optimizer.get_mesh_dimensions(oriented_mesh)

        LOGGER.info(
            f"Applied orientation {request.orientation_id}: "
            f"new dimensions {new_dims}"
            + (f", scale_factor={scale_factor:.4f}" if scale_factor else "")
        )

        return ApplyOrientationResponse(
            success=True,
            oriented_mesh_path=oriented_path,
            new_dimensions=new_dims,
            applied_rotation=request.rotation_matrix,
            scale_factor=scale_factor,
            error=None,
        )

    except FileNotFoundError as e:
        LOGGER.error(f"Mesh file not found: {request.mesh_path}")
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        LOGGER.error(f"Failed to apply orientation: {e}")
        return ApplyOrientationResponse(
            success=False,
            oriented_mesh_path="",
            new_dimensions=(0.0, 0.0, 0.0),
            applied_rotation=request.rotation_matrix,
            scale_factor=None,
            error=str(e),
        )


@router.get("/orientations")
async def list_orientations() -> dict:
    """
    List available cardinal orientations.

    Returns the 6 cardinal orientations with their rotation matrices.
    """
    from ..orientation.optimizer import CARDINAL_ORIENTATIONS

    return {
        "orientations": [
            {
                "id": orient_id,
                "label": data["label"],
                "up_vector": data["up_vector"],
                "rotation_matrix": data["rotation_matrix"],
            }
            for orient_id, data in CARDINAL_ORIENTATIONS.items()
        ]
    }
