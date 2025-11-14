"""Unit tests for CameraCapture service.

Tests snapshot capture from multiple camera sources, MinIO upload,
and periodic capture scheduling.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError

from fabrication.monitoring.camera_capture import CameraCapture, SnapshotResult


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_minio():
    """Mock MinIO client."""
    minio = MagicMock()
    minio.put_object = MagicMock()
    return minio


@pytest.fixture
def mock_mqtt():
    """Mock MQTT client."""
    mqtt = MagicMock()
    mqtt.publish = MagicMock()
    return mqtt


@pytest.fixture
def camera_capture(mock_minio, mock_mqtt):
    """CameraCapture instance with mocked dependencies."""
    # Enable feature flags for testing
    with patch("fabrication.monitoring.camera_capture.settings") as mock_settings:
        mock_settings.enable_camera_capture = True
        mock_settings.enable_minio_snapshot_upload = True
        mock_settings.enable_raspberry_pi_cameras = True
        mock_settings.snapmaker_camera_url = "http://snapmaker-pi.local:8080/snapshot.jpg"
        mock_settings.elegoo_camera_url = "http://elegoo-pi.local:8080/snapshot.jpg"

        camera = CameraCapture(
            minio_client=mock_minio, mqtt_client=mock_mqtt, bucket_name="test-prints"
        )
        yield camera


@pytest.fixture
def camera_capture_no_clients():
    """CameraCapture instance without MinIO/MQTT clients (for testing mock URLs)."""
    return CameraCapture(minio_client=None, mqtt_client=None, bucket_name="test-prints")


# ============================================================================
# Snapshot Capture Tests
# ============================================================================


@pytest.mark.asyncio
async def test_capture_snapshot_raspberry_pi_success(camera_capture):
    """Test successful snapshot capture from Raspberry Pi camera."""
    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"fake_jpeg_data")

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        result = await camera_capture.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job123", milestone="start"
        )

    assert result.success
    assert result.url is not None
    assert result.milestone == "start"
    assert result.error is None
    assert "job123" in result.url
    assert "start" in result.url

    # Verify MinIO upload
    camera_capture.minio_client.put_object.assert_called_once()
    call_args = camera_capture.minio_client.put_object.call_args
    assert call_args.kwargs["bucket_name"] == "test-prints"
    assert "job123" in call_args.kwargs["object_name"]
    assert call_args.kwargs["content_type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_capture_snapshot_raspberry_pi_http_error(camera_capture):
    """Test snapshot capture failure with HTTP error."""
    # Mock HTTP error response
    mock_response = AsyncMock()
    mock_response.status = 500

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        result = await camera_capture.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job123", milestone="start"
        )

    assert not result.success
    assert result.url is None
    assert result.error == "Failed to capture snapshot from camera"


@pytest.mark.asyncio
async def test_capture_snapshot_raspberry_pi_timeout(camera_capture):
    """Test snapshot capture with timeout."""
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.side_effect = asyncio.TimeoutError()

        result = await camera_capture.capture_snapshot(
            printer_id="elegoo_giga", job_id="job456", milestone="progress"
        )

    assert not result.success
    assert result.url is None
    assert "Failed to capture snapshot from camera" in result.error


@pytest.mark.asyncio
async def test_capture_snapshot_bamboo_labs_not_implemented(camera_capture):
    """Test Bamboo Labs snapshot capture (not yet implemented)."""
    result = await camera_capture.capture_snapshot(
        printer_id="bamboo_h2d", job_id="job789", milestone="first_layer"
    )

    # Should fail gracefully since MQTT capture not implemented yet
    assert not result.success
    assert result.error == "Failed to capture snapshot from camera"


@pytest.mark.asyncio
async def test_capture_snapshot_unsupported_printer(camera_capture):
    """Test snapshot capture with unsupported printer type."""
    result = await camera_capture.capture_snapshot(
        printer_id="unknown_printer", job_id="job999", milestone="complete"
    )

    assert not result.success
    assert "Unsupported printer type" in result.error


@pytest.mark.asyncio
async def test_capture_snapshot_no_minio_client(camera_capture_no_clients):
    """Test snapshot capture without MinIO client (mock URL)."""
    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"fake_jpeg_data")

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        result = await camera_capture_no_clients.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job123", milestone="start"
        )

    assert result.success
    assert result.url.startswith("minio://test-prints/")
    assert "job123" in result.url


# ============================================================================
# Periodic Capture Tests
# ============================================================================


@pytest.mark.asyncio
async def test_start_periodic_capture(camera_capture):
    """Test starting periodic snapshot capture."""
    await camera_capture.start_periodic_capture(
        printer_id="snapmaker_artisan", job_id="job123", interval_minutes=1
    )

    assert "job123" in camera_capture._periodic_tasks
    assert isinstance(camera_capture._periodic_tasks["job123"], asyncio.Task)

    # Clean up
    await camera_capture.stop_periodic_capture("job123")


@pytest.mark.asyncio
async def test_start_periodic_capture_already_running(camera_capture):
    """Test starting periodic capture when already running."""
    await camera_capture.start_periodic_capture(
        printer_id="snapmaker_artisan", job_id="job123", interval_minutes=1
    )

    # Try to start again
    await camera_capture.start_periodic_capture(
        printer_id="snapmaker_artisan", job_id="job123", interval_minutes=1
    )

    # Should still have only one task
    assert len(camera_capture._periodic_tasks) == 1

    # Clean up
    await camera_capture.stop_periodic_capture("job123")


@pytest.mark.asyncio
async def test_stop_periodic_capture(camera_capture):
    """Test stopping periodic snapshot capture."""
    await camera_capture.start_periodic_capture(
        printer_id="snapmaker_artisan", job_id="job123", interval_minutes=1
    )

    # Stop capture
    await camera_capture.stop_periodic_capture("job123")

    # Task should be removed
    assert "job123" not in camera_capture._periodic_tasks


@pytest.mark.asyncio
async def test_stop_periodic_capture_not_running(camera_capture):
    """Test stopping periodic capture when not running."""
    # Should not raise error
    await camera_capture.stop_periodic_capture("nonexistent_job")


@pytest.mark.asyncio
async def test_periodic_capture_loop_executes(camera_capture):
    """Test that periodic capture loop actually captures snapshots."""
    captured_snapshots = []

    # Mock capture_snapshot to track calls
    original_capture = camera_capture.capture_snapshot

    async def mock_capture(printer_id, job_id, milestone):
        captured_snapshots.append((printer_id, job_id, milestone))
        return SnapshotResult(
            success=True,
            url=f"minio://test-prints/{job_id}/{milestone}.jpg",
            milestone=milestone,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        )

    camera_capture.capture_snapshot = mock_capture

    # Start periodic capture with short interval
    await camera_capture.start_periodic_capture(
        printer_id="snapmaker_artisan", job_id="job123", interval_minutes=0.01  # ~600ms
    )

    # Wait for a few captures
    await asyncio.sleep(2)

    # Stop capture
    await camera_capture.stop_periodic_capture("job123")

    # Verify at least one snapshot was captured
    assert len(captured_snapshots) >= 1
    assert captured_snapshots[0] == ("snapmaker_artisan", "job123", "progress")

    # Restore original method
    camera_capture.capture_snapshot = original_capture


# ============================================================================
# MinIO Upload Tests
# ============================================================================


@pytest.mark.asyncio
async def test_upload_to_minio_success(camera_capture):
    """Test successful MinIO upload."""
    timestamp = datetime(2025, 11, 14, 12, 0, 0)
    data = b"fake_jpeg_data"

    url = await camera_capture._upload_to_minio("job123", "start", timestamp, data)

    assert url == "minio://test-prints/job123/start_20251114_120000.jpg"

    # Verify MinIO call
    camera_capture.minio_client.put_object.assert_called_once()
    call_args = camera_capture.minio_client.put_object.call_args
    assert call_args.kwargs["bucket_name"] == "test-prints"
    assert call_args.kwargs["object_name"] == "job123/start_20251114_120000.jpg"
    assert call_args.kwargs["length"] == len(data)


@pytest.mark.asyncio
async def test_upload_to_minio_failure(camera_capture):
    """Test MinIO upload failure."""
    camera_capture.minio_client.put_object.side_effect = Exception("MinIO error")

    timestamp = datetime(2025, 11, 14, 12, 0, 0)
    data = b"fake_jpeg_data"

    with pytest.raises(Exception, match="MinIO error"):
        await camera_capture._upload_to_minio("job123", "start", timestamp, data)


@pytest.mark.asyncio
async def test_upload_to_minio_no_client(camera_capture_no_clients):
    """Test MinIO upload without client (returns mock URL)."""
    timestamp = datetime(2025, 11, 14, 12, 0, 0)
    data = b"fake_jpeg_data"

    url = await camera_capture_no_clients._upload_to_minio("job123", "start", timestamp, data)

    assert url.startswith("minio://test-prints/job123/start_")
    assert ".jpg" in url


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_full_snapshot_workflow(camera_capture):
    """Test complete snapshot capture and upload workflow."""
    # Mock HTTP response
    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"fake_jpeg_data_123")

    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_get.return_value.__aenter__.return_value = mock_response

        # Capture initial snapshot
        result1 = await camera_capture.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job_full", milestone="start"
        )

        # Capture progress snapshot
        result2 = await camera_capture.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job_full", milestone="progress"
        )

        # Capture final snapshot
        result3 = await camera_capture.capture_snapshot(
            printer_id="snapmaker_artisan", job_id="job_full", milestone="complete"
        )

    # Verify all snapshots captured successfully
    assert result1.success
    assert result2.success
    assert result3.success

    # Verify all have different URLs
    assert result1.url != result2.url != result3.url

    # Verify milestones
    assert result1.milestone == "start"
    assert result2.milestone == "progress"
    assert result3.milestone == "complete"

    # Verify MinIO uploads
    assert camera_capture.minio_client.put_object.call_count == 3
