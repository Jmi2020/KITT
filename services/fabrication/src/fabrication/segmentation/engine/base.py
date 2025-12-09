"""Base class for segmentation engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..schemas import SegmentationConfig, SegmentedPart, SegmentationResult

LOGGER = get_logger(__name__)


@dataclass
class CutCandidate:
    """A candidate cutting plane with scoring information."""

    plane: CuttingPlane
    score: float
    resulting_parts: int
    max_overhang_ratio: float = 0.0
    seam_visibility: float = 0.0
    balance_score: float = 0.0


@dataclass
class SegmentationState:
    """Current state of the segmentation process."""

    parts: List[MeshWrapper] = field(default_factory=list)
    cut_planes: List[CuttingPlane] = field(default_factory=list)
    iteration: int = 0
    parts_exceeding_volume: int = 0

    def all_parts_fit(self, build_volume: Tuple[float, float, float]) -> bool:
        """Check if all parts fit within build volume."""
        for part in self.parts:
            if not part.fits_in_volume(build_volume):
                return False
        return True

    def count_exceeding(self, build_volume: Tuple[float, float, float]) -> int:
        """Count parts that exceed build volume."""
        count = 0
        for part in self.parts:
            if not part.fits_in_volume(build_volume):
                count += 1
        return count


class SegmentationEngine(ABC):
    """
    Abstract base class for mesh segmentation engines.

    Subclasses implement different segmentation strategies:
    - PlanarSegmentationEngine: Simple axis-aligned planar cuts (MVP)
    - BspSegmentationEngine: BSP beam search with overhang optimization (Phase 2)
    """

    def __init__(self, config: SegmentationConfig):
        """Initialize engine with configuration."""
        self.config = config
        self.build_volume = config.build_volume

    @abstractmethod
    def segment(
        self,
        mesh: MeshWrapper,
        request: Optional["SegmentMeshRequest"] = None,
        output_dir: Optional[str] = None,
    ) -> SegmentationResult:
        """
        Segment mesh into parts that fit the build volume.

        Args:
            mesh: Input mesh to segment
            request: Optional request object (backwards compatibility)
            output_dir: Optional directory for output files

        Returns:
            SegmentationResult with parts and metadata
        """
        pass

    @abstractmethod
    def find_best_cut(
        self, mesh: MeshWrapper, state: SegmentationState
    ) -> Optional[CutCandidate]:
        """
        Find the best cutting plane for a mesh.

        Args:
            mesh: Mesh to find cut for
            state: Current segmentation state

        Returns:
            Best CutCandidate or None if no valid cut found
        """
        pass

    def needs_segmentation(self, mesh: MeshWrapper) -> bool:
        """Check if mesh exceeds build volume and needs segmentation."""
        return not mesh.fits_in_volume(self.build_volume)

    def check_segmentation(self, mesh: MeshWrapper) -> dict:
        """
        Check if mesh needs segmentation and return analysis.

        Returns:
            Dict with needs_segmentation, dimensions, exceeds_by, etc.
        """
        dims = mesh.dimensions
        exceeds = mesh.bounding_box.exceeds(self.build_volume)
        overage = mesh.bounding_box.overage(self.build_volume)

        # Estimate number of cuts needed
        cuts_needed = 0
        for i in range(3):
            if exceeds[i]:
                # Rough estimate: ceil(dimension / build_volume) - 1
                cuts_needed += int(dims[i] / self.build_volume[i])

        return {
            "needs_segmentation": any(exceeds),
            "model_dimensions_mm": dims,
            "build_volume_mm": self.build_volume,
            "exceeds_by_mm": overage,
            "exceeds_axes": exceeds,
            "recommended_cuts": max(cuts_needed, 1) if any(exceeds) else 0,
        }

    def execute_cut(
        self, mesh: MeshWrapper, plane: CuttingPlane
    ) -> Tuple[MeshWrapper, MeshWrapper]:
        """
        Execute a cut on the mesh.

        Args:
            mesh: Mesh to cut
            plane: Cutting plane

        Returns:
            Tuple of (positive_half, negative_half)
        """
        return mesh.split(plane)

    def create_part_info(
        self, mesh: MeshWrapper, index: int, file_path: str = ""
    ) -> SegmentedPart:
        """Create SegmentedPart info from a mesh."""
        dims = mesh.dimensions

        # Determine if supports are needed based on overhang analysis
        requires_supports = self._analyze_overhangs(mesh)

        return SegmentedPart(
            index=index,
            name=f"part_{index:02d}",
            dimensions_mm=dims,
            volume_cm3=mesh.volume_cm3,
            file_path=file_path,
            minio_uri="",
            joints=[],
            requires_supports=requires_supports,
        )

    def _analyze_overhangs(self, mesh: MeshWrapper, threshold_angle: float = 45.0) -> bool:
        """
        Analyze mesh for significant overhangs.

        Args:
            mesh: Mesh to analyze
            threshold_angle: Angle from vertical considered overhang (degrees)

        Returns:
            True if mesh has significant overhangs requiring supports
        """
        overhang_ratio = self.calculate_overhang_ratio(mesh, threshold_angle)
        return overhang_ratio > 0.10

    def calculate_overhang_ratio(
        self, mesh: MeshWrapper, threshold_angle: float = 45.0
    ) -> float:
        """
        Calculate the ratio of surface area with overhangs exceeding threshold.

        Args:
            mesh: Mesh to analyze
            threshold_angle: Angle from vertical considered overhang (degrees)

        Returns:
            Ratio of overhang area to total area (0.0 to 1.0)
        """
        import numpy as np

        try:
            normals = mesh.face_normals
            areas = mesh.face_areas

            # Calculate angle from build plate (Z up)
            z_up = np.array([0, 0, 1])
            cos_angles = np.dot(normals, z_up)

            # Find downward-facing triangles (negative Z component)
            downward_mask = cos_angles < 0

            if not np.any(downward_mask):
                return 0.0

            # Calculate overhang angle for downward faces
            overhang_angles = np.degrees(np.arccos(np.abs(cos_angles[downward_mask])))

            # Calculate area of faces exceeding threshold
            overhang_threshold_mask = overhang_angles > threshold_angle
            overhang_area = np.sum(areas[downward_mask][overhang_threshold_mask])
            total_area = np.sum(areas)

            return float(overhang_area / total_area) if total_area > 0 else 0.0

        except Exception as e:
            LOGGER.warning(f"Overhang calculation failed: {e}")
            return 0.0

    def estimate_part_overhangs(
        self,
        mesh: MeshWrapper,
        plane: CuttingPlane,
        side: str = "positive",
        threshold_angle: float = 45.0,
    ) -> float:
        """
        Estimate MINIMUM overhang ratio for a potential cut result,
        considering that the part can be reoriented for optimal printing.

        This enables overhang-aware cut scoring by predicting which cuts will
        produce parts with fewer overhangs after optimal orientation.

        Strategy:
        1. Identify faces that would end up on the specified side of the cut
        2. Test multiple print orientations (6 cardinal directions)
        3. Return the MINIMUM overhang ratio (best orientation)

        Args:
            mesh: Mesh to analyze
            plane: Proposed cutting plane
            side: "positive" or "negative" side of plane
            threshold_angle: Angle threshold for overhangs (degrees)

        Returns:
            Estimated minimum overhang ratio (0.0 to 1.0) for the resulting part
            in its optimal print orientation
        """
        import numpy as np

        try:
            # Get face data
            normals = mesh.face_normals
            areas = mesh.face_areas
            tm = mesh.as_trimesh

            # Get face centroids to determine which side of plane they're on
            face_centroids = tm.triangles_center

            # Calculate signed distance from plane for each face centroid
            plane_origin = np.array(plane.origin)
            plane_normal = np.array(plane.normal)
            plane_normal = plane_normal / np.linalg.norm(plane_normal)

            # Signed distance: positive = on normal side, negative = opposite side
            signed_distances = np.dot(face_centroids - plane_origin, plane_normal)

            # Select faces on the requested side
            if side == "positive":
                side_mask = signed_distances >= 0
            else:
                side_mask = signed_distances < 0

            if not np.any(side_mask):
                return 0.0

            # Get faces on this side
            side_normals = normals[side_mask]
            side_areas = areas[side_mask]
            side_total_area = np.sum(side_areas)

            if side_total_area <= 0:
                return 0.0

            # Test 6 cardinal orientations (each axis as build plate normal)
            # This simulates rotating the part to find the best print orientation
            test_up_vectors = [
                np.array([0, 0, 1]),   # Z up (original)
                np.array([0, 0, -1]),  # Z down
                np.array([0, 1, 0]),   # Y up
                np.array([0, -1, 0]),  # Y down
                np.array([1, 0, 0]),   # X up
                np.array([-1, 0, 0]),  # X down
            ]

            min_overhang_ratio = 1.0

            for up_vector in test_up_vectors:
                # Calculate overhang for this orientation
                cos_angles = np.dot(side_normals, up_vector)

                # Find downward-facing triangles (opposite to up_vector)
                downward_mask = cos_angles < 0

                if not np.any(downward_mask):
                    # No overhangs in this orientation - perfect!
                    return 0.0

                # Calculate overhang angles
                overhang_angles = np.degrees(np.arccos(np.abs(cos_angles[downward_mask])))

                # Calculate overhang area exceeding threshold
                overhang_threshold_mask = overhang_angles > threshold_angle
                overhang_area = np.sum(side_areas[downward_mask][overhang_threshold_mask])

                overhang_ratio = overhang_area / side_total_area
                min_overhang_ratio = min(min_overhang_ratio, overhang_ratio)

            return float(min_overhang_ratio)

        except Exception as e:
            LOGGER.debug(f"Overhang estimation failed: {e}")
            return 0.0

    def validate_result(self, result: SegmentationResult) -> SegmentationResult:
        """Validate segmentation result and add warnings if needed."""
        warnings = []

        # Check all parts fit
        for part in result.parts:
            dims = part.dimensions_mm
            if (
                dims[0] > self.build_volume[0]
                or dims[1] > self.build_volume[1]
                or dims[2] > self.build_volume[2]
            ):
                warnings.append(f"Part {part.name} still exceeds build volume")

        # Check for very small parts
        for part in result.parts:
            if part.volume_cm3 < 1.0:
                warnings.append(f"Part {part.name} is very small ({part.volume_cm3:.2f}cm³)")

        if warnings:
            if result.assembly_notes:
                result.assembly_notes += "\n\nWarnings:\n" + "\n".join(f"- {w}" for w in warnings)
            else:
                result.assembly_notes = "Warnings:\n" + "\n".join(f"- {w}" for w in warnings)

        return result
