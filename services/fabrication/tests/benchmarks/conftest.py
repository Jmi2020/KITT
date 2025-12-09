# noqa: D104
"""Pytest fixtures for benchmarking segmentation upgrades."""

from __future__ import annotations

import json
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Generator

import numpy as np
import pytest
import trimesh


@dataclass
class CutQualityMetrics:
    """Metrics for evaluating cut quality."""

    total_overhang_area_mm2: float = 0.0
    max_overhang_angle_deg: float = 0.0
    avg_overhang_ratio: float = 0.0
    seam_visibility_score: float = 0.0  # 0-1, lower=better
    fit_efficiency: float = 0.0  # % of build volume utilized
    balance_score: float = 0.0  # Evenness of part volumes
    num_parts: int = 0
    num_cuts: int = 0


@dataclass
class PerformanceMetrics:
    """Metrics for evaluating performance."""

    total_time_ms: float = 0.0
    hollowing_time_ms: float = 0.0
    cutting_time_ms: float = 0.0
    joint_generation_time_ms: float = 0.0
    output_generation_time_ms: float = 0.0
    peak_memory_mb: float = 0.0


@dataclass
class BenchmarkResult:
    """Combined benchmark result for a test case."""

    test_name: str
    mesh_description: str
    build_volume: tuple[float, float, float]
    quality: CutQualityMetrics = field(default_factory=CutQualityMetrics)
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    timestamp: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "test_name": self.test_name,
            "mesh_description": self.mesh_description,
            "build_volume": self.build_volume,
            "quality": asdict(self.quality),
            "performance": asdict(self.performance),
            "timestamp": self.timestamp,
        }


class BenchmarkRecorder:
    """Records and persists benchmark results."""

    def __init__(self, output_path: Path | None = None):
        self.results: list[BenchmarkResult] = []
        self.output_path = output_path or Path.home() / ".kitt_benchmarks"
        self.output_path.mkdir(parents=True, exist_ok=True)

    def record(self, result: BenchmarkResult) -> None:
        """Record a benchmark result."""
        import datetime

        result.timestamp = datetime.datetime.now().isoformat()
        self.results.append(result)

    def save(self, filename: str = "benchmark_results.json") -> Path:
        """Save results to JSON file."""
        output_file = self.output_path / filename
        with open(output_file, "w") as f:
            json.dump([r.to_dict() for r in self.results], f, indent=2)
        return output_file

    def load_baseline(self, filename: str = "baseline_results.json") -> list[dict]:
        """Load baseline results for comparison."""
        baseline_file = self.output_path / filename
        if baseline_file.exists():
            with open(baseline_file) as f:
                return json.load(f)
        return []


@pytest.fixture
def benchmark_recorder(tmp_path: Path) -> BenchmarkRecorder:
    """Create a benchmark recorder with temp output path."""
    return BenchmarkRecorder(output_path=tmp_path)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test outputs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# Complex mesh fixtures for benchmarking


@pytest.fixture
def diagonal_box_mesh() -> trimesh.Trimesh:
    """
    Create a diagonally-oriented box that benefits from oblique cuts.

    This mesh is rotated 45° around Z, making axis-aligned cuts suboptimal.
    Used to test oblique cut improvements in Phase 1C.
    """
    box = trimesh.creation.box(extents=[400, 200, 150])
    # Rotate 45 degrees around Z axis
    rotation = trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
    box.apply_transform(rotation)
    return box


@pytest.fixture
def high_overhang_mesh() -> trimesh.Trimesh:
    """
    Create a mesh with significant overhangs for testing overhang-aware scoring.

    A tilted rectangular prism that creates overhangs when cut horizontally.
    """
    # Create a box tilted 60 degrees - creates major overhangs
    box = trimesh.creation.box(extents=[300, 150, 200])
    rotation = trimesh.transformations.rotation_matrix(np.pi / 3, [1, 0, 0])
    box.apply_transform(rotation)
    return box


@pytest.fixture
def organic_mesh() -> trimesh.Trimesh:
    """
    Create an organic-shaped mesh (deformed sphere) for realistic testing.

    Simulates a sculpted object with varied geometry.
    """
    sphere = trimesh.creation.icosphere(subdivisions=3, radius=200)
    # Deform it to make it non-uniform
    vertices = sphere.vertices.copy()
    # Apply sinusoidal deformation
    vertices[:, 0] *= 1.0 + 0.3 * np.sin(vertices[:, 2] / 50)
    vertices[:, 1] *= 1.0 + 0.2 * np.cos(vertices[:, 0] / 50)
    sphere.vertices = vertices
    return sphere


@pytest.fixture
def multi_component_mesh() -> trimesh.Trimesh:
    """
    Create a complex mesh that needs many cuts (600x400x300mm).

    Tests beam search effectiveness with many possible cut sequences.
    """
    return trimesh.creation.box(extents=[600, 400, 300])


@pytest.fixture
def architectural_mesh() -> trimesh.Trimesh:
    """
    Create an L-shaped mesh simulating architectural geometry.

    Tests seam visibility scoring - cuts should prefer hidden surfaces.
    """
    # Create L-shape by subtracting a box from a larger box
    outer = trimesh.creation.box(extents=[300, 300, 200])
    inner = trimesh.creation.box(extents=[150, 150, 200])
    # Move inner box to corner
    inner.apply_translation([75, 75, 0])
    # Boolean difference
    try:
        import manifold3d as m3d

        # Convert to Manifold3D format
        outer_mesh = m3d.Mesh(
            vert_properties=outer.vertices.astype(np.float32),
            tri_verts=outer.faces.astype(np.uint32),
        )
        inner_mesh = m3d.Mesh(
            vert_properties=inner.vertices.astype(np.float32),
            tri_verts=inner.faces.astype(np.uint32),
        )
        outer_m = m3d.Manifold(outer_mesh)
        inner_m = m3d.Manifold(inner_mesh)
        result_m = outer_m - inner_m
        mesh_data = result_m.to_mesh()
        return trimesh.Trimesh(vertices=mesh_data.vert_properties, faces=mesh_data.tri_verts)
    except (ImportError, AttributeError):
        # Fallback if manifold3d not available
        return outer


@pytest.fixture
def small_build_volume() -> tuple[float, float, float]:
    """Small build volume (150x150x150mm) for testing segmentation."""
    return (150.0, 150.0, 150.0)


@pytest.fixture
def medium_build_volume() -> tuple[float, float, float]:
    """Medium build volume (256x256x256mm)."""
    return (256.0, 256.0, 256.0)


@pytest.fixture
def large_build_volume() -> tuple[float, float, float]:
    """Large build volume (300x320x325mm) - Bambu H2D."""
    return (300.0, 320.0, 325.0)


# Timing utilities


class Timer:
    """Context manager for timing code blocks."""

    def __init__(self):
        self.elapsed_ms: float = 0.0
        self._start: float = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000


@pytest.fixture
def timer() -> type[Timer]:
    """Provide Timer class for benchmarks."""
    return Timer
