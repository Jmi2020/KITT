"""Mesh segmentation module for splitting large 3D models into printable parts."""

from __future__ import annotations

from .schemas import (
    JointType,
    SegmentMeshRequest,
    SegmentMeshResponse,
    SegmentedPart,
    CuttingPlane,
    SegmentationConfig,
    SegmentationResult,
)
from .engine.base import SegmentationEngine
from .engine.planar_engine import PlanarSegmentationEngine
from .geometry.mesh_wrapper import MeshWrapper
from .hollowing.sdf_hollower import SdfHollower
from .joints.dowel import DowelJointFactory
from .output.threemf_writer import ThreeMFWriter

__all__ = [
    # Schemas
    "JointType",
    "SegmentMeshRequest",
    "SegmentMeshResponse",
    "SegmentedPart",
    "CuttingPlane",
    "SegmentationConfig",
    "SegmentationResult",
    # Engine
    "SegmentationEngine",
    "PlanarSegmentationEngine",
    # Geometry
    "MeshWrapper",
    # Hollowing
    "SdfHollower",
    # Joints
    "DowelJointFactory",
    # Output
    "ThreeMFWriter",
]
