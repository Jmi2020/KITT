"""Parallel Job Scheduler - P3 #20 Multi-Printer Coordination.

Schedules jobs across multiple printers with distributed locking and RabbitMQ distribution.
Enhanced with PrintExecutor integration for automated print execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from common.db.models import QueuedPrint, QueueStatus, JobStatusHistory
from common.logging import get_logger

from ..status.printer_status import PrinterStatusChecker, PrinterStatus
from .queue_optimizer import QueueOptimizer

LOGGER = get_logger(__name__)

try:
    from ..executor import PrintExecutor
    PRINT_EXECUTOR_AVAILABLE = True
except ImportError:
    PRINT_EXECUTOR_AVAILABLE = False
    LOGGER.warning("PrintExecutor not available - automated execution disabled")


@dataclass
class JobAssignment:
    """Result of job assignment to printer."""
    job_id: str
    job_name: str
    printer_id: str
    material_id: str
    estimated_duration_hours: float
    assigned_at: datetime
    status: str  # "scheduled" or "failed"
    error: Optional[str] = None


class ParallelJobScheduler:
    """Schedule jobs across multiple printers with optimization.

    Scheduling Strategy:
    1. Get all printers with real-time status
    2. Find idle printers (online + not printing)
    3. For each idle printer:
       a. Get top-priority job from optimized queue
       b. Filter jobs that fit printer's build volume
       c. Prefer jobs with matching material (reduce swaps)
       d. Assign job and update database
       e. Publish to RabbitMQ (handled by caller)
    4. Reschedule after interval or on printer-idle event
    """

    def __init__(
        self,
        db: Session,
        status_checker: PrinterStatusChecker,
        queue_optimizer: QueueOptimizer,
        print_executor: Optional["PrintExecutor"] = None,
    ):
        """Initialize scheduler.

        Args:
            db: Database session
            status_checker: Printer status checker
            queue_optimizer: Queue optimizer for job selection
            print_executor: Optional PrintExecutor for automated execution
        """
        self.db = db
        self.status_checker = status_checker
        self.queue_optimizer = queue_optimizer
        self.print_executor = print_executor

    async def schedule_next_jobs(
        self,
        force_printers: Optional[List[str]] = None,
    ) -> List[JobAssignment]:
        """Schedule next jobs for all idle printers.

        Args:
            force_printers: Optional list of printer IDs to force scheduling
                          (ignores status check, useful for testing)

        Returns:
            List of job assignments
        """
        LOGGER.info("Starting job scheduling cycle")

        # Get printer statuses
        statuses = await self.status_checker.get_all_statuses()

        # Find idle printers
        if force_printers:
            idle_printers = force_printers
            LOGGER.info("Force scheduling", printers=idle_printers)
        else:
            idle_printers = [
                printer_id
                for printer_id, status in statuses.items()
                if status.is_online and not status.is_printing
            ]

        LOGGER.info("Idle printers found", count=len(idle_printers), printers=idle_printers)

        if not idle_printers:
            LOGGER.info("No idle printers available")
            return []

        # Schedule jobs for each idle printer
        assignments: List[JobAssignment] = []
        for printer_id in idle_printers:
            assignment = await self._schedule_for_printer(
                printer_id,
                statuses.get(printer_id),
            )
            if assignment:
                assignments.append(assignment)

        LOGGER.info("Scheduling cycle complete", assignments=len(assignments))
        return assignments

    async def _schedule_for_printer(
        self,
        printer_id: str,
        status: Optional[PrinterStatus],
    ) -> Optional[JobAssignment]:
        """Schedule next job for a specific printer.

        Args:
            printer_id: Target printer ID
            status: Printer status (for material checking)

        Returns:
            JobAssignment if scheduled, None if no compatible jobs
        """
        LOGGER.info("Scheduling for printer", printer_id=printer_id)

        # TODO: Get current material from printer status or database
        # For now, we'll pass None and not optimize for material batching
        current_material = None

        # Get next optimized job
        job = await self.queue_optimizer.get_next_job(
            printer_id=printer_id,
            current_material=current_material,
        )

        if not job:
            LOGGER.info("No compatible jobs for printer", printer_id=printer_id)
            return None

        # Assign job to printer
        try:
            assignment = await self._assign_job(job, printer_id)
            LOGGER.info(
                "Job assigned",
                job_id=job.job_id,
                job_name=job.job_name,
                printer_id=printer_id,
            )
            return assignment

        except Exception as e:
            LOGGER.error(
                "Failed to assign job",
                job_id=job.job_id,
                printer_id=printer_id,
                error=str(e),
                exc_info=True,
            )
            return JobAssignment(
                job_id=job.job_id,
                job_name=job.job_name,
                printer_id=printer_id,
                material_id=job.material_id,
                estimated_duration_hours=float(job.estimated_duration_hours),
                assigned_at=datetime.utcnow(),
                status="failed",
                error=str(e),
            )

    async def _assign_job(
        self,
        job: QueuedPrint,
        printer_id: str,
    ) -> JobAssignment:
        """Assign job to printer and update database.

        Args:
            job: Job to assign
            printer_id: Target printer

        Returns:
            JobAssignment record
        """
        # Update job status and assignment
        job.printer_id = printer_id
        job.status = QueueStatus.scheduled
        job.scheduled_start = datetime.utcnow()
        job.updated_at = datetime.utcnow()

        # Add status history
        history = JobStatusHistory(
            id=str(uuid4()),
            job_id=job.id,
            from_status="queued",
            to_status="scheduled",
            reason=f"Scheduled to {printer_id}",
            changed_at=datetime.utcnow(),
            changed_by="scheduler",
        )
        self.db.add(history)

        # Commit changes
        self.db.commit()

        return JobAssignment(
            job_id=job.job_id,
            job_name=job.job_name,
            printer_id=printer_id,
            material_id=job.material_id,
            estimated_duration_hours=float(job.estimated_duration_hours),
            assigned_at=datetime.utcnow(),
            status="scheduled",
        )

    async def get_printer_queue_depth(self) -> dict[str, int]:
        """Get queue depth per printer.

        Returns:
            Dict mapping printer_id to number of jobs (scheduled + printing)
        """
        stmt = (
            select(QueuedPrint)
            .where(
                QueuedPrint.status.in_([QueueStatus.scheduled, QueueStatus.printing])
            )
        )
        active_jobs = self.db.execute(stmt).scalars().all()

        queue_depth = {}
        for job in active_jobs:
            if job.printer_id:
                queue_depth[job.printer_id] = queue_depth.get(job.printer_id, 0) + 1

        return queue_depth

    async def cancel_job(
        self,
        job_id: str,
        reason: str = "User requested",
        cancelled_by: str = "user",
    ) -> bool:
        """Cancel a queued or scheduled job.

        Args:
            job_id: Job ID to cancel
            reason: Cancellation reason
            cancelled_by: Who cancelled (user ID or "system")

        Returns:
            True if cancelled, False if not found or already completed
        """
        stmt = select(QueuedPrint).where(QueuedPrint.job_id == job_id)
        job = self.db.execute(stmt).scalar_one_or_none()

        if not job:
            LOGGER.warning("Job not found for cancellation", job_id=job_id)
            return False

        if job.status in [QueueStatus.completed, QueueStatus.failed, QueueStatus.cancelled]:
            LOGGER.warning(
                "Cannot cancel completed job",
                job_id=job_id,
                status=job.status.value,
            )
            return False

        # Update job status
        old_status = job.status.value
        job.status = QueueStatus.cancelled
        job.status_reason = reason
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()

        # Add status history
        history = JobStatusHistory(
            id=str(uuid4()),
            job_id=job.id,
            from_status=old_status,
            to_status="cancelled",
            reason=reason,
            changed_at=datetime.utcnow(),
            changed_by=cancelled_by,
        )
        self.db.add(history)

        self.db.commit()

        LOGGER.info("Job cancelled", job_id=job_id, reason=reason)
        return True

    async def retry_failed_job(
        self,
        job_id: str,
    ) -> bool:
        """Retry a failed job.

        Args:
            job_id: Job ID to retry

        Returns:
            True if re-queued, False if max retries exceeded or not found
        """
        stmt = select(QueuedPrint).where(QueuedPrint.job_id == job_id)
        job = self.db.execute(stmt).scalar_one_or_none()

        if not job:
            LOGGER.warning("Job not found for retry", job_id=job_id)
            return False

        if job.status != QueueStatus.failed:
            LOGGER.warning(
                "Cannot retry non-failed job",
                job_id=job_id,
                status=job.status.value,
            )
            return False

        if job.retry_count >= job.max_retries:
            LOGGER.warning(
                "Max retries exceeded",
                job_id=job_id,
                retry_count=job.retry_count,
                max_retries=job.max_retries,
            )
            return False

        # Re-queue job
        job.status = QueueStatus.queued
        job.retry_count += 1
        job.printer_id = None  # Clear previous assignment
        job.scheduled_start = None
        job.started_at = None
        job.completed_at = None
        job.status_reason = None
        job.updated_at = datetime.utcnow()

        # Add status history
        history = JobStatusHistory(
            id=str(uuid4()),
            job_id=job.id,
            from_status="failed",
            to_status="queued",
            reason=f"Retry attempt {job.retry_count}/{job.max_retries}",
            changed_at=datetime.utcnow(),
            changed_by="scheduler",
        )
        self.db.add(history)

        self.db.commit()

        LOGGER.info(
            "Job re-queued for retry",
            job_id=job_id,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
        )
        return True

    async def update_job_priority(
        self,
        job_id: str,
        new_priority: int,
        updated_by: str = "user",
    ) -> bool:
        """Update job priority.

        Args:
            job_id: Job ID to update
            new_priority: New priority (1-10)
            updated_by: Who updated

        Returns:
            True if updated, False if not found
        """
        if not 1 <= new_priority <= 10:
            raise ValueError(f"Priority must be 1-10, got {new_priority}")

        stmt = select(QueuedPrint).where(QueuedPrint.job_id == job_id)
        job = self.db.execute(stmt).scalar_one_or_none()

        if not job:
            LOGGER.warning("Job not found for priority update", job_id=job_id)
            return False

        old_priority = job.priority
        job.priority = new_priority
        job.updated_at = datetime.utcnow()

        # Add status history
        history = JobStatusHistory(
            id=str(uuid4()),
            job_id=job.id,
            from_status=job.status.value,
            to_status=job.status.value,
            reason=f"Priority changed from {old_priority} to {new_priority}",
            changed_at=datetime.utcnow(),
            changed_by=updated_by,
        )
        self.db.add(history)

        self.db.commit()

        LOGGER.info(
            "Job priority updated",
            job_id=job_id,
            old_priority=old_priority,
            new_priority=new_priority,
        )
        return True

    async def schedule_and_execute_jobs(
        self,
        executor: "PrintExecutor",
        printer_configs: dict[str, dict],
        force_printers: Optional[List[str]] = None,
    ) -> List[JobAssignment]:
        """Schedule and automatically execute jobs on idle printers.

        This method combines job scheduling with automated execution:
        1. Schedule jobs to idle printers
        2. For each assignment, kick off PrintExecutor in background
        3. Return assignments immediately (execution continues async)

        Args:
            executor: PrintExecutor instance
            printer_configs: Dict mapping printer_id to driver configuration
            force_printers: Optional list of printer IDs to force scheduling

        Returns:
            List of job assignments (execution continues in background)
        """
        if not PRINT_EXECUTOR_AVAILABLE:
            LOGGER.error("PrintExecutor not available - cannot execute jobs")
            return []

        LOGGER.info("Starting schedule and execute cycle")

        # Schedule jobs to idle printers
        assignments = await self.schedule_next_jobs(force_printers)

        if not assignments:
            LOGGER.info("No jobs scheduled")
            return []

        # Kick off execution for each assignment (background tasks)
        for assignment in assignments:
            if assignment.status == "scheduled":
                # Launch execution in background
                asyncio.create_task(
                    self._execute_job_background(
                        executor,
                        assignment,
                        printer_configs.get(assignment.printer_id),
                    )
                )

        LOGGER.info(
            "Schedule and execute cycle complete",
            scheduled=len(assignments),
        )

        return assignments

    async def _execute_job_background(
        self,
        executor: "PrintExecutor",
        assignment: JobAssignment,
        printer_config: Optional[dict],
    ) -> None:
        """Execute job in background (async task).

        Args:
            executor: PrintExecutor instance
            assignment: Job assignment details
            printer_config: Printer driver configuration
        """
        if not printer_config:
            LOGGER.error(
                "No printer config for job execution",
                job_id=assignment.job_id,
                printer_id=assignment.printer_id,
            )
            return

        try:
            # Get job from database
            stmt = select(QueuedPrint).where(QueuedPrint.job_id == assignment.job_id)
            job = self.db.execute(stmt).scalar_one_or_none()

            if not job:
                LOGGER.error("Job not found for execution", job_id=assignment.job_id)
                return

            LOGGER.info(
                "Starting background job execution",
                job_id=assignment.job_id,
                printer_id=assignment.printer_id,
            )

            # Execute job
            result = await executor.execute_job(
                job=job,
                printer_id=assignment.printer_id,
                printer_config=printer_config,
            )

            if result.success:
                LOGGER.info(
                    "Background job execution completed",
                    job_id=assignment.job_id,
                    printer_id=assignment.printer_id,
                )
            else:
                LOGGER.error(
                    "Background job execution failed",
                    job_id=assignment.job_id,
                    printer_id=assignment.printer_id,
                    error=result.error_message,
                )

        except Exception as e:
            LOGGER.error(
                "Error in background job execution",
                job_id=assignment.job_id,
                printer_id=assignment.printer_id,
                error=str(e),
                exc_info=True,
            )
