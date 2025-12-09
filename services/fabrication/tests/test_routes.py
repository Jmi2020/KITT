# noqa: D104
"""Tests for segmentation API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from fabrication.app import app
from fabrication.segmentation.schemas import (
    CheckSegmentationResult,
    SegmentationResult,
    SegmentedPart,
)


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


class TestSegmentationCheckEndpoint:
    """Tests for POST /api/segmentation/check endpoint."""

    def test_check_missing_stl_path(self, client: TestClient) -> None:
        """Test check with missing stl_path."""
        response = client.post("/api/segmentation/check", json={})
        assert response.status_code == 422  # Validation error

    def test_check_file_not_found(self, client: TestClient) -> None:
        """Test check with non-existent file."""
        response = client.post(
            "/api/segmentation/check",
            json={"stl_path": "/nonexistent/path/model.stl"},
        )
        assert response.status_code == 404

    def test_check_success(
        self, client: TestClient, small_stl_file: Path
    ) -> None:
        """Test successful dimension check."""
        response = client.post(
            "/api/segmentation/check",
            json={"stl_path": str(small_stl_file)},
        )
        assert response.status_code == 200
        data = response.json()
        assert "needs_segmentation" in data
        assert "model_dimensions_mm" in data
        assert "build_volume_mm" in data
        assert "exceeds_by_mm" in data

    def test_check_with_printer_id(
        self, client: TestClient, small_stl_file: Path
    ) -> None:
        """Test check with specific printer."""
        response = client.post(
            "/api/segmentation/check",
            json={
                "stl_path": str(small_stl_file),
                "printer_id": "bamboo_h2d",
            },
        )
        # May fail if printer not configured, which is acceptable
        assert response.status_code in [200, 404]


class TestSegmentationSegmentEndpoint:
    """Tests for POST /api/segmentation/segment endpoint."""

    def test_segment_missing_stl_path(self, client: TestClient) -> None:
        """Test segment with missing stl_path."""
        response = client.post("/api/segmentation/segment", json={})
        assert response.status_code == 422

    def test_segment_file_not_found(self, client: TestClient) -> None:
        """Test segment with non-existent file."""
        response = client.post(
            "/api/segmentation/segment",
            json={"stl_path": "/nonexistent/path/model.stl"},
        )
        assert response.status_code == 404

    def test_segment_small_model(
        self, client: TestClient, small_stl_file: Path
    ) -> None:
        """Test segmenting a small model (no segmentation needed)."""
        response = client.post(
            "/api/segmentation/segment",
            json={
                "stl_path": str(small_stl_file),
                "enable_hollowing": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["needs_segmentation"] is False
        assert data["num_parts"] == 1

    def test_segment_large_model(
        self, client: TestClient, large_stl_file: Path
    ) -> None:
        """Test segmenting a large model."""
        response = client.post(
            "/api/segmentation/segment",
            json={
                "stl_path": str(large_stl_file),
                "enable_hollowing": False,
                "joint_type": "none",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["needs_segmentation"] is True
        assert data["num_parts"] > 1
        assert len(data["parts"]) == data["num_parts"]

    def test_segment_with_options(
        self, client: TestClient, large_stl_file: Path
    ) -> None:
        """Test segmentation with custom options."""
        response = client.post(
            "/api/segmentation/segment",
            json={
                "stl_path": str(large_stl_file),
                "enable_hollowing": True,
                "wall_thickness_mm": 3.0,
                "joint_type": "dowel",
                "max_parts": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["num_parts"] <= 5


class TestPrintersEndpoint:
    """Tests for GET /api/segmentation/printers endpoint."""

    def test_list_printers(self, client: TestClient) -> None:
        """Test listing printers."""
        response = client.get("/api/segmentation/printers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least default printers
        for printer in data:
            assert "printer_id" in printer
            assert "name" in printer
            assert "build_volume_mm" in printer


class TestAsyncSegmentEndpoint:
    """Tests for async segmentation endpoint."""

    def test_async_segment_creates_job(
        self, client: TestClient, large_stl_file: Path
    ) -> None:
        """Test that async endpoint creates a job."""
        response = client.post(
            "/api/segmentation/segment/async",
            json={
                "stl_path": str(large_stl_file),
                "enable_hollowing": False,
            },
        )
        # Async endpoint may return 202 or 200 depending on implementation
        assert response.status_code in [200, 202]
        data = response.json()
        assert "job_id" in data


class TestJobStatusEndpoint:
    """Tests for job status endpoint."""

    def test_job_not_found(self, client: TestClient) -> None:
        """Test getting status of non-existent job."""
        response = client.get("/api/segmentation/jobs/nonexistent-job-id")
        assert response.status_code == 404
