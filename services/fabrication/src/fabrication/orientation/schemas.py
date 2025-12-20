"""Pydantic schemas for orientation optimization."""

from typing import List, Tuple, Optional
from pydantic import BaseModel, Field


class OrientationOption(BaseModel):
    """A possible orientation for printing."""

    id: str = Field(..., description="Unique identifier, e.g., 'z_up', 'x_up_pos'")
    label: str = Field(..., description="Human-readable label, e.g., 'Z-Up (Original)'")
    rotation_matrix: List[List[float]] = Field(
        ..., description="3x3 rotation matrix to apply"
    )
    up_vector: Tuple[float, float, float] = Field(
        ..., description="The up vector for this orientation"
    )
    overhang_ratio: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of surface area needing supports (0-1)"
    )
    support_estimate: str = Field(
        ..., description="Support requirement: 'none', 'minimal', 'moderate', 'significant'"
    )
    is_recommended: bool = Field(
        default=False, description="True if this is the best orientation"
    )


class AnalyzeOrientationRequest(BaseModel):
    """Request to analyze orientation options for a mesh."""

    mesh_path: str = Field(..., description="Path to mesh file (STL, GLB, 3MF)")
    threshold_angle: float = Field(
        default=45.0,
        ge=15.0,
        le=60.0,
        description="Overhang threshold angle in degrees (faces steeper than this need support)",
    )
    include_intermediate: bool = Field(
        default=False,
        description="Include 45-degree intermediate rotations (18 total vs 6)",
    )


class AnalyzeOrientationResponse(BaseModel):
    """Response containing orientation analysis results."""

    success: bool = Field(..., description="Whether analysis succeeded")
    original_dimensions: Tuple[float, float, float] = Field(
        ..., description="Original mesh dimensions (width, depth, height) in mm"
    )
    face_count: int = Field(..., description="Number of faces in mesh")
    orientations: List[OrientationOption] = Field(
        ..., description="List of orientation options ranked by overhang ratio"
    )
    best_orientation_id: str = Field(
        ..., description="ID of the recommended orientation"
    )
    analysis_time_ms: int = Field(..., description="Time taken for analysis in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class ApplyOrientationRequest(BaseModel):
    """Request to apply an orientation to a mesh."""

    mesh_path: str = Field(..., description="Path to original mesh file")
    orientation_id: str = Field(..., description="ID of selected orientation")
    rotation_matrix: List[List[float]] = Field(
        ..., description="3x3 rotation matrix to apply"
    )


class ApplyOrientationResponse(BaseModel):
    """Response after applying orientation."""

    success: bool = Field(..., description="Whether application succeeded")
    oriented_mesh_path: str = Field(
        ..., description="Path to the rotated mesh copy"
    )
    new_dimensions: Tuple[float, float, float] = Field(
        ..., description="New dimensions after rotation (width, depth, height) in mm"
    )
    applied_rotation: List[List[float]] = Field(
        ..., description="The rotation matrix that was applied"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
