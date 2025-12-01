# noqa: D104
"""Tests for segmentation schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fabrication.segmentation.schemas import (
    SegmentationRequest,
    SegmentationResult,
    SegmentedPart,
    CheckSegmentationRequest,
    CheckSegmentationResult,
)


class TestSegmentationRequest:
    """Tests for SegmentationRequest schema."""

    def test_minimal_request(self) -> None:
        """Test creating request with minimal fields."""
        request = SegmentationRequest(stl_path="/path/to/model.stl")
        assert request.stl_path == "/path/to/model.stl"
        assert request.printer_id is None
        assert request.enable_hollowing is True  # Default
        assert request.wall_thickness_mm == 2.0  # Default
        assert request.joint_type == "dowel"  # Default
        assert request.max_parts == 10  # Default

    def test_full_request(self) -> None:
        """Test creating request with all fields."""
        request = SegmentationRequest(
            stl_path="/path/to/model.stl",
            printer_id="bamboo_h2d",
            enable_hollowing=False,
            wall_thickness_mm=3.5,
            joint_type="dovetail",
            max_parts=5,
        )
        assert request.printer_id == "bamboo_h2d"
        assert not request.enable_hollowing
        assert request.wall_thickness_mm == 3.5
        assert request.joint_type == "dovetail"
        assert request.max_parts == 5

    def test_invalid_joint_type(self) -> None:
        """Test that invalid joint type raises error."""
        with pytest.raises(ValidationError):
            SegmentationRequest(
                stl_path="/path/to/model.stl",
                joint_type="invalid_type",
            )

    def test_invalid_wall_thickness(self) -> None:
        """Test that invalid wall thickness raises error."""
        with pytest.raises(ValidationError):
            SegmentationRequest(
                stl_path="/path/to/model.stl",
                wall_thickness_mm=-1.0,  # Negative
            )

    def test_invalid_max_parts(self) -> None:
        """Test that invalid max_parts raises error."""
        with pytest.raises(ValidationError):
            SegmentationRequest(
                stl_path="/path/to/model.stl",
                max_parts=0,  # Must be at least 1
            )


class TestSegmentedPart:
    """Tests for SegmentedPart schema."""

    def test_create_part(self) -> None:
        """Test creating a segmented part."""
        part = SegmentedPart(
            part_id="part_001",
            path="artifacts/3mf/model_part_001.3mf",
            dimensions={"x": 100.0, "y": 100.0, "z": 100.0},
            volume_mm3=1000000.0,
            joint_count=4,
        )
        assert part.part_id == "part_001"
        assert part.path == "artifacts/3mf/model_part_001.3mf"
        assert part.dimensions["x"] == 100.0
        assert part.volume_mm3 == 1000000.0
        assert part.joint_count == 4

    def test_part_with_zero_joints(self) -> None:
        """Test part with no joints."""
        part = SegmentedPart(
            part_id="part_001",
            path="artifacts/3mf/model_part_001.3mf",
            dimensions={"x": 50.0, "y": 50.0, "z": 50.0},
            volume_mm3=125000.0,
            joint_count=0,
        )
        assert part.joint_count == 0


class TestSegmentationResult:
    """Tests for SegmentationResult schema."""

    def test_no_segmentation_result(self) -> None:
        """Test result when no segmentation needed."""
        result = SegmentationResult(
            needs_segmentation=False,
            num_parts=1,
            parts=[
                SegmentedPart(
                    part_id="original",
                    path="artifacts/3mf/model.3mf",
                    dimensions={"x": 50.0, "y": 50.0, "z": 50.0},
                    volume_mm3=125000.0,
                    joint_count=0,
                )
            ],
        )
        assert not result.needs_segmentation
        assert result.num_parts == 1
        assert len(result.parts) == 1

    def test_segmentation_result(self) -> None:
        """Test result when segmentation performed."""
        result = SegmentationResult(
            needs_segmentation=True,
            num_parts=4,
            parts=[
                SegmentedPart(
                    part_id=f"part_{i:03d}",
                    path=f"artifacts/3mf/model_part_{i:03d}.3mf",
                    dimensions={"x": 100.0, "y": 100.0, "z": 100.0},
                    volume_mm3=250000.0,
                    joint_count=2,
                )
                for i in range(4)
            ],
            combined_3mf_path="artifacts/3mf/model_assembly.3mf",
            combined_3mf_uri="fabrication://artifacts/3mf/model_assembly.3mf",
            hardware_required={
                "dowels": {"count": 8, "diameter_mm": 6.0, "length_mm": 30.0}
            },
            assembly_notes="Assembly instructions...",
        )
        assert result.needs_segmentation
        assert result.num_parts == 4
        assert len(result.parts) == 4
        assert result.combined_3mf_path is not None
        assert result.hardware_required is not None
        assert result.hardware_required["dowels"]["count"] == 8


class TestCheckSegmentationRequest:
    """Tests for CheckSegmentationRequest schema."""

    def test_check_request(self) -> None:
        """Test creating a check request."""
        request = CheckSegmentationRequest(
            stl_path="/path/to/model.stl",
            printer_id="bamboo_h2d",
        )
        assert request.stl_path == "/path/to/model.stl"
        assert request.printer_id == "bamboo_h2d"

    def test_check_request_no_printer(self) -> None:
        """Test check request without printer."""
        request = CheckSegmentationRequest(stl_path="/path/to/model.stl")
        assert request.printer_id is None


class TestCheckSegmentationResult:
    """Tests for CheckSegmentationResult schema."""

    def test_check_result_fits(self) -> None:
        """Test check result when model fits."""
        result = CheckSegmentationResult(
            needs_segmentation=False,
            model_dimensions={"x": 50.0, "y": 50.0, "z": 50.0},
            build_volume={"x": 256.0, "y": 256.0, "z": 256.0},
            exceeds={"x": False, "y": False, "z": False},
            recommended_cuts=0,
            printer_id="bamboo_h2d",
        )
        assert not result.needs_segmentation
        assert result.recommended_cuts == 0

    def test_check_result_exceeds(self) -> None:
        """Test check result when model exceeds build volume."""
        result = CheckSegmentationResult(
            needs_segmentation=True,
            model_dimensions={"x": 400.0, "y": 300.0, "z": 200.0},
            build_volume={"x": 256.0, "y": 256.0, "z": 256.0},
            exceeds={"x": True, "y": True, "z": False},
            recommended_cuts=3,
            printer_id="bamboo_h2d",
        )
        assert result.needs_segmentation
        assert result.exceeds["x"]
        assert result.exceeds["y"]
        assert not result.exceeds["z"]
        assert result.recommended_cuts == 3
