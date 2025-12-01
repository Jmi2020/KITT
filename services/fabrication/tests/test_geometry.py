# noqa: D104
"""Tests for segmentation geometry modules."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from fabrication.segmentation.geometry.plane import CuttingPlane, Axis
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper


class TestCuttingPlane:
    """Tests for CuttingPlane dataclass."""

    def test_create_x_plane(self) -> None:
        """Test creating an X-axis plane."""
        plane = CuttingPlane(axis=Axis.X, position=100.0)
        assert plane.axis == Axis.X
        assert plane.position == 100.0
        assert np.allclose(plane.normal, [1, 0, 0])
        assert np.allclose(plane.point, [100, 0, 0])

    def test_create_y_plane(self) -> None:
        """Test creating a Y-axis plane."""
        plane = CuttingPlane(axis=Axis.Y, position=50.0)
        assert plane.axis == Axis.Y
        assert plane.position == 50.0
        assert np.allclose(plane.normal, [0, 1, 0])
        assert np.allclose(plane.point, [0, 50, 0])

    def test_create_z_plane(self) -> None:
        """Test creating a Z-axis plane."""
        plane = CuttingPlane(axis=Axis.Z, position=75.0)
        assert plane.axis == Axis.Z
        assert plane.position == 75.0
        assert np.allclose(plane.normal, [0, 0, 1])
        assert np.allclose(plane.point, [0, 0, 75])

    def test_from_axis_and_bounds(self) -> None:
        """Test creating plane from axis and bounds."""
        bounds = np.array([[0, 0, 0], [100, 200, 300]])
        plane = CuttingPlane.from_axis_and_bounds(Axis.Y, bounds, fraction=0.5)
        assert plane.axis == Axis.Y
        assert plane.position == 100.0  # Midpoint of 0-200

    def test_flip(self) -> None:
        """Test flipping a plane."""
        plane = CuttingPlane(axis=Axis.X, position=50.0)
        flipped = plane.flip()
        assert np.allclose(flipped.normal, [-1, 0, 0])
        assert flipped.position == 50.0

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        plane = CuttingPlane(axis=Axis.Z, position=25.0)
        d = plane.to_dict()
        assert d["axis"] == "Z"
        assert d["position"] == 25.0
        assert "normal" in d
        assert "point" in d


class TestMeshWrapper:
    """Tests for MeshWrapper class."""

    def test_from_trimesh(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test creating MeshWrapper from trimesh."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        assert wrapper.trimesh is not None
        assert wrapper.vertex_count > 0
        assert wrapper.face_count > 0

    def test_from_file(self, small_stl_file: Path) -> None:
        """Test loading MeshWrapper from file."""
        wrapper = MeshWrapper.from_file(str(small_stl_file))
        assert wrapper.trimesh is not None
        assert wrapper.bounds is not None

    def test_bounds_calculation(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test bounds calculation."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        bounds = wrapper.bounds
        # 50mm cube centered at origin
        assert np.allclose(bounds[0], [-25, -25, -25])
        assert np.allclose(bounds[1], [25, 25, 25])

    def test_dimensions(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test dimension calculation."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        dims = wrapper.dimensions
        assert np.allclose(dims, [50, 50, 50])

    def test_centroid(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test centroid calculation."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        centroid = wrapper.centroid
        assert np.allclose(centroid, [0, 0, 0], atol=1e-6)

    def test_volume(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test volume calculation."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        volume = wrapper.volume
        expected = 50 * 50 * 50  # 125000 mm³
        assert abs(volume - expected) < 1.0

    def test_is_watertight(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test watertight check."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        assert wrapper.is_watertight

    def test_fits_in_volume_true(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test fits_in_volume with sufficient space."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        assert wrapper.fits_in_volume(100, 100, 100)

    def test_fits_in_volume_false(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test fits_in_volume with insufficient space."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        assert not wrapper.fits_in_volume(40, 40, 40)

    def test_exceeds_volume(self, large_cube_mesh: trimesh.Trimesh) -> None:
        """Test exceeds_volume detection."""
        wrapper = MeshWrapper.from_trimesh(large_cube_mesh)
        exceeds = wrapper.exceeds_volume(256, 256, 256)
        assert exceeds["x"]
        assert exceeds["y"]
        assert exceeds["z"]

    def test_split_by_plane(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test splitting mesh by plane."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        plane = CuttingPlane(axis=Axis.X, position=0.0)
        parts = wrapper.split_by_plane(plane)
        assert len(parts) == 2
        for part in parts:
            assert part.volume > 0

    def test_export_stl(self, small_cube_mesh: trimesh.Trimesh, temp_dir: Path) -> None:
        """Test STL export."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        out_path = temp_dir / "export.stl"
        wrapper.export(str(out_path), file_format="stl")
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_copy(self, small_cube_mesh: trimesh.Trimesh) -> None:
        """Test mesh copy."""
        wrapper = MeshWrapper.from_trimesh(small_cube_mesh)
        copy = wrapper.copy()
        assert copy.vertex_count == wrapper.vertex_count
        assert copy is not wrapper
