"""Queue Optimizer - P3 #20 Multi-Printer Coordination.

Optimizes job queue with material batching, priority sorting, and build volume filtering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

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


class QueueOptimizer:
    """Optimize job queue with intelligent sorting and material batching.

    Optimization Goals:
    1. Deadlines - Jobs with approaching deadlines prioritized
    2. Material Batching - Group same material to reduce filament swaps
    3. User Priority - High-priority jobs first
    4. Build Volume - Ensure job fits printer
    5. FIFO - First-in-first-out for same priority
    """

    def __init__(
        self,
        db: Session,
        analyzer: STLAnalyzer,
        deadline_hours_threshold: int = 24,
        material_batch_bonus: float = 50.0,
    ):
        """Initialize queue optimizer.

        Args:
            db: Database session
            analyzer: STL analyzer for dimension checks
            deadline_hours_threshold: Hours before deadline to boost priority (default: 24)
            material_batch_bonus: Score bonus for material matching (default: 50.0)
        """
        self.db = db
        self.analyzer = analyzer
        self.deadline_hours_threshold = deadline_hours_threshold
        self.material_batch_bonus = material_batch_bonus

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

            # Calculate optimization score
            score, reasoning = self._calculate_score(job, current_material)
            scored_jobs.append(
                OptimizationResult(
                    job=job,
                    optimization_score=score,
                    reasoning=reasoning,
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
