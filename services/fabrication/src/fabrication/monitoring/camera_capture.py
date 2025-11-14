"""Camera capture service for print monitoring.

Captures snapshots from multiple camera sources (Bamboo Labs MQTT, Raspberry Pi HTTP)
and stores them in MinIO for visual print outcome tracking.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import aiohttp
from common.logging import get_logger

LOGGER = get_logger(__name__)


@dataclass
class SnapshotResult:
    """Result of snapshot capture operation."""

    success: bool
    url: Optional[str] = None  # MinIO URL if successful
    error: Optional[str] = None  # Error message if failed
    milestone: Optional[str] = None  # start, first_layer, progress, complete
    timestamp: Optional[datetime] = None


class CameraCapture:
    """Capture snapshots from printer cameras.

    Supports multiple camera types:
    - Bamboo Labs H2D: Built-in camera via MQTT
    - Raspberry Pi cameras: HTTP endpoint for Snapmaker and Elegoo
    """

    def __init__(
        self,
        minio_client=None,  # MinIO client (optional for testing)
        mqtt_client=None,  # MQTT client for Bamboo Labs (optional for testing)
        bucket_name: str = "prints",
    ):
        """Initialize camera capture service.

        Args:
            minio_client: MinIO client instance (optional)
            mqtt_client: MQTT client for Bamboo Labs (optional)
            bucket_name: MinIO bucket name for storing snapshots
        """
        self.minio_client = minio_client
        self.mqtt_client = mqtt_client
        self.bucket_name = bucket_name
        self._periodic_tasks: Dict[str, asyncio.Task] = {}  # job_id -> task

    # ========================================================================
    # Snapshot Capture
    # ========================================================================

    async def capture_snapshot(
        self,
        printer_id: str,
        job_id: str,
        milestone: str,  # "start", "first_layer", "progress", "complete"
    ) -> SnapshotResult:
        """Capture snapshot from printer camera and upload to MinIO.

        Args:
            printer_id: Printer identifier (e.g., "bamboo_h2d", "snapmaker_artisan")
            job_id: Print job identifier
            milestone: Snapshot milestone type

        Returns:
            SnapshotResult with MinIO URL or error
        """
        timestamp = datetime.utcnow()

        LOGGER.info(
            "Capturing snapshot",
            printer_id=printer_id,
            job_id=job_id,
            milestone=milestone,
            timestamp=timestamp.isoformat(),
        )

        try:
            # Determine camera type and capture
            if printer_id == "bamboo_h2d":
                snapshot_data = await self._capture_bamboo_snapshot(printer_id)
            elif printer_id in ["snapmaker_artisan", "elegoo_giga"]:
                snapshot_data = await self._capture_pi_snapshot(printer_id)
            else:
                return SnapshotResult(
                    success=False,
                    error=f"Unsupported printer type: {printer_id}",
                    milestone=milestone,
                    timestamp=timestamp,
                )

            if not snapshot_data:
                return SnapshotResult(
                    success=False,
                    error="Failed to capture snapshot from camera",
                    milestone=milestone,
                    timestamp=timestamp,
                )

            # Upload to MinIO
            minio_url = await self._upload_to_minio(job_id, milestone, timestamp, snapshot_data)

            LOGGER.info(
                "Snapshot captured successfully",
                printer_id=printer_id,
                job_id=job_id,
                milestone=milestone,
                minio_url=minio_url,
            )

            return SnapshotResult(
                success=True, url=minio_url, milestone=milestone, timestamp=timestamp
            )

        except Exception as e:
            LOGGER.error(
                "Snapshot capture failed",
                printer_id=printer_id,
                job_id=job_id,
                milestone=milestone,
                error=str(e),
                exc_info=True,
            )
            return SnapshotResult(
                success=False, error=str(e), milestone=milestone, timestamp=timestamp
            )

    async def _capture_bamboo_snapshot(self, printer_id: str) -> Optional[bytes]:
        """Capture snapshot from Bamboo Labs camera via MQTT.

        Args:
            printer_id: Printer identifier

        Returns:
            JPEG image data or None if failed
        """
        if not self.mqtt_client:
            LOGGER.warning("MQTT client not configured, cannot capture Bamboo Labs snapshot")
            return None

        try:
            # Bamboo Labs MQTT snapshot request
            # Topic: device/{serial}/request
            # Command: {"command": "pushall", "push_target": 1}  # 1 = snapshot
            #
            # Response on: device/{serial}/report
            # Field: ipcam.img (base64 encoded JPEG)
            #
            # TODO: Implement MQTT request/response pattern
            # For now, return None to indicate not yet implemented

            LOGGER.info("Bamboo Labs MQTT snapshot capture not yet implemented", printer_id=printer_id)
            return None

        except Exception as e:
            LOGGER.error("Bamboo Labs snapshot capture failed", printer_id=printer_id, error=str(e))
            return None

    async def _capture_pi_snapshot(self, printer_id: str) -> Optional[bytes]:
        """Capture snapshot from Raspberry Pi camera via HTTP.

        Args:
            printer_id: Printer identifier

        Returns:
            JPEG image data or None if failed
        """
        # Map printer ID to Raspberry Pi camera endpoint
        # TODO: Get these from configuration or device registry
        camera_endpoints = {
            "snapmaker_artisan": "http://snapmaker-pi.local:8080/snapshot.jpg",
            "elegoo_giga": "http://elegoo-pi.local:8080/snapshot.jpg",
        }

        endpoint = camera_endpoints.get(printer_id)
        if not endpoint:
            LOGGER.warning("No camera endpoint configured", printer_id=printer_id)
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        snapshot_data = await response.read()
                        LOGGER.debug(
                            "Captured snapshot from Raspberry Pi",
                            printer_id=printer_id,
                            size_bytes=len(snapshot_data),
                        )
                        return snapshot_data
                    else:
                        LOGGER.error(
                            "Failed to capture snapshot from Raspberry Pi",
                            printer_id=printer_id,
                            status=response.status,
                        )
                        return None

        except asyncio.TimeoutError:
            LOGGER.error("Raspberry Pi snapshot capture timed out", printer_id=printer_id)
            return None
        except Exception as e:
            LOGGER.error(
                "Raspberry Pi snapshot capture failed", printer_id=printer_id, error=str(e)
            )
            return None

    async def _upload_to_minio(
        self, job_id: str, milestone: str, timestamp: datetime, data: bytes
    ) -> str:
        """Upload snapshot to MinIO.

        Args:
            job_id: Print job identifier
            milestone: Snapshot milestone type
            timestamp: Capture timestamp
            data: JPEG image data

        Returns:
            MinIO URL (e.g., "minio://prints/job123/start_20250314_120000.jpg")
        """
        if not self.minio_client:
            # Return mock URL for testing
            object_name = f"{job_id}/{milestone}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            return f"minio://{self.bucket_name}/{object_name}"

        try:
            # Generate object name: prints/{job_id}/{milestone}_{timestamp}.jpg
            object_name = f"{job_id}/{milestone}_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"

            # Upload to MinIO
            self.minio_client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type="image/jpeg",
            )

            minio_url = f"minio://{self.bucket_name}/{object_name}"

            LOGGER.debug(
                "Uploaded snapshot to MinIO",
                object_name=object_name,
                size_bytes=len(data),
                url=minio_url,
            )

            return minio_url

        except Exception as e:
            LOGGER.error(
                "Failed to upload snapshot to MinIO",
                job_id=job_id,
                milestone=milestone,
                error=str(e),
            )
            raise

    # ========================================================================
    # Periodic Snapshot Capture
    # ========================================================================

    async def start_periodic_capture(
        self,
        printer_id: str,
        job_id: str,
        interval_minutes: int = 5,
    ) -> None:
        """Start background task for periodic snapshot capture.

        Args:
            printer_id: Printer identifier
            job_id: Print job identifier
            interval_minutes: Interval between snapshots (default: 5 minutes)
        """
        if job_id in self._periodic_tasks:
            LOGGER.warning("Periodic capture already running", job_id=job_id)
            return

        LOGGER.info(
            "Starting periodic snapshot capture",
            printer_id=printer_id,
            job_id=job_id,
            interval_minutes=interval_minutes,
        )

        # Create background task
        task = asyncio.create_task(
            self._periodic_capture_loop(printer_id, job_id, interval_minutes)
        )
        self._periodic_tasks[job_id] = task

    async def stop_periodic_capture(self, job_id: str) -> None:
        """Stop background task for periodic snapshot capture.

        Args:
            job_id: Print job identifier
        """
        task = self._periodic_tasks.pop(job_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            LOGGER.info("Stopped periodic snapshot capture", job_id=job_id)
        else:
            LOGGER.warning("No periodic capture task found", job_id=job_id)

    async def _periodic_capture_loop(
        self, printer_id: str, job_id: str, interval_minutes: int
    ) -> None:
        """Background loop for periodic snapshot capture.

        Args:
            printer_id: Printer identifier
            job_id: Print job identifier
            interval_minutes: Interval between snapshots
        """
        interval_seconds = interval_minutes * 60

        try:
            while True:
                await asyncio.sleep(interval_seconds)

                # Capture progress snapshot
                result = await self.capture_snapshot(printer_id, job_id, "progress")

                if not result.success:
                    LOGGER.warning(
                        "Periodic snapshot capture failed",
                        job_id=job_id,
                        error=result.error,
                    )

        except asyncio.CancelledError:
            LOGGER.debug("Periodic capture loop cancelled", job_id=job_id)
            raise
        except Exception as e:
            LOGGER.error(
                "Periodic capture loop failed",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
