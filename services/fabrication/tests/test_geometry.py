# noqa: D104
"""Tests for segmentation geometry modules."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from fabrication.segmentation.geometry.plane import CuttingPlane
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper


class TestCuttingPlane:
    """Tests for CuttingPlane dataclass."""

    def test_create_x_plane(self) -> None:
        """Test creating an X-axis plane."""
        plane = CuttingPlane.vertical_x(100.0)
        assert np.allclose(plane.normal_array, [1, 0, 0])
        assert np.allclose(plane.origin_array, [100, 0, 0])

    def test_create_y_plane(self) -> None:
        """Test creating a Y-axis plane."""
        plane = CuttingPlane.vertical_y(50.0)
        assert np.allclose(plane.normal_array, [0, 1, 0])
        assert np.allclose(plane.origin_array, [0, 50, 0])

    def test_create_z_plane(self) -> None:
        """Test creating a Z-axis plane."""
        plane = CuttingPlane.horizontal(75.0)
        assert np.allclose(plane.normal_array, [0, 0, 1])
        assert np.allclose(plane.origin_array, [0, 0, 75])

    def test_from_axis(self) -> None:
        """Test creating plane from axis index."""
        plane = CuttingPlane.from_axis(axis=1, position=100.0)
        assert np.allclose(plane.normal_array, [0, 1, 0])
        assert np.allclose(plane.origin_array, [0, 100, 0])

    def test_flip(self) -> None:
        """Test flipping a plane."""
        plane = CuttingPlane.vertical_x(50.0)
        flipped = plane.flip()
        assert np.allclose(flipped.normal_array, [-1, 0, 0])
        assert np.allclose(flipped.origin_array, [50, 0, 0])

    def test_point_side_positive(self) -> None:
        """Test point on positive side of plane."""
        plane = CuttingPlane.vertical_x(0.0)
        assert plane.point_side((10.0, 0.0, 0.0)) == 1

    def test_point_side_negative(self) -> None:
        """Test point on negative side of plane."""
        plane = CuttingPlane.vertical_x(0.0)
        assert plane.point_side((-10.0, 0.0, 0.0)) == -1

    def test_point_side_on_plane(self) -> None:
        """Test point on the plane."""
        plane = CuttingPlane.vertical_x(0.0)
        assert plane.point_side((0.0, 5.0, 10.0)) == 0

    def test_offset(self) -> None:
        """Test plane offset calculation."""
        plane = CuttingPlane.horizontal(100.0)
        assert abs(plane.offset - 100.0) < 1e-6


class TestMeshWrapper:
    """Tests for MeshWrapper class."""

    def test_from_trimesh(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test creating MeshWrapper from trimesh."""
        wrapper = MeshWrapper(small_cube_mesh)
        assert wrapper.as_trimesh is not None
        assert len(wrapper.vertices) > 0
        assert len(wrapper.faces) > 0

    def test_from_file(self, small_stl_file: Path) -> None:
        """Test loading MeshWrapper from file."""
        wrapper = MeshWrapper(str(small_stl_file))
        assert wrapper.as_trimesh is not None
        assert wrapper.bounding_box is not None

    def test_bounds_calculation(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test bounding_box calculation."""
        wrapper = MeshWrapper(small_cube_mesh)
        bbox = wrapper.bounding_box
        # 50mm cube centered at origin
        assert abs(bbox.min_x - (-25)) < 1e-6
        assert abs(bbox.max_x - 25) < 1e-6
        assert abs(bbox.min_y - (-25)) < 1e-6
        assert abs(bbox.max_y - 25) < 1e-6
        assert abs(bbox.min_z - (-25)) < 1e-6
        assert abs(bbox.max_z - 25) < 1e-6

    def test_dimensions(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test dimension calculation."""
        wrapper = MeshWrapper(small_cube_mesh)
        dims = wrapper.dimensions
        assert np.allclose(dims, [50, 50, 50])

    def test_centroid(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test center calculation via bounding_box."""
        wrapper = MeshWrapper(small_cube_mesh)
        bbox = wrapper.bounding_box
        # Centroid should be at origin for centered cube
        center_x = (bbox.min_x + bbox.max_x) / 2
        center_y = (bbox.min_y + bbox.max_y) / 2
        center_z = (bbox.min_z + bbox.max_z) / 2
        assert abs(center_x) < 1e-6
        assert abs(center_y) < 1e-6
        assert abs(center_z) < 1e-6

    def test_volume(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test volume calculation."""
        wrapper = MeshWrapper(small_cube_mesh)
        volume = wrapper.volume
        expected = 50 * 50 * 50  # 125000 mm³
        assert abs(volume - expected) < 1.0

    def test_is_watertight(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test watertight check."""
        wrapper = MeshWrapper(small_cube_mesh)
        assert wrapper.is_watertight

    def test_fits_in_volume_true(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test fits_in_volume with sufficient space."""
        wrapper = MeshWrapper(small_cube_mesh)
        assert wrapper.fits_in_volume((100, 100, 100))

    def test_fits_in_volume_false(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test fits_in_volume with insufficient space."""
        wrapper = MeshWrapper(small_cube_mesh)
        assert not wrapper.fits_in_volume((40, 40, 40))

    def test_export_stl(self, small_cube_mesh: trimesh.Trimesh, temp_dir: Path) -> None:
        """Test STL export."""
        wrapper = MeshWrapper(small_cube_mesh)
        out_path = temp_dir / "export.stl"
        wrapper.export(str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_split_by_plane(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test splitting mesh by plane."""
        wrapper = MeshWrapper(small_cube_mesh)
        plane = CuttingPlane.vertical_x(0.0)
        pos_part, neg_part = wrapper.split(plane)
        assert pos_part is not None
        assert neg_part is not None
        assert pos_part.volume > 0
        assert neg_part.volume > 0
