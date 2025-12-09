"""Beam search algorithm for optimal mesh segmentation."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, List, Optional, Tuple

import numpy as np

from common.logging import get_logger

from ..geometry.mesh_wrapper import MeshWrapper
from ..geometry.plane import CuttingPlane
from ..schemas import SegmentationConfig

if TYPE_CHECKING:
    from .base import CutCandidate

LOGGER = get_logger(__name__)


@dataclass
class SegmentationPath:
    """
    Represents a path through the segmentation search space.

    A path consists of a sequence of cuts applied to the original mesh,
    resulting in a set of parts. The score represents the overall quality
    of this segmentation solution.
    """

    # Current parts after all cuts applied
    parts: List[MeshWrapper] = field(default_factory=list)

    # Sequence of cuts made to reach this state
    cuts: List[CuttingPlane] = field(default_factory=list)

    # Which part each cut was applied to (for reconstruction)
    cut_part_indices: List[int] = field(default_factory=list)

    # Cumulative score (product of individual cut scores)
    score: float = 1.0

    # Sum of individual cut scores (alternative metric)
    score_sum: float = 0.0

    # Depth in search tree
    depth: int = 0

    def is_complete(self, build_volume: Tuple[float, float, float]) -> bool:
        """Check if all parts fit within build volume."""
        return all(part.fits_in_volume(build_volume) for part in self.parts)

    def parts_exceeding(self, build_volume: Tuple[float, float, float]) -> List[int]:
        """Return indices of parts that exceed build volume."""
        return [
            i for i, part in enumerate(self.parts)
            if not part.fits_in_volume(build_volume)
        ]

    def copy(self) -> "SegmentationPath":
        """Create a copy of this path."""
        return SegmentationPath(
            parts=list(self.parts),
            cuts=list(self.cuts),
            cut_part_indices=list(self.cut_part_indices),
            score=self.score,
            score_sum=self.score_sum,
            depth=self.depth,
        )


@dataclass
class BeamSearchResult:
    """Result from beam search algorithm."""

    best_path: Optional[SegmentationPath]
    all_paths_explored: int
    search_time_seconds: float
    terminated_reason: str  # "complete", "timeout", "max_depth", "no_valid_cuts"


class BeamSearchSegmenter:
    """
    Beam search algorithm for mesh segmentation.

    Instead of greedily selecting the single best cut at each step,
    beam search maintains multiple candidate solutions (the "beam")
    and explores them in parallel, keeping only the top-scoring paths.

    This can find better global solutions when a locally suboptimal
    cut leads to better overall results.
    """

    def __init__(
        self,
        config: SegmentationConfig,
        cut_scorer: Callable[[MeshWrapper, CuttingPlane], float],
        cut_generator: Callable[[MeshWrapper], List["CutCandidate"]],
        cut_executor: Callable[[MeshWrapper, CuttingPlane], Tuple[MeshWrapper, MeshWrapper]],
    ):
        """
        Initialize beam search segmenter.

        Args:
            config: Segmentation configuration
            cut_scorer: Function to score a cut on a mesh (returns 0-1)
            cut_generator: Function to generate candidate cuts for a mesh
            cut_executor: Function to execute a cut and return two parts
        """
        self.config = config
        self.build_volume = config.build_volume
        self.beam_width = config.beam_width
        self.max_depth = config.beam_max_depth
        self.timeout = config.beam_timeout_seconds

        self._score_cut = cut_scorer
        self._generate_cuts = cut_generator
        self._execute_cut = cut_executor

    def search(self, mesh: MeshWrapper) -> BeamSearchResult:
        """
        Perform beam search to find optimal segmentation.

        Args:
            mesh: Input mesh to segment

        Returns:
            BeamSearchResult with best path found
        """
        start_time = time.time()
        paths_explored = 0

        # Initialize beam with starting state
        initial_path = SegmentationPath(parts=[mesh])
        beam: List[SegmentationPath] = [initial_path]

        # Track best complete solution found
        best_complete: Optional[SegmentationPath] = None

        for depth in range(self.max_depth):
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                LOGGER.info(f"Beam search timeout after {elapsed:.1f}s at depth {depth}")
                return BeamSearchResult(
                    best_path=best_complete or self._get_best_path(beam),
                    all_paths_explored=paths_explored,
                    search_time_seconds=elapsed,
                    terminated_reason="timeout",
                )

            # Check if all paths are complete
            if all(path.is_complete(self.build_volume) for path in beam):
                LOGGER.info(f"All paths complete at depth {depth}")
                return BeamSearchResult(
                    best_path=self._get_best_path(beam),
                    all_paths_explored=paths_explored,
                    search_time_seconds=time.time() - start_time,
                    terminated_reason="complete",
                )

            # Expand all paths in beam
            all_expansions: List[SegmentationPath] = []

            for path in beam:
                if path.is_complete(self.build_volume):
                    # Keep complete paths in beam
                    all_expansions.append(path)
                    if best_complete is None or path.score > best_complete.score:
                        best_complete = path
                    continue

                # Expand this path by trying cuts on each oversized part
                expansions = self._expand_path(path)
                paths_explored += len(expansions)
                all_expansions.extend(expansions)

            if not all_expansions:
                LOGGER.warning(f"No valid expansions at depth {depth}")
                return BeamSearchResult(
                    best_path=best_complete,
                    all_paths_explored=paths_explored,
                    search_time_seconds=time.time() - start_time,
                    terminated_reason="no_valid_cuts",
                )

            # Keep top beam_width paths
            all_expansions.sort(key=lambda p: p.score, reverse=True)
            beam = all_expansions[:self.beam_width]

            LOGGER.debug(
                f"Depth {depth}: {len(all_expansions)} expansions, "
                f"top score: {beam[0].score:.3f}, "
                f"parts: {len(beam[0].parts)}"
            )

        # Reached max depth
        LOGGER.info(f"Beam search reached max depth {self.max_depth}")
        return BeamSearchResult(
            best_path=best_complete or self._get_best_path(beam),
            all_paths_explored=paths_explored,
            search_time_seconds=time.time() - start_time,
            terminated_reason="max_depth",
        )

    def _expand_path(self, path: SegmentationPath) -> List[SegmentationPath]:
        """
        Expand a path by applying one cut to each oversized part.

        Returns all possible single-cut expansions of the path.
        """
        expansions: List[SegmentationPath] = []
        exceeding_indices = path.parts_exceeding(self.build_volume)

        for part_idx in exceeding_indices:
            part = path.parts[part_idx]

            # Generate candidate cuts for this part
            candidates = self._generate_cuts(part)

            for candidate in candidates:
                # Execute the cut
                try:
                    positive, negative = self._execute_cut(part, candidate.plane)

                    # Skip if either piece is degenerate
                    if positive.volume_cm3 < 0.1 or negative.volume_cm3 < 0.1:
                        continue

                    # Create new path with this cut applied
                    new_parts = list(path.parts)
                    new_parts.pop(part_idx)
                    new_parts.extend([positive, negative])

                    new_path = SegmentationPath(
                        parts=new_parts,
                        cuts=path.cuts + [candidate.plane],
                        cut_part_indices=path.cut_part_indices + [part_idx],
                        score=path.score * candidate.score,
                        score_sum=path.score_sum + candidate.score,
                        depth=path.depth + 1,
                    )
                    expansions.append(new_path)

                except Exception as e:
                    LOGGER.debug(f"Cut execution failed: {e}")
                    continue

        return expansions

    def _get_best_path(self, beam: List[SegmentationPath]) -> Optional[SegmentationPath]:
        """Get the best path from the beam."""
        if not beam:
            return None

        # Prefer complete paths
        complete_paths = [p for p in beam if p.is_complete(self.build_volume)]
        if complete_paths:
            return max(complete_paths, key=lambda p: p.score)

        # Otherwise, return highest scoring path
        return max(beam, key=lambda p: p.score)


def create_beam_search_segmenter(
    config: SegmentationConfig,
    engine: "PlanarSegmentationEngine",
) -> BeamSearchSegmenter:
    """
    Factory function to create a BeamSearchSegmenter from an engine.

    Args:
        config: Segmentation configuration
        engine: PlanarSegmentationEngine to use for cut generation/execution

    Returns:
        Configured BeamSearchSegmenter
    """
    from .base import SegmentationState

    def score_cut(mesh: MeshWrapper, plane: CuttingPlane) -> float:
        """Score a cut using the engine's scoring logic."""
        # Use the engine's internal scoring - generate cuts for all axes
        bbox = mesh.bounding_box
        exceeds = bbox.exceeds(config.build_volume)
        candidates = []

        for axis in range(3):
            if exceeds[axis]:
                axis_cuts = engine._generate_axis_cuts(mesh, axis)
                candidates.extend(axis_cuts)

        for c in candidates:
            if _planes_equal(c.plane, plane):
                return c.score
        return 0.5  # Default score if not found

    def generate_cuts(mesh: MeshWrapper) -> List["CutCandidate"]:
        """Generate candidate cuts using the engine."""
        import numpy as np

        bbox = mesh.bounding_box
        dims = bbox.dimensions
        exceeds = bbox.exceeds(config.build_volume)

        candidates = []

        # Generate cuts for each axis that exceeds build volume
        for axis in range(3):
            if exceeds[axis]:
                axis_cuts = engine._generate_axis_cuts(mesh, axis)
                candidates.extend(axis_cuts)

        if not candidates:
            # If nothing exceeds, try cutting largest dimension
            largest_axis = int(np.argmax(dims))
            candidates = engine._generate_axis_cuts(mesh, largest_axis)

        # Also try oblique cuts if enabled
        if config.enable_oblique_cuts:
            oblique = engine._generate_oblique_cuts(mesh)
            candidates.extend(oblique)

        return candidates

    def execute_cut(
        mesh: MeshWrapper, plane: CuttingPlane
    ) -> Tuple[MeshWrapper, MeshWrapper]:
        """Execute a cut using the engine."""
        return engine.execute_cut(mesh, plane)

    return BeamSearchSegmenter(
        config=config,
        cut_scorer=score_cut,
        cut_generator=generate_cuts,
        cut_executor=execute_cut,
    )


def _planes_equal(p1: CuttingPlane, p2: CuttingPlane, tol: float = 1e-6) -> bool:
    """Check if two planes are approximately equal."""
    origin_match = np.allclose(p1.origin, p2.origin, atol=tol)
    normal_match = np.allclose(p1.normal, p2.normal, atol=tol)
    return origin_match and normal_match
