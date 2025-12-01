"""Dowel pin joint generation."""

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
class DowelConfig(JointConfig):
    """Configuration for dowel joints."""

    diameter_mm: float = 4.0
    depth_mm: float = 10.0
    hole_clearance_mm: float = 0.2  # Extra diameter for receiving hole
    min_joints_per_seam: int = 2
    max_joints_per_seam: int = 6
    target_joint_density: float = 0.002  # joints per mm² of seam area


class DowelJointFactory(JointFactory):
    """
    Factory for generating dowel pin joints.

    Creates cylindrical holes in both parts:
    - Pin side: Tight hole for press-fit dowel
    - Socket side: Slightly larger hole with clearance
    """

    def __init__(self, config: DowelConfig = None):
        """Initialize dowel factory."""
        self.dowel_config = config or DowelConfig()
        super().__init__(self.dowel_config)

    def generate_joints(
        self,
        part_a: MeshWrapper,
        part_b: MeshWrapper,
        cut_plane: CuttingPlane,
        part_a_index: int,
        part_b_index: int,
    ) -> List[JointPair]:
        """
        Generate dowel joints for two adjacent parts.

        Places dowels using Poisson disk sampling on the seam area
        for even distribution.
        """
        # Calculate seam area and determine number of joints
        seam_area = self.calculate_seam_area(part_a, cut_plane)
        num_joints = self._calculate_num_joints(seam_area)

        LOGGER.info(
            f"Generating {num_joints} dowel joints for seam "
            f"(area: {seam_area:.1f}mm²)"
        )

        # Find valid positions on the seam
        positions = self._find_joint_positions(part_a, cut_plane, num_joints)

        if not positions:
            LOGGER.warning("No valid joint positions found")
            return []

        # Create joint pairs
        joints = []
        for i, pos_3d in enumerate(positions):
            # Pin side (part A) - tight fit
            pin_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.dowel_config.diameter_mm,
                depth_mm=self.dowel_config.depth_mm,
                part_index=part_a_index,
            )

            # Socket side (part B) - with clearance
            socket_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.dowel_config.diameter_mm + self.dowel_config.hole_clearance_mm,
                depth_mm=self.dowel_config.depth_mm,
                part_index=part_b_index,
            )

            joints.append(
                JointPair(
                    part_a_index=part_a_index,
                    part_b_index=part_b_index,
                    location_a=pin_location,
                    location_b=socket_location,
                    joint_type=JointType.DOWEL,
                )
            )

        return joints

    def apply_joints_to_mesh(
        self, mesh: MeshWrapper, joints: List[JointLocation]
    ) -> MeshWrapper:
        """
        Apply dowel holes to a mesh.

        Creates cylindrical holes at each joint location.
        """
        if not joints:
            return mesh

        try:
            import trimesh

            result = mesh.as_trimesh.copy()

            for joint in joints:
                # Create cylinder for hole
                cylinder = trimesh.creation.cylinder(
                    radius=joint.diameter_mm / 2,
                    height=joint.depth_mm * 1.5,  # Extra depth for clean cut
                    sections=24,  # Smooth cylinder
                )

                # Position cylinder at joint location
                # Cylinder is created along Z axis, need to orient based on surface normal
                # For now, assume holes are perpendicular to cut plane (Z-aligned for horizontal, etc.)
                cylinder.apply_translation(joint.position)

                # Boolean subtraction to create hole
                try:
                    result = result.difference(cylinder)
                except Exception as e:
                    LOGGER.warning(f"Boolean subtraction failed for joint at {joint.position}: {e}")
                    continue

            return MeshWrapper(result)

        except Exception as e:
            LOGGER.error(f"Failed to apply joints to mesh: {e}")
            return mesh

    def _calculate_num_joints(self, seam_area: float) -> int:
        """Calculate number of joints based on seam area."""
        # Target density based joints
        target = int(seam_area * self.dowel_config.target_joint_density)

        # Clamp to min/max
        return max(
            self.dowel_config.min_joints_per_seam,
            min(target, self.dowel_config.max_joints_per_seam),
        )

    def _find_joint_positions(
        self,
        mesh: MeshWrapper,
        plane: CuttingPlane,
        num_joints: int,
    ) -> List[Tuple[float, float, float]]:
        """
        Find valid positions for joints on the seam.

        Uses cross-section of mesh with cutting plane and
        places joints using Poisson disk sampling.
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
                return self._fallback_positions(mesh, plane, num_joints)

            # Convert to 2D for sampling
            planar, transform = section.to_planar()
            if planar is None:
                return self._fallback_positions(mesh, plane, num_joints)

            # Get bounds of cross-section
            bounds = planar.bounds
            if bounds is None:
                return self._fallback_positions(mesh, plane, num_joints)

            # Shrink bounds by edge margin
            margin = self.dowel_config.min_edge_distance_mm
            bounds_2d = (
                bounds[0][0] + margin,
                bounds[1][0] - margin,
                bounds[0][1] + margin,
                bounds[1][1] - margin,
            )

            # Check if bounds are valid after margin
            if bounds_2d[1] <= bounds_2d[0] or bounds_2d[3] <= bounds_2d[2]:
                # Seam too small for margin, use center
                center_2d = (
                    (bounds[0][0] + bounds[1][0]) / 2,
                    (bounds[0][1] + bounds[1][1]) / 2,
                )
                positions_2d = [center_2d]
            else:
                # Generate positions using Poisson disk sampling
                positions_2d = self.poisson_disk_sample(
                    bounds_2d,
                    self.dowel_config.min_joint_spacing_mm,
                    num_joints,
                )

            # Transform 2D positions back to 3D
            positions_3d = []
            inv_transform = np.linalg.inv(transform)

            for pos_2d in positions_2d:
                # Create 3D point on the 2D plane
                pt_2d = np.array([pos_2d[0], pos_2d[1], 0, 1])
                pt_3d = inv_transform @ pt_2d
                positions_3d.append((float(pt_3d[0]), float(pt_3d[1]), float(pt_3d[2])))

            # Validate positions are inside mesh cross-section
            valid_positions = []
            for pos_3d in positions_3d:
                # Project back to 2D for containment check
                pt_3d = np.array([pos_3d[0], pos_3d[1], pos_3d[2], 1])
                pt_2d = transform @ pt_3d
                point_2d = [pt_2d[0], pt_2d[1]]

                # Check if point is inside the cross-section polygon
                if self._point_in_polygon(point_2d, planar):
                    valid_positions.append(pos_3d)

            if not valid_positions:
                return self._fallback_positions(mesh, plane, num_joints)

            return valid_positions[:num_joints]

        except Exception as e:
            LOGGER.warning(f"Joint position finding failed: {e}")
            return self._fallback_positions(mesh, plane, num_joints)

    def _point_in_polygon(self, point: List[float], path) -> bool:
        """Check if a 2D point is inside a path polygon."""
        try:
            from shapely.geometry import Point

            shapely_point = Point(point[0], point[1])

            # Get polygons from path
            for polygon in path.polygons_full:
                if polygon.contains(shapely_point):
                    return True
            return False
        except Exception:
            # If Shapely not available, assume valid
            return True

    def _fallback_positions(
        self,
        mesh: MeshWrapper,
        plane: CuttingPlane,
        num_joints: int,
    ) -> List[Tuple[float, float, float]]:
        """
        Fallback joint positions based on bounding box.

        Used when cross-section analysis fails.
        """
        bbox = mesh.bounding_box
        origin = np.array(plane.origin)
        normal = np.array(plane.normal)

        # Determine which axes are perpendicular to normal
        # (these define the seam plane)
        abs_normal = np.abs(normal)
        primary_axis = np.argmax(abs_normal)

        positions = []

        if primary_axis == 0:  # X cut - spread along Y and Z
            y_range = (bbox.min_y + 10, bbox.max_y - 10)
            z_range = (bbox.min_z + 10, bbox.max_z - 10)
            x = origin[0]

            if num_joints == 1:
                positions.append((x, (y_range[0] + y_range[1]) / 2, (z_range[0] + z_range[1]) / 2))
            else:
                # Grid pattern
                for y in np.linspace(y_range[0], y_range[1], min(3, num_joints)):
                    positions.append((x, float(y), (z_range[0] + z_range[1]) / 2))

        elif primary_axis == 1:  # Y cut - spread along X and Z
            x_range = (bbox.min_x + 10, bbox.max_x - 10)
            z_range = (bbox.min_z + 10, bbox.max_z - 10)
            y = origin[1]

            if num_joints == 1:
                positions.append(((x_range[0] + x_range[1]) / 2, y, (z_range[0] + z_range[1]) / 2))
            else:
                for x in np.linspace(x_range[0], x_range[1], min(3, num_joints)):
                    positions.append((float(x), y, (z_range[0] + z_range[1]) / 2))

        else:  # Z cut - spread along X and Y
            x_range = (bbox.min_x + 10, bbox.max_x - 10)
            y_range = (bbox.min_y + 10, bbox.max_y - 10)
            z = origin[2]

            if num_joints == 1:
                positions.append(((x_range[0] + x_range[1]) / 2, (y_range[0] + y_range[1]) / 2, z))
            else:
                for x in np.linspace(x_range[0], x_range[1], min(3, num_joints)):
                    positions.append((float(x), (y_range[0] + y_range[1]) / 2, z))

        return positions[:num_joints]
