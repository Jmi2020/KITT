# noqa: D104
"""Tests for segmentation schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fabrication.segmentation.schemas import (
    SegmentMeshRequest,
    SegmentMeshResponse,
    SegmentedPart,
    SegmentedPartResponse,
    SegmentationResult,
    CheckSegmentationRequest,
    CheckSegmentationResponse,
    JointType,
    JointLocation,
)


class TestSegmentationRequest:
    """Tests for SegmentMeshRequest schema."""

    def test_minimal_request(self) -> None:
        """Test creating request with minimal fields."""
        request = SegmentMeshRequest(stl_path="/path/to/model.stl")
        assert request.mesh_path == "/path/to/model.stl"
        assert request.printer_id is None
        assert request.enable_hollowing is True  # Default
        assert request.wall_thickness_mm == 2.0  # Default
        assert request.joint_type == JointType.INTEGRATED  # Default
        assert request.max_parts == 0  # Default (auto-calculate)

    def test_full_request(self) -> None:
        """Test creating request with all fields."""
        request = SegmentMeshRequest(
            stl_path="/path/to/model.stl",
            printer_id="bamboo_h2d",
            enable_hollowing=False,
            wall_thickness_mm=3.5,
            joint_type=JointType.DOWEL,
            max_parts=5,
        )
        assert request.printer_id == "bamboo_h2d"
        assert not request.enable_hollowing
        assert request.wall_thickness_mm == 3.5
        assert request.joint_type == JointType.DOWEL
        assert request.max_parts == 5

    def test_invalid_joint_type(self) -> None:
        """Test that invalid joint type raises error."""
        with pytest.raises(ValidationError):
            SegmentMeshRequest(
                stl_path="/path/to/model.stl",
                joint_type="invalid_type",
            )

    def test_invalid_wall_thickness(self) -> None:
        """Test that invalid wall thickness raises error."""
        with pytest.raises(ValidationError):
            SegmentMeshRequest(
                stl_path="/path/to/model.stl",
                wall_thickness_mm=0.5,  # Below minimum of 1.2
            )

    def test_invalid_max_parts(self) -> None:
        """Test that invalid max_parts raises error."""
        with pytest.raises(ValidationError):
            SegmentMeshRequest(
                stl_path="/path/to/model.stl",
                max_parts=-1,  # Negative not allowed
            )


class TestSegmentedPart:
    """Tests for SegmentedPart dataclass."""

    def test_create_part(self) -> None:
        """Test creating a segmented part."""
        part = SegmentedPart(
            index=0,
            name="part_001",
            file_path="artifacts/3mf/model_part_001.3mf",
            dimensions_mm=(100.0, 100.0, 100.0),
            volume_cm3=1000.0,
            joints=[],
        )
        assert part.index == 0
        assert part.name == "part_001"
        assert part.file_path == "artifacts/3mf/model_part_001.3mf"
        assert part.dimensions_mm[0] == 100.0
        assert part.volume_cm3 == 1000.0
        assert len(part.joints) == 0

    def test_part_with_zero_joints(self) -> None:
        """Test part with no joints."""
        part = SegmentedPart(
            index=0,
            name="part_001",
            file_path="artifacts/3mf/model_part_001.3mf",
            dimensions_mm=(50.0, 50.0, 50.0),
            volume_cm3=125.0,
            joints=[],
        )
        assert len(part.joints) == 0


class TestSegmentationResult:
    """Tests for SegmentationResult dataclass."""

    def test_no_segmentation_result(self) -> None:
        """Test result when no segmentation needed."""
        result = SegmentationResult(
            success=True,
            needs_segmentation=False,
            num_parts=1,
            parts=[
                SegmentedPart(
                    index=0,
                    name="original",
                    file_path="artifacts/3mf/model.3mf",
                    dimensions_mm=(50.0, 50.0, 50.0),
                    volume_cm3=125.0,
                    joints=[],
                )
            ],
            cut_planes=[],
        )
        assert result.success
        assert not result.needs_segmentation
        assert result.num_parts == 1
        assert len(result.parts) == 1

    def test_segmentation_result(self) -> None:
        """Test result when segmentation performed."""
        from fabrication.segmentation.schemas import CuttingPlane

        result = SegmentationResult(
            success=True,
            needs_segmentation=True,
            num_parts=4,
            parts=[
                SegmentedPart(
                    index=i,
                    name=f"part_{i:03d}",
                    file_path=f"artifacts/3mf/model_part_{i:03d}.3mf",
                    dimensions_mm=(100.0, 100.0, 100.0),
                    volume_cm3=250.0,
                    joints=[
                        JointLocation(position=(0, 0, 0)),
                        JointLocation(position=(10, 0, 0)),
                    ],
                )
                for i in range(4)
            ],
            cut_planes=[
                CuttingPlane(origin=(0, 0, 100), normal=(0, 0, 1)),
            ],
            combined_3mf_path="artifacts/3mf/model_assembly.3mf",
            combined_3mf_uri="fabrication://artifacts/3mf/model_assembly.3mf",
            hardware_required={
                "dowels": {"count": 8, "diameter_mm": 6.0, "length_mm": 30.0}
            },
            assembly_notes="Assembly instructions...",
        )
        assert result.success
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
        assert request.mesh_path == "/path/to/model.stl"
        assert request.printer_id == "bamboo_h2d"

    def test_check_request_no_printer(self) -> None:
        """Test check request without printer."""
        request = CheckSegmentationRequest(stl_path="/path/to/model.stl")
        assert request.printer_id is None


class TestCheckSegmentationResult:
    """Tests for CheckSegmentationResponse schema."""

    def test_check_result_fits(self) -> None:
        """Test check result when model fits."""
        result = CheckSegmentationResponse(
            needs_segmentation=False,
            model_dimensions_mm=(50.0, 50.0, 50.0),
            build_volume_mm=(256.0, 256.0, 256.0),
            exceeds_by_mm=(0.0, 0.0, 0.0),
            recommended_cuts=0,
        )
        assert not result.needs_segmentation
        assert result.recommended_cuts == 0

    def test_check_result_exceeds(self) -> None:
        """Test check result when model exceeds build volume."""
        result = CheckSegmentationResponse(
            needs_segmentation=True,
            model_dimensions_mm=(400.0, 300.0, 200.0),
            build_volume_mm=(256.0, 256.0, 256.0),
            exceeds_by_mm=(144.0, 44.0, 0.0),
            recommended_cuts=3,
        )
        assert result.needs_segmentation
        assert result.exceeds_by_mm[0] == 144.0  # X exceeds
        assert result.exceeds_by_mm[1] == 44.0  # Y exceeds
        assert result.exceeds_by_mm[2] == 0.0  # Z fits
        assert result.recommended_cuts == 3
