"""Orientation optimizer for 3D print preparation.

Analyzes mesh geometry to find optimal print orientations that minimize
overhangs and support requirements.
"""

from pathlib import Path
from typing import List, Tuple, Optional, Dict
import time
import tempfile
import uuid

import numpy as np
import trimesh

from common.logging import get_logger

from .schemas import OrientationOption

LOGGER = get_logger(__name__)


# Rotation matrices for 6 cardinal orientations
# These rotate the mesh so the specified axis points up (Z+)
CARDINAL_ORIENTATIONS: Dict[str, Dict] = {
    "z_up": {
        "label": "Z-Up (Original)",
        "up_vector": (0.0, 0.0, 1.0),
        "rotation_matrix": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
    },
    "z_down": {
        "label": "Z-Down (Flipped)",
        "up_vector": (0.0, 0.0, -1.0),
        "rotation_matrix": [
            [1.0, 0.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, -1.0],
        ],
    },
    "y_up": {
        "label": "Y-Up (Front Down)",
        "up_vector": (0.0, 1.0, 0.0),
        "rotation_matrix": [
            [1.0, 0.0, 0.0],
            [0.0, 0.0, -1.0],
            [0.0, 1.0, 0.0],
        ],
    },
    "y_down": {
        "label": "Y-Down (Front Up)",
        "up_vector": (0.0, -1.0, 0.0),
        "rotation_matrix": [
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, -1.0, 0.0],
        ],
    },
    "x_up": {
        "label": "X-Up (Side Down)",
        "up_vector": (1.0, 0.0, 0.0),
        "rotation_matrix": [
            [0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
            [-1.0, 0.0, 0.0],
        ],
    },
    "x_down": {
        "label": "X-Down (Side Up)",
        "up_vector": (-1.0, 0.0, 0.0),
        "rotation_matrix": [
            [0.0, 0.0, -1.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
        ],
    },
}


class OrientationOptimizer:
    """
    Analyzes mesh orientations to find optimal print orientation.

    Tests multiple orientations and scores them by overhang ratio.
    Lower overhang ratio = less support material = better for printing.
    """

    def __init__(self, threshold_angle: float = 45.0):
        """
        Initialize optimizer.

        Args:
            threshold_angle: Angle from vertical considered overhang (degrees).
                             Faces steeper than this require support.
                             Default 45 degrees is standard for FDM printing.
        """
        self.threshold_angle = threshold_angle
        self._temp_dir = Path(tempfile.gettempdir()) / "kitty_orientation"
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def load_mesh(self, mesh_path: str) -> trimesh.Trimesh:
        """
        Load mesh from file path.

        Args:
            mesh_path: Path to STL, GLB, or 3MF file

        Returns:
            Loaded trimesh object
        """
        path = Path(mesh_path)
        if not path.exists():
            raise FileNotFoundError(f"Mesh file not found: {mesh_path}")

        # Handle different file types
        suffix = path.suffix.lower()

        if suffix == ".3mf":
            # 3MF files may contain multiple meshes - combine them
            scene = trimesh.load(str(path))
            if isinstance(scene, trimesh.Scene):
                meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if not meshes:
                    raise ValueError("No valid meshes found in 3MF file")
                if len(meshes) == 1:
                    return meshes[0]
                # Combine multiple meshes
                return trimesh.util.concatenate(meshes)
            return scene
        elif suffix == ".glb" or suffix == ".gltf":
            scene = trimesh.load(str(path))
            if isinstance(scene, trimesh.Scene):
                meshes = [g for g in scene.geometry.values() if isinstance(g, trimesh.Trimesh)]
                if not meshes:
                    raise ValueError("No valid meshes found in GLB file")
                if len(meshes) == 1:
                    return meshes[0]
                return trimesh.util.concatenate(meshes)
            return scene
        else:
            # STL and other formats
            mesh = trimesh.load(str(path))
            if isinstance(mesh, trimesh.Scene):
                meshes = list(mesh.geometry.values())
                if meshes:
                    return meshes[0]
            return mesh

    def calculate_overhang_ratio(
        self,
        mesh: trimesh.Trimesh,
        up_vector: np.ndarray,
        threshold_angle: Optional[float] = None,
    ) -> float:
        """
        Calculate overhang ratio for a mesh with given up vector.

        Overhangs are faces pointing more than threshold_angle away from
        the up vector (i.e., faces that would need support during printing).

        Args:
            mesh: Trimesh to analyze
            up_vector: Unit vector indicating "up" direction
            threshold_angle: Override default threshold angle

        Returns:
            Ratio of surface area needing support (0.0 to 1.0)
        """
        threshold = threshold_angle or self.threshold_angle

        try:
            normals = mesh.face_normals
            areas = mesh.area_faces

            # Normalize up vector
            up = np.array(up_vector)
            up = up / np.linalg.norm(up)

            # Calculate dot product with up vector
            # Positive = facing up, Negative = facing down
            cos_angles = np.dot(normals, up)

            # Find downward-facing faces (opposite to up vector)
            downward_mask = cos_angles < 0

            if not np.any(downward_mask):
                return 0.0  # No overhangs

            # Calculate angle from horizontal for downward faces
            # cos_angle = cos(angle from up) -> angle from horizontal = 90 - angle from up
            overhang_angles = np.degrees(np.arccos(np.abs(cos_angles[downward_mask])))

            # Faces with angle > threshold need support
            overhang_threshold_mask = overhang_angles > threshold
            overhang_area = np.sum(areas[downward_mask][overhang_threshold_mask])
            total_area = np.sum(areas)

            return float(overhang_area / total_area) if total_area > 0 else 0.0

        except Exception as e:
            LOGGER.warning(f"Overhang calculation failed: {e}")
            return 0.0

    def _ratio_to_estimate(self, ratio: float) -> str:
        """Convert overhang ratio to human-readable estimate."""
        if ratio < 0.01:
            return "none"
        elif ratio < 0.10:
            return "minimal"
        elif ratio < 0.30:
            return "moderate"
        else:
            return "significant"

    def analyze_orientations(
        self,
        mesh_path: str,
        include_intermediate: bool = False,
    ) -> Tuple[List[OrientationOption], trimesh.Trimesh]:
        """
        Analyze all orientations for a mesh.

        Args:
            mesh_path: Path to mesh file
            include_intermediate: Include 45-degree rotations (not yet implemented)

        Returns:
            Tuple of (list of orientation options sorted by overhang ratio, loaded mesh)
        """
        mesh = self.load_mesh(mesh_path)

        results: List[OrientationOption] = []

        for orient_id, orient_data in CARDINAL_ORIENTATIONS.items():
            up_vector = np.array(orient_data["up_vector"])
            overhang_ratio = self.calculate_overhang_ratio(mesh, up_vector)

            results.append(OrientationOption(
                id=orient_id,
                label=orient_data["label"],
                rotation_matrix=orient_data["rotation_matrix"],
                up_vector=orient_data["up_vector"],
                overhang_ratio=round(overhang_ratio, 4),
                support_estimate=self._ratio_to_estimate(overhang_ratio),
                is_recommended=False,
            ))

        # Sort by overhang ratio (ascending - lower is better)
        results.sort(key=lambda x: x.overhang_ratio)

        # Mark the best one
        if results:
            results[0].is_recommended = True

        return results, mesh

    def get_best_orientation(self, mesh_path: str) -> OrientationOption:
        """
        Get the single best orientation for a mesh.

        Args:
            mesh_path: Path to mesh file

        Returns:
            Best orientation option
        """
        results, _ = self.analyze_orientations(mesh_path)
        return results[0]

    def apply_orientation(
        self,
        mesh: trimesh.Trimesh,
        rotation_matrix: List[List[float]],
    ) -> trimesh.Trimesh:
        """
        Apply rotation matrix to mesh.

        Args:
            mesh: Original mesh
            rotation_matrix: 3x3 rotation matrix

        Returns:
            New rotated mesh (original is not modified)
        """
        # Create a copy
        rotated = mesh.copy()

        # Build 4x4 transformation matrix from 3x3 rotation
        transform = np.eye(4)
        transform[:3, :3] = np.array(rotation_matrix)

        # Apply transformation
        rotated.apply_transform(transform)

        return rotated

    def save_oriented_mesh(
        self,
        mesh: trimesh.Trimesh,
        rotation_matrix: List[List[float]],
        original_path: str,
    ) -> str:
        """
        Apply orientation and save to temp file.

        Args:
            mesh: Original mesh
            rotation_matrix: 3x3 rotation matrix
            original_path: Original file path (for naming)

        Returns:
            Path to saved oriented mesh
        """
        rotated = self.apply_orientation(mesh, rotation_matrix)

        # Generate output filename
        original_name = Path(original_path).stem
        output_name = f"{original_name}_oriented_{uuid.uuid4().hex[:8]}.stl"
        output_path = self._temp_dir / output_name

        # Export as STL (universal format)
        rotated.export(str(output_path))

        LOGGER.info(f"Saved oriented mesh to: {output_path}")
        return str(output_path)

    def get_mesh_dimensions(self, mesh: trimesh.Trimesh) -> Tuple[float, float, float]:
        """
        Get mesh dimensions (width, depth, height).

        Args:
            mesh: Mesh to measure

        Returns:
            Tuple of (width, depth, height) in mm
        """
        bounds = mesh.bounds
        dims = bounds[1] - bounds[0]
        return (round(dims[0], 2), round(dims[1], 2), round(dims[2], 2))
