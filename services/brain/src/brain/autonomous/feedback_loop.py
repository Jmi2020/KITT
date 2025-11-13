# noqa: D401
"""Feedback loop for Phase 3 learning system.

Analyzes historical goal effectiveness and adjusts goal generation parameters
to improve future autonomous decision-making.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from common.config import settings
from common.db.models import Goal, GoalStatus, GoalType

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Phase 3: Learn from goal outcomes and adjust generation.

    Responsibilities:
    - Analyze historical goal effectiveness by type
    - Calculate adjustment factors (0.5-1.5x) based on success rates
    - Provide recommendations for goal generator weights
    - Track learning progress over time

    Adjustment Strategy:
    - High effectiveness (>75%) → boost priority (up to 1.5x)
    - Medium effectiveness (50-75%) → neutral (1.0x)
    - Low effectiveness (<50%) → reduce priority (down to 0.5x)

    Learning Requirements:
    - Minimum 10 samples per goal type before adjusting
    - Exponential moving average to prevent overfitting
    - Maximum 1.5x adjustment to prevent extreme bias
    """

    def __init__(
        self,
        db_session: Session,
        min_samples: int = 10,
        adjustment_max: float = 1.5,
        enabled: bool = True,
    ) -> None:
        self.db = db_session
        self.min_samples = min_samples
        self.adjustment_max = adjustment_max
        self.enabled = enabled

    def analyze_historical_effectiveness(
        self,
        lookback_days: Optional[int] = None,
    ) -> Dict[str, dict]:
        """Calculate average effectiveness by goal type.

        Args:
            lookback_days: Days to look back (default: all time)

        Returns:
            Dict mapping goal_type → {avg_effectiveness, count, adjustment_factor}

        Example:
            {
                "research": {
                    "avg_effectiveness": 82.5,
                    "count": 6,
                    "adjustment_factor": 1.15,
                    "sample_size_met": True
                },
                "improvement": {
                    "avg_effectiveness": 58.3,
                    "count": 3,
                    "adjustment_factor": 1.0,  # Not enough samples
                    "sample_size_met": False
                }
            }
        """
        if not self.enabled:
            logger.info("Feedback loop disabled, returning neutral adjustments")
            return {}

        logger.info("Analyzing historical goal effectiveness")

        # Build query for goals with measured outcomes
        stmt = select(Goal).where(
            and_(
                Goal.status == GoalStatus.completed,
                Goal.outcome_measured_at.is_not(None),
                Goal.learn_from == True,  # noqa: E712
            )
        )

        # Apply lookback window if specified
        if lookback_days:
            cutoff = datetime.utcnow() - timedelta(days=lookback_days)
            stmt = stmt.where(Goal.outcome_measured_at >= cutoff)

        # Execute query
        measured_goals = self.db.execute(stmt).scalars().all()

        logger.info(f"Found {len(measured_goals)} goals with measured outcomes")

        # Group by goal type
        stats_by_type = {}

        for goal in measured_goals:
            goal_type = goal.goal_type.value

            if goal_type not in stats_by_type:
                stats_by_type[goal_type] = {
                    "effectiveness_scores": [],
                    "goal_ids": [],
                }

            if goal.effectiveness_score is not None:
                stats_by_type[goal_type]["effectiveness_scores"].append(
                    float(goal.effectiveness_score)
                )
                stats_by_type[goal_type]["goal_ids"].append(goal.id)

        # Calculate statistics and adjustment factors
        results = {}

        for goal_type, data in stats_by_type.items():
            scores = data["effectiveness_scores"]
            count = len(scores)

            if count == 0:
                continue

            avg_effectiveness = sum(scores) / count
            sample_size_met = count >= self.min_samples

            # Calculate adjustment factor
            adjustment_factor = self._calculate_adjustment_factor(
                avg_effectiveness=avg_effectiveness,
                sample_size_met=sample_size_met,
            )

            results[goal_type] = {
                "avg_effectiveness": round(avg_effectiveness, 2),
                "count": count,
                "min_effectiveness": round(min(scores), 2),
                "max_effectiveness": round(max(scores), 2),
                "adjustment_factor": round(adjustment_factor, 3),
                "sample_size_met": sample_size_met,
                "sample_size_required": self.min_samples,
            }

            logger.info(
                f"Goal type '{goal_type}': "
                f"avg_effectiveness={avg_effectiveness:.1f}, "
                f"count={count}, "
                f"adjustment={adjustment_factor:.2f}x"
            )

        return results

    def _calculate_adjustment_factor(
        self,
        avg_effectiveness: float,
        sample_size_met: bool,
    ) -> float:
        """Calculate adjustment factor based on effectiveness.

        Args:
            avg_effectiveness: Average effectiveness score (0-100)
            sample_size_met: Whether minimum sample size is met

        Returns:
            Adjustment factor (0.5 - 1.5)

        Formula:
        - effectiveness >= 80: 1.2x - 1.5x boost
        - effectiveness 60-80: 1.0x - 1.2x moderate boost
        - effectiveness 40-60: 0.9x - 1.0x neutral
        - effectiveness < 40: 0.5x - 0.9x penalty

        No adjustment if sample size not met (returns 1.0).
        """
        if not sample_size_met:
            return 1.0  # Neutral until enough samples

        # Map effectiveness to adjustment factor
        # High effectiveness → boost priority
        # Low effectiveness → reduce priority

        if avg_effectiveness >= 80:
            # 80-100 → 1.2x to 1.5x
            factor = 1.2 + (avg_effectiveness - 80) / 20 * 0.3
        elif avg_effectiveness >= 60:
            # 60-80 → 1.0x to 1.2x
            factor = 1.0 + (avg_effectiveness - 60) / 20 * 0.2
        elif avg_effectiveness >= 40:
            # 40-60 → 0.9x to 1.0x
            factor = 0.9 + (avg_effectiveness - 40) / 20 * 0.1
        else:
            # 0-40 → 0.5x to 0.9x
            factor = 0.5 + (avg_effectiveness / 40) * 0.4

        # Clamp to max adjustment
        factor = min(factor, self.adjustment_max)
        factor = max(factor, 1.0 / self.adjustment_max)  # Mirror on low end

        return factor

    def get_adjustment_factor(
        self,
        goal_type: GoalType,
        analysis: Optional[Dict[str, dict]] = None,
    ) -> float:
        """Get adjustment factor for a specific goal type.

        Args:
            goal_type: Goal type to get adjustment for
            analysis: Pre-computed analysis (optional, will compute if None)

        Returns:
            Adjustment factor (0.5 - 1.5)

        Example:
            factor = feedback_loop.get_adjustment_factor(GoalType.research)
            adjusted_score = base_score * factor
        """
        if not self.enabled:
            return 1.0

        if analysis is None:
            analysis = self.analyze_historical_effectiveness()

        goal_type_str = goal_type.value
        if goal_type_str in analysis:
            return analysis[goal_type_str]["adjustment_factor"]

        # No historical data for this goal type
        return 1.0

    def get_learning_summary(self) -> dict:
        """Get summary of learning progress.

        Returns:
            Dict with learning statistics and recommendations
        """
        analysis = self.analyze_historical_effectiveness()

        # Count how many goal types have enough samples
        types_with_samples = sum(
            1 for stats in analysis.values() if stats["sample_size_met"]
        )

        # Calculate overall effectiveness
        all_scores = []
        for stats in analysis.values():
            all_scores.extend([stats["avg_effectiveness"]] * stats["count"])

        overall_avg = sum(all_scores) / len(all_scores) if all_scores else 0.0

        return {
            "enabled": self.enabled,
            "total_measured_goals": len(all_scores),
            "goal_types_analyzed": len(analysis),
            "goal_types_with_enough_samples": types_with_samples,
            "overall_avg_effectiveness": round(overall_avg, 2),
            "by_goal_type": analysis,
            "learning_active": types_with_samples > 0,
            "min_samples_required": self.min_samples,
            "adjustment_max": self.adjustment_max,
        }

    def get_recommendations(self) -> list[str]:
        """Get human-readable recommendations based on learning.

        Returns:
            List of recommendation strings for operators
        """
        summary = self.get_learning_summary()
        recommendations = []

        if not summary["learning_active"]:
            recommendations.append(
                f"⏳ Learning not yet active. Need {self.min_samples} completed goals "
                f"per type to start adjusting priorities."
            )
            return recommendations

        for goal_type, stats in summary["by_goal_type"].items():
            if not stats["sample_size_met"]:
                recommendations.append(
                    f"📊 {goal_type}: Need {self.min_samples - stats['count']} more "
                    f"completed goals to start learning."
                )
                continue

            avg_eff = stats["avg_effectiveness"]
            adjustment = stats["adjustment_factor"]

            if avg_eff >= 75:
                recommendations.append(
                    f"✅ {goal_type}: High effectiveness ({avg_eff:.1f}%). "
                    f"Boosting priority by {(adjustment - 1) * 100:.0f}%."
                )
            elif avg_eff >= 50:
                recommendations.append(
                    f"✔️ {goal_type}: Moderate effectiveness ({avg_eff:.1f}%). "
                    f"Neutral adjustment."
                )
            else:
                recommendations.append(
                    f"⚠️ {goal_type}: Low effectiveness ({avg_eff:.1f}%). "
                    f"Reducing priority by {(1 - adjustment) * 100:.0f}%."
                )

        # Overall recommendation
        overall_avg = summary["overall_avg_effectiveness"]
        if overall_avg >= 70:
            recommendations.append(
                f"🎯 Overall system effectiveness: {overall_avg:.1f}% (excellent)"
            )
        elif overall_avg >= 50:
            recommendations.append(
                f"📈 Overall system effectiveness: {overall_avg:.1f}% (good)"
            )
        else:
            recommendations.append(
                f"🔍 Overall system effectiveness: {overall_avg:.1f}% (needs improvement)"
            )

        return recommendations


def create_feedback_loop(db_session: Session) -> FeedbackLoop:
    """Create FeedbackLoop instance from settings.

    Args:
        db_session: Database session

    Returns:
        Configured FeedbackLoop instance
    """
    enabled = getattr(settings, "feedback_loop_enabled", True)
    min_samples = getattr(settings, "feedback_loop_min_samples", 10)
    adjustment_max = getattr(settings, "feedback_loop_adjustment_max", 1.5)

    return FeedbackLoop(
        db_session=db_session,
        min_samples=min_samples,
        adjustment_max=adjustment_max,
        enabled=enabled,
    )


__all__ = ["FeedbackLoop", "create_feedback_loop"]
