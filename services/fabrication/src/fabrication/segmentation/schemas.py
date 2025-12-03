"""Pydantic schemas for mesh segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class JointType(str, Enum):
    """Joint type for part assembly."""

    DOWEL = "dowel"  # Cylindrical holes for external pins
    INTEGRATED = "integrated"  # Printed pins on one part, holes on other (no hardware)
    DOVETAIL = "dovetail"  # Trapezoidal key/slot (Phase 2)
    PYRAMID = "pyramid"  # Self-centering cones (Phase 2)
    NONE = "none"  # No joints, glue only


class HollowingStrategy(str, Enum):
    """When to apply hollowing during segmentation."""

    HOLLOW_THEN_SEGMENT = "hollow_then_segment"  # Hollow first, then segment shell (default)
    SEGMENT_THEN_HOLLOW = "segment_then_hollow"  # Segment solid, then hollow each piece
    NONE = "none"  # No hollowing


@dataclass
class CuttingPlane:
    """Represents a cutting plane in 3D space."""

    origin: tuple[float, float, float]
    normal: tuple[float, float, float]
    plane_type: str = "vertical"  # vertical_x, vertical_y, horizontal, oblique
    seam_area: float = 0.0

    def flip(self) -> "CuttingPlane":
        """Return plane with inverted normal."""
        return CuttingPlane(
            origin=self.origin,
            normal=tuple(-n for n in self.normal),
            plane_type=self.plane_type,
            seam_area=self.seam_area,
        )


@dataclass
class JointLocation:
    """Location of a joint connector."""

    position: tuple[float, float, float]
    diameter_mm: float = 4.0
    depth_mm: float = 10.0
    part_index: int = 0
    # Normal direction for cylinder orientation (perpendicular to seam)
    # Default is Z-up; set from cut plane normal when generating joints
    normal: tuple[float, float, float] = (0.0, 0.0, 1.0)


@dataclass
class SegmentationConfig:
    """Configuration for mesh segmentation."""

    # Build volume constraint (mm) - Default: Bambu H2D (300x320x325mm)
    build_volume: tuple[float, float, float] = (300.0, 320.0, 325.0)

    # Hollowing
    wall_thickness_mm: float = 10.0  # Must be >= pin_diameter for integrated joints
    enable_hollowing: bool = True
    min_wall_thickness_mm: float = 1.2
    hollowing_strategy: HollowingStrategy = HollowingStrategy.HOLLOW_THEN_SEGMENT
    # Voxel resolution for hollowing: higher = more detail but slower
    # 200 = fast/coarse (~5mm voxels for 1m model), 500 = medium (~2mm), 1000+ = high quality
    hollowing_resolution: int = 200

    # Joints
    joint_type: JointType = JointType.DOWEL
    joint_tolerance_mm: float = 0.3  # Clearance for joint fit (0.3mm works for printed pins)
    dowel_diameter_mm: float = 4.0
    dowel_depth_mm: float = 10.0
    # Integrated pin dimensions (for JointType.INTEGRATED)
    pin_diameter_mm: float = 8.0  # Pin diameter (must fit within wall thickness)
    pin_height_mm: float = 10.0  # Pin height (protrusion from surface)

    # Algorithm
    # max_parts: 0 = auto-calculate based on mesh/build volume, otherwise use specified limit
    max_parts: int = 0

    # Output
    output_dir: Optional[str] = None


@dataclass
class SegmentedPart:
    """Information about a segmented part."""

    index: int
    name: str
    dimensions_mm: tuple[float, float, float]
    volume_cm3: float
    file_path: str = ""
    minio_uri: str = ""
    joints: list[JointLocation] = field(default_factory=list)
    requires_supports: bool = False


@dataclass
class SegmentationResult:
    """Result of mesh segmentation operation."""

    success: bool
    needs_segmentation: bool
    num_parts: int
    parts: list[SegmentedPart]
    cut_planes: list[CuttingPlane]
    combined_3mf_path: str = ""
    combined_3mf_uri: str = ""
    hardware_required: dict = field(default_factory=dict)
    assembly_notes: str = ""
    error: Optional[str] = None


# API Request/Response Models


class SegmentMeshRequest(BaseModel):
    """Request to segment a mesh for multi-part 3D printing."""

    model_config = {"populate_by_name": True}

    mesh_path: str = Field(
        ...,
        description="Absolute path to 3MF or STL mesh file",
        examples=["/Users/Shared/KITTY/artifacts/cad/model.3mf"],
        alias="stl_path",  # Backwards compatibility
    )
    printer_id: Optional[str] = Field(
        default=None,
        description="Target printer for build volume constraints",
        examples=["bamboo_h2d"],
    )
    wall_thickness_mm: float = Field(
        default=2.0,
        description="Wall thickness for hollowing (mm)",
        ge=1.2,
        le=10.0,
    )
    joint_type: JointType = Field(
        default=JointType.DOWEL,
        description="Joint type for assembly",
    )
    joint_tolerance_mm: float = Field(
        default=0.2,
        description="Joint clearance for fit (mm)",
        ge=0.0,
        le=1.0,
    )
    max_parts: int = Field(
        default=10,
        description="Maximum number of parts to generate",
        ge=2,
        le=100,
    )
    enable_hollowing: bool = Field(
        default=True,
        description="Enable mesh hollowing to save material",
    )
    hollowing_strategy: HollowingStrategy = Field(
        default=HollowingStrategy.HOLLOW_THEN_SEGMENT,
        description="When to hollow: 'hollow_then_segment' (default) creates shell first for wall panels, "
        "'segment_then_hollow' hollows each piece after cutting",
    )
    pin_diameter_mm: float = Field(
        default=5.0,
        description="Diameter of integrated pins (mm). Only used when joint_type='integrated'",
        ge=2.0,
        le=10.0,
    )
    pin_height_mm: float = Field(
        default=8.0,
        description="Height of integrated pin protrusion (mm). Only used when joint_type='integrated'",
        ge=3.0,
        le=15.0,
    )


class SegmentedPartResponse(BaseModel):
    """Response model for a segmented part."""

    index: int
    name: str
    dimensions_mm: tuple[float, float, float]
    volume_cm3: float
    file_path: str
    minio_uri: str
    requires_supports: bool = False


class SegmentMeshResponse(BaseModel):
    """Response from mesh segmentation."""

    success: bool
    needs_segmentation: bool
    num_parts: int
    parts: list[SegmentedPartResponse]
    combined_3mf_path: str
    combined_3mf_uri: str
    hardware_required: dict
    assembly_notes: str
    error: Optional[str] = None


class CheckSegmentationRequest(BaseModel):
    """Request to check if mesh needs segmentation."""

    model_config = {"populate_by_name": True}

    mesh_path: str = Field(
        ...,
        description="Path to 3MF or STL mesh file",
        alias="stl_path",  # Backwards compatibility
    )
    printer_id: Optional[str] = Field(default=None, description="Target printer")


class CheckSegmentationResponse(BaseModel):
    """Response from segmentation check."""

    needs_segmentation: bool
    model_dimensions_mm: tuple[float, float, float]
    build_volume_mm: tuple[float, float, float]
    exceeds_by_mm: tuple[float, float, float]
    recommended_cuts: int
