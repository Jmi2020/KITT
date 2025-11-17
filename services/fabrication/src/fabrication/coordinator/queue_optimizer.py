"""Queue Optimizer - P3 #17/#20 Enhanced Queue Optimization.

Optimizes job queue with:
- Material batching (P3 #20)
- Deadline prioritization (P3 #20)
- Off-peak scheduling for long prints (P3 #17)
- Material change penalty accounting (P3 #17)
- Maintenance scheduling (P3 #17)
- Intelligent reasoning generation (P3 #17)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import QueuedPrint, QueueStatus
from common.logging import get_logger

from ..analysis.stl_analyzer import STLAnalyzer
from ..selector.printer_selector import PrinterSelector

LOGGER = get_logger(__name__)


@dataclass
class OptimizationResult:
    """Result of queue optimization."""
    job: QueuedPrint
    optimization_score: float
    reasoning: str
    scheduled_start: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None


@dataclass
class QueueEstimate:
    """Completion time estimate for queue."""
    total_print_hours: float
    total_material_changes: int
    material_change_time_hours: float
    maintenance_time_hours: float
    total_time_hours: float
    estimated_completion: datetime


class QueueOptimizer:
    """Optimize job queue with intelligent sorting and material batching.

    Optimization Goals (P3 #20 + #17):
    1. Deadlines - Jobs with approaching deadlines prioritized
    2. Material Batching - Group same material to reduce filament swaps
    3. Off-Peak Scheduling - Long prints delayed to off-peak hours
    4. User Priority - High-priority jobs first
    5. Build Volume - Ensure job fits printer
    6. FIFO - First-in-first-out for same priority
    7. Maintenance Windows - Schedule printer maintenance
    """

    def __init__(
        self,
        db: Session,
        analyzer: STLAnalyzer,
        deadline_hours_threshold: int = 24,
        material_batch_bonus: float = 50.0,
        off_peak_start_hour: int = 22,  # 10 PM
        off_peak_end_hour: int = 6,     # 6 AM
        long_print_threshold_hours: float = 8.0,
        material_change_penalty_minutes: int = 15,
        maintenance_interval_hours: int = 200,
    ):
        """Initialize queue optimizer.

        Args:
            db: Database session
            analyzer: STL analyzer for dimension checks
            deadline_hours_threshold: Hours before deadline to boost priority (default: 24)
            material_batch_bonus: Score bonus for material matching (default: 50.0)
            off_peak_start_hour: Hour when off-peak begins (default: 22 = 10 PM)
            off_peak_end_hour: Hour when off-peak ends (default: 6 = 6 AM)
            long_print_threshold_hours: Prints >=this duration eligible for off-peak (default: 8.0)
            material_change_penalty_minutes: Time penalty for material swap (default: 15)
            maintenance_interval_hours: Hours between maintenance cycles (default: 200)
        """
        self.db = db
        self.analyzer = analyzer
        self.deadline_hours_threshold = deadline_hours_threshold
        self.material_batch_bonus = material_batch_bonus

        # P3 #17 enhancements
        self.off_peak_start_hour = off_peak_start_hour
        self.off_peak_end_hour = off_peak_end_hour
        self.long_print_threshold_hours = long_print_threshold_hours
        self.material_change_penalty_minutes = material_change_penalty_minutes
        self.maintenance_interval_hours = maintenance_interval_hours

        # Printer maintenance tracking (hours printed since last maintenance)
        self._printer_hours: dict[str, float] = {}

    async def get_next_job(
        self,
        printer_id: str,
        current_material: Optional[str] = None,
    ) -> Optional[QueuedPrint]:
        """Get next optimized job for a specific printer.

        Args:
            printer_id: Target printer ID (bamboo_h2d, elegoo_giga, snapmaker_artisan)
            current_material: Currently loaded material ID (for batching optimization)

        Returns:
            Next job to print, or None if queue empty or no compatible jobs
        """
        LOGGER.info("Getting next job", printer_id=printer_id, current_material=current_material)

        # Get all queued jobs
        stmt = (
            select(QueuedPrint)
            .where(QueuedPrint.status == QueueStatus.queued)
            .order_by(QueuedPrint.queued_at)  # Initial FIFO ordering
        )
        queued_jobs = self.db.execute(stmt).scalars().all()

        if not queued_jobs:
            LOGGER.info("No queued jobs", printer_id=printer_id)
            return None

        LOGGER.info("Queued jobs found", count=len(queued_jobs), printer_id=printer_id)

        # Get printer capabilities
        printer_caps = PrinterSelector.PRINTERS.get(printer_id)
        if not printer_caps:
            LOGGER.error("Unknown printer", printer_id=printer_id)
            return None

        max_dimension = min(printer_caps.build_volume)

        # Score and filter jobs
        current_time = datetime.utcnow()
        scored_jobs: List[OptimizationResult] = []

        for job in queued_jobs:
            # Check if job fits printer's build volume
            try:
                from pathlib import Path
                dimensions = self.analyzer.analyze(Path(job.stl_path))
                if dimensions.max_dimension > max_dimension:
                    LOGGER.debug(
                        "Job too large for printer",
                        job_id=job.job_id,
                        model_size=f"{dimensions.max_dimension:.1f}mm",
                        printer_limit=f"{max_dimension:.1f}mm",
                        printer_id=printer_id,
                    )
                    continue  # Skip jobs that don't fit
            except Exception as e:
                LOGGER.error(
                    "Failed to analyze STL",
                    job_id=job.job_id,
                    stl_path=job.stl_path,
                    error=str(e),
                )
                continue

            # P3 #17: Check if job should be delayed to off-peak
            should_delay, delay_reason = self._should_delay_to_off_peak(job, current_time)

            if should_delay:
                # Skip this job for now - it should wait for off-peak
                LOGGER.debug(
                    "Delaying job to off-peak",
                    job_id=job.job_id,
                    job_name=job.job_name,
                    reason=delay_reason,
                )
                continue

            # Calculate optimization score
            score, reasoning = self._calculate_score(job, current_material)

            # Append delay_reason if applicable
            if not should_delay and delay_reason:
                reasoning += f"; {delay_reason}"

            scored_jobs.append(
                OptimizationResult(
                    job=job,
                    optimization_score=score,
                    reasoning=reasoning,
                    scheduled_start=current_time,
                    estimated_completion=current_time + timedelta(hours=float(job.estimated_duration_hours)),
                )
            )

        if not scored_jobs:
            LOGGER.info("No compatible jobs for printer", printer_id=printer_id)
            return None

        # Sort by optimization score (highest first)
        scored_jobs.sort(key=lambda x: x.optimization_score, reverse=True)

        best_job = scored_jobs[0]
        LOGGER.info(
            "Selected optimized job",
            job_id=best_job.job.job_id,
            job_name=best_job.job.job_name,
            score=f"{best_job.optimization_score:.2f}",
            reasoning=best_job.reasoning,
            printer_id=printer_id,
        )

        # Update job with optimization metadata
        best_job.job.priority_score = best_job.optimization_score
        best_job.job.optimization_reasoning = best_job.reasoning

        return best_job.job

    def _calculate_score(
        self,
        job: QueuedPrint,
        current_material: Optional[str],
    ) -> tuple[float, str]:
        """Calculate optimization score for a job.

        Returns:
            (score, reasoning) tuple
        """
        score = 0.0
        reasons = []

        # 1. Deadline Priority (highest weight: 0-1000 points)
        if job.deadline:
            hours_until_deadline = (job.deadline - datetime.utcnow()).total_seconds() / 3600

            if hours_until_deadline < 0:
                # Overdue! Highest priority
                score += 1000.0
                reasons.append(f"OVERDUE by {abs(hours_until_deadline):.1f}h")
            elif hours_until_deadline < self.deadline_hours_threshold:
                # Approaching deadline - scale priority
                urgency_score = 500.0 * (1 - hours_until_deadline / self.deadline_hours_threshold)
                score += urgency_score
                reasons.append(f"Deadline in {hours_until_deadline:.1f}h (urgency: {urgency_score:.1f})")
            else:
                reasons.append(f"Deadline in {hours_until_deadline:.1f}h")
        else:
            reasons.append("No deadline")

        # 2. User Priority (medium weight: 0-100 points)
        # Priority is 1-10 where 1 is highest, so invert: (11 - priority) * 10
        priority_score = (11 - job.priority) * 10
        score += priority_score
        reasons.append(f"Priority {job.priority} ({priority_score:.0f} pts)")

        # 3. Material Batching (medium weight: 0-50 points)
        if current_material and job.material_id == current_material:
            score += self.material_batch_bonus
            reasons.append(f"Material match (+{self.material_batch_bonus:.0f} pts)")
        else:
            reasons.append("Different material")

        # 4. FIFO tie-breaker (low weight: based on queue age in hours)
        # Jobs queued earlier get small boost
        hours_queued = (datetime.utcnow() - job.queued_at).total_seconds() / 3600
        fifo_score = min(hours_queued, 10.0)  # Cap at 10 points
        score += fifo_score
        reasons.append(f"Queued {hours_queued:.1f}h ago (+{fifo_score:.1f} pts)")

        reasoning = "; ".join(reasons)
        return score, reasoning

    async def get_queue_statistics(self) -> dict:
        """Get queue statistics for monitoring.

        Returns:
            Dict with queue metrics
        """
        stmt = select(QueuedPrint)
        all_jobs = self.db.execute(stmt).scalars().all()

        stats = {
            "total_jobs": len(all_jobs),
            "by_status": {},
            "by_priority": {},
            "by_material": {},
            "upcoming_deadlines": 0,
            "overdue": 0,
        }

        for job in all_jobs:
            # Count by status
            status = job.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Count by priority
            priority = f"p{job.priority}"
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

            # Count by material
            material = job.material_id
            stats["by_material"][material] = stats["by_material"].get(material, 0) + 1

            # Deadline tracking
            if job.deadline:
                hours_until = (job.deadline - datetime.utcnow()).total_seconds() / 3600
                if hours_until < 0:
                    stats["overdue"] += 1
                elif hours_until < 24:
                    stats["upcoming_deadlines"] += 1

        return stats

    async def reorder_queue_by_material(self, target_material: str) -> List[QueuedPrint]:
        """Preview jobs that would be batched with target material.

        Args:
            target_material: Material ID to batch

        Returns:
            List of jobs matching the material, sorted by priority
        """
        stmt = (
            select(QueuedPrint)
            .where(
                QueuedPrint.status == QueueStatus.queued,
                QueuedPrint.material_id == target_material,
            )
            .order_by(
                QueuedPrint.priority.asc(),
                QueuedPrint.queued_at.asc(),
            )
        )

        matching_jobs = self.db.execute(stmt).scalars().all()

        LOGGER.info(
            "Material batch preview",
            material=target_material,
            job_count=len(matching_jobs),
        )

        return matching_jobs

    # ========================================================================
    # P3 #17 Enhanced Optimization Features
    # ========================================================================

    def _is_off_peak(self, dt: datetime) -> bool:
        """Check if datetime is during off-peak hours.

        Args:
            dt: Datetime to check

        Returns:
            True if during off-peak window (10 PM - 6 AM default)
        """
        hour = dt.hour

        # Handle case where off-peak window crosses midnight
        if self.off_peak_start_hour > self.off_peak_end_hour:
            # e.g., 22:00 - 06:00 (crosses midnight)
            return hour >= self.off_peak_start_hour or hour < self.off_peak_end_hour
        else:
            # e.g., 01:00 - 05:00 (doesn't cross midnight)
            return self.off_peak_start_hour <= hour < self.off_peak_end_hour

    def _next_off_peak_start(self, current_time: datetime) -> datetime:
        """Calculate next off-peak window start time.

        Args:
            current_time: Current datetime

        Returns:
            Datetime when next off-peak window begins
        """
        # Create time object for off-peak start
        off_peak_time = time(hour=self.off_peak_start_hour, minute=0, second=0)

        # Check if today's off-peak window hasn't started yet
        today_off_peak = datetime.combine(current_time.date(), off_peak_time)

        if current_time.time() < off_peak_time:
            # Today's off-peak window is in the future
            return today_off_peak
        else:
            # Use tomorrow's off-peak window
            tomorrow = current_time.date() + timedelta(days=1)
            return datetime.combine(tomorrow, off_peak_time)

    def _should_delay_to_off_peak(
        self,
        job: QueuedPrint,
        current_time: datetime,
    ) -> Tuple[bool, str]:
        """Determine if job should be delayed to off-peak hours.

        Args:
            job: Print job to evaluate
            current_time: Current datetime

        Returns:
            (should_delay, reasoning) tuple
        """
        # Only consider long prints
        if job.estimated_duration_hours < self.long_print_threshold_hours:
            return False, "Short print (< {:.1f}h)".format(self.long_print_threshold_hours)

        # Already off-peak - no need to delay
        if self._is_off_peak(current_time):
            return False, "Already off-peak hours"

        # Check if job has urgent deadline
        if job.deadline:
            hours_until_deadline = (job.deadline - current_time).total_seconds() / 3600

            # Deadline within 24 hours - don't delay
            if hours_until_deadline < 24:
                return False, "Urgent deadline ({:.1f}h away)".format(hours_until_deadline)

        # Long print during peak hours with no urgent deadline - delay
        next_off_peak = self._next_off_peak_start(current_time)
        hours_until_off_peak = (next_off_peak - current_time).total_seconds() / 3600

        return True, "Long print ({:.1f}h) delayed to off-peak (in {:.1f}h)".format(
            job.estimated_duration_hours,
            hours_until_off_peak,
        )

    def check_maintenance_due(self, printer_id: str) -> Tuple[bool, float]:
        """Check if printer maintenance is due.

        Args:
            printer_id: Printer to check

        Returns:
            (is_due, hours_since_maintenance) tuple
        """
        hours_printed = self._printer_hours.get(printer_id, 0.0)
        is_due = hours_printed >= self.maintenance_interval_hours

        return is_due, hours_printed

    def record_print_completed(self, printer_id: str, print_duration_hours: float):
        """Record completed print for maintenance tracking.

        Args:
            printer_id: Printer that completed the print
            print_duration_hours: Duration of completed print
        """
        current_hours = self._printer_hours.get(printer_id, 0.0)
        self._printer_hours[printer_id] = current_hours + print_duration_hours

        LOGGER.info(
            "Recorded print completion",
            printer_id=printer_id,
            print_hours=print_duration_hours,
            total_hours=self._printer_hours[printer_id],
        )

    def record_maintenance_completed(self, printer_id: str):
        """Reset maintenance counter after maintenance performed.

        Args:
            printer_id: Printer that was serviced
        """
        self._printer_hours[printer_id] = 0.0

        LOGGER.info("Reset maintenance counter", printer_id=printer_id)

    async def estimate_queue_completion(
        self,
        printer_id: str,
        current_material: Optional[str] = None,
    ) -> QueueEstimate:
        """Estimate total completion time for queue.

        Accounts for:
        - Print durations
        - Material change penalties
        - Maintenance windows

        Args:
            printer_id: Target printer
            current_material: Currently loaded material (None = unknown)

        Returns:
            QueueEstimate with timing breakdown
        """
        # Get all queued jobs for this printer
        stmt = (
            select(QueuedPrint)
            .where(QueuedPrint.status == QueueStatus.queued)
            .order_by(QueuedPrint.queued_at)
        )
        queued_jobs = self.db.execute(stmt).scalars().all()

        total_print_hours = 0.0
        material_changes = 0
        last_material = current_material

        for job in queued_jobs:
            # Add print duration
            total_print_hours += float(job.estimated_duration_hours)

            # Count material changes
            if last_material and job.material_id != last_material:
                material_changes += 1

            last_material = job.material_id

        # Calculate material change time
        material_change_hours = (material_changes * self.material_change_penalty_minutes) / 60.0

        # Check if maintenance due
        is_due, hours_printed = self.check_maintenance_due(printer_id)
        maintenance_hours = 0.0

        if is_due or (hours_printed + total_print_hours >= self.maintenance_interval_hours):
            # Maintenance required during this queue
            maintenance_hours = 2.0  # Assume 2 hours for maintenance

        # Calculate total time
        total_hours = total_print_hours + material_change_hours + maintenance_hours

        # Estimate completion datetime
        estimated_completion = datetime.utcnow() + timedelta(hours=total_hours)

        return QueueEstimate(
            total_print_hours=total_print_hours,
            total_material_changes=material_changes,
            material_change_time_hours=material_change_hours,
            maintenance_time_hours=maintenance_hours,
            total_time_hours=total_hours,
            estimated_completion=estimated_completion,
        )
