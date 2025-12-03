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

    pin_diameter_mm: float = 8.0  # Pin diameter (must fit within wall thickness)
    pin_height_mm: float = 10.0  # Height of protruding pin
    hole_depth_mm: float = 12.0  # Hole is deeper than pin for clearance
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
        # Get the cut plane normal for cylinder orientation
        plane_normal = cut_plane.normal

        for i, pos_3d in enumerate(positions):
            # PrusaSlicer approach: connector SPANS the cut plane
            # Position is on the seam; we'll center the connector there
            # Both pin and hole use the SAME position - the cut plane boundary
            # The geometry application handles the spanning behavior

            # Pin side (part A) - exact dimensions
            # Pin will be unioned to Part A, spanning into where Part B was
            pin_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm,
                depth_mm=-self.pin_config.pin_height_mm,  # Negative = protrusion (union)
                part_index=part_a_index,
                normal=plane_normal,  # Points toward Part B
            )

            # Socket side (part B) - ENLARGED by clearance (both radius AND depth)
            # Socket will be subtracted from Part B
            # Clearance ensures the pin fits with room to spare
            socket_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm + (self.pin_config.hole_clearance_mm * 2),  # Clearance on diameter (both sides)
                depth_mm=self.pin_config.pin_height_mm + self.pin_config.hole_clearance_mm,  # Match pin height + clearance
                part_index=part_b_index,
                normal=tuple(-n for n in plane_normal),  # Points into Part B
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
        """
        Place joints ON the mesh boundary (wall material), not in the interior.

        For hollow shells, the seam cross-section is a ring shape (wall only).
        Pins must be placed at positions that intersect solid material, which
        means at the OUTER boundary of the mesh where walls exist.
        """
        positions = []

        if num_joints <= 0 or len(contour) < 3:
            return positions

        # Determine which axis is perpendicular to the plane
        normal = np.array(plane.normal)
        abs_normal = np.abs(normal)
        plane_axis = np.argmax(abs_normal)

        # Get the two in-plane axes
        axes = [i for i in range(3) if i != plane_axis]

        # For hollow shells, we need to place pins at OUTER BOUNDARY positions
        # The contour may contain both outer and inner perimeter points
        # Filter to only include points at the mesh extremes (outer walls)

        contour_2d = contour[:, axes]

        # Find the bounding box of the contour
        min_coords = contour_2d.min(axis=0)
        max_coords = contour_2d.max(axis=0)

        # Wall thickness tolerance (slightly larger to catch boundary points)
        wall_tol = 5.0  # mm - generous tolerance to catch outer wall points

        # Filter points that are on the OUTER boundary (near min/max coordinates)
        # A point is on the outer boundary if either coordinate is near min or max
        on_boundary = (
            (contour_2d[:, 0] < min_coords[0] + wall_tol) |
            (contour_2d[:, 0] > max_coords[0] - wall_tol) |
            (contour_2d[:, 1] < min_coords[1] + wall_tol) |
            (contour_2d[:, 1] > max_coords[1] - wall_tol)
        )

        boundary_points = contour[on_boundary]

        if len(boundary_points) < num_joints:
            LOGGER.warning(
                f"Only {len(boundary_points)} boundary points found, "
                f"using all contour points for joint placement"
            )
            boundary_points = contour

        LOGGER.debug(
            f"Filtered {len(contour)} contour points to {len(boundary_points)} boundary points"
        )

        # Now place joints evenly distributed among boundary points
        # Sort boundary points by angle from centroid to get consistent ordering
        centroid_2d = np.mean(boundary_points[:, axes], axis=0)
        boundary_2d = boundary_points[:, axes]
        angles = np.arctan2(
            boundary_2d[:, 1] - centroid_2d[1],
            boundary_2d[:, 0] - centroid_2d[0]
        )
        sorted_indices = np.argsort(angles)
        sorted_boundary = boundary_points[sorted_indices]

        # Select evenly spaced points
        n_boundary = len(sorted_boundary)
        if n_boundary <= num_joints:
            # Use all boundary points
            indices = list(range(n_boundary))
        else:
            # Select evenly spaced indices
            indices = [int(i * n_boundary / num_joints) for i in range(num_joints)]

        for idx in indices[:num_joints]:
            pos = sorted_boundary[idx]
            positions.append(tuple(pos))

        return positions

    def apply_joints_to_mesh(
        self,
        mesh: MeshWrapper,
        joints: List[JointLocation],
        is_pin_side: bool = False,  # Deprecated - now determined per-joint from depth_mm
    ) -> MeshWrapper:
        """
        Apply joint geometry to a mesh.

        Args:
            mesh: The mesh to modify
            joints: Joint locations for this mesh
            is_pin_side: Deprecated - pin vs hole is now determined per-joint from depth_mm

        Returns:
            Modified mesh with joint geometry
        """
        try:
            import manifold3d as m3d

            manifold = mesh.as_manifold
            pins_added = 0
            holes_added = 0

            for joint in joints:
                # Determine if this joint is a pin or hole from its depth
                # Negative depth = pin (protrusion), Positive depth = hole (cavity)
                is_pin = joint.depth_mm < 0

                # Create cylinder for pin or hole
                radius = joint.diameter_mm / 2
                height = abs(joint.depth_mm)

                # Create cylinder primitive (created along Z axis by default)
                cylinder = m3d.Manifold.cylinder(
                    height=height,
                    radius_low=radius,
                    radius_high=radius * (0.95 if is_pin else 1.0),  # Slight taper on pins
                    circular_segments=32,
                )

                # Orient cylinder along the joint normal (perpendicular to cut plane)
                normal = np.array(joint.normal)
                cylinder = self._orient_cylinder(cylinder, normal, height, is_pin=is_pin)

                # Position the cylinder at the joint location
                pos = joint.position
                cylinder = cylinder.translate([pos[0], pos[1], pos[2]])

                if is_pin:
                    # Pin: union with mesh (protrusion from surface)
                    manifold = manifold + cylinder
                    pins_added += 1
                else:
                    # Hole: subtract from mesh (cavity into surface)
                    manifold = manifold - cylinder
                    holes_added += 1

            LOGGER.info(f"Applied {pins_added} pins and {holes_added} holes to mesh")
            return MeshWrapper._from_manifold(manifold)

        except ImportError:
            LOGGER.warning("manifold3d not available for joint geometry")
            return mesh
        except Exception as e:
            LOGGER.error(f"Failed to apply joint geometry: {e}")
            return mesh

    def _orient_cylinder(
        self, cylinder, target_normal: np.ndarray, height: float, is_pin: bool = False
    ):
        """
        Orient a cylinder to align with target normal.

        PrusaSlicer approach: connector geometry SPANS the cut plane.
        - Pin: extends from joint position INTO where the other part was (outward)
        - Hole: extends from joint position INTO this part (inward)

        The joint position is ON the cut plane boundary. Both pin and hole
        start there and extend in opposite directions.

        Args:
            cylinder: Manifold cylinder (created along Z axis with base at z=0)
            target_normal: Direction the cylinder should point
            height: Height of cylinder
            is_pin: True if this is a pin (protrusion), False if hole (cavity)

        Returns:
            Positioned and rotated cylinder
        """
        # Normalize target
        target_normal = target_normal / np.linalg.norm(target_normal)

        # Default cylinder axis is Z (0, 0, 1)
        z_axis = np.array([0.0, 0.0, 1.0])

        # Position cylinder so it extends FROM the cut plane boundary
        # Manifold3D creates cylinder with base at z=0, top at z=height
        # Overlap ensures clean boolean operations (geometry penetrates mesh surface)
        overlap = 1.0  # mm - overlap into the mesh for clean boolean

        if is_pin:
            # Pin: extends OUTWARD from cut plane (into where Part B was)
            # Base starts slightly inside Part A (-overlap), extends to +height
            # This creates a pin protruding from the cut surface
            cylinder = cylinder.translate([0, 0, -overlap])
        else:
            # Hole: extends INWARD into Part B from cut plane
            # We need the hole to start at the cut surface and go INTO the part
            # Shift so cylinder goes into the mesh (negative Z before rotation)
            cylinder = cylinder.translate([0, 0, -overlap])

        # Rotate to align Z axis with target normal
        dot = np.dot(z_axis, target_normal)

        if abs(dot) > 0.9999:
            # Already aligned with Z (or opposite)
            if dot < 0:
                # Flip 180 degrees around X axis
                cylinder = cylinder.rotate([180, 0, 0])
            return cylinder

        # General rotation for non-axis-aligned normals
        rotation_axis = np.cross(z_axis, target_normal)
        rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
        angle_rad = np.arccos(np.clip(dot, -1.0, 1.0))
        angle_deg = np.degrees(angle_rad)

        # Apply rotation based on dominant rotation axis
        if abs(rotation_axis[0]) > 0.9:
            # Rotation around X
            cylinder = cylinder.rotate([angle_deg * np.sign(rotation_axis[0]), 0, 0])
        elif abs(rotation_axis[1]) > 0.9:
            # Rotation around Y
            cylinder = cylinder.rotate([0, angle_deg * np.sign(rotation_axis[1]), 0])
        else:
            # Rotation around Z
            cylinder = cylinder.rotate([0, 0, angle_deg * np.sign(rotation_axis[2])])

        return cylinder


__all__ = ["IntegratedJointFactory", "IntegratedPinConfig"]
