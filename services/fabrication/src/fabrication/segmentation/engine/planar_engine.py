"""Planar segmentation engine with axis-aligned cuts."""

from __future__ import annotations

from typing import List, Optional, Tuple
import numpy as np

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..hollowing import SdfHollower
from ..hollowing.sdf_hollower import HollowingConfig
from ..schemas import SegmentationConfig, SegmentedPart, SegmentationResult
from .base import CutCandidate, SegmentationEngine, SegmentationState

LOGGER = get_logger(__name__)


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

    def segment(self, mesh: MeshWrapper) -> SegmentationResult:
        """
        Segment mesh into parts fitting build volume.

        Uses iterative axis-aligned cuts until all parts fit.
        """
        # Check if segmentation needed
        if not self.needs_segmentation(mesh):
            LOGGER.info("Mesh fits build volume, no segmentation needed")
            return self._create_single_part_result(mesh)

        LOGGER.info(
            f"Starting segmentation: mesh dims {mesh.dimensions}, "
            f"build volume {self.build_volume}"
        )

        # Initialize state
        state = SegmentationState(parts=[mesh])
        cut_planes: List[CuttingPlane] = []

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

            # Only add non-empty parts
            if not positive.is_empty():
                state.parts.append(positive)
            if not negative.is_empty():
                state.parts.append(negative)

            cut_planes.append(cut_candidate.plane)
            state.iteration += 1

            LOGGER.info(
                f"Cut {state.iteration}: {len(state.parts)} parts, "
                f"{state.count_exceeding(self.build_volume)} exceeding"
            )

        # Apply hollowing if enabled
        if self.hollower:
            state.parts = self._apply_hollowing(state.parts)

        # Create result
        return self._create_result(state.parts, cut_planes)

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

        # Determine number of cuts needed
        num_pieces = int(np.ceil(axis_length / build_limit))
        if num_pieces < 2:
            num_pieces = 2

        # Generate evenly-spaced cut positions
        margin = axis_length * 0.1  # 10% margin from edges
        cut_positions = np.linspace(
            min_val + margin,
            max_val - margin,
            num_pieces + 1,  # More positions to evaluate
        )[1:-1]  # Exclude endpoints

        for pos in cut_positions:
            plane = CuttingPlane.from_axis(axis, pos)

            # Estimate resulting part sizes
            size_before = pos - min_val
            size_after = max_val - pos

            # Score based on balance and fit
            balance = 1.0 - abs(size_before - size_after) / axis_length
            fits_before = 1.0 if size_before <= build_limit else build_limit / size_before
            fits_after = 1.0 if size_after <= build_limit else build_limit / size_after
            fit_score = (fits_before + fits_after) / 2

            score = balance * 0.3 + fit_score * 0.7

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

    def _create_single_part_result(self, mesh: MeshWrapper) -> SegmentationResult:
        """Create result for mesh that doesn't need segmentation."""
        # Apply hollowing if enabled
        if self.hollower:
            result = self.hollower.hollow(mesh)
            if result.success and result.mesh is not None:
                mesh = result.mesh

        part_info = self.create_part_info(mesh, 0)

        return SegmentationResult(
            success=True,
            needs_segmentation=False,
            num_parts=1,
            parts=[part_info],
            cut_planes=[],
            hardware_required={},
            assembly_notes="Single part, no assembly required.",
        )

    def _create_result(
        self, parts: List[MeshWrapper], cut_planes: List[CuttingPlane]
    ) -> SegmentationResult:
        """Create segmentation result from parts."""
        part_infos: List[SegmentedPart] = []

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
            hardware_required=hardware,
            assembly_notes=assembly_notes,
        )

        return self.validate_result(result)

    def _calculate_hardware(self, num_parts: int) -> dict:
        """Calculate required hardware for assembly."""
        if self.config.joint_type.value == "none":
            return {}

        # Each cut creates a seam requiring joints
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
