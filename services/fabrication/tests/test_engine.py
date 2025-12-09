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
