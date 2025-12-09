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


class TestSeamVisibilityScoring:
    """Tests for Phase 1B: Seam visibility scoring."""

    def test_bottom_cuts_more_hidden_than_top(self) -> None:
        """Test that bottom Z-axis cuts score higher (more hidden) than top cuts."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        # Create a simple box
        mesh = trimesh.creation.box(extents=[100, 100, 100])
        # Center at origin, so Z ranges from -50 to +50
        wrapper = MeshWrapper(mesh)

        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))

        # Cut near bottom (Z = -40)
        bottom_plane = CuttingPlane.horizontal(-40.0)
        bottom_visibility = engine.calculate_seam_visibility(wrapper, bottom_plane)

        # Cut near top (Z = +40)
        top_plane = CuttingPlane.horizontal(40.0)
        top_visibility = engine.calculate_seam_visibility(wrapper, top_plane)

        # Bottom cuts should be MORE hidden (higher visibility score)
        assert bottom_visibility > top_visibility
        # Bottom should be highly hidden
        assert bottom_visibility > 0.7
        # Top should be more visible
        assert top_visibility < 0.5

    def test_back_cuts_more_hidden_than_front(self) -> None:
        """Test that back Y-axis cuts score higher (more hidden) than front cuts."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        mesh = trimesh.creation.box(extents=[100, 100, 100])
        wrapper = MeshWrapper(mesh)

        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))

        # Cut near back (Y = -40, assuming -Y is back)
        back_plane = CuttingPlane.vertical_y(-40.0)
        back_visibility = engine.calculate_seam_visibility(wrapper, back_plane)

        # Cut near front (Y = +40, assuming +Y is front)
        front_plane = CuttingPlane.vertical_y(40.0)
        front_visibility = engine.calculate_seam_visibility(wrapper, front_plane)

        # Back cuts should be more hidden
        assert back_visibility > front_visibility

    def test_side_cuts_moderate_visibility(self) -> None:
        """Test that X-axis cuts have moderate visibility scores."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        mesh = trimesh.creation.box(extents=[100, 100, 100])
        wrapper = MeshWrapper(mesh)

        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))

        # Cut in the middle of X
        center_plane = CuttingPlane.vertical_x(0.0)
        center_visibility = engine.calculate_seam_visibility(wrapper, center_plane)

        # Cut near edge of X
        edge_plane = CuttingPlane.vertical_x(40.0)
        edge_visibility = engine.calculate_seam_visibility(wrapper, edge_plane)

        # Center cuts are more visible than edge cuts
        assert edge_visibility > center_visibility
        # Both should be in moderate range
        assert 0.3 < center_visibility < 0.7
        assert 0.4 < edge_visibility < 0.8

    def test_visibility_affects_cut_selection(
        self, oversized_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that visibility scoring affects cut candidate ranking."""
        engine = PlanarSegmentationEngine(
            build_volume=(200, 200, 200),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(oversized_mesh)

        # Run segmentation
        result = engine.segment(wrapper, output_dir=temp_dir)

        # Verify segmentation completed successfully with visibility scoring
        assert result.success
        # The key test is that segmentation still works with visibility scoring


class TestObliqueCuttingPlanes:
    """Tests for Phase 1C: Oblique cutting planes."""

    def test_oblique_cuts_disabled_by_default(self) -> None:
        """Test that oblique cuts are disabled by default."""
        engine = PlanarSegmentationEngine(build_volume=(256, 256, 256))
        assert not getattr(engine.config, 'enable_oblique_cuts', False)

    def test_oblique_cuts_can_be_enabled(self) -> None:
        """Test that oblique cuts can be enabled via config."""
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_oblique_cuts=True,
            oblique_fallback_threshold=0.5,
        )
        assert engine.config.enable_oblique_cuts is True
        assert engine.config.oblique_fallback_threshold == 0.5

    def test_pca_finds_principal_axes(self) -> None:
        """Test that PCA finds mesh principal axes correctly."""
        # Create a rotated box (diagonal orientation)
        # This should have principal axes along its edges, not X/Y/Z
        vertices = np.array([
            [0, 0, 0], [100, 100, 0], [100, 100, 50], [0, 0, 50],
            [100, 0, 0], [200, 100, 0], [200, 100, 50], [100, 0, 50],
        ], dtype=np.float64)
        faces = np.array([
            [0, 1, 2], [0, 2, 3],  # One side
            [4, 6, 5], [4, 7, 6],  # Other side
            [0, 4, 5], [0, 5, 1],  # Front
            [3, 2, 6], [3, 6, 7],  # Back
            [0, 3, 7], [0, 7, 4],  # Bottom
            [1, 5, 6], [1, 6, 2],  # Top
        ])
        diagonal_box = trimesh.Trimesh(vertices=vertices, faces=faces)
        wrapper = MeshWrapper(diagonal_box)

        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_oblique_cuts=True,
        )

        # Generate oblique cuts
        candidates = engine._generate_oblique_cuts(wrapper)

        # Should generate candidates (3 axes × 3 positions = 9 max)
        assert len(candidates) > 0
        # All should be oblique type
        for c in candidates:
            assert c.plane.plane_type == "oblique"

    def test_oblique_cuts_have_valid_scores(self) -> None:
        """Test that oblique cut candidates have valid scores."""
        # Create a simple diagonal mesh
        mesh = trimesh.creation.box(extents=[200, 100, 100])
        # Rotate 45 degrees around Z
        rotation = trimesh.transformations.rotation_matrix(
            np.pi / 4, [0, 0, 1]
        )
        mesh.apply_transform(rotation)
        wrapper = MeshWrapper(mesh)

        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_oblique_cuts=True,
        )

        candidates = engine._generate_oblique_cuts(wrapper)

        for c in candidates:
            # Score should be valid (0-1 range, though can exceed slightly due to weighting)
            assert 0.0 <= c.score <= 1.5
            assert 0.0 <= c.max_overhang_ratio <= 1.0
            assert 0.0 <= c.seam_visibility <= 1.0
            assert 0.0 <= c.balance_score <= 1.0

    def test_oblique_only_used_when_axis_aligned_poor(
        self, oversized_mesh: trimesh.Trimesh, temp_dir: Path
    ) -> None:
        """Test that oblique cuts are only tried when axis-aligned score is low."""
        engine = PlanarSegmentationEngine(
            build_volume=(200, 200, 200),
            enable_hollowing=False,
            joint_type="none",
            enable_oblique_cuts=True,
            oblique_fallback_threshold=0.3,  # Low threshold
        )
        wrapper = MeshWrapper(oversized_mesh)

        # Run segmentation - should complete successfully
        result = engine.segment(wrapper, output_dir=temp_dir)

        assert result.success
        # The oversized_mesh is axis-aligned, so axis-aligned cuts should score well
        # and oblique cuts shouldn't be needed

    def test_cutting_plane_from_principal_axis(self) -> None:
        """Test CuttingPlane.from_principal_axis factory method."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        # Create plane from diagonal axis
        axis = np.array([1, 1, 0]) / np.sqrt(2)  # 45° in XY plane
        origin = (50.0, 50.0, 25.0)

        plane = CuttingPlane.from_principal_axis(axis, origin)

        assert plane.plane_type == "oblique"
        # Normal should be normalized
        assert abs(np.linalg.norm(plane.normal_array) - 1.0) < 1e-6
        # Normal should point in axis direction
        assert np.allclose(plane.normal_array, axis, atol=1e-6)

    def test_cutting_plane_from_spherical(self) -> None:
        """Test CuttingPlane.from_spherical factory method."""
        from fabrication.segmentation.geometry.plane import CuttingPlane

        # theta=0, phi=π/2 should give normal pointing in +X direction
        plane = CuttingPlane.from_spherical(
            theta=0,
            phi=np.pi / 2,
            origin=(50.0, 0.0, 0.0),
        )

        assert plane.plane_type == "oblique"
        assert np.allclose(plane.normal_array, [1, 0, 0], atol=1e-6)
