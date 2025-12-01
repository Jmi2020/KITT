"""Base class for joint generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Tuple

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..schemas import JointLocation, JointType

LOGGER = get_logger(__name__)


@dataclass
class JointPair:
    """A pair of joint locations (hole and pin or key and slot)."""

    part_a_index: int
    part_b_index: int
    location_a: JointLocation  # Joint feature in part A
    location_b: JointLocation  # Matching feature in part B
    joint_type: JointType


@dataclass
class JointConfig:
    """Configuration for joint generation."""

    joint_type: JointType = JointType.DOWEL
    tolerance_mm: float = 0.2  # Clearance for fit
    min_edge_distance_mm: float = 5.0  # Minimum distance from part edge
    min_joint_spacing_mm: float = 15.0  # Minimum spacing between joints


class JointFactory(ABC):
    """
    Abstract factory for generating joints between mesh parts.

    Joint factories create matching features (holes, keys, etc.) on
    adjacent parts to enable accurate assembly.
    """

    def __init__(self, config: JointConfig):
        """Initialize factory with configuration."""
        self.config = config

    @abstractmethod
    def generate_joints(
        self,
        part_a: MeshWrapper,
        part_b: MeshWrapper,
        cut_plane: CuttingPlane,
        part_a_index: int,
        part_b_index: int,
    ) -> List[JointPair]:
        """
        Generate joints for two adjacent parts.

        Args:
            part_a: First part (on positive side of cut)
            part_b: Second part (on negative side of cut)
            cut_plane: The plane where parts meet
            part_a_index: Index of first part
            part_b_index: Index of second part

        Returns:
            List of JointPairs with locations on both parts
        """
        pass

    @abstractmethod
    def apply_joints_to_mesh(
        self, mesh: MeshWrapper, joints: List[JointLocation]
    ) -> MeshWrapper:
        """
        Apply joint features (holes, keys, etc.) to a mesh.

        Args:
            mesh: Mesh to modify
            joints: Joint locations to add

        Returns:
            Modified mesh with joint features
        """
        pass

    def find_seam_intersection(
        self, mesh: MeshWrapper, plane: CuttingPlane
    ) -> List[Tuple[float, float, float]]:
        """
        Find the outline where mesh intersects cutting plane.

        Returns vertices on or near the cutting plane.
        """
        import numpy as np

        vertices = mesh.vertices
        origin = np.array(plane.origin)
        normal = np.array(plane.normal)

        # Calculate signed distance of each vertex to plane
        distances = np.dot(vertices - origin, normal)

        # Find vertices close to plane
        tolerance = 0.5  # mm
        near_plane_mask = np.abs(distances) < tolerance
        seam_vertices = vertices[near_plane_mask]

        return [tuple(v) for v in seam_vertices]

    def calculate_seam_area(
        self, mesh: MeshWrapper, plane: CuttingPlane
    ) -> float:
        """
        Calculate the area of the seam between parts.

        Uses intersection of mesh with cutting plane.
        """
        try:
            import trimesh

            tm = mesh.as_trimesh

            # Get cross-section at cutting plane
            section = tm.section(
                plane_origin=plane.origin,
                plane_normal=plane.normal,
            )

            if section is None:
                return 0.0

            # Convert to 2D path and calculate area
            planar, _ = section.to_planar()
            if planar is None:
                return 0.0

            return float(planar.area)

        except Exception as e:
            LOGGER.warning(f"Failed to calculate seam area: {e}")
            return 0.0

    def poisson_disk_sample(
        self,
        bounds_2d: Tuple[float, float, float, float],  # min_x, max_x, min_y, max_y
        min_distance: float,
        max_samples: int = 50,
    ) -> List[Tuple[float, float]]:
        """
        Generate well-distributed 2D points using Poisson disk sampling.

        Args:
            bounds_2d: Bounding rectangle (min_x, max_x, min_y, max_y)
            min_distance: Minimum distance between points
            max_samples: Maximum number of points to generate

        Returns:
            List of 2D points
        """
        import numpy as np

        min_x, max_x, min_y, max_y = bounds_2d
        width = max_x - min_x
        height = max_y - min_y

        if width < min_distance or height < min_distance:
            # Area too small, return center point
            return [((min_x + max_x) / 2, (min_y + max_y) / 2)]

        # Simple grid-based Poisson disk approximation
        cell_size = min_distance / np.sqrt(2)
        cols = int(np.ceil(width / cell_size))
        rows = int(np.ceil(height / cell_size))

        grid = [[None for _ in range(cols)] for _ in range(rows)]
        points: List[Tuple[float, float]] = []
        active: List[Tuple[float, float]] = []

        # Start with center point
        start = ((min_x + max_x) / 2, (min_y + max_y) / 2)
        points.append(start)
        active.append(start)

        col = int((start[0] - min_x) / cell_size)
        row = int((start[1] - min_y) / cell_size)
        if 0 <= row < rows and 0 <= col < cols:
            grid[row][col] = start

        while active and len(points) < max_samples:
            idx = np.random.randint(len(active))
            point = active[idx]

            found = False
            for _ in range(30):  # 30 attempts per point
                angle = np.random.uniform(0, 2 * np.pi)
                radius = np.random.uniform(min_distance, 2 * min_distance)

                new_x = point[0] + radius * np.cos(angle)
                new_y = point[1] + radius * np.sin(angle)

                # Check bounds
                if new_x < min_x or new_x > max_x or new_y < min_y or new_y > max_y:
                    continue

                # Check distance to existing points
                col = int((new_x - min_x) / cell_size)
                row = int((new_y - min_y) / cell_size)

                if not (0 <= row < rows and 0 <= col < cols):
                    continue

                # Check neighbors
                valid = True
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        nr, nc = row + dr, col + dc
                        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc]:
                            neighbor = grid[nr][nc]
                            dist = np.sqrt(
                                (new_x - neighbor[0]) ** 2 + (new_y - neighbor[1]) ** 2
                            )
                            if dist < min_distance:
                                valid = False
                                break
                    if not valid:
                        break

                if valid:
                    new_point = (new_x, new_y)
                    points.append(new_point)
                    active.append(new_point)
                    grid[row][col] = new_point
                    found = True
                    break

            if not found:
                active.pop(idx)

        return points
