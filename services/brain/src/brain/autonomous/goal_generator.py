"""Goal generator for autonomous opportunity detection.

Analyzes fabrication history, knowledge gaps, and system patterns to identify
high-impact goals for KITTY's autonomous work cycles.
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from common.db.models import (
    Goal,
    GoalType,
    GoalStatus,
    FabricationJob,
    FabricationStatus,
    RoutingDecision,
)
from common.db import SessionLocal

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger()


class OpportunityScore:
    """Impact scoring for autonomous goal prioritization."""

    def __init__(
        self,
        *,
        frequency: float = 0.0,
        severity: float = 0.0,
        cost_savings: float = 0.0,
        knowledge_gap: float = 0.0,
        strategic_value: float = 0.0,
    ):
        """Initialize opportunity score components.

        Args:
            frequency: How often the issue occurs (0.0-1.0)
            severity: Impact severity when it occurs (0.0-1.0)
            cost_savings: Potential cost reduction (0.0-1.0)
            knowledge_gap: How critical the knowledge gap is (0.0-1.0)
            strategic_value: Long-term strategic importance (0.0-1.0)
        """
        self.frequency = frequency
        self.severity = severity
        self.cost_savings = cost_savings
        self.knowledge_gap = knowledge_gap
        self.strategic_value = strategic_value

    @property
    def total_score(self) -> float:
        """Calculate weighted total score (0.0-100.0).

        Weights:
        - Frequency: 20%
        - Severity: 25%
        - Cost Savings: 20%
        - Knowledge Gap: 20%
        - Strategic Value: 15%
        """
        return (
            self.frequency * 20
            + self.severity * 25
            + self.cost_savings * 20
            + self.knowledge_gap * 20
            + self.strategic_value * 15
        )

    def to_dict(self) -> Dict[str, float]:
        """Export scores as dictionary."""
        return {
            "frequency": self.frequency,
            "severity": self.severity,
            "cost_savings": self.cost_savings,
            "knowledge_gap": self.knowledge_gap,
            "strategic_value": self.strategic_value,
            "total_score": self.total_score,
        }


class GoalGenerator:
    """Generates autonomous goals from fabrication history and system patterns.

    Phase 3: Integrates feedback loop to learn from historical effectiveness
    and adjust goal generation priorities based on outcome measurements.
    """

    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        lookback_days: int = 30,
        min_failure_count: int = 3,
        min_impact_score: float = 50.0,
        feedback_loop=None,
    ):
        """Initialize goal generator.

        Args:
            session_factory: SQLAlchemy session factory
            lookback_days: Days of history to analyze for patterns
            min_failure_count: Minimum failures before suggesting improvement
            min_impact_score: Minimum total score to create goal (0-100)
            feedback_loop: Optional FeedbackLoop for Phase 3 learning
        """
        self._session_factory = session_factory
        self.lookback_days = lookback_days
        self.min_failure_count = min_failure_count
        self.min_impact_score = min_impact_score
        self.feedback_loop = feedback_loop

    def generate_goals(self, max_goals: int = 5) -> List[Goal]:
        """Generate high-impact autonomous goals.

        Analyzes:
        1. Print failure patterns (first_layer, spaghetti, warping)
        2. Knowledge base gaps (missing materials, techniques)
        3. High-cost routing patterns (excessive cloud usage)
        4. Underutilized equipment

        Args:
            max_goals: Maximum number of goals to generate

        Returns:
            List of Goal objects (unsaved, status=identified)
        """
        struct_logger.info("goal_generation_started", max_goals=max_goals)

        with self._session_factory() as session:
            goals: List[Goal] = []

            # 1. Detect print failure patterns
            failure_goals = self._detect_print_failures(session)
            goals.extend(failure_goals)

            # 2. Identify knowledge gaps
            knowledge_goals = self._detect_knowledge_gaps(session)
            goals.extend(knowledge_goals)

            # 3. Analyze routing cost patterns
            cost_goals = self._detect_cost_opportunities(session)
            goals.extend(cost_goals)

            # Calculate impact scores with feedback loop adjustment
            goals_with_scores = []
            for goal in goals:
                base_score = self._calculate_impact_score(goal, session)

                # Phase 3: Apply feedback loop adjustment
                adjustment_factor = 1.0
                if self.feedback_loop:
                    adjustment_factor = self.feedback_loop.get_adjustment_factor(
                        goal.goal_type
                    )

                adjusted_score = base_score.total_score * adjustment_factor

                # Store both scores in goal metadata for transparency
                if goal.goal_metadata is None:
                    goal.goal_metadata = {}
                goal.goal_metadata["base_impact_score"] = round(base_score.total_score, 2)
                goal.goal_metadata["adjustment_factor"] = round(adjustment_factor, 3)
                goal.goal_metadata["adjusted_impact_score"] = round(adjusted_score, 2)

                goals_with_scores.append((goal, base_score, adjusted_score))

            # Sort by adjusted score and take top N
            goals_with_scores.sort(key=lambda x: x[2], reverse=True)

            # Filter by minimum score and limit
            high_impact_goals = [
                goal
                for goal, base_score, adjusted_score in goals_with_scores
                if adjusted_score >= self.min_impact_score
            ][:max_goals]

            struct_logger.info(
                "goal_generation_completed",
                total_candidates=len(goals),
                high_impact_count=len(high_impact_goals),
                top_scores=[
                    {"base": round(base_score.total_score, 2), "adjusted": round(adjusted, 2)}
                    for _, base_score, adjusted in goals_with_scores[:max_goals]
                ],
                feedback_loop_active=self.feedback_loop is not None,
            )

            return high_impact_goals

    def _detect_print_failures(self, session: Session) -> List[Goal]:
        """Detect recurring print failure patterns.

        Looks for:
        - First layer adhesion failures
        - Spaghetti detection (nozzle clogs)
        - Warping issues
        - Material-specific failures

        Returns:
            List of Goal objects for failure remediation
        """
        goals: List[Goal] = []
        cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)

        # Query failed fabrication jobs
        stmt = (
            select(FabricationJob)
            .where(
                and_(
                    FabricationJob.status == FabricationStatus.failed,
                    FabricationJob.created_at >= cutoff_date,
                )
            )
        )

        failed_jobs = session.execute(stmt).scalars().all()

        if len(failed_jobs) < self.min_failure_count:
            logger.debug(
                f"Not enough failures to analyze ({len(failed_jobs)} < {self.min_failure_count})"
            )
            return goals

        # Group failures by failure_reason (if stored in metadata)
        failure_patterns: Dict[str, int] = {}
        for job in failed_jobs:
            reason = job.job_metadata.get("failure_reason", "unknown")
            failure_patterns[reason] = failure_patterns.get(reason, 0) + 1

        # Generate goals for top failure patterns
        for reason, count in sorted(
            failure_patterns.items(), key=lambda x: x[1], reverse=True
        ):
            if count >= self.min_failure_count:
                goal = Goal(
                    id=str(uuid.uuid4()),
                    goal_type=GoalType.improvement,
                    description=f"Reduce {reason} failures in 3D printing",
                    rationale=(
                        f"Observed {count} failures due to '{reason}' in the past {self.lookback_days} days. "
                        f"Research and document best practices to reduce failure rate."
                    ),
                    estimated_budget=Decimal("2.50"),
                    estimated_duration_hours=4,
                    status=GoalStatus.identified,
                    identified_at=datetime.utcnow(),
                    goal_metadata={
                        "source": "print_failure_analysis",
                        "failure_reason": reason,
                        "failure_count": count,
                        "lookback_days": self.lookback_days,
                    },
                )
                goals.append(goal)

        return goals

    def _detect_knowledge_gaps(self, session: Session) -> List[Goal]:
        """Identify gaps in knowledge base.

        Checks:
        - Missing material documentation for used filaments
        - Technique guides needed for common issues
        - Equipment documentation completeness

        Returns:
            List of Goal objects for knowledge base expansion
        """
        goals: List[Goal] = []

        # Import knowledge updater to check current KB
        from ..knowledge.updater import KnowledgeUpdater

        kb_updater = KnowledgeUpdater()
        materials = set(kb_updater.list_materials())

        # Check if common materials are missing
        common_materials = {"pla", "petg", "abs", "tpu", "asa", "nylon", "pc"}
        missing_materials = common_materials - materials

        if missing_materials:
            for material in list(missing_materials)[:2]:  # Top 2 missing materials
                goal = Goal(
                    id=str(uuid.uuid4()),
                    goal_type=GoalType.research,
                    description=f"Research and document {material.upper()} material properties",
                    rationale=(
                        f"Knowledge base is missing comprehensive {material.upper()} documentation. "
                        f"Research optimal print settings, suppliers, and sustainability profile."
                    ),
                    estimated_budget=Decimal("1.50"),
                    estimated_duration_hours=3,
                    status=GoalStatus.identified,
                    identified_at=datetime.utcnow(),
                    goal_metadata={
                        "source": "knowledge_gap_analysis",
                        "material": material,
                        "kb_status": "missing",
                    },
                )
                goals.append(goal)

        return goals

    def _detect_cost_opportunities(self, session: Session) -> List[Goal]:
        """Analyze routing decisions for cost optimization opportunities.

        Looks for:
        - Excessive frontier tier usage (GPT-4/Claude)
        - Prompts that could be handled locally
        - Repeated expensive queries

        Returns:
            List of Goal objects for cost optimization
        """
        goals: List[Goal] = []
        cutoff_date = datetime.utcnow() - timedelta(days=self.lookback_days)

        # Query high-cost routing decisions
        stmt = (
            select(
                RoutingDecision.tier,
                func.count(RoutingDecision.id).label("count"),
                func.sum(RoutingDecision.cost_estimate).label("total_cost"),
            )
            .where(RoutingDecision.created_at >= cutoff_date)
            .group_by(RoutingDecision.tier)
        )

        tier_stats = session.execute(stmt).all()

        # Calculate frontier tier cost
        frontier_cost = 0.0
        total_requests = 0
        for tier, count, cost in tier_stats:
            total_requests += count
            if tier == "frontier":
                frontier_cost = float(cost or 0.0)

        # If frontier tier usage is >30% of budget, suggest optimization
        frontier_ratio = frontier_cost / (sum(float(c or 0) for _, _, c in tier_stats) + 0.01)

        if frontier_ratio > 0.30 and frontier_cost > 5.0:
            goal = Goal(
                id=str(uuid.uuid4()),
                goal_type=GoalType.optimization,
                description="Optimize routing to reduce frontier tier usage",
                rationale=(
                    f"Frontier tier accounts for {frontier_ratio*100:.1f}% of routing costs "
                    f"(${frontier_cost:.2f} over {self.lookback_days} days). "
                    f"Research prompt patterns to improve local model routing."
                ),
                estimated_budget=Decimal("3.00"),
                estimated_duration_hours=6,
                status=GoalStatus.identified,
                identified_at=datetime.utcnow(),
                goal_metadata={
                    "source": "cost_optimization_analysis",
                    "frontier_cost_usd": frontier_cost,
                    "frontier_ratio": frontier_ratio,
                    "lookback_days": self.lookback_days,
                },
            )
            goals.append(goal)

        return goals

    def _calculate_impact_score(
        self, goal: Goal, session: Session
    ) -> OpportunityScore:
        """Calculate impact score for a goal.

        Args:
            goal: Goal to score
            session: Database session for additional queries

        Returns:
            OpportunityScore with weighted components
        """
        # Extract metadata
        metadata = goal.goal_metadata or {}
        source = metadata.get("source", "")

        # Initialize score components
        frequency = 0.0
        severity = 0.0
        cost_savings = 0.0
        knowledge_gap = 0.0
        strategic_value = 0.0

        # Score based on goal type and source
        if source == "print_failure_analysis":
            failure_count = metadata.get("failure_count", 0)
            # Frequency: normalize to 0-1 (10+ failures = 1.0)
            frequency = min(failure_count / 10.0, 1.0)
            # Severity: higher for more disruptive failures
            severity = 0.7  # Default high severity for failures
            # Cost savings: based on wasted material/time
            cost_savings = min(failure_count * 0.05, 1.0)
            strategic_value = 0.6

        elif source == "knowledge_gap_analysis":
            # Knowledge gaps have lower frequency but high strategic value
            frequency = 0.3
            severity = 0.4
            knowledge_gap = 0.9  # High knowledge gap score
            strategic_value = 0.8  # Important for long-term capability

        elif source == "cost_optimization_analysis":
            frontier_cost = metadata.get("frontier_cost_usd", 0)
            # Frequency: constant (ongoing cost)
            frequency = 0.8
            # Cost savings: based on potential reduction
            cost_savings = min(frontier_cost / 20.0, 1.0)
            strategic_value = 0.9  # Critical for sustainability

        return OpportunityScore(
            frequency=frequency,
            severity=severity,
            cost_savings=cost_savings,
            knowledge_gap=knowledge_gap,
            strategic_value=strategic_value,
        )

    def persist_goals(self, goals: List[Goal]) -> int:
        """Save generated goals to database.

        Args:
            goals: List of Goal objects to persist

        Returns:
            Number of goals successfully saved
        """
        with self._session_factory() as session:
            saved_count = 0
            for goal in goals:
                try:
                    session.add(goal)
                    session.commit()
                    saved_count += 1
                    struct_logger.info(
                        "goal_persisted",
                        goal_id=goal.id,
                        goal_type=goal.goal_type.value,
                        description=goal.description[:100],
                    )
                except Exception as exc:
                    logger.error(f"Failed to persist goal {goal.id}: {exc}")
                    session.rollback()

            return saved_count


__all__ = ["GoalGenerator", "OpportunityScore"]
