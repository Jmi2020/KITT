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
    # Voxel resolution for fallback hollowing (trimesh voxelization)
    # Higher values = more detail but slower. 200 is fast, 500+ is high quality
    # Set to 0 to auto-calculate based on voxel_size_mm
    voxels_per_dim: int = 200

    # Post-hollowing mesh cleanup options
    # Simplification reduces triangle count while preserving shape
    enable_simplification: bool = True
    simplification_ratio: float = 0.3  # Reduce to 30% of original faces (voxel method)
    target_faces: Optional[int] = None  # Override ratio with specific count

    # Surface shell inner surface simplification
    # The inner surface is not visible, so we aggressively simplify it
    # 0.1 = reduce to 10% of faces (90% reduction) - default for quality/size balance
    surface_shell_inner_ratio: float = 0.1
    surface_shell_inner_min_faces: int = 1000  # Minimum faces to keep for stability

    # Smoothing reduces jagged voxel artifacts
    enable_smoothing: bool = True
    smooth_iterations: int = 2  # Number of Laplacian smoothing passes


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

    def hollow(self, mesh: MeshWrapper, strategy: str = "voxel") -> HollowingResult:
        """
        Hollow a mesh to create a shell with specified wall thickness.

        Args:
            mesh: Input mesh to hollow
            strategy: "voxel" (default) or "surface_shell" (preserves original surface)

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

        # Use surface shell method if requested (preserves original surface)
        if strategy == "surface_shell":
            return self._hollow_surface_shell(mesh, original_volume)

        # Otherwise use voxel-based methods
        if self._meshlib_available:
            return self._hollow_meshlib(mesh, original_volume)
        else:
            return self._hollow_fallback(mesh, original_volume)

    def _hollow_surface_shell(
        self, mesh: MeshWrapper, original_volume: float
    ) -> HollowingResult:
        """
        Surface-preserving hollowing that keeps the original outer surface.

        Creates an inner offset surface by moving vertices along normals,
        then uses boolean subtraction to create a shell.

        This preserves all original surface detail/texture on the outside,
        while aggressively simplifying the inner surface (not visible).
        """
        try:
            import manifold3d as m3d
            import trimesh

            tm = mesh.as_trimesh.copy()
            wall_thickness = self.config.wall_thickness_mm

            LOGGER.info(
                f"Surface shell hollowing: wall_thickness={wall_thickness}mm, "
                f"preserving original {len(tm.faces):,} faces"
            )

            # Get smooth vertex normals
            vertex_normals = tm.vertex_normals

            # THIN WALL PROTECTION: Compute safe offset distance per vertex
            # to prevent paper-thin walls in areas where geometry converges
            from scipy.spatial import cKDTree

            # Build KD-tree for fast nearest neighbor lookup
            tree = cKDTree(tm.vertices)

            # Build adjacency set for each vertex (vertices connected by edges)
            vertex_adjacency = [set() for _ in range(len(tm.vertices))]
            for face in tm.faces:
                for i in range(3):
                    vertex_adjacency[face[i]].update(face)

            # Find 2nd nearest neighbor for each vertex (1st is itself or adjacent)
            # Query k=10 neighbors to skip adjacent vertices
            k = min(10, len(tm.vertices))
            distances, indices = tree.query(tm.vertices, k=k)

            # For each vertex, find distance to nearest NON-ADJACENT vertex
            safe_offsets = np.full(len(tm.vertices), wall_thickness, dtype=np.float32)
            min_wall = self.config.min_wall_thickness_mm

            for i in range(len(tm.vertices)):
                adjacent = vertex_adjacency[i]
                for j in range(1, k):  # Skip 0 (self)
                    neighbor_idx = indices[i, j]
                    if neighbor_idx not in adjacent:
                        dist = distances[i, j]
                        if dist < wall_thickness * 2.5:
                            # Limit offset to prevent crossing over
                            max_safe_offset = max(min_wall, (dist - min_wall) / 2)
                            safe_offsets[i] = min(wall_thickness, max_safe_offset)
                        break  # Found nearest non-adjacent

            # Count vertices with reduced offset (thin regions)
            reduced_count = np.sum(safe_offsets < wall_thickness * 0.9)
            if reduced_count > 0:
                LOGGER.info(
                    f"Thin wall protection: {reduced_count:,} vertices "
                    f"({reduced_count / len(tm.vertices) * 100:.1f}%) have reduced offset"
                )

            # Create inner surface by offsetting vertices inward with safe offsets
            inner_vertices = tm.vertices - vertex_normals * safe_offsets[:, np.newaxis]
            inner_tm = trimesh.Trimesh(vertices=inner_vertices, faces=tm.faces.copy())

            # Aggressively simplify inner mesh - no one sees the inside!
            # Use configurable ratio (default 0.1 = 10% of faces = 90% reduction)
            inner_target_faces = max(
                self.config.surface_shell_inner_min_faces,
                int(len(tm.faces) * self.config.surface_shell_inner_ratio)
            )
            original_inner_faces = len(inner_tm.faces)

            try:
                inner_tm = inner_tm.simplify_quadric_decimation(face_count=inner_target_faces)
                LOGGER.info(
                    f"Simplified inner surface: {original_inner_faces:,} -> {len(inner_tm.faces):,} faces "
                    f"({len(inner_tm.faces)/original_inner_faces*100:.1f}%)"
                )
            except Exception as e:
                LOGGER.warning(f"Inner surface simplification failed: {e}, using full resolution")
                inner_tm = trimesh.Trimesh(vertices=inner_vertices, faces=tm.faces.copy())

            # Convert both to manifold3d
            outer_mesh = m3d.Mesh(
                vert_properties=tm.vertices.astype(np.float32),
                tri_verts=tm.faces.astype(np.uint32),
            )
            outer_manifold = m3d.Manifold(outer_mesh)

            inner_mesh = m3d.Mesh(
                vert_properties=inner_tm.vertices.astype(np.float32),
                tri_verts=inner_tm.faces.astype(np.uint32),
            )
            inner_manifold = m3d.Manifold(inner_mesh)

            # Boolean subtract inner from outer to create shell
            shell_manifold = outer_manifold - inner_manifold

            if shell_manifold.status() != m3d.Error.NoError:
                LOGGER.warning(f"Surface shell boolean failed: {shell_manifold.status()}")
                # Fall back to voxel method
                return self._hollow_fallback(mesh, original_volume)

            # Convert back to MeshWrapper
            shell_mesh_data = shell_manifold.to_mesh()
            shell_verts = np.array(shell_mesh_data.vert_properties)[:, :3]
            shell_faces = np.array(shell_mesh_data.tri_verts)
            shell_tm = trimesh.Trimesh(vertices=shell_verts, faces=shell_faces)

            result_mesh = MeshWrapper(shell_tm)
            hollowed_volume = result_mesh.volume_cm3

            savings = (
                (original_volume - hollowed_volume) / original_volume * 100
                if original_volume > 0
                else 0
            )

            LOGGER.info(
                f"Surface shell complete: {original_volume:.1f}cm³ → {hollowed_volume:.1f}cm³ "
                f"({savings:.1f}% savings), {result_mesh.face_count:,} faces"
            )

            return HollowingResult(
                success=True,
                mesh=result_mesh,
                original_volume_cm3=original_volume,
                hollowed_volume_cm3=hollowed_volume,
                material_savings_percent=savings,
                wall_thickness_achieved_mm=wall_thickness,
            )

        except Exception as e:
            LOGGER.error(f"Surface shell hollowing failed: {e}")
            # Fall back to voxel method
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

            # Apply post-hollowing cleanup (simplification + smoothing)
            result_mesh = self._apply_cleanup(result_mesh)

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

            # Adaptive voxel size based on config resolution or explicit voxel size
            max_dim = mesh.max_dimension
            target_voxels_per_dim = self.config.voxels_per_dim

            if target_voxels_per_dim > 0:
                # Use specified resolution
                voxel_size = max_dim / target_voxels_per_dim
            else:
                # Use explicit voxel_size_mm from config
                voxel_size = self.config.voxel_size_mm

            # Ensure voxel size doesn't exceed wall thickness (need at least 1 erosion iteration)
            # But allow smaller voxels for higher quality - more erosion iterations will be used
            voxel_size = min(voxel_size, self.config.wall_thickness_mm)

            # Minimum voxel size to prevent memory issues (0.5mm for very high quality)
            voxel_size = max(voxel_size, 0.5)

            actual_voxels = int(max_dim / voxel_size)
            erosion_iters = max(1, int(self.config.wall_thickness_mm / voxel_size))
            LOGGER.info(
                f"Voxel hollowing: {actual_voxels} voxels/dim, "
                f"voxel_size={voxel_size:.2f}mm, erosion_iterations={erosion_iters}"
            )

            # Voxelize the mesh
            voxelized = tm.voxelized(voxel_size)

            # CRITICAL: voxelized.matrix only contains SURFACE voxels, not a solid fill.
            # We need to fill the interior before eroding to create proper walls.
            # Use binary_fill_holes to convert surface voxels to solid interior.
            from scipy import ndimage

            # Fill the interior of the voxelized surface to get a solid volume
            surface_voxels = voxelized.matrix.copy()
            filled = ndimage.binary_fill_holes(surface_voxels)
            LOGGER.debug(
                f"Voxel fill: surface={surface_voxels.sum()} -> filled={filled.sum()} voxels"
            )

            # Calculate erosion iterations - need enough to create wall thickness
            erosion_iterations = max(1, int(self.config.wall_thickness_mm / voxel_size))

            # THIN WALL PROTECTION: Use distance transform to identify thin features
            # that would become paper-thin or disappear after erosion
            # These areas should be left solid rather than hollowed
            distance_to_surface = ndimage.distance_transform_edt(filled)

            # Areas where the distance to surface is less than wall_thickness
            # are "thin features" - the interior doesn't have room for hollowing
            min_interior_distance = erosion_iterations  # In voxel units
            thin_feature_mask = (distance_to_surface > 0) & (distance_to_surface < min_interior_distance)

            # Standard erosion for thick regions
            eroded = ndimage.binary_erosion(
                filled,
                iterations=erosion_iterations,
            )

            # Create shell, but preserve thin features as solid
            shell = filled & ~eroded

            # Add back thin features as solid (don't hollow them)
            # This ensures areas that would become paper-thin stay solid
            thin_features_to_keep = filled & thin_feature_mask
            shell = shell | thin_features_to_keep

            thin_voxel_count = thin_features_to_keep.sum()
            if thin_voxel_count > 0:
                LOGGER.info(
                    f"Thin wall protection: preserved {thin_voxel_count:,} voxels "
                    f"({thin_voxel_count / filled.sum() * 100:.1f}% of model) as solid"
                )

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

            # Apply post-hollowing cleanup (simplification + smoothing)
            result_mesh = self._apply_cleanup(result_mesh)

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

    def _apply_cleanup(self, mesh: MeshWrapper) -> MeshWrapper:
        """
        Apply post-hollowing mesh cleanup (simplification + smoothing + repair).

        Reduces triangle count from voxelization, smooths jagged surfaces,
        and removes degenerate triangles that can cause "icicle" artifacts.
        """
        original_faces = mesh.face_count

        # Apply simplification first (reduces triangle count)
        if self.config.enable_simplification:
            if self.config.target_faces is not None:
                mesh = mesh.simplify(target_faces=self.config.target_faces)
            else:
                mesh = mesh.simplify(ratio=self.config.simplification_ratio)

        # Apply smoothing after (reduces voxel artifacts)
        if self.config.enable_smoothing and self.config.smooth_iterations > 0:
            mesh = mesh.smooth(iterations=self.config.smooth_iterations)

        # Repair mesh to remove degenerate triangles
        # NOTE: We only remove zero-area degenerate faces, not elongated ones,
        # because removing elongated faces creates holes that break manifold cutting.
        # The "icicle" artifacts from smoothing are less harmful than broken meshes.
        mesh = mesh.repair(
            remove_degenerate=True,
            remove_elongated=False,  # Disabled - creates holes that break manifold3d
        )

        final_faces = mesh.face_count
        if final_faces != original_faces:
            LOGGER.info(
                f"Mesh cleanup: {original_faces} -> {final_faces} faces "
                f"({final_faces/original_faces*100:.1f}% of original)"
            )

        return mesh

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
