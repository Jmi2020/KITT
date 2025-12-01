"""Cutting plane representation for mesh segmentation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple
import numpy as np


@dataclass
class CuttingPlane:
    """
    Represents a cutting plane in 3D space.

    A plane is defined by a point (origin) and a normal vector.
    The positive half-space is in the direction of the normal.
    """

    origin: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    plane_type: str = "vertical"  # vertical_x, vertical_y, horizontal, oblique
    seam_area: float = 0.0

    def __post_init__(self):
        """Normalize the normal vector."""
        n = np.array(self.normal)
        length = np.linalg.norm(n)
        if length > 0:
            self.normal = tuple(n / length)

    def flip(self) -> "CuttingPlane":
        """Return plane with inverted normal."""
        return CuttingPlane(
            origin=self.origin,
            normal=tuple(-n for n in self.normal),
            plane_type=self.plane_type,
            seam_area=self.seam_area,
        )

    @property
    def normal_array(self) -> np.ndarray:
        """Get normal as numpy array."""
        return np.array(self.normal)

    @property
    def origin_array(self) -> np.ndarray:
        """Get origin as numpy array."""
        return np.array(self.origin)

    @property
    def offset(self) -> float:
        """Calculate plane offset (d in ax + by + cz = d)."""
        return float(np.dot(self.normal_array, self.origin_array))

    @classmethod
    def from_axis(
        cls,
        axis: int,
        position: float,
        positive_direction: bool = True,
    ) -> "CuttingPlane":
        """
        Create an axis-aligned cutting plane.

        Args:
            axis: 0=X, 1=Y, 2=Z
            position: Position along the axis
            positive_direction: Normal points in positive direction

        Returns:
            CuttingPlane aligned to specified axis
        """
        origin = [0.0, 0.0, 0.0]
        origin[axis] = position

        normal = [0.0, 0.0, 0.0]
        normal[axis] = 1.0 if positive_direction else -1.0

        plane_types = {0: "vertical_x", 1: "vertical_y", 2: "horizontal"}

        return cls(
            origin=tuple(origin),
            normal=tuple(normal),
            plane_type=plane_types.get(axis, "oblique"),
        )

    @classmethod
    def vertical_x(cls, x_position: float) -> "CuttingPlane":
        """Create a vertical plane perpendicular to X axis."""
        return cls.from_axis(axis=0, position=x_position)

    @classmethod
    def vertical_y(cls, y_position: float) -> "CuttingPlane":
        """Create a vertical plane perpendicular to Y axis."""
        return cls.from_axis(axis=1, position=y_position)

    @classmethod
    def horizontal(cls, z_position: float) -> "CuttingPlane":
        """Create a horizontal plane perpendicular to Z axis."""
        return cls.from_axis(axis=2, position=z_position)

    def point_side(self, point: Tuple[float, float, float]) -> int:
        """
        Determine which side of the plane a point is on.

        Returns:
            1 if point is on positive side (in direction of normal)
            -1 if point is on negative side
            0 if point is on the plane (within epsilon)
        """
        p = np.array(point)
        d = np.dot(p - self.origin_array, self.normal_array)
        epsilon = 1e-6
        if d > epsilon:
            return 1
        elif d < -epsilon:
            return -1
        return 0
