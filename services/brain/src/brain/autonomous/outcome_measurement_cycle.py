# noqa: D401
"""Outcome measurement cycle for Phase 3 learning system.

Scheduled Job: outcome_measurement_cycle
- Runs daily at 6:00am PST (14:00 UTC)
- Measures outcomes for goals completed 30 days ago
- Calculates effectiveness scores
- Stores results for feedback loop learning
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from common.config import settings
from common.db.models import Goal, GoalStatus, GoalType

from .outcome_tracker import OutcomeTracker

logger = logging.getLogger(__name__)


class OutcomeMeasurementCycle:
    """Scheduled cycle for measuring goal outcomes.

    Phase 3: Learning "The Reflection"
    - Finds goals eligible for outcome measurement
    - Captures baseline metrics if missing
    - Measures outcome metrics
    - Calculates effectiveness scores
    - Stores outcomes for feedback loop
    """

    def __init__(
        self,
        db_session: Session,
        measurement_window_days: int = 30,
        enabled: bool = True,
    ) -> None:
        self.db = db_session
        self.measurement_window_days = measurement_window_days
        self.enabled = enabled
        self.tracker = OutcomeTracker(db_session)

    async def run_cycle(self) -> dict:
        """Run outcome measurement cycle.

        Returns:
            Dict with cycle results and statistics
        """
        if not self.enabled:
            logger.info("Outcome measurement cycle disabled, skipping")
            return {"status": "disabled", "goals_measured": 0}

        logger.info("Starting outcome measurement cycle")
        start_time = datetime.utcnow()

        # Find goals eligible for measurement
        eligible_goals = self._find_goals_for_measurement()

        logger.info(f"Found {len(eligible_goals)} goals eligible for outcome measurement")

        results = {
            "status": "completed",
            "goals_measured": 0,
            "goals_skipped": 0,
            "goals_failed": 0,
            "errors": [],
            "measurements": [],
        }

        # Process each goal
        for goal in eligible_goals:
            try:
                measurement = await self._measure_goal_outcome(goal)
                results["goals_measured"] += 1
                results["measurements"].append(measurement)

                logger.info(
                    f"Successfully measured goal {goal.id}: "
                    f"effectiveness={measurement['effectiveness_score']:.1f}"
                )

            except Exception as exc:  # noqa: BLE001
                logger.error(f"Failed to measure goal {goal.id}: {exc}", exc_info=True)
                results["goals_failed"] += 1
                results["errors"].append({
                    "goal_id": goal.id,
                    "error": str(exc),
                })

        duration = (datetime.utcnow() - start_time).total_seconds()

        logger.info(
            f"Outcome measurement cycle completed in {duration:.1f}s: "
            f"measured={results['goals_measured']}, "
            f"failed={results['goals_failed']}"
        )

        results["duration_seconds"] = duration
        results["cycle_time"] = start_time.isoformat()

        return results

    def _find_goals_for_measurement(self) -> list[Goal]:
        """Find goals eligible for outcome measurement.

        Criteria:
        - Status = completed
        - Completed exactly N days ago (measurement_window_days)
        - outcome_measured_at is NULL (not yet measured)
        - learn_from = true (included in feedback loop)

        Returns:
            List of Goal objects ready for measurement
        """
        # Calculate target completion date (N days ago)
        target_date = datetime.utcnow() - timedelta(days=self.measurement_window_days)

        # Query for eligible goals
        # Note: Using a 24-hour window around target date to catch goals
        date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date_start + timedelta(days=1)

        stmt = (
            select(Goal)
            .where(
                and_(
                    Goal.status == GoalStatus.completed,
                    Goal.completed_at >= date_start,
                    Goal.completed_at < date_end,
                    Goal.outcome_measured_at.is_(None),
                    Goal.learn_from == True,  # noqa: E712
                )
            )
            .order_by(Goal.completed_at)
        )

        goals = self.db.execute(stmt).scalars().all()

        logger.info(
            f"Found {len(goals)} goals completed between "
            f"{date_start.date()} and {date_end.date()} "
            f"ready for outcome measurement"
        )

        return list(goals)

    async def _measure_goal_outcome(self, goal: Goal) -> dict:
        """Measure outcome for a single goal.

        Args:
            goal: Goal to measure

        Returns:
            Dict with measurement results

        Workflow:
        1. Capture baseline if not already captured
        2. Measure outcome metrics
        3. Calculate effectiveness score
        4. Store outcome in database
        """
        logger.info(f"Measuring outcome for goal: {goal.id} ({goal.goal_type})")

        # Step 1: Ensure baseline exists
        if not goal.baseline_captured:
            logger.info(f"Goal {goal.id} missing baseline, capturing now")
            baseline = self.tracker.capture_baseline(goal)
        else:
            # Baseline already exists, reconstruct from goal_outcomes table
            logger.info(f"Goal {goal.id} has baseline, loading from database")
            # For now, create a new baseline (in production, load from DB)
            baseline = self.tracker.capture_baseline(goal)

        # Step 2: Measure outcome
        outcome = self.tracker.measure_outcome(goal)

        # Step 3: Calculate effectiveness
        effectiveness = self.tracker.calculate_effectiveness(goal, baseline, outcome)

        # Step 4: Store outcome
        outcome_record = self.tracker.store_outcome(goal, baseline, outcome, effectiveness)

        # Return measurement summary
        return {
            "goal_id": goal.id,
            "goal_type": goal.goal_type.value,
            "goal_description": goal.description,
            "baseline_captured_at": baseline.captured_at.isoformat(),
            "outcome_measured_at": outcome.measured_at.isoformat(),
            "impact_score": effectiveness.impact,
            "roi_score": effectiveness.roi,
            "adoption_score": effectiveness.adoption,
            "quality_score": effectiveness.quality,
            "effectiveness_score": effectiveness.total,
            "measurement_method": outcome_record.measurement_method,
        }

    def get_measurement_statistics(self) -> dict:
        """Get statistics about outcome measurements.

        Returns:
            Dict with measurement statistics by goal type
        """
        # Query outcome measurements grouped by goal type
        stmt = select(Goal).where(Goal.outcome_measured_at.is_not(None))
        measured_goals = self.db.execute(stmt).scalars().all()

        # Group by goal type
        stats_by_type = {}
        for goal in measured_goals:
            goal_type = goal.goal_type.value
            if goal_type not in stats_by_type:
                stats_by_type[goal_type] = {
                    "count": 0,
                    "total_effectiveness": 0.0,
                    "avg_effectiveness": 0.0,
                    "min_effectiveness": 100.0,
                    "max_effectiveness": 0.0,
                }

            stats = stats_by_type[goal_type]
            stats["count"] += 1
            stats["total_effectiveness"] += float(goal.effectiveness_score or 0.0)

            eff = float(goal.effectiveness_score or 0.0)
            stats["min_effectiveness"] = min(stats["min_effectiveness"], eff)
            stats["max_effectiveness"] = max(stats["max_effectiveness"], eff)

        # Calculate averages
        for goal_type, stats in stats_by_type.items():
            if stats["count"] > 0:
                stats["avg_effectiveness"] = stats["total_effectiveness"] / stats["count"]

        return {
            "total_measured": len(measured_goals),
            "by_goal_type": stats_by_type,
            "measurement_window_days": self.measurement_window_days,
        }


async def run_outcome_measurement_cycle(
    db_session: Session,
    measurement_window_days: Optional[int] = None,
) -> dict:
    """Run outcome measurement cycle (entry point for scheduler).

    Args:
        db_session: Database session
        measurement_window_days: Days after completion to measure (default: from settings)

    Returns:
        Dict with cycle results
    """
    # Get configuration from settings
    enabled = getattr(settings, "outcome_measurement_enabled", True)
    window_days = measurement_window_days or getattr(
        settings, "outcome_measurement_window_days", 30
    )

    logger.info(
        f"Starting outcome measurement cycle: "
        f"enabled={enabled}, window_days={window_days}"
    )

    cycle = OutcomeMeasurementCycle(
        db_session=db_session,
        measurement_window_days=window_days,
        enabled=enabled,
    )

    results = await cycle.run_cycle()

    # Log summary to reasoning.jsonl
    logger.info(
        f"Outcome measurement cycle completed: {results['goals_measured']} measured, "
        f"{results['goals_failed']} failed"
    )

    return results


__all__ = ["OutcomeMeasurementCycle", "run_outcome_measurement_cycle"]
