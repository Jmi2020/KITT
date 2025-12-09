# noqa: D104
"""Performance benchmark tests for segmentation operations.

These tests measure execution time and memory usage for:
- Hollowing operations (Phase 4 GPU target)
- Cut generation and scoring
- Joint generation
- Overall segmentation pipeline
"""

from __future__ import annotations

import gc
import time
import tracemalloc
from pathlib import Path

import pytest
import trimesh

from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper

from .conftest import BenchmarkRecorder, BenchmarkResult, PerformanceMetrics


class TestSegmentationPerformance:
    """Performance benchmarks for segmentation pipeline."""

    def test_small_mesh_performance(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark segmentation of a small mesh (no cuts needed).

        Establishes baseline for pipeline overhead.
        """
        mesh = trimesh.creation.box(extents=[50, 50, 50])
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(mesh)

        # Warm-up run
        engine.segment(wrapper, output_dir=temp_dir)

        # Timed run
        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[PERF] Small mesh (50mm cube): {elapsed_ms:.2f}ms")
        print(f"[PERF] Parts: {result.num_parts}")

        # Should be fast (< 500ms)
        assert elapsed_ms < 500, f"Small mesh took too long: {elapsed_ms:.2f}ms"

    def test_large_mesh_cutting_performance(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark cutting performance for large mesh.

        Target: Phase 2 beam search should not regress significantly.
        """
        mesh = trimesh.creation.box(extents=[400, 400, 400])
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="none",
        )
        wrapper = MeshWrapper(mesh)

        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[PERF] Large mesh (400mm cube) cutting: {elapsed_ms:.2f}ms")
        print(f"[PERF] Parts generated: {result.num_parts}")

        # Should complete in reasonable time (< 10s)
        assert elapsed_ms < 10000, f"Large mesh cutting took too long: {elapsed_ms:.2f}ms"

    def test_oversized_mesh_performance(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark performance for heavily oversized mesh.

        600x400x300 into 150³ build volume = many cuts.
        """
        mesh = trimesh.creation.box(extents=[600, 400, 300])
        engine = PlanarSegmentationEngine(
            build_volume=(150, 150, 150),
            enable_hollowing=False,
            joint_type="none",
            max_parts=50,
        )
        wrapper = MeshWrapper(mesh)

        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        cuts_per_second = (result.num_parts - 1) / (elapsed_ms / 1000) if elapsed_ms > 0 else 0

        print(f"\n[PERF] Oversized mesh (600x400x300mm): {elapsed_ms:.2f}ms")
        print(f"[PERF] Parts: {result.num_parts}")
        print(f"[PERF] Cuts per second: {cuts_per_second:.2f}")

        # Performance target
        assert elapsed_ms < 30000, f"Oversized mesh took too long: {elapsed_ms:.2f}ms"


class TestHollowingPerformance:
    """Performance benchmarks for hollowing operations.

    Phase 4 GPU acceleration should significantly improve these.
    """

    @pytest.mark.parametrize("resolution", [100, 200, 500])
    def test_hollowing_at_resolution(
        self,
        resolution: int,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark hollowing at different voxel resolutions.

        GPU acceleration in Phase 4 should show major improvements here.
        """
        mesh = trimesh.creation.box(extents=[200, 200, 200])
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=True,
            wall_thickness_mm=5.0,
            hollowing_resolution=resolution,
            joint_type="none",
        )
        wrapper = MeshWrapper(mesh)

        gc.collect()  # Clean up before measurement

        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[PERF] Hollowing resolution {resolution}: {elapsed_ms:.2f}ms")

        # Resolution-dependent timeout (includes simplification + smoothing overhead)
        max_time_ms = {
            100: 10000,
            200: 35000,  # Increased to account for simplification/smoothing
            500: 90000,
        }

        assert elapsed_ms < max_time_ms.get(resolution, 60000), (
            f"Hollowing at {resolution} took too long: {elapsed_ms:.2f}ms"
        )


