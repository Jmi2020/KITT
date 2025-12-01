"""Integrated (printed) pin joint generation.

Creates alignment pins directly on the mesh surface - no external hardware needed.
One part gets cylindrical protrusions, the mating part gets matching holes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..schemas import JointLocation, JointType
from .base import JointConfig, JointFactory, JointPair

LOGGER = get_logger(__name__)


@dataclass
class IntegratedPinConfig(JointConfig):
    """Configuration for integrated printed pins."""

    pin_diameter_mm: float = 5.0  # Slightly larger than dowels for printability
    pin_height_mm: float = 8.0  # Height of protruding pin
    hole_depth_mm: float = 10.0  # Hole is deeper than pin for clearance
    # Tolerance/clearance for printed pins - accounts for layer expansion
    # Default 0.3mm works well for FDM prints
    # This is added to hole diameter (hole = pin_diameter + clearance)
    hole_clearance_mm: float = 0.3  # Clearance for printed fit
    taper_angle_deg: float = 2.0  # Slight taper for easier insertion
    min_joints_per_seam: int = 2
    max_joints_per_seam: int = 6
    target_joint_density: float = 0.0015  # joints per mm² of seam area


class IntegratedJointFactory(JointFactory):
    """
    Factory for generating integrated (printed) pin joints.

    Creates geometry that is directly added to the mesh:
    - Pin side: Cylindrical protrusion extending from cut face
    - Socket side: Matching hole with clearance for fit

    Benefits over external dowels:
    - No hardware to purchase or lose
    - Guaranteed alignment during print
    - Can be printed in one piece with the part
    - Slight taper helps with assembly
    """

    def __init__(self, config: IntegratedPinConfig = None):
        """Initialize integrated pin factory."""
        self.pin_config = config or IntegratedPinConfig()
        super().__init__(self.pin_config)

    def generate_joints(
        self,
        part_a: MeshWrapper,
        part_b: MeshWrapper,
        cut_plane: CuttingPlane,
        part_a_index: int,
        part_b_index: int,
    ) -> List[JointPair]:
        """
        Generate integrated pin joints for two adjacent parts.

        Part A receives protruding pins, Part B receives matching holes.
        """
        # Calculate seam area and determine number of joints
        seam_area = self.calculate_seam_area(part_a, cut_plane)
        num_joints = self._calculate_num_joints(seam_area)

        LOGGER.info(
            f"Generating {num_joints} integrated pins for seam "
            f"(area: {seam_area:.1f}mm²)"
        )

        # Find valid positions on the seam
        positions = self._find_joint_positions(part_a, cut_plane, num_joints)

        if not positions:
            LOGGER.warning("No valid joint positions found for integrated pins")
            return []

        # Create joint pairs
        joints = []
        for i, pos_3d in enumerate(positions):
            # Pin side (part A) - protruding cylinder
            # Negative depth indicates protrusion rather than hole
            pin_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm,
                depth_mm=-self.pin_config.pin_height_mm,  # Negative = protrusion
                part_index=part_a_index,
            )

            # Socket side (part B) - hole with clearance
            socket_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm + self.pin_config.hole_clearance_mm,
                depth_mm=self.pin_config.hole_depth_mm,  # Positive = hole
                part_index=part_b_index,
            )

            joints.append(
                JointPair(
                    part_a_index=part_a_index,
                    part_b_index=part_b_index,
                    location_a=pin_location,
                    location_b=socket_location,
                    joint_type=JointType.INTEGRATED,
                )
            )

        return joints

    def _calculate_num_joints(self, seam_area: float) -> int:
        """Calculate optimal number of joints based on seam area."""
        # Target density calculation
        target = int(seam_area * self.pin_config.target_joint_density)

        # Clamp to min/max range
        return max(
            self.pin_config.min_joints_per_seam,
            min(target, self.pin_config.max_joints_per_seam),
        )

    def _find_joint_positions(
        self,
        mesh: MeshWrapper,
        plane: CuttingPlane,
        num_joints: int,
    ) -> List[Tuple[float, float, float]]:
        """
        Find optimal positions for joints on the seam area.

        Uses Poisson disk sampling for even distribution with
        margin from edges to ensure printability.
        """
        # Get seam contour
        try:
            contour_points = self._get_seam_contour(mesh, plane)
            if len(contour_points) < 3:
                return []

            # Calculate centroid and bounds
            centroid = np.mean(contour_points, axis=0)

            # Use simple grid-based placement for reliability
            positions = self._place_joints_grid(
                contour_points, centroid, plane, num_joints
            )

            return positions

        except Exception as e:
            LOGGER.warning(f"Joint position calculation failed: {e}")
            return []

    def _get_seam_contour(
        self, mesh: MeshWrapper, plane: CuttingPlane
    ) -> np.ndarray:
        """Get the boundary contour of the seam area."""
        try:
            tm = mesh.as_trimesh
            # Slice mesh at plane to get contour
            slice_result = tm.section(
                plane_origin=plane.origin,
                plane_normal=plane.normal,
            )
            if slice_result is None:
                return np.array([])

            # Get vertices from the slice
            if hasattr(slice_result, "vertices"):
                return np.array(slice_result.vertices)
            return np.array([])

        except Exception as e:
            LOGGER.warning(f"Failed to get seam contour: {e}")
            return np.array([])

    def _place_joints_grid(
        self,
        contour: np.ndarray,
        centroid: np.ndarray,
        plane: CuttingPlane,
        num_joints: int,
    ) -> List[Tuple[float, float, float]]:
        """Place joints using grid pattern with inset from edges."""
        positions = []

        if num_joints <= 0:
            return positions

        # Calculate bounding box of contour
        min_pt = contour.min(axis=0)
        max_pt = contour.max(axis=0)

        # Inset margin (keep pins away from edges for strength)
        margin = self.pin_config.pin_diameter_mm * 2

        # Determine which axes to use based on plane normal
        normal = np.array(plane.normal)
        abs_normal = np.abs(normal)
        plane_axis = np.argmax(abs_normal)  # Axis perpendicular to plane

        # Get the two axes we'll place joints along
        axes = [i for i in range(3) if i != plane_axis]

        if num_joints == 1:
            # Single joint at centroid
            positions.append(tuple(centroid))
        elif num_joints == 2:
            # Two joints along longest axis
            span = max_pt - min_pt
            long_axis = axes[0] if span[axes[0]] > span[axes[1]] else axes[1]

            for offset in [-0.3, 0.3]:
                pos = centroid.copy()
                pos[long_axis] += offset * (span[long_axis] - 2 * margin)
                positions.append(tuple(pos))
        else:
            # Grid pattern for more joints
            span = max_pt - min_pt
            usable_span = span - 2 * margin

            # Calculate grid dimensions
            aspect = usable_span[axes[0]] / max(usable_span[axes[1]], 1)
            cols = max(1, int(np.sqrt(num_joints * aspect)))
            rows = max(1, int(num_joints / cols))

            for row in range(rows):
                for col in range(cols):
                    if len(positions) >= num_joints:
                        break

                    pos = centroid.copy()

                    # Distribute evenly with margin
                    if cols > 1:
                        t_col = col / (cols - 1) if cols > 1 else 0.5
                        pos[axes[0]] = min_pt[axes[0]] + margin + t_col * usable_span[axes[0]]
                    if rows > 1:
                        t_row = row / (rows - 1) if rows > 1 else 0.5
                        pos[axes[1]] = min_pt[axes[1]] + margin + t_row * usable_span[axes[1]]

                    positions.append(tuple(pos))

        return positions[:num_joints]

    def apply_joints_to_mesh(
        self,
        mesh: MeshWrapper,
        joints: List[JointLocation],
        is_pin_side: bool,
    ) -> MeshWrapper:
        """
        Apply joint geometry to a mesh.

        Args:
            mesh: The mesh to modify
            joints: Joint locations for this mesh
            is_pin_side: True to add pins, False to add holes

        Returns:
            Modified mesh with joint geometry
        """
        try:
            import manifold3d as m3d

            manifold = mesh.as_manifold

            for joint in joints:
                # Create cylinder for pin or hole
                radius = joint.diameter_mm / 2
                height = abs(joint.depth_mm)

                # Create cylinder primitive
                cylinder = m3d.Manifold.cylinder(
                    height=height,
                    radius_low=radius,
                    radius_high=radius * (0.95 if is_pin_side else 1.0),  # Slight taper on pins
                    circular_segments=32,
                )

                # Position the cylinder
                pos = joint.position

                if is_pin_side and joint.depth_mm < 0:
                    # Pin: union with mesh
                    # Translate cylinder to position (extending from surface)
                    cylinder = cylinder.translate([pos[0], pos[1], pos[2]])
                    manifold = manifold + cylinder
                else:
                    # Hole: subtract from mesh
                    # Translate cylinder to position (going into surface)
                    cylinder = cylinder.translate([pos[0], pos[1], pos[2] - height])
                    manifold = manifold - cylinder

            return MeshWrapper._from_manifold(manifold)

        except ImportError:
            LOGGER.warning("manifold3d not available for joint geometry")
            return mesh
        except Exception as e:
            LOGGER.error(f"Failed to apply joint geometry: {e}")
            return mesh


__all__ = ["IntegratedJointFactory", "IntegratedPinConfig"]
