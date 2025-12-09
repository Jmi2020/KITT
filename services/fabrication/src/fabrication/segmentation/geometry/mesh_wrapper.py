"""Unified mesh abstraction bridging trimesh, MeshLib, and Manifold3D."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np
import trimesh

from common.logging import get_logger

from .plane import CuttingPlane

LOGGER = get_logger(__name__)


@dataclass
class BoundingBox:
    """Axis-aligned bounding box."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float

    @property
    def center(self) -> Tuple[float, float, float]:
        """Get center point of bounding box."""
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2,
        )

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        """Get dimensions (width, depth, height)."""
        return (
            self.max_x - self.min_x,
            self.max_y - self.min_y,
            self.max_z - self.min_z,
        )

    @property
    def max_dimension(self) -> float:
        """Get the largest dimension."""
        return max(self.dimensions)

    def exceeds(self, limits: Tuple[float, float, float]) -> Tuple[bool, bool, bool]:
        """Check if dimensions exceed limits."""
        dims = self.dimensions
        return (dims[0] > limits[0], dims[1] > limits[1], dims[2] > limits[2])

    def overage(self, limits: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Calculate how much dimensions exceed limits."""
        dims = self.dimensions
        return (
            max(0, dims[0] - limits[0]),
            max(0, dims[1] - limits[1]),
            max(0, dims[2] - limits[2]),
        )


class MeshWrapper:
    """
    Unified mesh abstraction bridging trimesh, MeshLib, and Manifold3D.

    Design principle: Use trimesh for I/O and analysis, MeshLib for
    volumetric ops (hollowing), Manifold3D for boolean cuts (guaranteed manifold).
    """

    def __init__(self, source: Union[Path, str, trimesh.Trimesh, np.ndarray]):
        """
        Initialize from file path, trimesh object, or vertex/face arrays.

        Args:
            source: Path to mesh file, trimesh object, or numpy arrays
        """
        self._trimesh: Optional[trimesh.Trimesh] = None
        self._manifold: Optional[object] = None  # manifold3d.Manifold
        self._meshlib: Optional[object] = None  # mrmeshpy.Mesh
        self._source_path: Optional[Path] = None

        if isinstance(source, (Path, str)):
            self._source_path = Path(source)
            self._load_from_file(self._source_path)
        elif isinstance(source, trimesh.Trimesh):
            self._trimesh = source
        elif isinstance(source, np.ndarray):
            raise ValueError("Direct numpy array initialization not yet supported")
        else:
            raise ValueError(f"Unsupported source type: {type(source)}")

    # === Lazy conversion between libraries ===

    @property
    def as_trimesh(self) -> trimesh.Trimesh:
        """Get trimesh representation (creates if needed)."""
        if self._trimesh is None:
            self._trimesh = self._convert_to_trimesh()
        return self._trimesh

    @property
    def as_manifold(self) -> object:
        """Get Manifold3D representation (creates if needed)."""
        if self._manifold is None:
            self._manifold = self._convert_to_manifold()
        return self._manifold

    @property
    def as_meshlib(self) -> object:
        """Get MeshLib representation (creates if needed)."""
        if self._meshlib is None:
            self._meshlib = self._convert_to_meshlib()
        return self._meshlib

    # === Geometric properties (via trimesh) ===

    @property
    def bounding_box(self) -> BoundingBox:
        """Get axis-aligned bounding box."""
        bounds = self.as_trimesh.bounds
        return BoundingBox(
            min_x=float(bounds[0][0]),
            max_x=float(bounds[1][0]),
            min_y=float(bounds[0][1]),
            max_y=float(bounds[1][1]),
            min_z=float(bounds[0][2]),
            max_z=float(bounds[1][2]),
        )

    @property
    def max_dimension(self) -> float:
        """Get the largest dimension."""
        return self.bounding_box.max_dimension

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        """Get dimensions (width, depth, height) in mm."""
        return self.bounding_box.dimensions

    @property
    def height(self) -> float:
        """Z-axis extent."""
        bbox = self.bounding_box
        return bbox.max_z - bbox.min_z

    @property
    def volume(self) -> float:
        """Get volume in mm³."""
        return float(self.as_trimesh.volume)

    @property
    def volume_cm3(self) -> float:
        """Get volume in cm³."""
        return self.volume / 1000.0

    @property
    def surface_area(self) -> float:
        """Get surface area in mm²."""
        return float(self.as_trimesh.area)

    @property
    def is_watertight(self) -> bool:
        """Check if mesh is watertight (manifold)."""
        return bool(self.as_trimesh.is_watertight)

    @property
    def face_normals(self) -> np.ndarray:
        """Get face normal vectors."""
        return self.as_trimesh.face_normals

    @property
    def face_areas(self) -> np.ndarray:
        """Get face areas."""
        return self.as_trimesh.area_faces

    @property
    def vertices(self) -> np.ndarray:
        """Get vertex positions."""
        return self.as_trimesh.vertices

    @property
    def faces(self) -> np.ndarray:
        """Get face indices."""
        return self.as_trimesh.faces

    def is_empty(self) -> bool:
        """Check if mesh has no geometry."""
        return self.as_trimesh.vertices.shape[0] == 0

    def fits_in_volume(self, limits: Tuple[float, float, float]) -> bool:
        """Check if mesh fits within build volume."""
        dims = self.dimensions
        return dims[0] <= limits[0] and dims[1] <= limits[1] and dims[2] <= limits[2]

    # === Operations ===

    def split(self, plane: CuttingPlane) -> Tuple["MeshWrapper", "MeshWrapper"]:
        """
        Split mesh along plane using Manifold3D.

        Returns (positive_half, negative_half) relative to plane normal.
        Manifold3D guarantees both halves are manifold with capped faces.
        """
        try:
            import manifold3d as m3d

            manifold = self.as_manifold

            # Calculate offset from origin along normal
            # offset = normal · origin
            offset = sum(n * o for n, o in zip(plane.normal, plane.origin))

            # Convert normal to manifold3d format (positional args)
            normal = plane.normal

            # Intersect with positive halfspace
            positive_manifold = manifold.trim_by_plane(normal, offset)

            # Intersect with negative halfspace (flip normal and offset)
            neg_normal = tuple(-n for n in plane.normal)
            negative_manifold = manifold.trim_by_plane(neg_normal, -offset)

            positive = MeshWrapper._from_manifold(positive_manifold)
            negative = MeshWrapper._from_manifold(negative_manifold)

            return (positive, negative)

        except ImportError:
            LOGGER.warning("manifold3d not available, falling back to trimesh")
            return self._split_trimesh(plane)

    def _split_trimesh(self, plane: CuttingPlane) -> Tuple["MeshWrapper", "MeshWrapper"]:
        """Fallback split using trimesh (may produce non-manifold results)."""
        mesh = self.as_trimesh

        # Use trimesh's slice_plane for cutting
        try:
            positive = mesh.slice_plane(
                plane_origin=plane.origin,
                plane_normal=plane.normal,
                cap=True,
            )
            negative = mesh.slice_plane(
                plane_origin=plane.origin,
                plane_normal=tuple(-n for n in plane.normal),
                cap=True,
            )

            if positive is None or positive.vertices.shape[0] == 0:
                positive = trimesh.Trimesh()
            if negative is None or negative.vertices.shape[0] == 0:
                negative = trimesh.Trimesh()

            return (MeshWrapper(positive), MeshWrapper(negative))

        except Exception as e:
            LOGGER.error(f"Trimesh split failed: {e}")
            return (MeshWrapper(trimesh.Trimesh()), MeshWrapper(trimesh.Trimesh()))

    def boolean_subtract(self, tool: "MeshWrapper") -> "MeshWrapper":
        """Boolean subtraction using Manifold3D."""
        try:
            import manifold3d as m3d

            result = m3d.Manifold.__sub__(self.as_manifold, tool.as_manifold)
            return MeshWrapper._from_manifold(result)
        except ImportError:
            LOGGER.warning("manifold3d not available for boolean operations")
            # Fallback to trimesh boolean (less reliable)
            result = self.as_trimesh.difference(tool.as_trimesh)
            return MeshWrapper(result)

    def boolean_union(self, other: "MeshWrapper") -> "MeshWrapper":
        """Boolean union using Manifold3D."""
        try:
            import manifold3d as m3d

            result = m3d.Manifold.__or__(self.as_manifold, other.as_manifold)
            return MeshWrapper._from_manifold(result)
        except ImportError:
            result = self.as_trimesh.union(other.as_trimesh)
            return MeshWrapper(result)

    def hollow(self, wall_thickness: float, voxel_size: float = 0.5) -> "MeshWrapper":
        """
        Create hollow shell using MeshLib SDF approach.

        Uses voxel-based signed distance field for robust self-intersection handling.
        """
        try:
            import mrmeshpy as mr

            mesh = self.as_meshlib

            # Configure offset parameters
            params = mr.OffsetParameters()
            params.voxelSize = min(voxel_size, wall_thickness / 5.0)
            params.type = mr.OffsetParametersType.Shell

            # Perform hollowing (negative thickness = inward offset)
            hollowed = mr.offsetMesh(mesh, -wall_thickness, params)

            if hollowed.topology.numValidFaces() == 0:
                LOGGER.warning("Hollowing collapsed, returning original mesh")
                return self

            return MeshWrapper._from_meshlib(hollowed)

        except ImportError:
            LOGGER.warning("mrmeshpy not available, skipping hollowing")
            return self
        except Exception as e:
            LOGGER.error(f"Hollowing failed: {e}")
            return self

    def center_at_origin(self) -> "MeshWrapper":
        """Center mesh at origin (Z on build plate)."""
        mesh = self.as_trimesh.copy()
        bbox = mesh.bounds
        center_xy = (bbox[0][:2] + bbox[1][:2]) / 2
        translation = np.array([-center_xy[0], -center_xy[1], -bbox[0][2]])
        mesh.apply_translation(translation)
        return MeshWrapper(mesh)

    # === Conversion methods ===

    def _load_from_file(self, path: Path) -> None:
        """Load mesh from STL or 3MF file."""
        if not path.exists():
            raise FileNotFoundError(f"Mesh file not found: {path}")

        try:
            loaded = trimesh.load(str(path), force="mesh")
            if isinstance(loaded, trimesh.Scene):
                # Flatten scene to single mesh
                self._trimesh = loaded.dump(concatenate=True)
            else:
                self._trimesh = loaded

            # Handle 3MF unit conversion to millimeters
            if path.suffix.lower() == ".3mf":
                scale = self._get_3mf_scale_to_mm(path)
                if scale != 1.0:
                    LOGGER.info(f"Scaling 3MF mesh by {scale}x to convert to mm")
                    self._trimesh.apply_scale(scale)

        except Exception as e:
            raise ValueError(f"Failed to load mesh from {path}: {e}")

    def _get_3mf_scale_to_mm(self, path: Path) -> float:
        """Get scale factor to convert 3MF units to millimeters."""
        import zipfile
        import xml.etree.ElementTree as ET

        # Unit conversion factors to mm
        unit_scales = {
            "millimeter": 1.0,
            "centimeter": 10.0,
            "meter": 1000.0,
            "inch": 25.4,
            "foot": 304.8,
            "micron": 0.001,
        }

        try:
            with zipfile.ZipFile(str(path), 'r') as z:
                content = z.read('3D/3dmodel.model')
                root = ET.fromstring(content)
                unit = root.attrib.get('unit', 'millimeter').lower()
                return unit_scales.get(unit, 1.0)
        except Exception as e:
            LOGGER.warning(f"Could not determine 3MF units, assuming mm: {e}")
            return 1.0

    def _convert_to_trimesh(self) -> trimesh.Trimesh:
        """Convert from other representations to trimesh."""
        if self._manifold is not None:
            try:
                import manifold3d as m3d

                mesh_data = self._manifold.to_mesh()
                verts = np.array(mesh_data.vert_properties)[:, :3]
                faces = np.array(mesh_data.tri_verts)
                return trimesh.Trimesh(vertices=verts, faces=faces)
            except Exception as e:
                LOGGER.error(f"Manifold to trimesh conversion failed: {e}")

        if self._meshlib is not None:
            # MeshLib to trimesh conversion
            try:
                import mrmeshpy as mr
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
                    mr.saveMesh(self._meshlib, f.name)
                    return trimesh.load(f.name, force="mesh")
            except Exception as e:
                LOGGER.error(f"MeshLib to trimesh conversion failed: {e}")

        raise ValueError("No source mesh available for conversion")

    def _convert_to_manifold(self) -> object:
        """Convert from trimesh to Manifold3D."""
        import manifold3d as m3d

        tm = self.as_trimesh

        # Ensure mesh is valid
        if not tm.is_watertight:
            LOGGER.warning("Mesh is not watertight, attempting repair")
            tm.fill_holes()

        mesh = m3d.Mesh(
            vert_properties=tm.vertices.astype(np.float32),
            tri_verts=tm.faces.astype(np.uint32),
        )
        return m3d.Manifold(mesh)

    def _convert_to_meshlib(self) -> object:
        """Convert from trimesh to MeshLib."""
        import mrmeshpy as mr
        import tempfile

        # Export trimesh to temporary STL and load in MeshLib
        tm = self.as_trimesh
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as f:
            tm.export(f.name)
            return mr.loadMesh(f.name)

    @classmethod
    def _from_manifold(cls, manifold: object) -> "MeshWrapper":
        """Create MeshWrapper from Manifold3D object."""
        wrapper = cls.__new__(cls)
        wrapper._trimesh = None
        wrapper._meshlib = None
        wrapper._manifold = manifold
        wrapper._source_path = None
        return wrapper

    @classmethod
    def _from_meshlib(cls, mesh: object) -> "MeshWrapper":
        """Create MeshWrapper from MeshLib object."""
        wrapper = cls.__new__(cls)
        wrapper._trimesh = None
        wrapper._meshlib = mesh
        wrapper._manifold = None
        wrapper._source_path = None
        return wrapper

    # === I/O ===

    def export(self, path: Union[Path, str], file_type: Optional[str] = None) -> None:
        """Export mesh to file (format inferred from extension)."""
        path = Path(path)
        self.as_trimesh.export(str(path), file_type=file_type)

    def copy(self) -> "MeshWrapper":
        """Create a deep copy of this mesh."""
        return MeshWrapper(self.as_trimesh.copy())

    @property
    def face_count(self) -> int:
        """Get number of faces/triangles."""
        return len(self.as_trimesh.faces)

    @property
    def vertex_count(self) -> int:
        """Get number of vertices."""
        return len(self.as_trimesh.vertices)

    def simplify(
        self,
        target_faces: Optional[int] = None,
        ratio: float = 0.5,
        preserve_topology: bool = True,
    ) -> "MeshWrapper":
        """
        Reduce triangle count while preserving mesh shape.

        Uses quadric decimation for high-quality simplification.

        Args:
            target_faces: Target number of faces (overrides ratio if set)
            ratio: Reduction ratio (0.5 = reduce to 50% of faces)
            preserve_topology: Try to preserve mesh topology (slower but safer)

        Returns:
            Simplified MeshWrapper
        """
        tm = self.as_trimesh.copy()
        current_faces = len(tm.faces)

        if target_faces is None:
            target_faces = int(current_faces * ratio)

        # Ensure we don't try to reduce below minimum viable mesh
        target_faces = max(target_faces, 100)

        if target_faces >= current_faces:
            LOGGER.debug(f"Mesh already has {current_faces} faces, no simplification needed")
            return MeshWrapper(tm)

        LOGGER.info(f"Simplifying mesh: {current_faces} -> {target_faces} faces ({target_faces/current_faces*100:.1f}%)")

        try:
            # Use trimesh's simplify_quadric_decimation with face_count parameter
            simplified = tm.simplify_quadric_decimation(face_count=target_faces)

            if simplified is None or len(simplified.faces) == 0:
                LOGGER.warning("Simplification failed, returning original mesh")
                return MeshWrapper(tm)

            LOGGER.info(f"Simplification complete: {len(simplified.faces)} faces")
            return MeshWrapper(simplified)

        except Exception as e:
            LOGGER.warning(f"Quadric decimation failed: {e}, trying fast_simplification directly")
            try:
                # Fallback: use fast_simplification directly
                import fast_simplification
                points, faces_out = fast_simplification.simplify(
                    tm.vertices.astype(np.float32),
                    tm.faces.astype(np.int32),
                    target_reduction=1.0 - ratio  # e.g., 0.7 reduction = keep 30%
                )
                simplified = trimesh.Trimesh(vertices=points, faces=faces_out)

                if len(simplified.faces) > 0:
                    LOGGER.info(f"fast_simplification complete: {len(simplified.faces)} faces")
                    return MeshWrapper(simplified)
            except Exception as e2:
                LOGGER.warning(f"fast_simplification also failed: {e2}")

            return MeshWrapper(tm)

    def smooth(self, iterations: int = 3, lamb: float = 0.5) -> "MeshWrapper":
        """
        Apply Laplacian smoothing to reduce jagged voxel artifacts.

        Args:
            iterations: Number of smoothing iterations (more = smoother but more distortion)
            lamb: Smoothing factor (0-1, higher = more smoothing per iteration)

        Returns:
            Smoothed MeshWrapper
        """
        tm = self.as_trimesh.copy()

        LOGGER.info(f"Smoothing mesh: {iterations} iterations, lambda={lamb}")

        try:
            # Laplacian smoothing
            smoothed = trimesh.smoothing.filter_laplacian(
                tm,
                lamb=lamb,
                iterations=iterations,
                implicit_time_integration=False,
                volume_constraint=True,  # Try to preserve volume
            )

            if smoothed is not None:
                LOGGER.info(f"Smoothing complete")
                return MeshWrapper(smoothed)

        except Exception as e:
            LOGGER.warning(f"Laplacian smoothing failed: {e}")

        return MeshWrapper(tm)

    def repair(
        self,
        remove_degenerate: bool = True,
        remove_elongated: bool = True,
        max_aspect_ratio: float = 20.0,
        fill_holes: bool = False,
    ) -> "MeshWrapper":
        """
        Repair mesh issues like degenerate triangles and non-manifold edges.

        Args:
            remove_degenerate: Remove degenerate (zero-area) triangles
            remove_elongated: Remove extremely elongated triangles ("icicles")
            max_aspect_ratio: Maximum allowed aspect ratio (longest/shortest edge)
            fill_holes: Attempt to fill holes in the mesh

        Returns:
            Repaired MeshWrapper
        """
        tm = self.as_trimesh.copy()
        original_faces = len(tm.faces)

        LOGGER.info(f"Repairing mesh: {original_faces} faces")

        try:
            if remove_degenerate:
                # Remove degenerate faces (zero area, collinear vertices)
                tm.remove_degenerate_faces()

                # Also remove faces with very small area (near-degenerate)
                face_areas = tm.area_faces
                min_area = 0.01  # mm² - faces smaller than this are degenerate
                valid_small = face_areas > min_area
                small_area_count = (~valid_small).sum()
                if small_area_count > 0:
                    tm.update_faces(valid_small)
                    tm.remove_unreferenced_vertices()
                    LOGGER.info(f"Removed {small_area_count} near-degenerate faces (area < {min_area}mm²)")

            if remove_elongated:
                # Remove extremely elongated triangles ("icicle" artifacts)
                # These are triangles where one edge is much longer than others
                vertices = tm.vertices
                faces = tm.faces
                valid_elongated = np.ones(len(faces), dtype=bool)

                # Calculate aspect ratio for each face
                for i, face in enumerate(faces):
                    v0, v1, v2 = vertices[face]
                    e0 = np.linalg.norm(v1 - v0)
                    e1 = np.linalg.norm(v2 - v1)
                    e2 = np.linalg.norm(v0 - v2)
                    edges = sorted([e0, e1, e2])
                    if edges[0] > 0.001:
                        aspect = edges[2] / edges[0]
                        if aspect > max_aspect_ratio:
                            valid_elongated[i] = False

                elongated_count = (~valid_elongated).sum()
                if elongated_count > 0:
                    tm.update_faces(valid_elongated)
                    tm.remove_unreferenced_vertices()
                    LOGGER.info(f"Removed {elongated_count} elongated faces (aspect ratio > {max_aspect_ratio})")

            # Remove unreferenced vertices after face removal
            tm.remove_unreferenced_vertices()

            if fill_holes:
                tm.fill_holes()

            final_faces = len(tm.faces)
            if final_faces != original_faces:
                LOGGER.info(f"Repair complete: {original_faces} -> {final_faces} faces")
            else:
                LOGGER.info(f"Repair complete: no changes needed")

            return MeshWrapper(tm)

        except Exception as e:
            LOGGER.warning(f"Mesh repair failed: {e}")
            return MeshWrapper(tm)

    def simplify_and_smooth(
        self,
        target_faces: Optional[int] = None,
        ratio: float = 0.5,
        smooth_iterations: int = 2,
    ) -> "MeshWrapper":
        """
        Combined simplification and smoothing for post-hollowing cleanup.

        Applies simplification first (to reduce triangle count),
        then smoothing (to reduce voxel artifacts).

        Args:
            target_faces: Target face count (overrides ratio)
            ratio: Reduction ratio if target_faces not set
            smooth_iterations: Number of smoothing iterations

        Returns:
            Simplified and smoothed MeshWrapper
        """
        result = self.simplify(target_faces=target_faces, ratio=ratio)
        if smooth_iterations > 0:
            result = result.smooth(iterations=smooth_iterations)
        return result
