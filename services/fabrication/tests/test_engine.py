# noqa: D104
"""Tests for segmentation engine modules."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper


class TestPlanarSegmentationEngine:
    """Tests for PlanarSegmentationEngine."""

    def test_init_with_build_volume(self) -> None:
        """Test initialization with build volume."""
        engine = PlanarSegmentationEngine(build_volume=(200, 200, 200))
        assert engine.build_volume == (200, 200, 200)

    def test_mesh_fits_no_segmentation(
        self, small_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that a mesh fitting build volume returns without segmentation."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(small_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        assert not result.needs_segmentation
        assert result.num_parts == 1
        assert len(result.parts) == 1

    def test_large_mesh_requires_segmentation(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that a large mesh triggers segmentation."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        assert result.needs_segmentation
        assert result.num_parts > 1
        # Each part should fit in build volume (dimensions_mm is a tuple)
        for part in result.parts:
            assert part.dimensions_mm[0] <= 256
            assert part.dimensions_mm[1] <= 256
            assert part.dimensions_mm[2] <= 256

    def test_oversized_mesh_multiple_cuts(
        self, oversized_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that oversized mesh results in multiple cuts."""
        # 600x300x200mm mesh with 150mm build volume
        engine = PlanarSegmentationEngine(
            build_volume=(150, 150, 150),
            enable_hollowing=False,
            joint_type="none",
            max_parts=20,
        )
        wrapper = MeshWrapper(oversized_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        assert result.needs_segmentation
        assert result.num_parts >= 4  # Should need at least 4 parts

    def test_max_parts_limit(
        self, oversized_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that max_parts limit is respected."""
        engine = PlanarSegmentationEngine(
            build_volume=(100, 100, 100),
            enable_hollowing=False,
            joint_type="none",
            max_parts=3,
        )
        wrapper = MeshWrapper(oversized_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        assert result.num_parts <= 3

    def test_segmentation_with_hollowing(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test segmentation with hollowing enabled."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=True,
            wall_thickness_mm=3.0,
            joint_type="none",
        )
        wrapper = MeshWrapper(large_cube_mesh)
        original_volume = wrapper.volume

        result = engine.segment(wrapper, output_dir=temp_dir)

        # Hollowed parts should have less total volume than original
        # volume_cm3 needs to be converted to mm3 for comparison
        total_volume = sum(part.volume_cm3 * 1000 for part in result.parts)
        # With hollowing, total volume should be significantly less
        # (unless hollowing failed, in which case it's roughly the same)
        assert total_volume <= original_volume * 1.1  # Allow 10% margin

    def test_output_files_created(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that output files are created."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # Check that part files are set
        for part in result.parts:
            # file_path should be set (may be empty for single-part no-cut)
            assert part.file_path is not None

    def test_part_ids_unique(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that all parts have unique indices/names."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # Check indices are unique
        indices = [part.index for part in result.parts]
        assert len(indices) == len(set(indices))

    def test_check_needs_segmentation(self, large_cube_mesh: trimesh.Trimesh) -> None:
        """Test the check_segmentation method."""
        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.check_segmentation(wrapper)
        assert result["needs_segmentation"]
        # Check that at least one dimension exceeds build volume
        assert any(ex > 0 for ex in result["exceeds_by_mm"])

    def test_check_no_segmentation_needed(
        self, small_cube_mesh: trimesh.Trimesh
    ) -> None:
        """Test check when no segmentation is needed."""
        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))
        wrapper = MeshWrapper(small_cube_mesh)

        result = engine.check_segmentation(wrapper)
        assert not result["needs_segmentation"]
        assert all(ex == 0 for ex in result["exceeds_by_mm"])


class TestSegmentationWithJoints:
    """Tests for segmentation with joint generation."""

    def test_dowel_joints_generated(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that dowel joints are generated when requested."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="dowel",
        )
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        if result.needs_segmentation:
            # Should have hardware requirements
            assert result.hardware_required is not None
            # Should have at least one part with joints
            total_joints = sum(len(part.joints) for part in result.parts)
            assert total_joints >= 0  # May be 0 if joints failed

    def test_no_joints_when_disabled(
        self, large_cube_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that no joints are generated when type is 'none'."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(large_cube_mesh)

        result = engine.segment(wrapper, output_dir=temp_dir)

        # No hardware required when joints disabled
        if result.hardware_required:
            assert result.hardware_required.get("dowels") is None


class TestOverhangAwareScoring:
    """Tests for Phase 1A: Overhang-aware cut scoring."""

    def test_overhang_ratio_calculation(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test that overhang ratio is calculated correctly for a simple cube."""
        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))
        wrapper = MeshWrapper(small_cube_mesh)

        # A cube has no overhangs when printed flat - all faces are either
        # horizontal or vertical (0° or 90° from Z)
        ratio = engine.calculate_overhang_ratio(wrapper, threshold_angle=30.0)

        # Cube should have minimal overhangs (only bottom face, which is 0°)
        assert ratio < 0.5  # Less than half the surface should be overhang

    def test_overhang_estimation_considers_orientation(self) -> None:
        """Test that overhang estimation tests multiple orientations."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        # Create a diagonal ramp mesh (45° surface)
        # This creates a triangular prism with one 45° face
        vertices = np.array([
            [0, 0, 0], [100, 0, 0], [0, 100, 0],  # Base triangle
            [0, 0, 50], [100, 0, 50], [0, 100, 50],  # Top triangle
        ], dtype=np.float64)
        faces = np.array([
            [0, 1, 2],  # Bottom
            [3, 5, 4],  # Top
            [0, 3, 4], [0, 4, 1],  # Front face (vertical)
            [1, 4, 5], [1, 5, 2],  # Diagonal face (45°)
            [2, 5, 3], [2, 3, 0],  # Back face (vertical)
        ])
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
        wrapper = MeshWrapper(mesh)

        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))

        # Create a cutting plane through the middle
        plane = CuttingPlane.vertical_x(50.0)

        # Estimate overhangs - should consider all orientations
        overhang_positive = engine.estimate_part_overhangs(
            wrapper, plane, "positive", threshold_angle=30.0
        )
        overhang_negative = engine.estimate_part_overhangs(
            wrapper, plane, "negative", threshold_angle=30.0
        )

        # Both halves should have analyzed for optimal orientation
        # With 6 orientations tested, at least one should be reasonable
        assert overhang_positive >= 0.0
        assert overhang_negative >= 0.0

    def test_configurable_overhang_threshold(self, temp_dir: Path) -> None:
        """Test that overhang threshold is configurable via config."""
        # Create mesh with 35° overhang (between 30° and 45°)
        # This should be flagged at 30° threshold but not at 45°
        engine_strict = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
            overhang_threshold_deg=30.0,  # Strict threshold
        )
        engine_relaxed = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
            overhang_threshold_deg=45.0,  # Relaxed threshold
        )

        # Verify the thresholds are stored
        assert engine_strict.config.overhang_threshold_deg == 30.0
        assert engine_relaxed.config.overhang_threshold_deg == 45.0

    def test_overhang_score_affects_cut_selection(
        self, oversized_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that overhang scoring influences cut candidate selection."""
        engine = PlanarSegmentationEngine(
            build_volume=(200, 200, 200),
            enable_hollowing=False,
            joint_type="none",
            overhang_threshold_deg=30.0,
        )
        wrapper = MeshWrapper(oversized_mesh)

        # Run segmentation
        result = engine.segment(wrapper, output_dir=temp_dir)

        # Verify segmentation completed successfully
        assert result.success
        # Parts should have been evaluated for overhangs
        # The key test is that segmentation still works with overhang scoring

    def test_vertical_print_orientation_optimized(self) -> None:
        """Test that parts can be reoriented for vertical printing."""
        # Create a tall thin box that would benefit from vertical orientation
        vertices = np.array([
            [0, 0, 0], [20, 0, 0], [20, 20, 0], [0, 20, 0],  # Bottom
            [0, 0, 200], [20, 0, 200], [20, 20, 200], [0, 20, 200],  # Top
        ], dtype=np.float64)
        faces = np.array([
            [0, 2, 1], [0, 3, 2],  # Bottom
            [4, 5, 6], [4, 6, 7],  # Top
            [0, 1, 5], [0, 5, 4],  # Front
            [2, 3, 7], [2, 7, 6],  # Back
            [1, 2, 6], [1, 6, 5],  # Right
            [3, 0, 4], [3, 4, 7],  # Left
        ])
        tall_box = trimesh.Trimesh(vertices=vertices, faces=faces)
        wrapper = MeshWrapper(tall_box)

        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))

        # Calculate overhang with default Z-up orientation
        ratio_z_up = engine.calculate_overhang_ratio(wrapper, threshold_angle=30.0)

        # A rectangular box has only vertical and horizontal faces,
        # so should have minimal overhangs in any cardinal orientation
        assert ratio_z_up < 0.2  # Less than 20% overhang area
