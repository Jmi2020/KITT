"""Print Executor - Orchestrates automated print execution workflow.

Manages the complete print lifecycle:
1. Job assignment from scheduler
2. Driver initialization and connection
3. G-code upload
4. Print start
5. Progress monitoring
6. Snapshot capture
7. Completion detection
8. Outcome recording
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from common.db.models import QueuedPrint, QueueStatus, JobStatusHistory
from common.logging import get_logger

from ..drivers import PrinterDriver, MoonrakerDriver, BambuMqttDriver, PrinterState
from ..cv.camera_capture import CameraCapture

LOGGER = get_logger(__name__)


@dataclass
class PrintExecutionResult:
    """Result of print execution attempt."""

    success: bool
    job_id: str
    printer_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class PrintExecutor:
    """Orchestrates automated print execution workflow.

    Responsibilities:
    - Connect to printer via driver
    - Upload G-code
    - Start print
    - Monitor progress
    - Capture snapshots
    - Handle errors and retries
    - Record outcomes
    """

    def __init__(
        self,
        db: Session,
        camera_capture: Optional[CameraCapture] = None,
        status_poll_interval: int = 30,
        snapshot_interval: int = 300,
        max_retries: int = 2,
        retry_delay: int = 300,
    ):
        """Initialize print executor.

        Args:
            db: Database session
            camera_capture: Camera capture service for snapshots
            status_poll_interval: Seconds between status checks (default: 30)
            snapshot_interval: Seconds between snapshots (default: 300 = 5 min)
            max_retries: Maximum print retries on failure (default: 2)
            retry_delay: Seconds to wait before retry (default: 300 = 5 min)
        """
        self.db = db
        self.camera_capture = camera_capture
        self.status_poll_interval = status_poll_interval
        self.snapshot_interval = snapshot_interval
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Active drivers (printer_id -> driver instance)
        self._drivers: dict[str, PrinterDriver] = {}

    async def execute_job(
        self,
        job: QueuedPrint,
        printer_id: str,
        printer_config: dict,
    ) -> PrintExecutionResult:
        """Execute a print job on the specified printer.

        Args:
            job: Queued print job to execute
            printer_id: Target printer identifier
            printer_config: Printer driver configuration

        Returns:
            Print execution result with success status
        """
        LOGGER.info(
            "Starting print execution",
            job_id=job.job_id,
            job_name=job.job_name,
            printer_id=printer_id,
        )

        started_at = datetime.utcnow()

        try:
            # Initialize printer driver
            driver = await self._get_or_create_driver(printer_id, printer_config)

            # Update job status: scheduled → uploading
            await self._update_job_status(
                job,
                QueueStatus.uploading,
                "Uploading G-code to printer",
            )

            # Upload G-code to printer
            remote_filename = await self._upload_gcode(driver, job)

            # Update job status: uploading → printing
            await self._update_job_status(
                job,
                QueueStatus.printing,
                f"Starting print: {remote_filename}",
            )

            # Start print
            success = await driver.start_print(remote_filename)
            if not success:
                raise RuntimeError("Failed to start print on printer")

            # Capture first layer snapshot
            if self.camera_capture:
                await self._capture_snapshot(job, printer_id, "first_layer")

            # Monitor print progress
            await self._monitor_print_progress(driver, job, printer_id)

            # Print completed successfully
            completed_at = datetime.utcnow()

            # Capture final snapshot
            if self.camera_capture:
                await self._capture_snapshot(job, printer_id, "complete")

            # Update job status: printing → completed
            await self._update_job_status(
                job,
                QueueStatus.completed,
                "Print completed successfully",
            )

            LOGGER.info(
                "Print execution completed",
                job_id=job.job_id,
                printer_id=printer_id,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )

            return PrintExecutionResult(
                success=True,
                job_id=job.job_id,
                printer_id=printer_id,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as e:
            LOGGER.error(
                "Print execution failed",
                job_id=job.job_id,
                printer_id=printer_id,
                error=str(e),
                exc_info=True,
            )

            # Update job status: * → failed
            await self._update_job_status(
                job,
                QueueStatus.failed,
                f"Print failed: {str(e)}",
            )

            # Check if retry allowed
            if job.retry_count < job.max_retries:
                LOGGER.info(
                    "Scheduling print retry",
                    job_id=job.job_id,
                    retry_count=job.retry_count + 1,
                    max_retries=job.max_retries,
                )

                # Increment retry count
                job.retry_count += 1

                # Reset status to queued for retry
                await self._update_job_status(
                    job,
                    QueueStatus.queued,
                    f"Retry {job.retry_count}/{job.max_retries} after {self.retry_delay}s",
                )

                # Wait before retry
                await asyncio.sleep(self.retry_delay)

            return PrintExecutionResult(
                success=False,
                job_id=job.job_id,
                printer_id=printer_id,
                started_at=started_at,
                error_message=str(e),
                retry_count=job.retry_count,
            )

    async def _get_or_create_driver(
        self,
        printer_id: str,
        printer_config: dict,
    ) -> PrinterDriver:
        """Get existing driver or create new one.

        Args:
            printer_id: Printer identifier
            printer_config: Driver configuration

        Returns:
            Connected printer driver

        Raises:
            ConnectionError: If driver fails to connect
        """
        # Check if driver already exists and is connected
        if printer_id in self._drivers:
            driver = self._drivers[printer_id]
            if await driver.is_connected():
                return driver

        # Create new driver based on type
        driver_type = printer_config["driver"]

        if driver_type == "moonraker":
            driver = MoonrakerDriver(printer_id, printer_config["config"])
        elif driver_type == "bamboo_mqtt":
            driver = BambuMqttDriver(printer_id, printer_config["config"])
        else:
            raise ValueError(f"Unknown driver type: {driver_type}")

        # Connect to printer
        connected = await driver.connect()
        if not connected:
            raise ConnectionError(f"Failed to connect to printer: {printer_id}")

        # Cache driver
        self._drivers[printer_id] = driver

        LOGGER.info(
            "Printer driver initialized",
            printer_id=printer_id,
            driver_type=driver_type,
        )

        return driver

    async def _upload_gcode(
        self,
        driver: PrinterDriver,
        job: QueuedPrint,
    ) -> str:
        """Upload G-code file to printer.

        Args:
            driver: Printer driver
            job: Print job with gcode_path

        Returns:
            Remote filename on printer

        Raises:
            FileNotFoundError: If gcode_path doesn't exist
            ConnectionError: If upload fails
        """
        gcode_path = job.gcode_path
        if not gcode_path:
            raise ValueError(f"Job {job.job_id} has no G-code path")

        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            raise FileNotFoundError(f"G-code file not found: {gcode_path}")

        LOGGER.info(
            "Uploading G-code",
            job_id=job.job_id,
            gcode_path=gcode_path,
            size_bytes=gcode_file.stat().st_size,
        )

        # Use job_name as filename
        filename = f"{job.job_name}.gcode"

        remote_filename = await driver.upload_gcode(str(gcode_path), filename)

        LOGGER.info(
            "G-code uploaded",
            job_id=job.job_id,
            remote_filename=remote_filename,
        )

        return remote_filename

    async def _monitor_print_progress(
        self,
        driver: PrinterDriver,
        job: QueuedPrint,
        printer_id: str,
    ) -> None:
        """Monitor print progress until completion or failure.

        Args:
            driver: Printer driver
            job: Print job being executed
            printer_id: Printer identifier

        Raises:
            RuntimeError: If print fails or printer goes offline
        """
        LOGGER.info(
            "Starting print monitoring",
            job_id=job.job_id,
            printer_id=printer_id,
            poll_interval=self.status_poll_interval,
        )

        last_snapshot_time = datetime.utcnow()
        snapshot_count = 0

        while True:
            # Poll printer status
            status = await driver.get_status()

            LOGGER.debug(
                "Print status",
                job_id=job.job_id,
                state=status.state.value,
                progress=status.progress_percent,
                layer=f"{status.current_layer}/{status.total_layers}" if status.current_layer else None,
            )

            # Check for completion
            if status.state == PrinterState.complete:
                LOGGER.info(
                    "Print completed",
                    job_id=job.job_id,
                    printer_id=printer_id,
                )
                break

            # Check for errors
            if status.state == PrinterState.error:
                error_msg = status.error_message or "Unknown printer error"
                LOGGER.error(
                    "Printer error during print",
                    job_id=job.job_id,
                    printer_id=printer_id,
                    error=error_msg,
                )
                raise RuntimeError(f"Printer error: {error_msg}")

            # Check if printer went offline
            if not status.is_online or status.state == PrinterState.offline:
                LOGGER.error(
                    "Printer went offline",
                    job_id=job.job_id,
                    printer_id=printer_id,
                )
                raise RuntimeError("Printer offline during print")

            # Capture periodic snapshots
            if self.camera_capture:
                time_since_snapshot = (datetime.utcnow() - last_snapshot_time).total_seconds()
                if time_since_snapshot >= self.snapshot_interval:
                    snapshot_count += 1
                    await self._capture_snapshot(
                        job,
                        printer_id,
                        f"progress_{snapshot_count}",
                    )
                    last_snapshot_time = datetime.utcnow()

            # Wait before next poll
            await asyncio.sleep(self.status_poll_interval)

    async def _capture_snapshot(
        self,
        job: QueuedPrint,
        printer_id: str,
        milestone: str,
    ) -> None:
        """Capture camera snapshot at milestone.

        Args:
            job: Print job
            printer_id: Printer identifier
            milestone: Snapshot milestone (first_layer, progress_1, complete, etc.)
        """
        if not self.camera_capture:
            return

        try:
            LOGGER.info(
                "Capturing snapshot",
                job_id=job.job_id,
                printer_id=printer_id,
                milestone=milestone,
            )

            snapshot_url = await self.camera_capture.capture_snapshot(
                printer_id=printer_id,
                job_id=job.job_id,
                milestone=milestone,
            )

            LOGGER.info(
                "Snapshot captured",
                job_id=job.job_id,
                snapshot_url=snapshot_url,
            )

        except Exception as e:
            LOGGER.error(
                "Failed to capture snapshot",
                job_id=job.job_id,
                printer_id=printer_id,
                milestone=milestone,
                error=str(e),
            )

    async def _update_job_status(
        self,
        job: QueuedPrint,
        status: QueueStatus,
        reason: str,
    ) -> None:
        """Update job status and record in history.

        Args:
            job: Print job
            status: New status
            reason: Status change reason
        """
        old_status = job.status

        # Update job status
        job.status = status
        job.status_reason = reason
        job.updated_at = datetime.utcnow()

        # Record in status history
        history_entry = JobStatusHistory(
            job_id=job.job_id,
            from_status=old_status,
            to_status=status,
            reason=reason,
            changed_at=datetime.utcnow(),
        )
        self.db.add(history_entry)
        self.db.commit()

        LOGGER.info(
            "Job status updated",
            job_id=job.job_id,
            old_status=old_status.value,
            new_status=status.value,
            reason=reason,
        )

    async def pause_job(
        self,
        job_id: str,
        printer_id: str,
    ) -> bool:
        """Pause a running print job.

        Args:
            job_id: Job identifier
            printer_id: Printer identifier

        Returns:
            True if paused successfully
        """
        driver = self._drivers.get(printer_id)
        if not driver:
            LOGGER.error("No active driver for printer", printer_id=printer_id)
            return False

        try:
            success = await driver.pause_print()

            if success:
                LOGGER.info("Print paused", job_id=job_id, printer_id=printer_id)

            return success

        except Exception as e:
            LOGGER.error(
                "Failed to pause print",
                job_id=job_id,
                printer_id=printer_id,
                error=str(e),
            )
            return False

    async def resume_job(
        self,
        job_id: str,
        printer_id: str,
    ) -> bool:
        """Resume a paused print job.

        Args:
            job_id: Job identifier
            printer_id: Printer identifier

        Returns:
            True if resumed successfully
        """
        driver = self._drivers.get(printer_id)
        if not driver:
            LOGGER.error("No active driver for printer", printer_id=printer_id)
            return False

        try:
            success = await driver.resume_print()

            if success:
                LOGGER.info("Print resumed", job_id=job_id, printer_id=printer_id)

            return success

        except Exception as e:
            LOGGER.error(
                "Failed to resume print",
                job_id=job_id,
                printer_id=printer_id,
                error=str(e),
            )
            return False

    async def cancel_job(
        self,
        job_id: str,
        printer_id: str,
    ) -> bool:
        """Cancel a running print job.

        Args:
            job_id: Job identifier
            printer_id: Printer identifier

        Returns:
            True if cancelled successfully
        """
        driver = self._drivers.get(printer_id)
        if not driver:
            LOGGER.error("No active driver for printer", printer_id=printer_id)
            return False

        try:
            success = await driver.cancel_print()

            if success:
                LOGGER.info("Print cancelled", job_id=job_id, printer_id=printer_id)

            return success

        except Exception as e:
            LOGGER.error(
                "Failed to cancel print",
                job_id=job_id,
                printer_id=printer_id,
                error=str(e),
            )
            return False

    async def cleanup(self) -> None:
        """Disconnect all active drivers."""
        for printer_id, driver in self._drivers.items():
            try:
                await driver.disconnect()
                LOGGER.info("Disconnected driver", printer_id=printer_id)
            except Exception as e:
                LOGGER.error(
                    "Error disconnecting driver",
                    printer_id=printer_id,
                    error=str(e),
                )

        self._drivers.clear()
