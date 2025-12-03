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
    pin_height_mm: float = 10.0  # Total pin height (2mm anchor + 8mm protrusion)
    hole_depth_mm: float = 8.0  # Hole depth matches pin protrusion
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

        # CRITICAL: Determine pin normal direction based on part positions
        # The pin must protrude FROM part_a TOWARD part_b
        # We do this by checking which side of the plane each part's centroid is on
        plane_origin = np.array(cut_plane.origin)
        plane_normal = np.array(cut_plane.normal)

        # Get centroids of both parts
        centroid_a = np.array(part_a.as_trimesh.centroid)
        centroid_b = np.array(part_b.as_trimesh.centroid)

        # Calculate signed distance from plane for each centroid
        # Positive = same side as normal, Negative = opposite side
        dist_a = np.dot(centroid_a - plane_origin, plane_normal)
        dist_b = np.dot(centroid_b - plane_origin, plane_normal)

        # Pin normal should point FROM part_a TOWARD part_b
        # If part_a is on positive side (dist_a > 0) and part_b on negative (dist_b < 0),
        # then we need to INVERT the plane normal so pin points toward part_b
        if dist_a > 0 and dist_b < 0:
            # Part A is on positive side, part B on negative - invert normal
            pin_normal = tuple(-n for n in plane_normal)
        elif dist_a < 0 and dist_b > 0:
            # Part A is on negative side, part B on positive - use normal as-is
            pin_normal = tuple(plane_normal)
        else:
            # Fallback: use plane normal (shouldn't happen for valid cuts)
            LOGGER.warning(f"Parts not on opposite sides of plane: dist_a={dist_a:.1f}, dist_b={dist_b:.1f}")
            pin_normal = tuple(plane_normal)

        LOGGER.info(f"Pin normal direction: {pin_normal} (part_a dist={dist_a:.1f}, part_b dist={dist_b:.1f})")

        for i, pos_3d in enumerate(positions):
            # PrusaSlicer approach: connector SPANS the cut plane
            # Position is on the seam; we'll center the connector there
            # Both pin and hole use the SAME position - the cut plane boundary
            # The geometry application handles the spanning behavior

            # Pin side (part A) - exact dimensions
            # Pin will be unioned to Part A, spanning into where Part B was
            # pin_normal points FROM part_a TOWARD part_b (calculated above)
            pin_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm,
                depth_mm=-self.pin_config.pin_height_mm,  # Negative = protrusion (union)
                part_index=part_a_index,
                normal=pin_normal,  # Points toward Part B (calculated from part positions)
            )

            # Socket side (part B) - ENLARGED by clearance
            # Socket will be subtracted from Part B
            # Clearance ensures the pin fits with room to spare
            # Hole normal is OPPOSITE to pin normal (points INTO part B)
            hole_normal = tuple(-n for n in pin_normal)
            socket_location = JointLocation(
                position=pos_3d,
                diameter_mm=self.pin_config.pin_diameter_mm + (self.pin_config.hole_clearance_mm * 2),  # Clearance on diameter (both sides)
                depth_mm=self.pin_config.hole_depth_mm + self.pin_config.hole_clearance_mm,  # Hole depth + small clearance
                part_index=part_b_index,
                normal=hole_normal,  # Points into Part B (opposite to pin)
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
        Place joints WITHIN the wall material on the cut face.

        For hollow shells, the seam cross-section is a ring shape (wall only).
        Pins must be placed at positions that:
        1. Are ON the cut plane face (where parts mate)
        2. Are WITHIN the wall material (not at edges)
        3. Point PERPENDICULAR to the cut plane (toward mating part)

        The contour from mesh.section() gives us the wall cross-section outline.
        We place pins at the MIDPOINT of wall segments, not at the edges.
        """
        positions = []

        if num_joints <= 0 or len(contour) < 3:
            return positions

        # Determine which axis is perpendicular to the plane (cut direction)
        normal = np.array(plane.normal)
        abs_normal = np.abs(normal)
        plane_axis = np.argmax(abs_normal)

        # Get the two in-plane axes (the cut face)
        axes = [i for i in range(3) if i != plane_axis]

        # Project contour to 2D (the cut face plane)
        contour_2d = contour[:, axes]

        # Find bounding box to identify wall structure
        min_coords = contour_2d.min(axis=0)
        max_coords = contour_2d.max(axis=0)
        bbox_center = (min_coords + max_coords) / 2

        # For a hollow shell cut face, we want to place pins along the walls
        # The walls form a frame around the hollow interior
        # We'll place pins at strategic positions along each wall segment

        # Calculate positions along the 4 walls of the cut face
        # Wall positions are at the MIDPOINT between outer and inner boundaries
        wall_positions = []

        # Wall tolerance for identifying wall regions
        # Should be slightly larger than expected wall thickness to capture all wall points
        # Default wall is 10mm, so use 15mm tolerance
        wall_tol = 15.0  # mm - tolerance for identifying wall regions

        # Get the plane coordinate value (Z position for horizontal cuts, etc.)
        plane_coord = plane.origin[plane_axis]

        # Top wall (max Y region)
        top_mask = contour_2d[:, 1] > max_coords[1] - wall_tol
        if np.any(top_mask):
            top_points = contour_2d[top_mask]
            # Midpoint along X, at Y position within wall
            mid_x = np.mean(top_points[:, 0])
            mid_y = np.mean(top_points[:, 1])
            pos_3d = [0.0, 0.0, 0.0]
            pos_3d[axes[0]] = mid_x
            pos_3d[axes[1]] = mid_y
            pos_3d[plane_axis] = plane_coord
            wall_positions.append(tuple(pos_3d))

        # Bottom wall (min Y region)
        bottom_mask = contour_2d[:, 1] < min_coords[1] + wall_tol
        if np.any(bottom_mask):
            bottom_points = contour_2d[bottom_mask]
            mid_x = np.mean(bottom_points[:, 0])
            mid_y = np.mean(bottom_points[:, 1])
            pos_3d = [0.0, 0.0, 0.0]
            pos_3d[axes[0]] = mid_x
            pos_3d[axes[1]] = mid_y
            pos_3d[plane_axis] = plane_coord
            wall_positions.append(tuple(pos_3d))

        # Left wall (min X region)
        left_mask = contour_2d[:, 0] < min_coords[0] + wall_tol
        if np.any(left_mask):
            left_points = contour_2d[left_mask]
            mid_x = np.mean(left_points[:, 0])
            mid_y = np.mean(left_points[:, 1])
            pos_3d = [0.0, 0.0, 0.0]
            pos_3d[axes[0]] = mid_x
            pos_3d[axes[1]] = mid_y
            pos_3d[plane_axis] = plane_coord
            wall_positions.append(tuple(pos_3d))

        # Right wall (max X region)
        right_mask = contour_2d[:, 0] > max_coords[0] - wall_tol
        if np.any(right_mask):
            right_points = contour_2d[right_mask]
            mid_x = np.mean(right_points[:, 0])
            mid_y = np.mean(right_points[:, 1])
            pos_3d = [0.0, 0.0, 0.0]
            pos_3d[axes[0]] = mid_x
            pos_3d[axes[1]] = mid_y
            pos_3d[plane_axis] = plane_coord
            wall_positions.append(tuple(pos_3d))

        # Filter out positions that are too close to corners
        # Corners are where multiple cut planes intersect - joints there would conflict
        corner_margin = self.pin_config.pin_diameter_mm * 2  # Stay away from corners

        filtered_positions = []
        for pos in wall_positions:
            # Extract 2D coordinates on the cut face
            pos_2d = [pos[axes[0]], pos[axes[1]]]

            # Check if position is near multiple edges (corner)
            near_top = pos_2d[1] > max_coords[1] - corner_margin
            near_bottom = pos_2d[1] < min_coords[1] + corner_margin
            near_left = pos_2d[0] < min_coords[0] + corner_margin
            near_right = pos_2d[0] > max_coords[0] - corner_margin

            # Count how many edges this position is near
            edge_count = sum([near_top, near_bottom, near_left, near_right])

            # If near 2+ edges, it's in a corner - skip to avoid conflicts
            if edge_count < 2:
                filtered_positions.append(pos)
            else:
                LOGGER.debug(f"Skipping corner position {pos} (near {edge_count} edges)")

        # Select the requested number of positions
        if len(filtered_positions) >= num_joints:
            positions = filtered_positions[:num_joints]
        else:
            # Use all available non-corner positions
            positions = filtered_positions

        LOGGER.debug(
            f"Placed {len(positions)} joints at wall midpoints on cut face "
            f"(filtered {len(wall_positions) - len(filtered_positions)} corner positions)"
        )

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

            # Debug: log mesh bounds before processing
            input_mesh_data = manifold.to_mesh()
            input_verts = np.array(input_mesh_data.vert_properties)[:, :3]
            LOGGER.debug(f"Input mesh Z range: {input_verts[:, 2].min():.1f} to {input_verts[:, 2].max():.1f}")

            for joint in joints:
                # Determine if this joint is a pin or hole from its depth
                # Negative depth = pin (protrusion), Positive depth = hole (cavity)
                is_pin = joint.depth_mm < 0

                LOGGER.info(f"Processing joint: pos={joint.position}, normal={joint.normal}, depth={joint.depth_mm}, is_pin={is_pin}")

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

            # Debug: verify the mesh bounds changed
            result_mesh = manifold.to_mesh()
            result_verts = np.array(result_mesh.vert_properties)[:, :3]
            LOGGER.debug(f"Result mesh Z range: {result_verts[:, 2].min():.1f} to {result_verts[:, 2].max():.1f}")

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

        IMPORTANT: We must rotate FIRST, then translate. If we translate before
        rotating, the rotation happens around the origin, which moves the
        translated cylinder to the wrong position.

        Args:
            cylinder: Manifold cylinder (created along Z axis with base at z=0)
            target_normal: Direction the cylinder should point
            height: Height of cylinder
            is_pin: True if this is a pin (protrusion), False if hole (cavity)

        Returns:
            Positioned and rotated cylinder (centered at origin, ready for final translation)
        """
        # Normalize target
        target_normal = target_normal / np.linalg.norm(target_normal)

        # Default cylinder axis is Z (0, 0, 1)
        z_axis = np.array([0.0, 0.0, 1.0])

        # FIRST: Rotate cylinder to align with target normal (while still at origin)
        dot = np.dot(z_axis, target_normal)

        if abs(dot) < 0.9999:
            # Need to rotate - general case for non-axis-aligned normals
            rotation_axis = np.cross(z_axis, target_normal)
            rotation_axis = rotation_axis / np.linalg.norm(rotation_axis)
            angle_rad = np.arccos(np.clip(dot, -1.0, 1.0))
            angle_deg = np.degrees(angle_rad)

            # Apply rotation based on dominant rotation axis
            if abs(rotation_axis[0]) > 0.9:
                cylinder = cylinder.rotate([angle_deg * np.sign(rotation_axis[0]), 0, 0])
            elif abs(rotation_axis[1]) > 0.9:
                cylinder = cylinder.rotate([0, angle_deg * np.sign(rotation_axis[1]), 0])
            else:
                cylinder = cylinder.rotate([0, 0, angle_deg * np.sign(rotation_axis[2])])
        elif dot < 0:
            # Opposite direction - flip 180 degrees around X axis
            cylinder = cylinder.rotate([180, 0, 0])

        # SECOND: After rotation, translate along the (now aligned) target normal
        # The cylinder is now oriented so its axis points along target_normal
        # We need to position it so it protrudes/recedes from the cut plane

        # Anchor depth: how much of the pin is embedded in the mesh for attachment
        anchor_depth = 2.0  # mm - small anchor inside mesh for clean boolean union
        overlap = 1.0  # mm - extra depth for clean boolean subtraction

        if is_pin:
            # Pin: PROTRUDES OUTWARD from cut surface along target_normal
            # Most of the pin should be external (visible), with small anchor inside
            # Translate so cylinder extends from -anchor_depth to +(height - anchor_depth) along normal
            # Since cylinder was at z=0 to z=height, and we rotated it to align with normal,
            # we translate backward along normal by anchor_depth
            offset = -anchor_depth
        else:
            # Hole: extends INWARD into mesh (opposite to target_normal)
            # Hole should go INTO the part, starting slightly outside for clean boolean
            # The hole's normal points INTO the part, so we translate forward slightly
            # and the hole extends backward (into the mesh)
            offset = overlap - height

        # Apply offset along the target normal direction
        offset_vec = target_normal * offset
        cylinder = cylinder.translate([offset_vec[0], offset_vec[1], offset_vec[2]])

        return cylinder


__all__ = ["IntegratedJointFactory", "IntegratedPinConfig"]
