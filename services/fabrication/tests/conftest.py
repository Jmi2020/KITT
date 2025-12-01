# noqa: D104
"""Pytest fixtures for fabrication tests."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator

import numpy as np
import pytest
import trimesh


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def small_cube_mesh() -> trimesh.Trimesh:
    """Create a small cube mesh (50mm) that fits in any printer build volume."""
    return trimesh.creation.box(extents=[50, 50, 50])


@pytest.fixture
def large_cube_mesh() -> trimesh.Trimesh:
    """Create a large cube mesh (400mm) that exceeds typical build volumes."""
    return trimesh.creation.box(extents=[400, 400, 400])


@pytest.fixture
def oversized_mesh() -> trimesh.Trimesh:
    """Create an oversized mesh (600x300x200mm) that needs segmentation."""
    return trimesh.creation.box(extents=[600, 300, 200])


@pytest.fixture
def sphere_mesh() -> trimesh.Trimesh:
    """Create a sphere mesh for testing curved surfaces."""
    return trimesh.creation.icosphere(subdivisions=2, radius=100)


@pytest.fixture
def small_stl_file(temp_dir: Path, small_cube_mesh: trimesh.Trimesh) -> Path:
    """Create a small cube STL file."""
    path = temp_dir / "small_cube.stl"
    small_cube_mesh.export(str(path))
    return path


@pytest.fixture
def large_stl_file(temp_dir: Path, large_cube_mesh: trimesh.Trimesh) -> Path:
    """Create a large cube STL file."""
    path = temp_dir / "large_cube.stl"
    large_cube_mesh.export(str(path))
    return path


@pytest.fixture
def oversized_stl_file(temp_dir: Path, oversized_mesh: trimesh.Trimesh) -> Path:
    """Create an oversized STL file."""
    path = temp_dir / "oversized.stl"
    oversized_mesh.export(str(path))
    return path


@pytest.fixture
def default_build_volume() -> tuple[float, float, float]:
    """Default build volume (256x256x256mm) for testing."""
    return (256.0, 256.0, 256.0)


@pytest.fixture
def small_build_volume() -> tuple[float, float, float]:
    """Small build volume (150x150x150mm) for testing segmentation."""
    return (150.0, 150.0, 150.0)
