"""Pydantic schemas for mesh segmentation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class JointType(str, Enum):
    """Joint type for part assembly."""

    DOWEL = "dowel"  # Cylindrical holes for external wooden/metal dowel pins
    INTEGRATED = "integrated"  # Printed pins on one part, holes on other (default, no hardware needed)
    DOVETAIL = "dovetail"  # Trapezoidal key/slot (Phase 2)
    PYRAMID = "pyramid"  # Self-centering cones (Phase 2)
    NONE = "none"  # No joints - use glue, magnets, or other external attachment methods


class HollowingStrategy(str, Enum):
    """When to apply hollowing during segmentation."""

    HOLLOW_THEN_SEGMENT = "hollow_then_segment"  # Hollow first via voxelization, then segment
    SEGMENT_THEN_HOLLOW = "segment_then_hollow"  # Segment solid, then hollow each piece
    SURFACE_SHELL = "surface_shell"  # Preserve original surface, offset inward (default, best quality)
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
    hollowing_strategy: HollowingStrategy = HollowingStrategy.SURFACE_SHELL
    # Voxel resolution for hollowing: higher = more detail but slower
    # 200 = fast/coarse (~5mm voxels for 1m model), 500 = medium (~2mm), 1000+ = high quality
    hollowing_resolution: int = 200

    # Cut face reinforcement - add solid flanges at cut interfaces
    # This prevents paper-thin walls when hollowing cuts through shell walls
    cut_face_flange_depth_mm: float = 10.0  # DEPRECATED: Use cut_wall_reinforcement_mm instead

    # Wall reinforcement at cuts - adds solid material at cut faces during the split operation
    # This fills the hollow cavity at cut interfaces to enforce minimum wall thickness
    # Works for all hollowing strategies. Recommended: 8mm for structural stability.
    # 0 = disabled, >0 = depth of solid reinforcement at each cut face
    cut_wall_reinforcement_mm: float = 8.0

    # Post-hollowing mesh cleanup
    # Simplification reduces excessive triangles from voxelization
    enable_simplification: bool = True
    simplification_ratio: float = 0.3  # Reduce to 30% of original faces
    # Smoothing reduces jagged voxel surface artifacts
    # WARNING: Smoothing can create "icicle" artifacts on thin geometry/overhangs
    # Use sparingly (0-1 iterations) or disable for models with fine details
    enable_smoothing: bool = False  # Disabled by default to avoid icicles
    smooth_iterations: int = 0  # Number of Laplacian smoothing passes

    # Joints
    joint_type: JointType = JointType.INTEGRATED  # Printed pins on one part, holes on other
    joint_tolerance_mm: float = 0.3  # Clearance for joint fit (0.3mm works for printed pins)
    dowel_diameter_mm: float = 4.0
    dowel_depth_mm: float = 10.0
    # Integrated pin dimensions (for JointType.INTEGRATED)
    pin_diameter_mm: float = 8.0  # Pin diameter (must fit within wall thickness)
    pin_height_mm: float = 10.0  # Pin height (protrusion from surface)

    # Algorithm
    # max_parts: 0 = auto-calculate based on mesh/build volume, otherwise use specified limit
    max_parts: int = 0

    # Overhang optimization (Phase 1A)
    # Threshold angle from vertical for overhang detection (degrees)
    # 30° = strict (cleaner surfaces), 45° = standard FDM threshold
    overhang_threshold_deg: float = 30.0

    # Oblique cutting planes (Phase 1C)
    # When enabled, uses PCA to find mesh principal axes and generates
    # oblique cuts perpendicular to those axes. Only used as fallback
    # when axis-aligned cuts score poorly.
    enable_oblique_cuts: bool = False
    # Minimum score threshold - only try oblique cuts if best axis-aligned score is below this
    oblique_fallback_threshold: float = 0.5

    # Beam search (Phase 2)
    # When enabled, uses beam search to explore multiple cut sequences
    # instead of greedy single-best selection at each step.
    enable_beam_search: bool = False
    beam_width: int = 3  # Number of candidate paths to keep at each depth
    beam_max_depth: int = 10  # Maximum search depth (cuts)
    beam_timeout_seconds: float = 60.0  # Timeout for beam search

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
        default=10.0,
        description="Wall thickness for hollowing (mm)",
        ge=1.2,
        le=50.0,
    )
    joint_type: JointType = Field(
        default=JointType.INTEGRATED,
        description="Joint type for part assembly. Options: "
        "'integrated' (default) - printed pins on one part, holes on other, no hardware needed; "
        "'dowel' - cylindrical holes for external wooden/metal dowel pins; "
        "'none' - no joints, use external attachment methods (glue, magnets, etc).",
    )
    joint_tolerance_mm: float = Field(
        default=0.2,
        description="Joint clearance for fit (mm)",
        ge=0.0,
        le=1.0,
    )
    max_parts: int = Field(
        default=0,
        description="Maximum number of parts to generate (0 = auto-calculate based on mesh/build volume)",
        ge=0,
        le=500,
    )
    enable_hollowing: bool = Field(
        default=True,
        description="Enable mesh hollowing to save material",
    )
    hollowing_strategy: HollowingStrategy = Field(
        default=HollowingStrategy.SURFACE_SHELL,
        description="Hollowing strategy: 'surface_shell' (default) preserves surface detail, "
        "'hollow_then_segment' uses faster voxel method, 'segment_then_hollow' hollows each piece after cutting",
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
    hollowing_resolution: int = Field(
        default=1000,
        description="Voxel resolution for hollowing (200=fast, 500=medium, 1000+=high quality)",
        ge=50,
        le=2000,
    )
    enable_simplification: bool = Field(
        default=True,
        description="Enable mesh simplification after hollowing to reduce triangle count",
    )
    simplification_ratio: float = Field(
        default=0.3,
        description="Target ratio for mesh simplification (0.3 = reduce to 30% of faces)",
        ge=0.05,
        le=1.0,
    )
    enable_smoothing: bool = Field(
        default=True,
        description="Enable Laplacian smoothing after hollowing to reduce voxel artifacts",
    )
    smooth_iterations: int = Field(
        default=2,
        description="Number of smoothing iterations (more = smoother but may lose detail)",
        ge=0,
        le=10,
    )
    custom_build_volume: Optional[tuple[float, float, float]] = Field(
        default=None,
        description="Custom build volume (X, Y, Z in mm). Overrides printer_id if provided.",
        examples=[(300.0, 300.0, 400.0)],
    )
    overhang_threshold_deg: float = Field(
        default=30.0,
        description="Overhang angle threshold (degrees from vertical). "
        "Faces steeper than this are considered overhangs. "
        "30° = strict (cleaner surfaces), 45° = standard FDM threshold.",
        ge=15.0,
        le=60.0,
    )
    cut_wall_reinforcement_mm: float = Field(
        default=8.0,
        description="Depth of solid wall reinforcement at cut faces (mm). "
        "When cutting hollow meshes, this fills the exposed cavity to enforce minimum wall thickness. "
        "Recommended: 8mm for structural stability. 0 = disabled.",
        ge=0.0,
        le=50.0,
    )


# Backwards compatibility alias
SegmentationRequest = SegmentMeshRequest


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


# Backwards compatibility alias
CheckSegmentationResult = CheckSegmentationResponse
