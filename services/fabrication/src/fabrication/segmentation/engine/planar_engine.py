"""Planar segmentation engine with axis-aligned cuts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..hollowing import SdfHollower
from ..hollowing.sdf_hollower import HollowingConfig
from ..joints.base import JointFactory, JointPair
from ..joints.integrated import IntegratedJointFactory, IntegratedPinConfig
from ..joints.dowel import DowelJointFactory, DowelConfig
from ..schemas import (
    HollowingStrategy,
    JointType,
    SegmentationConfig,
    SegmentedPart,
    SegmentationResult,
)
from .base import CutCandidate, SegmentationEngine, SegmentationState

LOGGER = get_logger(__name__)


@dataclass
class SeamRelationship:
    """Tracks which parts share a seam from a cut."""

    part_a_idx: int  # Index of part on positive side of cut
    part_b_idx: int  # Index of part on negative side of cut
    cut_plane: CuttingPlane  # The plane where they meet


class PlanarSegmentationEngine(SegmentationEngine):
    """
    MVP segmentation engine using axis-aligned planar cuts.

    Strategy:
    1. Identify which axis exceeds build volume most
    2. Place cuts along that axis to divide into fitting pieces
    3. Repeat for other axes if needed
    4. Apply hollowing to reduce material
    """

    def __init__(self, config: SegmentationConfig):
        """Initialize planar engine."""
        super().__init__(config)
        self.hollower = None
        if config.enable_hollowing:
            hollow_config = HollowingConfig(
                wall_thickness_mm=config.wall_thickness_mm,
                min_wall_thickness_mm=config.min_wall_thickness_mm,
            )
            self.hollower = SdfHollower(hollow_config)

        # Initialize joint factory based on config
        self.joint_factory: Optional[JointFactory] = None
        self._init_joint_factory()

    def segment(
        self, mesh: MeshWrapper, output_dir: Optional[str] = None
    ) -> SegmentationResult:
        """
        Segment mesh into parts fitting build volume.

        Uses iterative axis-aligned cuts until all parts fit.
        Hollowing strategy determines when hollowing is applied:
        - HOLLOW_THEN_SEGMENT: Hollow first, then segment the shell (wall panels)
        - SEGMENT_THEN_HOLLOW: Segment solid, then hollow each piece (hollow boxes)

        Args:
            mesh: The mesh to segment
            output_dir: Optional directory to export parts to (creates 3MF files)

        Returns:
            SegmentationResult with part info and optional file paths
        """
        strategy = self.config.hollowing_strategy

        # HOLLOW FIRST if strategy is HOLLOW_THEN_SEGMENT
        # Handle both enum and string values
        should_hollow_first = (
            strategy == HollowingStrategy.HOLLOW_THEN_SEGMENT
            or strategy == "hollow_then_segment"
        )
        if should_hollow_first and self.hollower:
            LOGGER.info(
                f"Hollowing mesh BEFORE segmentation (wall_thickness={self.config.wall_thickness_mm}mm)..."
            )
            hollow_result = self.hollower.hollow(mesh)
            if hollow_result.success and hollow_result.mesh is not None:
                original_volume = mesh.volume_cm3
                mesh = hollow_result.mesh
                LOGGER.info(
                    f"Hollowed: {hollow_result.material_savings_percent:.1f}% material savings "
                    f"({original_volume:.1f} → {mesh.volume_cm3:.1f} cm³)"
                )
            else:
                LOGGER.warning(f"Hollowing failed: {hollow_result.error}, proceeding with solid mesh")

        # Check if segmentation needed (on potentially-hollowed mesh)
        if not self.needs_segmentation(mesh):
            LOGGER.info("Mesh fits build volume, no segmentation needed")
            return self._create_single_part_result(mesh, output_dir)

        LOGGER.info(
            f"Starting segmentation: mesh dims {mesh.dimensions}, "
            f"build volume {self.build_volume}"
        )

        # Initialize state
        state = SegmentationState(parts=[mesh])
        cut_planes: List[CuttingPlane] = []

        # Track seam relationships: list of (part_a, part_b, plane) tuples
        # We store mesh references initially, then resolve to indices after cutting
        seam_pairs: List[Tuple[MeshWrapper, MeshWrapper, CuttingPlane]] = []

        # Iteratively cut until all parts fit or max parts reached
        while True:
            state.parts_exceeding_volume = state.count_exceeding(self.build_volume)

            if state.parts_exceeding_volume == 0:
                LOGGER.info(f"All {len(state.parts)} parts fit build volume")
                break

            if len(state.parts) >= self.config.max_parts:
                LOGGER.warning(f"Reached max parts limit ({self.config.max_parts})")
                break

            # Find part that exceeds volume most
            target_part, target_idx = self._find_largest_exceeding_part(state.parts)

            if target_part is None:
                break

            # Find best cut for this part
            cut_candidate = self.find_best_cut(target_part, state)

            if cut_candidate is None:
                LOGGER.warning(f"No valid cut found for part {target_idx}")
                break

            # Execute cut
            positive, negative = self.execute_cut(target_part, cut_candidate.plane)

            # Replace target part with two new parts
            state.parts.pop(target_idx)

            # Only add non-empty parts and track the seam relationship
            if not positive.is_empty() and not negative.is_empty():
                state.parts.append(positive)
                state.parts.append(negative)
                # Track this seam - these two parts share the cut plane
                seam_pairs.append((positive, negative, cut_candidate.plane))
            elif not positive.is_empty():
                state.parts.append(positive)
            elif not negative.is_empty():
                state.parts.append(negative)

            cut_planes.append(cut_candidate.plane)
            state.iteration += 1

            LOGGER.info(
                f"Cut {state.iteration}: {len(state.parts)} parts, "
                f"{state.count_exceeding(self.build_volume)} exceeding"
            )

        # HOLLOW AFTER if strategy is SEGMENT_THEN_HOLLOW
        should_hollow_after = (
            strategy == HollowingStrategy.SEGMENT_THEN_HOLLOW
            or strategy == "segment_then_hollow"
        )
        if should_hollow_after and self.hollower:
            LOGGER.info("Hollowing parts AFTER segmentation...")
            state.parts = self._apply_hollowing(state.parts)

        # APPLY JOINTS to parts if joint generation is enabled
        if self.joint_factory and seam_pairs:
            LOGGER.info(f"Applying joints to {len(seam_pairs)} seams...")
            state.parts = self._apply_joints(state.parts, seam_pairs)

        # Create result and optionally export
        return self._create_result(state.parts, cut_planes, output_dir)

    def find_best_cut(
        self, mesh: MeshWrapper, state: SegmentationState
    ) -> Optional[CutCandidate]:
        """
        Find best axis-aligned cut for a mesh.

        Evaluates cuts along each axis and selects based on:
        - Balance: Even volume distribution between halves
        - Fit: Both halves should fit or be closer to fitting
        """
        bbox = mesh.bounding_box
        dims = bbox.dimensions
        exceeds = bbox.exceeds(self.build_volume)

        candidates: List[CutCandidate] = []

        # Generate candidate cuts for each axis that exceeds
        for axis in range(3):
            if not exceeds[axis]:
                continue

            # Generate multiple cut positions along this axis
            axis_cuts = self._generate_axis_cuts(mesh, axis)
            candidates.extend(axis_cuts)

        if not candidates:
            # If nothing exceeds, try cutting largest dimension anyway
            largest_axis = np.argmax(dims)
            candidates = self._generate_axis_cuts(mesh, largest_axis)

        if not candidates:
            return None

        # Score and select best candidate
        best = max(candidates, key=lambda c: c.score)
        return best

    def _generate_axis_cuts(
        self, mesh: MeshWrapper, axis: int
    ) -> List[CutCandidate]:
        """Generate candidate cuts along an axis."""
        candidates = []
        bbox = mesh.bounding_box

        # Get axis range
        if axis == 0:
            min_val, max_val = bbox.min_x, bbox.max_x
        elif axis == 1:
            min_val, max_val = bbox.min_y, bbox.max_y
        else:
            min_val, max_val = bbox.min_z, bbox.max_z

        axis_length = max_val - min_val
        build_limit = self.build_volume[axis]

        # Determine number of pieces needed
        num_pieces = int(np.ceil(axis_length / build_limit))
        if num_pieces < 2:
            num_pieces = 2

        # Generate candidate cut positions
        # Include positions at build_limit intervals for optimal fitting
        margin = min(axis_length * 0.05, 10.0)  # 5% margin or 10mm max

        cut_positions = set()

        # Add cuts at build_limit intervals from each end
        for i in range(1, num_pieces):
            pos_from_min = min_val + i * build_limit
            pos_from_max = max_val - i * build_limit
            if min_val + margin < pos_from_min < max_val - margin:
                cut_positions.add(pos_from_min)
            if min_val + margin < pos_from_max < max_val - margin:
                cut_positions.add(pos_from_max)

        # Add evenly-spaced positions for evaluation
        even_positions = np.linspace(
            min_val + margin,
            max_val - margin,
            num_pieces + 1,
        )[1:-1]
        for pos in even_positions:
            cut_positions.add(pos)

        for pos in cut_positions:
            plane = CuttingPlane.from_axis(axis, pos)

            # Estimate resulting part sizes
            size_before = pos - min_val
            size_after = max_val - pos

            # Score prioritizing fit over balance
            # A piece that fits perfectly scores 1.0
            # A piece at exactly build_limit scores high (optimal use of space)
            fits_before = 1.0 if size_before <= build_limit else build_limit / size_before
            fits_after = 1.0 if size_after <= build_limit else build_limit / size_after

            # Bonus for pieces close to build_limit (better material utilization)
            # Optimal piece is ~90% of build_limit
            optimal_size = build_limit * 0.9
            utilization_before = 1.0 - abs(size_before - optimal_size) / build_limit if size_before <= build_limit else 0.0
            utilization_after = 1.0 - abs(size_after - optimal_size) / build_limit if size_after <= build_limit else 0.0
            utilization_score = (utilization_before + utilization_after) / 2

            fit_score = (fits_before + fits_after) / 2
            balance = 1.0 - abs(size_before - size_after) / axis_length

            # Prioritize: fit (must fit) > utilization (use space well) > balance
            score = fit_score * 0.5 + utilization_score * 0.35 + balance * 0.15

            candidates.append(
                CutCandidate(
                    plane=plane,
                    score=score,
                    resulting_parts=2,
                    balance_score=balance,
                )
            )

        return candidates

    def _find_largest_exceeding_part(
        self, parts: List[MeshWrapper]
    ) -> Tuple[Optional[MeshWrapper], int]:
        """Find the part that exceeds build volume by the most."""
        max_overage = 0.0
        target_part = None
        target_idx = -1

        for i, part in enumerate(parts):
            if part.fits_in_volume(self.build_volume):
                continue

            overage = part.bounding_box.overage(self.build_volume)
            total_overage = sum(overage)

            if total_overage > max_overage:
                max_overage = total_overage
                target_part = part
                target_idx = i

        return target_part, target_idx

    def _apply_hollowing(self, parts: List[MeshWrapper]) -> List[MeshWrapper]:
        """Apply hollowing to all parts."""
        hollowed_parts = []

        for i, part in enumerate(parts):
            LOGGER.info(f"Hollowing part {i + 1}/{len(parts)}")
            result = self.hollower.hollow(part)

            if result.success and result.mesh is not None:
                hollowed_parts.append(result.mesh)
                LOGGER.info(
                    f"Part {i + 1}: {result.material_savings_percent:.1f}% material savings"
                )
            else:
                LOGGER.warning(f"Hollowing failed for part {i + 1}, using solid")
                hollowed_parts.append(part)

        return hollowed_parts

    def _init_joint_factory(self) -> None:
        """Initialize the appropriate joint factory based on configuration."""
        joint_type = self.config.joint_type

        # Handle both enum and string values
        if joint_type == JointType.NONE or joint_type == "none":
            self.joint_factory = None
            return

        if joint_type == JointType.INTEGRATED or joint_type == "integrated":
            # Get pin dimensions from config (with defaults)
            pin_diameter = getattr(self.config, "pin_diameter_mm", 8.0)
            pin_height = getattr(self.config, "pin_height_mm", 10.0)
            wall_thickness = self.config.wall_thickness_mm

            # Validate wall thickness can accommodate pin diameter
            # Wall must be thick enough to contain the pin without jutting through
            if wall_thickness < pin_diameter:
                adjusted_wall = pin_diameter + 2.0
                LOGGER.warning(
                    f"Wall thickness ({wall_thickness}mm) < pin diameter ({pin_diameter}mm). "
                    f"Auto-adjusting wall thickness to {adjusted_wall}mm for integrated joints."
                )
                self.config.wall_thickness_mm = adjusted_wall

            # Calculate hole depth to match pin protrusion
            # Pin has 2mm anchor inside, so protrusion = pin_height - 2mm
            # Hole depth should match the protrusion
            hole_depth = pin_height - 2.0  # 8mm for 10mm pin height

            config = IntegratedPinConfig(
                joint_type=JointType.INTEGRATED,
                tolerance_mm=self.config.joint_tolerance_mm,
                hole_clearance_mm=self.config.joint_tolerance_mm,
                pin_diameter_mm=pin_diameter,
                pin_height_mm=pin_height,
                hole_depth_mm=hole_depth,
            )
            self.joint_factory = IntegratedJointFactory(config)

            # Reduce build volume to account for pin protrusion
            # Pins can be on any face, so reduce all axes by pin height
            self.build_volume = tuple(
                dim - pin_height for dim in self.build_volume
            )
            LOGGER.info(
                f"Initialized integrated pin factory (pin: {pin_diameter}x{pin_height}mm), "
                f"adjusted build volume to {self.build_volume}"
            )

        elif joint_type == JointType.DOWEL or joint_type == "dowel":
            config = DowelConfig(
                joint_type=JointType.DOWEL,
                tolerance_mm=self.config.joint_tolerance_mm,
                diameter_mm=self.config.dowel_diameter_mm,
                depth_mm=self.config.dowel_depth_mm,
                hole_clearance_mm=self.config.joint_tolerance_mm,
            )
            self.joint_factory = DowelJointFactory(config)
            LOGGER.info("Initialized dowel joint factory")

        else:
            LOGGER.info(f"Joint type '{joint_type}' not implemented, no joints will be added")
            self.joint_factory = None

    def _deduplicate_joint_positions(
        self,
        joints: List[Tuple],
        min_spacing_mm: float = 15.0
    ) -> List[Tuple]:
        """
        Remove overlapping joints. When pin/hole collide, remove BOTH.

        Strategy (per user preference):
        - When a pin and hole are at the same location: REMOVE BOTH
        - When two pins or two holes overlap: Keep first, remove duplicate

        Args:
            joints: List of (JointLocation, is_pin) tuples
            min_spacing_mm: Minimum distance between joints

        Returns:
            Deduplicated list of (JointLocation, is_pin) tuples
        """
        if len(joints) <= 1:
            return joints

        # First pass: identify positions to exclude (pin/hole conflicts)
        positions_to_exclude = set()
        for i, (joint_i, is_pin_i) in enumerate(joints):
            pos_i = np.array(joint_i.position)
            for j, (joint_j, is_pin_j) in enumerate(joints[i + 1:], start=i + 1):
                pos_j = np.array(joint_j.position)
                distance = np.linalg.norm(pos_i - pos_j)

                if distance < min_spacing_mm:
                    # Different types (pin vs hole) = conflict, remove both
                    if is_pin_i != is_pin_j:
                        LOGGER.debug(
                            f"Pin/hole conflict at distance {distance:.1f}mm - removing both"
                        )
                        positions_to_exclude.add(i)
                        positions_to_exclude.add(j)

        # Second pass: build deduplicated list (skip conflicts, dedupe same-type)
        deduplicated = []
        for i, (joint, is_pin) in enumerate(joints):
            if i in positions_to_exclude:
                continue  # Skip pin/hole conflicts

            pos = np.array(joint.position)
            too_close = False
            for existing_joint, _ in deduplicated:
                existing_pos = np.array(existing_joint.position)
                if np.linalg.norm(pos - existing_pos) < min_spacing_mm:
                    too_close = True
                    LOGGER.debug(
                        f"Duplicate joint at distance {np.linalg.norm(pos - existing_pos):.1f}mm - keeping first"
                    )
                    break

            if not too_close:
                deduplicated.append((joint, is_pin))

        removed_count = len(joints) - len(deduplicated)
        if removed_count > 0:
            LOGGER.info(
                f"Deduplicated joints: {len(joints)} -> {len(deduplicated)} "
                f"(removed {removed_count} conflicts/duplicates)"
            )

        return deduplicated

    def _apply_joints(
        self,
        parts: List[MeshWrapper],
        seam_pairs: List[Tuple[MeshWrapper, MeshWrapper, CuttingPlane]],
    ) -> List[MeshWrapper]:
        """
        Apply joint geometry to all parts based on seam relationships.

        Instead of tracking mesh object identity (which breaks when parts are cut further),
        we find parts that share each cut plane by checking if the plane intersects them.

        Args:
            parts: List of final mesh parts
            seam_pairs: List of (part_a, part_b, plane) tuples from cutting (for plane info)

        Returns:
            Parts with joint geometry applied
        """
        if not self.joint_factory:
            return parts

        # Collect all joint locations per part
        # Key: part index, Value: list of JointLocation objects + is_pin_side flag
        part_joints: Dict[int, List[Tuple[any, bool]]] = {i: [] for i in range(len(parts))}

        # Get unique cut planes from seam_pairs
        processed_planes = set()

        for _, _, plane in seam_pairs:
            # Use plane position as key to avoid duplicates
            plane_key = (round(plane.origin[0], 1), round(plane.origin[1], 1), round(plane.origin[2], 1))
            if plane_key in processed_planes:
                continue
            processed_planes.add(plane_key)

            # Find all adjacent part pairs at this cut plane
            adjacent_pairs = self._find_parts_at_plane(parts, plane)

            if not adjacent_pairs:
                LOGGER.debug(f"No adjacent part pairs found at plane {plane_key}")
                continue

            # Generate joints for each pair of adjacent parts
            for idx_a, idx_b in adjacent_pairs:
                # Create a unique key for this part pair to avoid duplicates
                pair_key = (min(idx_a, idx_b), max(idx_a, idx_b), plane_key)
                if pair_key in processed_planes:
                    continue
                processed_planes.add(pair_key)

                try:
                    joint_pairs = self.joint_factory.generate_joints(
                        parts[idx_a],
                        parts[idx_b],
                        plane,
                        idx_a,
                        idx_b,
                    )

                    for jp in joint_pairs:
                        is_pin = jp.location_a.depth_mm < 0
                        part_joints[idx_a].append((jp.location_a, is_pin))
                        part_joints[idx_b].append((jp.location_b, False))

                    LOGGER.info(f"Generated {len(joint_pairs)} joints for seam between parts {idx_a} and {idx_b}")

                except Exception as e:
                    LOGGER.warning(f"Joint generation failed for seam between {idx_a} and {idx_b}: {e}")
                    continue

        # Apply collected joints to each part
        result_parts = []
        for i, part in enumerate(parts):
            if not part_joints[i]:
                result_parts.append(part)
                continue

            try:
                # Deduplicate joints for this part (removes pin/hole conflicts and duplicates)
                deduplicated_joints = self._deduplicate_joint_positions(
                    part_joints[i], min_spacing_mm=15.0
                )

                if not deduplicated_joints:
                    # All joints were removed due to conflicts
                    result_parts.append(part)
                    continue

                joint_locations = [jl for jl, _ in deduplicated_joints]
                is_pin_side = any(is_pin for _, is_pin in deduplicated_joints)

                # Get bounds before applying joints
                z_min_before = part.as_trimesh.bounds[0][2]
                z_max_before = part.as_trimesh.bounds[1][2]

                if isinstance(self.joint_factory, IntegratedJointFactory):
                    modified = self.joint_factory.apply_joints_to_mesh(
                        part, joint_locations, is_pin_side
                    )
                else:
                    modified = self.joint_factory.apply_joints_to_mesh(part, joint_locations)

                # Verify bounds changed
                z_min_after = modified.as_trimesh.bounds[0][2]
                z_max_after = modified.as_trimesh.bounds[1][2]

                LOGGER.info(
                    f"Applied {len(joint_locations)} joints to part {i}: "
                    f"Z [{z_min_before:.1f},{z_max_before:.1f}] -> [{z_min_after:.1f},{z_max_after:.1f}]"
                )

                result_parts.append(modified)

            except Exception as e:
                LOGGER.warning(f"Failed to apply joints to part {i}: {e}")
                result_parts.append(part)

        return result_parts

    def _find_parts_at_plane(
        self, parts: List[MeshWrapper], plane: CuttingPlane
    ) -> List[Tuple[int, int]]:
        """
        Find pairs of part indices that share a face at the cut plane.

        Returns list of (idx_positive, idx_negative) tuples where:
        - idx_positive: part on the positive side of the plane normal
        - idx_negative: part on the negative side of the plane normal

        Parts are paired if they are adjacent (share the cut plane face).
        """
        import numpy as np

        tolerance = 10.0  # mm - generous tolerance for voxelization drift

        # Determine which axis the plane is perpendicular to
        normal = np.array(plane.normal)
        axis = np.argmax(np.abs(normal))
        plane_pos = plane.origin[axis]
        normal_dir = 1 if normal[axis] > 0 else -1

        # Categorize parts by which side of the plane they're on
        # positive_side: parts whose MIN face touches the plane (they're on + side)
        # negative_side: parts whose MAX face touches the plane (they're on - side)
        positive_side = []  # Parts on positive side (min face at plane)
        negative_side = []  # Parts on negative side (max face at plane)

        for i, part in enumerate(parts):
            bbox = part.bounding_box

            # Get min/max along the cut axis
            if axis == 0:
                part_min, part_max = bbox.min_x, bbox.max_x
            elif axis == 1:
                part_min, part_max = bbox.min_y, bbox.max_y
            else:
                part_min, part_max = bbox.min_z, bbox.max_z

            # Check if this part's min or max face is at the plane
            if abs(part_min - plane_pos) < tolerance:
                # Part's minimum face is at the plane -> part is on positive side
                if normal_dir > 0:
                    positive_side.append((i, part_min, part_max))
                else:
                    negative_side.append((i, part_min, part_max))

            if abs(part_max - plane_pos) < tolerance:
                # Part's maximum face is at the plane -> part is on negative side
                if normal_dir > 0:
                    negative_side.append((i, part_min, part_max))
                else:
                    positive_side.append((i, part_min, part_max))

        # Now pair up parts that are truly adjacent (share a face, not just edge/corner)
        # Two parts share a face if they overlap SIGNIFICANTLY in the other two dimensions
        pairs = []
        min_overlap_ratio = 0.5  # Require at least 50% overlap to be considered adjacent

        for pos_idx, pos_min, pos_max in positive_side:
            pos_bbox = parts[pos_idx].bounding_box

            for neg_idx, neg_min, neg_max in negative_side:
                if pos_idx == neg_idx:
                    continue

                neg_bbox = parts[neg_idx].bounding_box

                # Check overlap in the other two axes
                overlap_ratios = []
                for check_axis in range(3):
                    if check_axis == axis:
                        continue

                    # Get bounds for this axis
                    if check_axis == 0:
                        pos_lo, pos_hi = pos_bbox.min_x, pos_bbox.max_x
                        neg_lo, neg_hi = neg_bbox.min_x, neg_bbox.max_x
                    elif check_axis == 1:
                        pos_lo, pos_hi = pos_bbox.min_y, pos_bbox.max_y
                        neg_lo, neg_hi = neg_bbox.min_y, neg_bbox.max_y
                    else:
                        pos_lo, pos_hi = pos_bbox.min_z, pos_bbox.max_z
                        neg_lo, neg_hi = neg_bbox.min_z, neg_bbox.max_z

                    # Calculate overlap
                    overlap_lo = max(pos_lo, neg_lo)
                    overlap_hi = min(pos_hi, neg_hi)
                    overlap_size = max(0, overlap_hi - overlap_lo)

                    # Calculate overlap ratio relative to smaller extent
                    pos_size = pos_hi - pos_lo
                    neg_size = neg_hi - neg_lo
                    min_size = min(pos_size, neg_size)

                    if min_size > 0:
                        overlap_ratios.append(overlap_size / min_size)
                    else:
                        overlap_ratios.append(0)

                # Parts are adjacent if they have significant overlap in BOTH other axes
                if all(ratio >= min_overlap_ratio for ratio in overlap_ratios):
                    pairs.append((pos_idx, neg_idx))

        return pairs

    def _find_part_index(
        self, original_part: MeshWrapper, current_parts: List[MeshWrapper]
    ) -> Optional[int]:
        """
        Find the index of a part in the current list.

        Uses object identity first, falls back to center matching.
        This handles the case where hollowing creates slightly different mesh bounds.
        """
        # Try direct object match first (most reliable)
        for i, part in enumerate(current_parts):
            if part is original_part:
                return i

        # Fall back to center-based matching
        # Parts from the same cut will have similar centers even after hollowing
        target_center = original_part.bounding_box.center

        best_match = None
        best_distance = float("inf")

        for i, part in enumerate(current_parts):
            center = part.bounding_box.center
            distance = sum((c1 - c2) ** 2 for c1, c2 in zip(center, target_center)) ** 0.5

            if distance < best_distance:
                best_distance = distance
                best_match = i

        # Use a more generous tolerance - 50mm should catch voxelization drift
        # while still being much smaller than typical part sizes
        if best_match is not None and best_distance < 50.0:
            return best_match

        return None

    def _create_single_part_result(
        self, mesh: MeshWrapper, output_dir: Optional[str] = None
    ) -> SegmentationResult:
        """Create result for mesh that doesn't need segmentation."""
        from pathlib import Path
        from ..output.threemf_writer import ThreeMFWriter

        # Apply hollowing if enabled
        if self.hollower:
            result = self.hollower.hollow(mesh)
            if result.success and result.mesh is not None:
                mesh = result.mesh

        # Export if output_dir provided
        file_path = ""
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            file_path = str(output_path / "part_00.3mf")
            mesh.export(file_path)
            LOGGER.info(f"Exported single part to {file_path}")

        part_info = self.create_part_info(mesh, 0, file_path)

        return SegmentationResult(
            success=True,
            needs_segmentation=False,
            num_parts=1,
            parts=[part_info],
            cut_planes=[],
            combined_3mf_path=file_path,
            hardware_required={},
            assembly_notes="Single part, no assembly required.",
        )

    def _create_result(
        self,
        parts: List[MeshWrapper],
        cut_planes: List[CuttingPlane],
        output_dir: Optional[str] = None,
    ) -> SegmentationResult:
        """Create segmentation result from parts."""
        from pathlib import Path
        from ..output.threemf_writer import ThreeMFWriter

        part_infos: List[SegmentedPart] = []
        combined_3mf_path = ""

        # Export parts if output_dir provided
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            # Export individual parts
            for i, part in enumerate(parts):
                file_path = str(output_path / f"part_{i:02d}.3mf")
                part.export(file_path)
                info = self.create_part_info(part, i, file_path)
                part_infos.append(info)
                LOGGER.info(f"Exported part {i} to {file_path}")

            # Export combined 3MF with all parts
            try:
                writer = ThreeMFWriter()
                combined_3mf_path = str(output_path / "combined_assembly.3mf")
                writer.write(parts, Path(combined_3mf_path))
                LOGGER.info(f"Exported combined assembly to {combined_3mf_path}")
            except Exception as e:
                LOGGER.warning(f"Failed to create combined 3MF: {e}")
        else:
            # No export, just create part info
            for i, part in enumerate(parts):
                info = self.create_part_info(part, i)
                part_infos.append(info)

        # Calculate hardware requirements
        hardware = self._calculate_hardware(len(parts))

        # Generate assembly notes
        assembly_notes = self._generate_assembly_notes(parts, cut_planes)

        result = SegmentationResult(
            success=True,
            needs_segmentation=True,
            num_parts=len(parts),
            parts=part_infos,
            cut_planes=cut_planes,
            combined_3mf_path=combined_3mf_path,
            hardware_required=hardware,
            assembly_notes=assembly_notes,
        )

        return self.validate_result(result)

    def _calculate_hardware(self, num_parts: int) -> dict:
        """Calculate required hardware for assembly."""
        if self.config.joint_type.value == "none":
            return {"adhesive": {"type": "CA glue or epoxy", "estimated_ml": (num_parts - 1) * 2}}

        if self.config.joint_type.value == "integrated":
            # Integrated pins are printed, no external hardware needed
            return {
                "integrated_pins": {
                    "note": "Pins are printed directly on parts - no external hardware needed",
                    "pins_per_seam": 3,
                    "total_pins": (num_parts - 1) * 3,
                },
                "adhesive": {
                    "type": "CA glue or epoxy (optional for extra strength)",
                    "estimated_ml": (num_parts - 1) * 1,
                },
            }

        # Dowel joints require external pins
        num_seams = num_parts - 1
        joints_per_seam = 3  # Typical number of dowels per seam

        return {
            "dowel_pins": {
                "quantity": num_seams * joints_per_seam,
                "diameter_mm": self.config.dowel_diameter_mm,
                "length_mm": self.config.dowel_depth_mm * 2,
            },
            "adhesive": {
                "type": "CA glue or epoxy",
                "estimated_ml": num_seams * 2,
            },
        }

    def _generate_assembly_notes(
        self, parts: List[MeshWrapper], cut_planes: List[CuttingPlane]
    ) -> str:
        """Generate assembly instructions."""
        notes = [
            f"Assembly Instructions for {len(parts)} Parts",
            "=" * 40,
            "",
            "Parts Overview:",
        ]

        total_volume = 0.0
        for i, part in enumerate(parts):
            dims = part.dimensions
            vol = part.volume_cm3
            total_volume += vol
            notes.append(
                f"  Part {i + 1}: {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm "
                f"({vol:.1f} cm³)"
            )

        notes.extend([
            "",
            f"Total Volume: {total_volume:.1f} cm³",
            f"Number of Seams: {len(cut_planes)}",
            "",
            "Assembly Steps:",
            "1. Print all parts with recommended settings",
            "2. Clean cut surfaces and remove any support material",
            "3. Dry-fit parts to verify alignment",
        ])

        if self.config.joint_type.value == "dowel":
            notes.extend([
                "4. Insert dowel pins into pre-drilled holes",
                "5. Apply adhesive to seam surfaces",
                "6. Press parts together and clamp until cured",
            ])
        elif self.config.joint_type.value == "integrated":
            notes.extend([
                "4. Align integrated pins with matching holes",
                "5. Apply small amount of adhesive around pins (optional)",
                "6. Press parts together - pins provide alignment",
                "",
                "Note: Integrated pins are printed directly on parts.",
                "No external hardware needed!",
            ])
        else:
            notes.extend([
                "4. Apply adhesive to seam surfaces",
                "5. Press parts together and clamp until cured",
            ])

        notes.extend([
            "",
            "Recommended Print Settings:",
            "- Layer height: 0.2mm",
            "- Infill: 15-20% (parts are hollowed)",
            "- Perimeters: 3-4",
            "- Support: As indicated per part",
        ])

        return "\n".join(notes)
