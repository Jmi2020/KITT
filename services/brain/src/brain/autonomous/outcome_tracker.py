# noqa: D401
"""Outcome tracker for Phase 3 learning and effectiveness measurement."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from common.db.models import Goal, GoalOutcome, GoalStatus, GoalType, Project, Task

logger = logging.getLogger(__name__)


class BaselineMetrics:
    """Baseline metrics captured before goal execution."""

    def __init__(self, goal_type: GoalType, metrics: Dict[str, Any]) -> None:
        self.goal_type = goal_type
        self.metrics = metrics
        self.captured_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_type": self._get_baseline_type(),
            "captured_at": self.captured_at.isoformat(),
            **self.metrics,
        }

    def _get_baseline_type(self) -> str:
        """Get baseline type based on goal type."""
        type_map = {
            GoalType.research: "kb_gap",
            GoalType.improvement: "print_failure",
            GoalType.optimization: "cost_optimization",
        }
        return type_map.get(self.goal_type, "unknown")


class OutcomeMetrics:
    """Outcome metrics measured after goal completion."""

    def __init__(self, goal_type: GoalType, metrics: Dict[str, Any]) -> None:
        self.goal_type = goal_type
        self.metrics = metrics
        self.measured_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "measured_at": self.measured_at.isoformat(),
            **self.metrics,
        }


class EffectivenessScore:
    """Effectiveness score calculated from baseline and outcome metrics."""

    def __init__(
        self,
        impact: float,
        roi: float,
        adoption: float,
        quality: float,
    ) -> None:
        self.impact = max(0.0, min(100.0, impact))
        self.roi = max(0.0, min(100.0, roi))
        self.adoption = max(0.0, min(100.0, adoption))
        self.quality = max(0.0, min(100.0, quality))

        # Weighted average (Impact 40%, ROI 30%, Adoption 20%, Quality 10%)
        self.total = (
            self.impact * 0.40
            + self.roi * 0.30
            + self.adoption * 0.20
            + self.quality * 0.10
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "impact_score": round(self.impact, 2),
            "roi_score": round(self.roi, 2),
            "adoption_score": round(self.adoption, 2),
            "quality_score": round(self.quality, 2),
            "effectiveness_score": round(self.total, 2),
        }


class OutcomeTracker:
    """Tracks outcomes and measures effectiveness of autonomous goals.

    Phase 3: Learning "The Reflection"
    - Captures baseline metrics when goals are approved
    - Measures outcomes 30 days after completion
    - Calculates effectiveness scores (0-100)
    - Stores outcomes for feedback loop learning
    """

    def __init__(self, db_session: Session) -> None:
        self.db = db_session

    def capture_baseline(self, goal: Goal) -> BaselineMetrics:
        """Capture baseline metrics when goal is approved.

        Args:
            goal: Goal to capture baseline for

        Returns:
            BaselineMetrics with goal-type-specific metrics

        Note:
            Different goal types have different baseline metrics:
            - Research: KB gap analysis, failure counts, questions asked
            - Improvement: Current failure rate, technique usage
            - Optimization: Current costs, query counts
        """
        logger.info(f"Capturing baseline for goal {goal.id} (type: {goal.goal_type})")

        if goal.goal_type == GoalType.research:
            metrics = self._capture_research_baseline(goal)
        elif goal.goal_type == GoalType.improvement:
            metrics = self._capture_improvement_baseline(goal)
        elif goal.goal_type == GoalType.optimization:
            metrics = self._capture_optimization_baseline(goal)
        else:
            logger.warning(f"Unknown goal type: {goal.goal_type}, using generic baseline")
            metrics = self._capture_generic_baseline(goal)

        baseline = BaselineMetrics(goal.goal_type, metrics)

        # Mark goal as having baseline captured
        goal.baseline_captured = True
        goal.baseline_captured_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Baseline captured for goal {goal.id}: {len(metrics)} metrics")
        return baseline

    def _capture_research_baseline(self, goal: Goal) -> Dict[str, Any]:
        """Capture baseline metrics for research goals.

        Metrics:
        - related_failures: Count of failures related to research topic
        - questions_asked: Count of questions/issues related to topic
        - manual_research_time_hours: Estimated time spent on manual research
        - material_usage_count: Current usage count (if material research)
        """
        # Extract topic from goal description (simple keyword extraction)
        topic_keywords = self._extract_keywords(goal.description)

        # Count related failures in last 90 days (rough approximation)
        # In production, this would query actual failure logs
        related_failures = self._estimate_related_failures(topic_keywords)

        # Estimate questions/issues
        questions_asked = self._estimate_related_questions(topic_keywords)

        return {
            "related_failures": related_failures,
            "questions_asked": questions_asked,
            "manual_research_time_hours": 4.5,  # Default estimate
            "material_usage_count": 0,  # Will be updated if material research
            "topic_keywords": topic_keywords,
        }

    def _capture_improvement_baseline(self, goal: Goal) -> Dict[str, Any]:
        """Capture baseline metrics for improvement goals.

        Metrics:
        - failure_count_30d: Failure count in last 30 days
        - failure_rate: Failure rate as percentage
        - technique_usage: Times technique has been referenced
        """
        # Extract technique/area from goal description
        technique = self._extract_technique(goal.description)

        # Query actual failure data (simplified for now)
        failure_count = self._get_recent_failure_count(technique, days=30)
        total_prints = self._get_recent_print_count(days=30)
        failure_rate = (failure_count / total_prints * 100) if total_prints > 0 else 0.0

        return {
            "failure_count_30d": failure_count,
            "failure_rate": round(failure_rate, 2),
            "technique_usage": 8,  # Default estimate
            "technique": technique,
            "total_prints": total_prints,
        }

    def _capture_optimization_baseline(self, goal: Goal) -> Dict[str, Any]:
        """Capture baseline metrics for optimization goals.

        Metrics:
        - frontier_cost_30d: Frontier API costs in last 30 days
        - local_cost_30d: Local inference costs in last 30 days
        - total_queries: Total query count
        """
        # Query actual routing costs (simplified)
        frontier_cost = self._get_recent_frontier_cost(days=30)
        local_cost = self._get_recent_local_cost(days=30)
        total_queries = self._get_recent_query_count(days=30)

        return {
            "frontier_cost_30d": round(frontier_cost, 2),
            "local_cost_30d": round(local_cost, 2),
            "total_queries": total_queries,
            "optimization_target": self._extract_optimization_target(goal.description),
        }

    def _capture_generic_baseline(self, goal: Goal) -> Dict[str, Any]:
        """Capture generic baseline metrics for unknown goal types."""
        return {
            "goal_description": goal.description,
            "estimated_budget": float(goal.estimated_budget),
            "captured_at": datetime.utcnow().isoformat(),
        }

    def measure_outcome(self, goal: Goal) -> OutcomeMetrics:
        """Measure outcome metrics 30 days after goal completion.

        Args:
            goal: Completed goal to measure outcome for

        Returns:
            OutcomeMetrics with goal-type-specific outcome data

        Note:
            Should be called 30 days after goal completion.
            Uses baseline metrics for comparison.
        """
        logger.info(f"Measuring outcome for goal {goal.id} (type: {goal.goal_type})")

        # Verify goal has baseline
        if not goal.baseline_captured:
            logger.warning(f"Goal {goal.id} has no baseline, capturing now")
            self.capture_baseline(goal)

        if goal.goal_type == GoalType.research:
            metrics = self._measure_research_outcome(goal)
        elif goal.goal_type == GoalType.improvement:
            metrics = self._measure_improvement_outcome(goal)
        elif goal.goal_type == GoalType.optimization:
            metrics = self._measure_optimization_outcome(goal)
        else:
            logger.warning(f"Unknown goal type: {goal.goal_type}, using generic outcome")
            metrics = self._measure_generic_outcome(goal)

        outcome = OutcomeMetrics(goal.goal_type, metrics)

        logger.info(f"Outcome measured for goal {goal.id}: {len(metrics)} metrics")
        return outcome

    def _measure_research_outcome(self, goal: Goal) -> Dict[str, Any]:
        """Measure outcome metrics for research goals.

        Metrics:
        - kb_article_views: View count of created KB article
        - kb_article_references: Reference count in other articles
        - related_failures_after: Failure count after KB article
        - questions_answered: Questions answered via KB
        - estimated_time_saved_hours: Estimated time saved by KB
        - material_usage_count: Material usage (if applicable)
        """
        # Find KB article created by this goal's project
        kb_article_path = self._find_kb_article_for_goal(goal)

        if kb_article_path:
            views = self._get_kb_article_views(kb_article_path)
            references = self._get_kb_article_references(kb_article_path)
        else:
            logger.warning(f"No KB article found for goal {goal.id}")
            views = 0
            references = 0

        # Measure post-completion failures
        topic_keywords = self._extract_keywords(goal.description)
        failures_after = self._estimate_related_failures(topic_keywords, days=30)

        # Estimate time saved (conservative)
        time_saved = (views * 0.5) + (references * 2.0)  # 30min per view, 2hr per reference

        return {
            "kb_article_views": views,
            "kb_article_references": references,
            "related_failures_after": failures_after,
            "questions_answered": max(0, views - 5),  # Estimate self-service
            "estimated_time_saved_hours": round(time_saved, 2),
            "material_usage_count": self._get_material_usage(topic_keywords),
            "kb_article_path": kb_article_path or "none",
        }

    def _measure_improvement_outcome(self, goal: Goal) -> Dict[str, Any]:
        """Measure outcome metrics for improvement goals.

        Metrics:
        - failure_count_30d: Failure count in last 30 days
        - failure_rate: Current failure rate
        - failure_reduction_pct: Percentage reduction from baseline
        - technique_usage: Current technique usage count
        - user_feedback: Qualitative feedback (if available)
        """
        technique = self._extract_technique(goal.description)

        # Query current failure data
        failure_count = self._get_recent_failure_count(technique, days=30)
        total_prints = self._get_recent_print_count(days=30)
        failure_rate = (failure_count / total_prints * 100) if total_prints > 0 else 0.0

        # Calculate reduction (requires baseline)
        baseline_failures = 12  # Default, should be from actual baseline
        failure_reduction = ((baseline_failures - failure_count) / baseline_failures * 100) if baseline_failures > 0 else 0.0

        return {
            "failure_count_30d": failure_count,
            "failure_rate": round(failure_rate, 2),
            "failure_reduction_pct": round(max(0, failure_reduction), 2),
            "technique_usage": 24,  # Default estimate, should query actual usage
            "user_feedback": "positive",  # Default
        }

    def _measure_optimization_outcome(self, goal: Goal) -> Dict[str, Any]:
        """Measure outcome metrics for optimization goals.

        Metrics:
        - frontier_cost_30d: Current frontier costs
        - local_cost_30d: Current local costs
        - cost_savings_usd: Total cost savings
        - total_queries: Current query count
        - performance_degradation_pct: Performance impact
        """
        # Query current costs
        frontier_cost = self._get_recent_frontier_cost(days=30)
        local_cost = self._get_recent_local_cost(days=30)
        total_queries = self._get_recent_query_count(days=30)

        # Calculate savings (requires baseline)
        baseline_frontier = 45.00  # Default, should be from actual baseline
        cost_savings = max(0, baseline_frontier - frontier_cost)

        return {
            "frontier_cost_30d": round(frontier_cost, 2),
            "local_cost_30d": round(local_cost, 2),
            "cost_savings_usd": round(cost_savings, 2),
            "total_queries": total_queries,
            "performance_degradation_pct": 2,  # Default estimate
        }

    def _measure_generic_outcome(self, goal: Goal) -> Dict[str, Any]:
        """Measure generic outcome metrics for unknown goal types."""
        return {
            "goal_completed": True,
            "completion_date": goal.completed_at.isoformat() if goal.completed_at else None,
            "measured_at": datetime.utcnow().isoformat(),
        }

    def calculate_effectiveness(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
    ) -> EffectivenessScore:
        """Calculate effectiveness score from baseline and outcome metrics.

        Args:
            goal: Goal being measured
            baseline: Baseline metrics
            outcome: Outcome metrics

        Returns:
            EffectivenessScore with component scores and total

        Formula:
            effectiveness = (impact * 0.40) + (roi * 0.30) + (adoption * 0.20) + (quality * 0.10)

        Note:
            Different goal types use different calculation strategies.
        """
        logger.info(f"Calculating effectiveness for goal {goal.id} (type: {goal.goal_type})")

        if goal.goal_type == GoalType.research:
            score = self._calculate_research_effectiveness(goal, baseline, outcome)
        elif goal.goal_type == GoalType.improvement:
            score = self._calculate_improvement_effectiveness(goal, baseline, outcome)
        elif goal.goal_type == GoalType.optimization:
            score = self._calculate_optimization_effectiveness(goal, baseline, outcome)
        else:
            logger.warning(f"Unknown goal type: {goal.goal_type}, using generic scoring")
            score = self._calculate_generic_effectiveness(goal, baseline, outcome)

        logger.info(
            f"Effectiveness for goal {goal.id}: "
            f"impact={score.impact:.1f}, roi={score.roi:.1f}, "
            f"adoption={score.adoption:.1f}, quality={score.quality:.1f}, "
            f"total={score.total:.1f}"
        )

        return score

    def _calculate_research_effectiveness(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
    ) -> EffectivenessScore:
        """Calculate effectiveness for research goals.

        Impact: Failure reduction percentage
        ROI: (Time saved * $50/hr) / cost
        Adoption: KB views + (references * 5)
        Quality: Article quality check (grammar, completeness, citations)
        """
        baseline_metrics = baseline.metrics
        outcome_metrics = outcome.metrics

        # Impact: Failure reduction
        baseline_failures = baseline_metrics.get("related_failures", 10)
        outcome_failures = outcome_metrics.get("related_failures_after", 5)
        impact = ((baseline_failures - outcome_failures) / baseline_failures * 100) if baseline_failures > 0 else 0.0

        # ROI: Time saved / cost
        time_saved = outcome_metrics.get("estimated_time_saved_hours", 0)
        cost_usd = self._get_goal_actual_cost(goal)
        roi_value = (time_saved * 50.0) / cost_usd if cost_usd > 0 else 0.0
        roi = min(roi_value * 10, 100)  # Scale to 0-100

        # Adoption: Usage metrics
        views = outcome_metrics.get("kb_article_views", 0)
        references = outcome_metrics.get("kb_article_references", 0)
        adoption = min((views + references * 5) / 50 * 100, 100)

        # Quality: Default 80 for now (could check article quality)
        quality = 80.0

        return EffectivenessScore(
            impact=impact,
            roi=roi,
            adoption=adoption,
            quality=quality,
        )

    def _calculate_improvement_effectiveness(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
    ) -> EffectivenessScore:
        """Calculate effectiveness for improvement goals.

        Impact: Failure reduction percentage
        ROI: (Failures prevented * $10) / cost
        Adoption: Technique usage increase
        Quality: Default 80 (hard to measure)
        """
        baseline_metrics = baseline.metrics
        outcome_metrics = outcome.metrics

        # Impact: Direct failure reduction
        impact = outcome_metrics.get("failure_reduction_pct", 0.0)

        # ROI: Failures prevented value
        baseline_failures = baseline_metrics.get("failure_count_30d", 12)
        outcome_failures = outcome_metrics.get("failure_count_30d", 3)
        failures_prevented = max(0, baseline_failures - outcome_failures)
        cost_usd = self._get_goal_actual_cost(goal)
        roi_value = (failures_prevented * 10.0) / cost_usd if cost_usd > 0 else 0.0
        roi = min(roi_value * 10, 100)

        # Adoption: Technique usage increase
        baseline_usage = baseline_metrics.get("technique_usage", 8)
        outcome_usage = outcome_metrics.get("technique_usage", 24)
        usage_increase = ((outcome_usage - baseline_usage) / baseline_usage * 100) if baseline_usage > 0 else 0.0
        adoption = min(usage_increase, 100)

        # Quality: Default
        quality = 80.0

        return EffectivenessScore(
            impact=impact,
            roi=roi,
            adoption=adoption,
            quality=quality,
        )

    def _calculate_optimization_effectiveness(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
    ) -> EffectivenessScore:
        """Calculate effectiveness for optimization goals.

        Impact: Cost reduction percentage
        ROI: Savings / optimization cost
        Adoption: Binary (works or doesn't based on performance)
        Quality: 100 - performance_degradation_pct
        """
        baseline_metrics = baseline.metrics
        outcome_metrics = outcome.metrics

        # Impact: Cost reduction
        baseline_cost = baseline_metrics.get("frontier_cost_30d", 45.0)
        outcome_cost = outcome_metrics.get("frontier_cost_30d", 12.0)
        cost_reduction = ((baseline_cost - outcome_cost) / baseline_cost * 100) if baseline_cost > 0 else 0.0
        impact = cost_reduction

        # ROI: Savings / cost
        savings = outcome_metrics.get("cost_savings_usd", 33.0)
        cost_usd = self._get_goal_actual_cost(goal)
        roi_value = (savings / cost_usd) if cost_usd > 0 else 0.0
        roi = min(roi_value * 10, 100)

        # Adoption: Binary based on performance
        perf_degradation = outcome_metrics.get("performance_degradation_pct", 2)
        adoption = 100.0 if perf_degradation < 5 else 50.0

        # Quality: Inverse of performance degradation
        quality = max(0, 100 - perf_degradation)

        return EffectivenessScore(
            impact=impact,
            roi=roi,
            adoption=adoption,
            quality=quality,
        )

    def _calculate_generic_effectiveness(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
    ) -> EffectivenessScore:
        """Calculate generic effectiveness for unknown goal types."""
        # Default moderate scores
        return EffectivenessScore(
            impact=50.0,
            roi=50.0,
            adoption=50.0,
            quality=50.0,
        )

    def store_outcome(
        self,
        goal: Goal,
        baseline: BaselineMetrics,
        outcome: OutcomeMetrics,
        effectiveness: EffectivenessScore,
    ) -> GoalOutcome:
        """Store outcome in database.

        Args:
            goal: Goal being measured
            baseline: Baseline metrics
            outcome: Outcome metrics
            effectiveness: Calculated effectiveness score

        Returns:
            Created GoalOutcome record
        """
        logger.info(f"Storing outcome for goal {goal.id}")

        # Create or update outcome record
        outcome_record = self.db.execute(
            select(GoalOutcome).where(GoalOutcome.goal_id == goal.id)
        ).scalar_one_or_none()

        if outcome_record:
            logger.info(f"Updating existing outcome record for goal {goal.id}")
            outcome_record.baseline_date = baseline.captured_at
            outcome_record.measurement_date = outcome.measured_at
            outcome_record.baseline_metrics = baseline.to_dict()
            outcome_record.outcome_metrics = outcome.to_dict()
            outcome_record.impact_score = effectiveness.impact
            outcome_record.roi_score = effectiveness.roi
            outcome_record.adoption_score = effectiveness.adoption
            outcome_record.quality_score = effectiveness.quality
            outcome_record.effectiveness_score = effectiveness.total
            outcome_record.measured_at = datetime.utcnow()
        else:
            logger.info(f"Creating new outcome record for goal {goal.id}")
            outcome_record = GoalOutcome(
                id=f"outcome_{goal.id}",
                goal_id=goal.id,
                baseline_date=baseline.captured_at,
                measurement_date=outcome.measured_at,
                baseline_metrics=baseline.to_dict(),
                outcome_metrics=outcome.to_dict(),
                impact_score=effectiveness.impact,
                roi_score=effectiveness.roi,
                adoption_score=effectiveness.adoption,
                quality_score=effectiveness.quality,
                effectiveness_score=effectiveness.total,
                measurement_method=self._get_measurement_method(goal.goal_type),
                measured_at=datetime.utcnow(),
                measured_by="system-autonomous",
            )
            self.db.add(outcome_record)

        # Update goal with effectiveness score
        goal.effectiveness_score = effectiveness.total
        goal.outcome_measured_at = datetime.utcnow()

        self.db.commit()

        logger.info(
            f"Outcome stored for goal {goal.id}: "
            f"effectiveness={effectiveness.total:.1f}"
        )

        return outcome_record

    def _get_measurement_method(self, goal_type: GoalType) -> str:
        """Get measurement method name based on goal type."""
        method_map = {
            GoalType.research: "kb_usage",
            GoalType.improvement: "failure_rate",
            GoalType.optimization: "cost_savings",
        }
        return method_map.get(goal_type, "generic")

    # Helper methods for metric collection (simplified implementations)

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract keywords from text (simplified)."""
        # In production, use NLP/LLM for better extraction
        words = text.lower().split()
        # Filter common words
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        keywords = [w for w in words if w not in stopwords and len(w) > 3]
        return keywords[:5]  # Top 5 keywords

    def _extract_technique(self, text: str) -> str:
        """Extract technique name from text (simplified)."""
        # In production, use NLP/LLM for better extraction
        return self._extract_keywords(text)[0] if self._extract_keywords(text) else "unknown"

    def _extract_optimization_target(self, text: str) -> str:
        """Extract optimization target from text."""
        if "cost" in text.lower():
            return "cost_reduction"
        elif "performance" in text.lower():
            return "performance_improvement"
        else:
            return "general_optimization"

    def _estimate_related_failures(self, keywords: list[str], days: int = 90) -> int:
        """Estimate failures related to keywords (simplified)."""
        # In production, query actual failure logs
        return 8  # Default estimate

    def _estimate_related_questions(self, keywords: list[str]) -> int:
        """Estimate questions related to keywords (simplified)."""
        # In production, query actual support/question logs
        return 15  # Default estimate

    def _get_recent_failure_count(self, technique: str, days: int = 30) -> int:
        """Get recent failure count (simplified)."""
        # In production, query actual fabrication failure logs
        return 3  # Default estimate

    def _get_recent_print_count(self, days: int = 30) -> int:
        """Get recent print count (simplified)."""
        # In production, query actual fabrication job logs
        return 50  # Default estimate

    def _get_recent_frontier_cost(self, days: int = 30) -> float:
        """Get recent frontier API costs (simplified)."""
        # In production, query actual routing_decisions table
        cutoff = datetime.utcnow() - timedelta(days=days)
        # This would query routing_decisions where tier='frontier'
        return 12.00  # Default estimate

    def _get_recent_local_cost(self, days: int = 30) -> float:
        """Get recent local inference costs (simplified)."""
        # In production, calculate from GPU time
        return 5.50  # Default estimate

    def _get_recent_query_count(self, days: int = 30) -> int:
        """Get recent query count (simplified)."""
        # In production, query routing_decisions table
        return 1300  # Default estimate

    def _find_kb_article_for_goal(self, goal: Goal) -> Optional[str]:
        """Find KB article created by goal's project (simplified)."""
        # In production, query project artifacts
        # For now, construct expected path
        if goal.projects:
            project = goal.projects[0]
            return f"Knowledge/{project.name}.md"
        return None

    def _get_kb_article_views(self, article_path: str) -> int:
        """Get KB article view count (simplified)."""
        # In production, query actual KB usage logs
        return 23  # Default estimate

    def _get_kb_article_references(self, article_path: str) -> int:
        """Get KB article reference count (simplified)."""
        # In production, search for references in other KB articles
        return 5  # Default estimate

    def _get_material_usage(self, keywords: list[str]) -> int:
        """Get material usage count (simplified)."""
        # In production, query fabrication material logs
        return 18  # Default estimate

    def _get_goal_actual_cost(self, goal: Goal) -> float:
        """Get actual cost of goal execution.

        Sums actual costs from all projects associated with goal.
        Falls back to estimated budget if actual costs not available.
        """
        if not goal.projects:
            return float(goal.estimated_budget)

        total_cost = 0.0
        for project in goal.projects:
            if project.actual_cost_usd:
                total_cost += float(project.actual_cost_usd)
            else:
                # Fallback to estimated budget portion
                total_cost += float(goal.estimated_budget) / len(goal.projects)

        return max(total_cost, 0.01)  # Minimum $0.01 to avoid division by zero


__all__ = ["OutcomeTracker", "BaselineMetrics", "OutcomeMetrics", "EffectivenessScore"]