class TestJointGenerationPerformance:
    """Performance benchmarks for joint generation."""

    def test_integrated_joints_performance(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark integrated (printed) joint generation.
        """
        mesh = trimesh.creation.box(extents=[400, 400, 400])
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="integrated",
        )
        wrapper = MeshWrapper(mesh)

        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Count joints from each part's joints list
        total_joints = sum(len(p.joints) for p in result.parts)

        print(f"\n[PERF] Integrated joints: {elapsed_ms:.2f}ms")
        print(f"[PERF] Total joints generated: {total_joints}")
        print(f"[PERF] Parts: {result.num_parts}")

    def test_dowel_joints_performance(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Benchmark dowel joint generation.
        """
        mesh = trimesh.creation.box(extents=[400, 400, 400])
        engine = PlanarSegmentationEngine(
            build_volume=(256, 256, 256),
            enable_hollowing=False,
            joint_type="dowel",
        )
        wrapper = MeshWrapper(mesh)

        start = time.perf_counter()
        result = engine.segment(wrapper, output_dir=temp_dir)
        elapsed_ms = (time.perf_counter() - start) * 1000

        print(f"\n[PERF] Dowel joints: {elapsed_ms:.2f}ms")
        print(f"[PERF] Parts: {result.num_parts}")
        if result.hardware_required:
            print(f"[PERF] Hardware: {result.hardware_required}")


class TestMemoryUsage:
    """Memory usage benchmarks."""

    def test_memory_usage_large_mesh(
        self,
        temp_dir: Path,
    ) -> None:
        """
        Measure memory usage for large mesh segmentation.
        """
        mesh = trimesh.creation.box(extents=[500, 500, 500])
        engine = PlanarSegmentationEngine(
            build_volume=(200, 200, 200),
            enable_hollowing=False,
            joint_type="none",
            max_parts=30,
        )
        wrapper = MeshWrapper(mesh)

        gc.collect()
        tracemalloc.start()

        result = engine.segment(wrapper, output_dir=temp_dir)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)

        print(f"\n[PERF] Peak memory: {peak_mb:.2f} MB")
        print(f"[PERF] Parts: {result.num_parts}")

        # Memory should be reasonable (< 2GB for this test)
        assert peak_mb < 2048, f"Memory usage too high: {peak_mb:.2f} MB"


class TestBaselineCapture:
    """Capture comprehensive baseline for all phases."""

    def test_capture_full_baseline(
        self,
        temp_dir: Path,
        benchmark_recorder: BenchmarkRecorder,
    ) -> None:
        """
        Capture a full baseline of all metrics for comparison.

        Run this before implementing any phases to establish baseline.
        """
        test_cases = [
            ("small_cube", trimesh.creation.box(extents=[50, 50, 50]), (256, 256, 256)),
            ("large_cube", trimesh.creation.box(extents=[400, 400, 400]), (256, 256, 256)),
            ("oversized", trimesh.creation.box(extents=[600, 400, 300]), (150, 150, 150)),
        ]

        for name, mesh, build_volume in test_cases:
            engine = PlanarSegmentationEngine(
                build_volume=build_volume,
                enable_hollowing=False,
                joint_type="none",
                max_parts=50,
            )
            wrapper = MeshWrapper(mesh)

            gc.collect()

            start = time.perf_counter()
            result = engine.segment(wrapper, output_dir=temp_dir)
            elapsed_ms = (time.perf_counter() - start) * 1000

            perf = PerformanceMetrics(
                total_time_ms=elapsed_ms,
                cutting_time_ms=elapsed_ms,  # Approximate
            )

            benchmark = BenchmarkResult(
                test_name=f"baseline_{name}",
                mesh_description=name,
                build_volume=build_volume,
                performance=perf,
            )
            benchmark_recorder.record(benchmark)

            print(f"\n[BASELINE] {name}: {elapsed_ms:.2f}ms, {result.num_parts} parts")

        # Save baseline
        output_path = benchmark_recorder.save("baseline_results.json")
        print(f"\n[BASELINE] Saved to: {output_path}")
