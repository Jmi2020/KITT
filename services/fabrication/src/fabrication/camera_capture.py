"""Camera Capture Service - Phase 4.

Captures snapshots from multiple camera sources:
- Bamboo Labs H2D built-in camera (via MQTT)
- Raspberry Pi cameras on Snapmaker/Elegoo (via HTTP)

Optionally uploads snapshots to MinIO for persistent storage.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from common.config import settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


class SnapshotResult:
    """Snapshot capture result."""

    def __init__(
        self,
        success: bool,
        url: Optional[str] = None,
        local_path: Optional[str] = None,
        camera_id: str = "",
        error: Optional[str] = None,
    ):
        """Initialize snapshot result.

        Args:
            success: Whether capture succeeded
            url: URL to snapshot (MinIO or mock)
            local_path: Local filesystem path
            camera_id: Camera identifier
            error: Error message if failed
        """
        self.success = success
        self.url = url
        self.local_path = local_path
        self.camera_id = camera_id
        self.error = error


class CameraCapture:
    """Handles camera snapshot capture and upload.

    Phase 4: Human-in-Loop implementation with Bamboo Labs and Raspberry Pi support.
    """

    def __init__(
        self,
        mqtt_client=None,
        minio_client=None,
        snapshot_dir: Optional[Path] = None,
    ):
        """Initialize camera capture service.

        Args:
            mqtt_client: Optional MQTT client for Bamboo Labs camera
            minio_client: Optional MinIO client for snapshot uploads
            snapshot_dir: Local directory for snapshot storage (default: /tmp/kitty/snapshots)
        """
        self.mqtt_client = mqtt_client
        self.minio_client = minio_client
        self.snapshot_dir = snapshot_dir or Path("/tmp/kitty/snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # HTTP client for Raspberry Pi cameras
        self.http_client = httpx.AsyncClient(timeout=10.0)

        LOGGER.info(
            "CameraCapture initialized",
            enable_camera=settings.enable_camera_capture,
            enable_bamboo=settings.enable_bamboo_camera,
            enable_pi=settings.enable_raspberry_pi_cameras,
            enable_minio=settings.enable_minio_snapshot_upload,
        )

    async def capture_snapshot(
        self,
        printer_id: str,
        camera_id: Optional[str] = None,
    ) -> SnapshotResult:
        """Capture snapshot from printer camera.

        Args:
            printer_id: Printer identifier (bamboo_h2d, snapmaker_artisan, elegoo_giga)
            camera_id: Optional specific camera ID (defaults to printer's default camera)

        Returns:
            SnapshotResult with URL and metadata
        """
        # Check feature flag
        if not settings.enable_camera_capture:
            LOGGER.debug("Camera capture disabled by feature flag")
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id="mock",
            )

        # Determine camera source
        if printer_id == "bamboo_h2d":
            return await self._capture_bamboo_snapshot()
        elif printer_id == "snapmaker_artisan":
            return await self._capture_pi_snapshot("snapmaker")
        elif printer_id == "elegoo_giga":
            return await self._capture_pi_snapshot("elegoo")
        else:
            LOGGER.warning(f"Unknown printer ID: {printer_id}, using mock snapshot")
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id="mock",
            )

    async def _capture_bamboo_snapshot(self) -> SnapshotResult:
        """Capture snapshot from Bamboo Labs H2D built-in camera via MQTT.

        Returns:
            SnapshotResult with snapshot URL
        """
        # Check feature flag
        if not settings.enable_bamboo_camera:
            LOGGER.debug("Bamboo camera disabled by feature flag")
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id="bamboo_mock",
            )

        # Check MQTT client
        if not self.mqtt_client:
            LOGGER.warning("MQTT client not available, using mock snapshot")
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id="bamboo_mock",
            )

        try:
            # Request snapshot via MQTT
            # Topic: device/{serial}/request
            # Payload: {"pushing": {"command": "pushall", "sequence_id": "0"}}
            serial = getattr(settings, "BAMBOO_SERIAL", None)
            if not serial:
                raise ValueError("BAMBOO_SERIAL not configured")

            request_topic = f"device/{serial}/request"
            request_payload = {
                "pushing": {
                    "command": "pushall",
                    "sequence_id": str(uuid.uuid4()),
                }
            }

            # Publish request
            self.mqtt_client.publish(request_topic, json.dumps(request_payload))

            # Wait for response (timeout 5s)
            # Response topic: device/{serial}/report
            # Contains camera image in base64
            response_topic = f"device/{serial}/report"

            # TODO: Implement MQTT subscriber pattern to receive snapshot
            # For now, use mock URL until MQTT subscriber is implemented
            LOGGER.info("Requested Bamboo snapshot via MQTT", topic=request_topic)

            # Mock response for Phase 4.1
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id="bamboo_h2d_camera",
            )

        except Exception as e:
            LOGGER.error("Failed to capture Bamboo snapshot", error=str(e), exc_info=True)
            return SnapshotResult(
                success=False,
                error=f"Bamboo camera error: {e}",
                camera_id="bamboo_h2d_camera",
            )

    async def _capture_pi_snapshot(self, pi_name: str) -> SnapshotResult:
        """Capture snapshot from Raspberry Pi camera via HTTP.

        Args:
            pi_name: Pi identifier (snapmaker or elegoo)

        Returns:
            SnapshotResult with snapshot URL
        """
        # Check feature flag
        if not settings.enable_raspberry_pi_cameras:
            LOGGER.debug("Raspberry Pi cameras disabled by feature flag")
            return SnapshotResult(
                success=True,
                url=self._mock_snapshot_url(),
                camera_id=f"{pi_name}_pi_mock",
            )

        try:
            # Get camera URL from settings
            if pi_name == "snapmaker":
                camera_url = settings.snapmaker_camera_url
            elif pi_name == "elegoo":
                camera_url = settings.elegoo_camera_url
            else:
                raise ValueError(f"Unknown Pi name: {pi_name}")

            if not camera_url:
                raise ValueError(f"Camera URL not configured for {pi_name}")

            # Fetch snapshot
            LOGGER.info(f"Fetching {pi_name} Pi snapshot", url=camera_url)
            response = await self.http_client.get(camera_url)
            response.raise_for_status()

            # Save to local file
            snapshot_id = f"{pi_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.jpg"
            local_path = self.snapshot_dir / snapshot_id

            with open(local_path, "wb") as f:
                f.write(response.content)

            LOGGER.info(f"Saved {pi_name} snapshot", path=str(local_path), size=len(response.content))

            # Upload to MinIO if enabled
            if settings.enable_minio_snapshot_upload and self.minio_client:
                minio_url = await self._upload_to_minio(local_path, snapshot_id)
                return SnapshotResult(
                    success=True,
                    url=minio_url,
                    local_path=str(local_path),
                    camera_id=f"{pi_name}_pi_camera",
                )
            else:
                # Use local file URL
                file_url = f"file://{local_path}"
                return SnapshotResult(
                    success=True,
                    url=file_url,
                    local_path=str(local_path),
                    camera_id=f"{pi_name}_pi_camera",
                )

        except Exception as e:
            LOGGER.error(f"Failed to capture {pi_name} Pi snapshot", error=str(e), exc_info=True)
            return SnapshotResult(
                success=False,
                error=f"{pi_name} Pi camera error: {e}",
                camera_id=f"{pi_name}_pi_camera",
            )

    async def _upload_to_minio(self, file_path: Path, object_name: str) -> str:
        """Upload snapshot to MinIO.

        Args:
            file_path: Local file path
            object_name: Object name in MinIO

        Returns:
            MinIO URL

        Raises:
            Exception: If upload fails
        """
        if not self.minio_client:
            raise ValueError("MinIO client not available")

        try:
            bucket_name = "kitty-snapshots"

            # Ensure bucket exists
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)
                LOGGER.info(f"Created MinIO bucket: {bucket_name}")

            # Upload file
            self.minio_client.fput_object(
                bucket_name,
                object_name,
                str(file_path),
                content_type="image/jpeg",
            )

            # Generate URL
            minio_url = f"http://{settings.MINIO_ENDPOINT}/{bucket_name}/{object_name}"

            LOGGER.info("Uploaded snapshot to MinIO", url=minio_url, size=file_path.stat().st_size)

            return minio_url

        except Exception as e:
            LOGGER.error("Failed to upload to MinIO", error=str(e), exc_info=True)
            raise

    def _mock_snapshot_url(self) -> str:
        """Generate mock snapshot URL for development.

        Returns:
            Mock URL with timestamp
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"mock://snapshot_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"

    async def cleanup(self):
        """Cleanup resources."""
        await self.http_client.aclose()
        LOGGER.info("CameraCapture cleaned up")
