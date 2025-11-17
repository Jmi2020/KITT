"""Job Distributor - P3 #20 Multi-Printer Coordination.

Distributes print jobs to printer-specific RabbitMQ queues for execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from common.db.models import QueuedPrint
from common.logging import get_logger
from common.messaging.client import MessageQueueClient

LOGGER = get_logger(__name__)

# Exchange and queue constants
FABRICATION_EXCHANGE = "kitty.tasks"  # Use existing tasks exchange

# Printer-specific queue names
BAMBOO_QUEUE = "fabrication.bamboo_h2d"
ELEGOO_QUEUE = "fabrication.elegoo_giga"
SNAPMAKER_QUEUE = "fabrication.snapmaker_artisan"

# Dead letter queue for failed jobs
DLQ_QUEUE = "fabrication.dlq"


@dataclass
class JobDistributionResult:
    """Result of job distribution to RabbitMQ."""
    job_id: str
    printer_id: str
    queue_name: str
    success: bool
    error: Optional[str] = None
    distributed_at: datetime = None


class JobDistributor:
    """Distribute print jobs to printer-specific RabbitMQ queues.

    Architecture:
    - Uses kitty.tasks exchange (topic exchange)
    - Each printer has dedicated queue
    - Jobs published with printer-specific routing key
    - Failed jobs go to dead letter queue for manual inspection
    """

    # Map printer IDs to queue names
    PRINTER_QUEUES = {
        "bamboo_h2d": BAMBOO_QUEUE,
        "elegoo_giga": ELEGOO_QUEUE,
        "snapmaker_artisan": SNAPMAKER_QUEUE,
    }

    def __init__(
        self,
        mq_client: MessageQueueClient,
    ):
        """Initialize job distributor.

        Args:
            mq_client: RabbitMQ client (must be connected)
        """
        self.mq_client = mq_client
        self._setup_queues()

    def _setup_queues(self) -> None:
        """Setup printer queues and bindings (idempotent).

        Creates:
        - Printer-specific queues with DLX
        - Dead letter queue
        - Bindings to kitty.tasks exchange
        """
        try:
            # Declare dead letter queue
            self.mq_client.declare_queue(
                queue_name=DLQ_QUEUE,
                durable=True,
            )
            LOGGER.info("Declared dead letter queue", queue=DLQ_QUEUE)

            # Declare printer queues with DLX
            for printer_id, queue_name in self.PRINTER_QUEUES.items():
                self.mq_client.declare_queue(
                    queue_name=queue_name,
                    durable=True,
                    arguments={
                        "x-dead-letter-exchange": "",  # Default exchange
                        "x-dead-letter-routing-key": DLQ_QUEUE,
                    },
                )

                # Bind queue to tasks exchange
                self.mq_client.bind_queue(
                    queue_name=queue_name,
                    exchange_name=FABRICATION_EXCHANGE,
                    routing_key=queue_name,  # Routing key matches queue name
                )

                LOGGER.info(
                    "Setup printer queue",
                    printer_id=printer_id,
                    queue=queue_name,
                )

        except Exception as e:
            LOGGER.error("Failed to setup queues", error=str(e), exc_info=True)
            raise

    async def distribute_job(
        self,
        job: QueuedPrint,
    ) -> JobDistributionResult:
        """Distribute job to printer-specific queue.

        Args:
            job: Print job to distribute (must have printer_id assigned)

        Returns:
            JobDistributionResult with success status
        """
        if not job.printer_id:
            error = "Job has no printer_id assigned"
            LOGGER.error("Cannot distribute job", job_id=job.job_id, error=error)
            return JobDistributionResult(
                job_id=job.job_id,
                printer_id="unknown",
                queue_name="",
                success=False,
                error=error,
            )

        queue_name = self.PRINTER_QUEUES.get(job.printer_id)
        if not queue_name:
            error = f"Unknown printer: {job.printer_id}"
            LOGGER.error("Cannot distribute job", job_id=job.job_id, error=error)
            return JobDistributionResult(
                job_id=job.job_id,
                printer_id=job.printer_id,
                queue_name="",
                success=False,
                error=error,
            )

        try:
            # Build job message
            message = self._build_job_message(job)

            # Publish to printer queue
            self.mq_client.publish_task(
                queue_name=queue_name,
                task_data=message,
                task_type="print_job",
                priority=max(0, min(10, 11 - job.priority)),  # Invert priority: 1 (high) -> 10, 10 (low) -> 1
            )

            LOGGER.info(
                "Job distributed",
                job_id=job.job_id,
                job_name=job.job_name,
                printer_id=job.printer_id,
                queue=queue_name,
            )

            return JobDistributionResult(
                job_id=job.job_id,
                printer_id=job.printer_id,
                queue_name=queue_name,
                success=True,
                distributed_at=datetime.utcnow(),
            )

        except Exception as e:
            error = f"Failed to publish to RabbitMQ: {str(e)}"
            LOGGER.error(
                "Job distribution failed",
                job_id=job.job_id,
                printer_id=job.printer_id,
                error=str(e),
                exc_info=True,
            )
            return JobDistributionResult(
                job_id=job.job_id,
                printer_id=job.printer_id,
                queue_name=queue_name,
                success=False,
                error=error,
            )

    def _build_job_message(self, job: QueuedPrint) -> dict:
        """Build job message for RabbitMQ.

        Args:
            job: Print job

        Returns:
            Message dict
        """
        return {
            "job_id": job.job_id,
            "job_name": job.job_name,
            "stl_path": job.stl_path,
            "gcode_path": job.gcode_path,
            "printer_id": job.printer_id,
            "material_id": job.material_id,
            "spool_id": job.spool_id,
            "print_settings": job.print_settings,
            "estimated_duration_hours": float(job.estimated_duration_hours),
            "estimated_material_grams": float(job.estimated_material_grams),
            "estimated_cost_usd": float(job.estimated_cost_usd),
            "priority": job.priority,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "retry_count": job.retry_count,
            "max_retries": job.max_retries,
            "goal_id": job.goal_id,
            "created_by": job.created_by,
        }

    async def publish_status_event(
        self,
        job_id: str,
        status: str,
        printer_id: str,
        progress_percent: Optional[float] = None,
        error: Optional[str] = None,
    ) -> None:
        """Publish job status update event.

        Args:
            job_id: Job ID
            status: New status (slicing, uploading, printing, completed, failed)
            printer_id: Printer ID
            progress_percent: Print progress (0-100)
            error: Error message if failed
        """
        try:
            event_data = {
                "job_id": job_id,
                "status": status,
                "printer_id": printer_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if progress_percent is not None:
                event_data["progress_percent"] = progress_percent

            if error:
                event_data["error"] = error

            self.mq_client.publish_event(
                routing_key=f"fabrication.job.{status}",
                event_data=event_data,
                event_type="job_status_update",
            )

            LOGGER.debug(
                "Published status event",
                job_id=job_id,
                status=status,
                printer_id=printer_id,
            )

        except Exception as e:
            LOGGER.error(
                "Failed to publish status event",
                job_id=job_id,
                status=status,
                error=str(e),
                exc_info=True,
            )

    def get_queue_depth(self, printer_id: str) -> int:
        """Get number of jobs in printer queue.

        Args:
            printer_id: Printer ID

        Returns:
            Number of jobs in queue, or -1 if unknown printer
        """
        queue_name = self.PRINTER_QUEUES.get(printer_id)
        if not queue_name:
            LOGGER.warning("Unknown printer for queue depth", printer_id=printer_id)
            return -1

        try:
            return self.mq_client.get_queue_size(queue_name)
        except Exception as e:
            LOGGER.error(
                "Failed to get queue depth",
                printer_id=printer_id,
                queue=queue_name,
                error=str(e),
            )
            return -1

    def get_all_queue_depths(self) -> dict[str, int]:
        """Get queue depths for all printers.

        Returns:
            Dict mapping printer_id to queue depth
        """
        depths = {}
        for printer_id in self.PRINTER_QUEUES.keys():
            depths[printer_id] = self.get_queue_depth(printer_id)

        return depths

    def get_dlq_size(self) -> int:
        """Get number of failed jobs in dead letter queue.

        Returns:
            Number of failed jobs
        """
        try:
            return self.mq_client.get_queue_size(DLQ_QUEUE)
        except Exception as e:
            LOGGER.error("Failed to get DLQ size", error=str(e))
            return -1
