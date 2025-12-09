# noqa: D104
"""Quality benchmark tests for cut scoring improvements.

These tests establish baselines and measure improvements for:
- Phase 1A: Overhang-aware scoring
- Phase 1B: Seam visibility scoring
- Phase 1C: Oblique cutting planes
- Phase 2: Beam search optimization
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper

from .conftest import BenchmarkRecorder, BenchmarkResult, CutQualityMetrics


def calculate_overhang_metrics(mesh: MeshWrapper, threshold_angle: float = 45.0) -> dict:
    """
    Calculate overhang metrics for a mesh.

    Returns dict with:
    - overhang_area_mm2: Total area of faces exceeding threshold
    - max_overhang_angle: Maximum overhang angle in degrees
    - overhang_ratio: Ratio of overhang area to total surface area
    """
    try:
        normals = mesh.face_normals
        areas = mesh.face_areas
    except (AttributeError, Exception):
        # Handle case where mesh doesn't expose these properties directly
        tm = mesh.as_trimesh if hasattr(mesh, "as_trimesh") else mesh._trimesh
        normals = tm.face_normals
        areas = tm.area_faces

    # Calculate angle from build plate (Z up)
    z_up = np.array([0, 0, 1])
    cos_angles = np.dot(normals, z_up)

    # Find downward-facing triangles
    downward_mask = cos_angles < 0

    if not np.any(downward_mask):
        return {"overhang_area_mm2": 0.0, "max_overhang_angle": 0.0, "overhang_ratio": 0.0}

    # Calculate overhang angles for downward faces
    overhang_angles = np.degrees(np.arccos(np.abs(cos_angles[downward_mask])))
    overhang_threshold_mask = overhang_angles > threshold_angle

    overhang_area = float(np.sum(areas[downward_mask][overhang_threshold_mask]))
    total_area = float(np.sum(areas))
    max_angle = float(np.max(overhang_angles)) if len(overhang_angles) > 0 else 0.0

    return {
        "overhang_area_mm2": overhang_area,
        "max_overhang_angle": max_angle,
        "overhang_ratio": overhang_area / total_area if total_area > 0 else 0.0,
    }


def calculate_fit_efficiency(
    parts: list, build_volume: tuple[float, float, float]
) -> float:
    """
    Calculate how efficiently parts use build volume.

    Returns ratio of part volume to build volume capacity (0-1).
    """
    bv_volume = build_volume[0] * build_volume[1] * build_volume[2]
    total_capacity = bv_volume * len(parts)

    # Use dimensions_mm tuple (x, y, z)
    total_part_volume = sum(
        p.dimensions_mm[0] * p.dimensions_mm[1] * p.dimensions_mm[2] for p in parts
    )

    return total_part_volume / total_capacity if total_capacity > 0 else 0.0


def calculate_balance_score(parts: list) -> float:
    """
    Calculate how evenly balanced part volumes are.

    Returns 1.0 for perfectly balanced, lower for unbalanced.
    """
    if len(parts) <= 1:
        return 1.0

    # Use volume_cm3 (convert to mm3 for consistency)
    volumes = [p.volume_cm3 * 1000 for p in parts]  # cm3 to mm3
    mean_vol = np.mean(volumes)
    std_vol = np.std(volumes)

    # Coefficient of variation (lower is better)
    cv = std_vol / mean_vol if mean_vol > 0 else 0.0

    # Convert to 0-1 score where 1 is best
    return max(0.0, 1.0 - cv)


class TestOverhangQualityBaseline:
    """Baseline tests for overhang metrics before Phase 1A improvements."""

    def test_high_overhang_mesh_baseline(
        self,
        high_overhang_mesh: trimesh.Trimesh,
        small_build_volume: tuple[float, float, float],
        temp_dir: Path,
        benchmark_recorder: BenchmarkRecorder,
    ) -> None:
        """
        Establish baseline overhang metrics for a tilted mesh.

        This test should show high overhang values that Phase 1A will improve.
        """
        engine = PlanarSegmentationEngine(
            build_volume=small_build_volume,
            enable_hollowing=False,
            joint_type="none",
            max_parts=20,
        )
        wrapper = MeshWrapper(high_overhang_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # Calculate overhang metrics for all output parts
        total_overhang_area = 0.0
        max_overhang_angle = 0.0
        total_ratio = 0.0

        for part in result.parts:
            # Load part mesh and analyze
            if part.file_path:
                part_path = Path(part.file_path)
                if part_path.exists():
                    part_mesh = MeshWrapper(str(part_path))
                    metrics = calculate_overhang_metrics(part_mesh)
                    total_overhang_area += metrics["overhang_area_mm2"]
                    max_overhang_angle = max(max_overhang_angle, metrics["max_overhang_angle"])
                    total_ratio += metrics["overhang_ratio"]

        avg_ratio = total_ratio / len(result.parts) if result.parts else 0.0

        # Record baseline
        quality = CutQualityMetrics(
            total_overhang_area_mm2=total_overhang_area,
            max_overhang_angle_deg=max_overhang_angle,
            avg_overhang_ratio=avg_ratio,
            num_parts=result.num_parts,
            num_cuts=result.num_parts - 1,
        )

        benchmark = BenchmarkResult(
            test_name="high_overhang_mesh_baseline",
            mesh_description="60° tilted box (300x150x200mm)",
            build_volume=small_build_volume,
            quality=quality,
        )
        benchmark_recorder.record(benchmark)

        # Assertions for baseline (these may fail initially, adjust thresholds)
        assert result.needs_segmentation
        assert result.num_parts >= 2

        # Log for visibility
        print(f"\n[BASELINE] Overhang area: {total_overhang_area:.2f} mm²")
        print(f"[BASELINE] Max overhang angle: {max_overhang_angle:.1f}°")
        print(f"[BASELINE] Avg overhang ratio: {avg_ratio:.3f}")

    def test_diagonal_mesh_axis_aligned_cuts(
        self,
        diagonal_box_mesh: trimesh.Trimesh,
        medium_build_volume: tuple[float, float, float],
        temp_dir: Path,
    ) -> None:
        """
        Test axis-aligned cuts on diagonally-oriented mesh.

        Phase 1C should improve this by using oblique cuts.
        """
        engine = PlanarSegmentationEngine(
            build_volume=medium_build_volume,
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(diagonal_box_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # Calculate fit efficiency
        efficiency = calculate_fit_efficiency(result.parts, medium_build_volume)

        print(f"\n[BASELINE] Diagonal mesh parts: {result.num_parts}")
        print(f"[BASELINE] Fit efficiency: {efficiency:.3f}")

        # Axis-aligned cuts on rotated mesh should have suboptimal efficiency
        assert result.needs_segmentation


class TestSeamVisibilityBaseline:
    """Baseline tests for seam visibility before Phase 1B improvements."""

    def test_architectural_mesh_seam_placement(
        self,
        architectural_mesh: trimesh.Trimesh,
        medium_build_volume: tuple[float, float, float],
        temp_dir: Path,
    ) -> None:
        """
        Test where seams are placed on architectural geometry.

        Phase 1B should prefer less visible surfaces.
        """
        engine = PlanarSegmentationEngine(
            build_volume=medium_build_volume,
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(architectural_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # For now, just verify segmentation works
        # Phase 1B will add seam visibility scoring
        print(f"\n[BASELINE] Architectural mesh parts: {result.num_parts}")

        if result.needs_segmentation:
            assert result.num_parts >= 2


class TestBalanceBaseline:
    """Baseline tests for part balance before Phase 2 beam search."""

    def test_multi_component_balance(
        self,
        multi_component_mesh: trimesh.Trimesh,
        small_build_volume: tuple[float, float, float],
        temp_dir: Path,
    ) -> None:
        """
        Test part volume balance for complex segmentation.

        Phase 2 beam search should produce more balanced parts.
        """
        engine = PlanarSegmentationEngine(
            build_volume=small_build_volume,
            enable_hollowing=False,
            joint_type="none",
            max_parts=30,
        )
        wrapper = MeshWrapper(multi_component_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        balance = calculate_balance_score(result.parts)
        efficiency = calculate_fit_efficiency(result.parts, small_build_volume)

        print(f"\n[BASELINE] Multi-component parts: {result.num_parts}")
        print(f"[BASELINE] Balance score: {balance:.3f}")
        print(f"[BASELINE] Fit efficiency: {efficiency:.3f}")

        assert result.needs_segmentation
        assert result.num_parts >= 4  # 600x400x300 into 150³ should need many parts


class TestOrganicMeshBaseline:
    """Baseline tests for organic/complex geometry."""

    def test_organic_mesh_segmentation(
        self,
        organic_mesh: trimesh.Trimesh,
        medium_build_volume: tuple[float, float, float],
        temp_dir: Path,
    ) -> None:
        """
        Test segmentation of organic (non-box) geometry.

        Establishes baseline for curved surface handling.
        """
        engine = PlanarSegmentationEngine(
            build_volume=medium_build_volume,
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(organic_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        print(f"\n[BASELINE] Organic mesh parts: {result.num_parts}")

        # Organic mesh (deformed sphere) is ~400mm diameter, should need cuts
        if result.needs_segmentation:
            assert result.num_parts >= 2
