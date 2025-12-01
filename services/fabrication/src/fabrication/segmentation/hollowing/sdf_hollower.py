"""SDF-based mesh hollowing using MeshLib."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper

LOGGER = get_logger(__name__)


@dataclass
class HollowingConfig:
    """Configuration for mesh hollowing."""

    wall_thickness_mm: float = 2.0
    min_wall_thickness_mm: float = 1.2
    voxel_size_mm: float = 0.5
    drain_holes: bool = True
    drain_hole_diameter_mm: float = 3.0
    drain_hole_count: int = 2


@dataclass
class HollowingResult:
    """Result of hollowing operation."""

    success: bool
    mesh: Optional[MeshWrapper]
    original_volume_cm3: float
    hollowed_volume_cm3: float
    material_savings_percent: float
    wall_thickness_achieved_mm: float
    error: Optional[str] = None


class SdfHollower:
    """
    SDF-based mesh hollowing using MeshLib.

    Uses voxel-based signed distance field for robust hollowing
    that handles self-intersections and complex geometry.
    """

    def __init__(self, config: Optional[HollowingConfig] = None):
        """Initialize hollower with configuration."""
        self.config = config or HollowingConfig()
        self._meshlib_available = self._check_meshlib()

    def _check_meshlib(self) -> bool:
        """Check if MeshLib is available."""
        try:
            import mrmeshpy  # noqa: F401

            return True
        except ImportError:
            LOGGER.warning("mrmeshpy not available, hollowing will be limited")
            return False

    def hollow(self, mesh: MeshWrapper) -> HollowingResult:
        """
        Hollow a mesh to create a shell with specified wall thickness.

        Args:
            mesh: Input mesh to hollow

        Returns:
            HollowingResult with hollowed mesh and statistics
        """
        original_volume = mesh.volume_cm3

        # Validate wall thickness
        if self.config.wall_thickness_mm < self.config.min_wall_thickness_mm:
            return HollowingResult(
                success=False,
                mesh=None,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=original_volume,
                material_savings_percent=0.0,
                wall_thickness_achieved_mm=0.0,
                error=f"Wall thickness {self.config.wall_thickness_mm}mm below minimum {self.config.min_wall_thickness_mm}mm",
            )

        # Check if mesh is too small to hollow
        min_dimension = min(mesh.dimensions)
        if min_dimension < self.config.wall_thickness_mm * 3:
            LOGGER.info(
                f"Mesh too small to hollow (min dimension {min_dimension:.1f}mm), skipping"
            )
            return HollowingResult(
                success=True,
                mesh=mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=original_volume,
                material_savings_percent=0.0,
                wall_thickness_achieved_mm=0.0,
                error=None,
            )

        if self._meshlib_available:
            return self._hollow_meshlib(mesh, original_volume)
        else:
            return self._hollow_fallback(mesh, original_volume)

    def _hollow_meshlib(
        self, mesh: MeshWrapper, original_volume: float
    ) -> HollowingResult:
        """Hollow using MeshLib SDF approach."""
        try:
            import mrmeshpy as mr

            ml_mesh = mesh.as_meshlib

            # Calculate adaptive voxel size based on mesh dimensions
            max_dim = mesh.max_dimension
            voxel_size = min(
                self.config.voxel_size_mm,
                self.config.wall_thickness_mm / 5.0,
                max_dim / 200.0,  # At least 200 voxels across largest dimension
            )
            voxel_size = max(voxel_size, 0.1)  # Minimum voxel size

            LOGGER.info(
                f"Hollowing with wall thickness {self.config.wall_thickness_mm}mm, "
                f"voxel size {voxel_size:.2f}mm"
            )

            # Configure offset parameters for shell creation
            params = mr.OffsetParameters()
            params.voxelSize = voxel_size
            params.type = mr.OffsetParametersType.Shell

            # Perform inward offset (negative = shell)
            hollowed = mr.offsetMesh(ml_mesh, -self.config.wall_thickness_mm, params)

            if hollowed is None or hollowed.topology.numValidFaces() == 0:
                LOGGER.warning("Hollowing collapsed mesh to zero volume")
                return HollowingResult(
                    success=False,
                    mesh=mesh,
                    original_volume_cm3=original_volume,
                    hollowed_volume_cm3=original_volume,
                    material_savings_percent=0.0,
                    wall_thickness_achieved_mm=0.0,
                    error="Hollowing collapsed mesh",
                )

            # Convert back to MeshWrapper
            result_mesh = MeshWrapper._from_meshlib(hollowed)
            hollowed_volume = result_mesh.volume_cm3

            # Calculate material savings
            savings = (
                (original_volume - hollowed_volume) / original_volume * 100
                if original_volume > 0
                else 0
            )

            LOGGER.info(
                f"Hollowing complete: {original_volume:.1f}cm³ → {hollowed_volume:.1f}cm³ "
                f"({savings:.1f}% material savings)"
            )

            return HollowingResult(
                success=True,
                mesh=result_mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=hollowed_volume,
                material_savings_percent=savings,
                wall_thickness_achieved_mm=self.config.wall_thickness_mm,
            )

        except Exception as e:
            LOGGER.error(f"MeshLib hollowing failed: {e}")
            return HollowingResult(
                success=False,
                mesh=mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=original_volume,
                material_savings_percent=0.0,
                wall_thickness_achieved_mm=0.0,
                error=str(e),
            )

    def _hollow_fallback(
        self, mesh: MeshWrapper, original_volume: float
    ) -> HollowingResult:
        """
        Fallback hollowing using trimesh (less robust).

        This is a simplified approach that creates an offset surface
        but may not handle complex geometry as well as MeshLib SDF.
        """
        try:
            import trimesh

            tm = mesh.as_trimesh

            # Adaptive voxel size: limit to ~200 voxels per dimension for performance
            # while ensuring we can achieve the wall thickness
            max_dim = mesh.max_dimension
            target_voxels_per_dim = 200
            min_voxel_for_performance = max_dim / target_voxels_per_dim

            # Need at least 2 voxels for wall thickness erosion
            max_voxel_for_thickness = self.config.wall_thickness_mm / 2

            voxel_size = max(min_voxel_for_performance, max_voxel_for_thickness)
            LOGGER.info(
                f"Voxel hollowing: {int(max_dim/voxel_size)} voxels/dim, "
                f"voxel_size={voxel_size:.1f}mm"
            )

            # Voxelize the mesh
            voxelized = tm.voxelized(voxel_size)

            # Hollow by eroding the voxel grid
            from scipy import ndimage

            filled = voxelized.matrix.copy()

            # Calculate erosion iterations - need enough to create wall thickness
            erosion_iterations = max(1, int(self.config.wall_thickness_mm / voxel_size))

            eroded = ndimage.binary_erosion(
                filled,
                iterations=erosion_iterations,
            )
            shell = filled & ~eroded

            # Convert shell back to mesh using trimesh's VoxelGrid
            from trimesh.voxel import VoxelGrid

            # Create new voxel grid from the shell boolean array
            shell_voxels = VoxelGrid(shell, voxelized.transform)

            hollowed_mesh = shell_voxels.marching_cubes

            # marching_cubes returns mesh in voxel coordinates - apply transform
            hollowed_mesh.apply_transform(voxelized.transform)

            if hollowed_mesh.vertices.shape[0] == 0:
                LOGGER.warning("Fallback hollowing produced empty mesh")
                return HollowingResult(
                    success=False,
                    mesh=mesh,
                    original_volume_cm3=original_volume,
                    hollowed_volume_cm3=original_volume,
                    material_savings_percent=0.0,
                    wall_thickness_achieved_mm=0.0,
                    error="Fallback hollowing failed",
                )

            result_mesh = MeshWrapper(hollowed_mesh)
            hollowed_volume = result_mesh.volume_cm3
            savings = (
                (original_volume - hollowed_volume) / original_volume * 100
                if original_volume > 0
                else 0
            )

            return HollowingResult(
                success=True,
                mesh=result_mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=hollowed_volume,
                material_savings_percent=savings,
                wall_thickness_achieved_mm=self.config.wall_thickness_mm,
            )

        except Exception as e:
            LOGGER.error(f"Fallback hollowing failed: {e}")
            return HollowingResult(
                success=False,
                mesh=mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=original_volume,
                material_savings_percent=0.0,
                wall_thickness_achieved_mm=0.0,
                error=str(e),
            )

    def add_drain_holes(
        self,
        mesh: MeshWrapper,
        positions: Optional[list[Tuple[float, float, float]]] = None,
    ) -> MeshWrapper:
        """
        Add drain holes to hollowed mesh for resin drainage.

        Args:
            mesh: Hollowed mesh
            positions: Optional specific positions, or auto-place at bottom

        Returns:
            Mesh with drain holes
        """
        if not self.config.drain_holes:
            return mesh

        try:
            import trimesh

            tm = mesh.as_trimesh
            bbox = mesh.bounding_box

            if positions is None:
                # Auto-place holes at bottom of mesh
                positions = self._calculate_drain_positions(bbox)

            # Create cylindrical holes
            for pos in positions:
                cylinder = trimesh.creation.cylinder(
                    radius=self.config.drain_hole_diameter_mm / 2,
                    height=self.config.wall_thickness_mm * 3,
                    sections=16,
                )
                # Position cylinder at drain location, oriented downward
                cylinder.apply_translation([pos[0], pos[1], pos[2]])

                # Boolean subtraction
                tm = tm.difference(cylinder)

            return MeshWrapper(tm)

        except Exception as e:
            LOGGER.warning(f"Failed to add drain holes: {e}")
            return mesh

    def _calculate_drain_positions(
        self, bbox
    ) -> list[Tuple[float, float, float]]:
        """Calculate optimal drain hole positions."""
        positions = []
        center = bbox.center

        # Place holes near bottom corners
        offset = min(bbox.dimensions[0], bbox.dimensions[1]) * 0.3

        if self.config.drain_hole_count >= 1:
            positions.append((center[0] - offset, center[1] - offset, bbox.min_z))

        if self.config.drain_hole_count >= 2:
            positions.append((center[0] + offset, center[1] + offset, bbox.min_z))

        return positions[: self.config.drain_hole_count]
