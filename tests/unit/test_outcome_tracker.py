"""Unit tests for Phase 3 OutcomeTracker.

Tests baseline capture, outcome measurement, and effectiveness scoring
for research, improvement, and optimization goals.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from services.brain.src.brain.autonomous.outcome_tracker import (
    OutcomeTracker,
    BaselineMetrics,
    OutcomeMetrics,
    EffectivenessScore,
)
from common.db.models import Goal, GoalType, GoalStatus, Project, GoalOutcome


@pytest.fixture
def db_session():
    """Mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def outcome_tracker(db_session):
    """Create OutcomeTracker instance."""
    return OutcomeTracker(db_session)


@pytest.fixture
def research_goal():
    """Create a research goal for testing."""
    goal = Goal(
        id="goal_research_001",
        goal_type=GoalType.research,
        description="Research and document NYLON material properties",
        rationale="KB is missing NYLON documentation",
        estimated_budget=Decimal("2.50"),
        estimated_duration_hours=4,
        status=GoalStatus.approved,
        created_by="system-autonomous",
        baseline_captured=False,
    )
    return goal


@pytest.fixture
def improvement_goal():
    """Create an improvement goal for testing."""
    goal = Goal(
        id="goal_improvement_001",
        goal_type=GoalType.improvement,
        description="Reduce first_layer failures",
        rationale="8 failures in past 30 days",
        estimated_budget=Decimal("1.50"),
        estimated_duration_hours=3,
        status=GoalStatus.approved,
        created_by="system-autonomous",
        baseline_captured=False,
        goal_metadata={"failure_reason": "first_layer", "failure_count": 8},
    )
    return goal


@pytest.fixture
def optimization_goal():
    """Create an optimization goal for testing."""
    goal = Goal(
        id="goal_optimization_001",
        goal_type=GoalType.optimization,
        description="Optimize routing to reduce frontier usage",
        rationale="Frontier tier at 35% usage, $12.50 cost",
        estimated_budget=Decimal("3.00"),
        estimated_duration_hours=6,
        status=GoalStatus.approved,
        created_by="system-autonomous",
        baseline_captured=False,
        goal_metadata={"frontier_cost_usd": 12.50, "frontier_ratio": 0.35},
    )
    return goal


class TestBaselineMetrics:
    """Test BaselineMetrics data class."""

    def test_baseline_metrics_creation(self):
        """Test creating BaselineMetrics."""
        metrics = BaselineMetrics(
            goal_type=GoalType.research,
            metrics={
                "related_failures": 8,
                "questions_asked": 15,
                "manual_research_time_hours": 4.5,
            }
        )

        assert metrics.goal_type == GoalType.research
        assert metrics.metrics["related_failures"] == 8
        assert metrics.captured_at is not None

    def test_baseline_to_dict(self):
        """Test converting BaselineMetrics to dict."""
        metrics = BaselineMetrics(
            goal_type=GoalType.research,
            metrics={"related_failures": 8}
        )

        result = metrics.to_dict()

        assert result["baseline_type"] == "kb_gap"
        assert result["related_failures"] == 8
        assert "captured_at" in result


class TestOutcomeMetrics:
    """Test OutcomeMetrics data class."""

    def test_outcome_metrics_creation(self):
        """Test creating OutcomeMetrics."""
        metrics = OutcomeMetrics(
            goal_type=GoalType.research,
            metrics={
                "kb_article_views": 23,
                "kb_article_references": 5,
                "estimated_time_saved_hours": 15.2,
            }
        )

        assert metrics.goal_type == GoalType.research
        assert metrics.metrics["kb_article_views"] == 23
        assert metrics.measured_at is not None

    def test_outcome_to_dict(self):
        """Test converting OutcomeMetrics to dict."""
        metrics = OutcomeMetrics(
            goal_type=GoalType.improvement,
            metrics={"failure_reduction_pct": 75.0}
        )

        result = metrics.to_dict()

        assert result["failure_reduction_pct"] == 75.0
        assert "measured_at" in result


class TestEffectivenessScore:
    """Test EffectivenessScore calculation."""

    def test_effectiveness_score_calculation(self):
        """Test weighted effectiveness score calculation."""
        score = EffectivenessScore(
            impact=80.0,
            roi=70.0,
            adoption=60.0,
            quality=90.0
        )

        # Formula: impact*0.4 + roi*0.3 + adoption*0.2 + quality*0.1
        # = 80*0.4 + 70*0.3 + 60*0.2 + 90*0.1
        # = 32 + 21 + 12 + 9 = 74
        assert score.total == 74.0

    def test_effectiveness_score_clamping(self):
        """Test scores are clamped to 0-100 range."""
        score = EffectivenessScore(
            impact=120.0,  # Over 100
            roi=-10.0,     # Below 0
            adoption=50.0,
            quality=50.0
        )

        assert score.impact == 100.0  # Clamped to 100
        assert score.roi == 0.0       # Clamped to 0

    def test_effectiveness_to_dict(self):
        """Test converting EffectivenessScore to dict."""
        score = EffectivenessScore(
            impact=80.0,
            roi=70.0,
            adoption=60.0,
            quality=90.0
        )

        result = score.to_dict()

        assert result["impact_score"] == 80.0
        assert result["roi_score"] == 70.0
        assert result["adoption_score"] == 60.0
        assert result["quality_score"] == 90.0
        assert result["effectiveness_score"] == 74.0


class TestOutcomeTracker:
    """Test OutcomeTracker class."""

    def test_capture_baseline_research(self, outcome_tracker, research_goal, db_session):
        """Test capturing baseline for research goal."""
        baseline = outcome_tracker.capture_baseline(research_goal)

        assert isinstance(baseline, BaselineMetrics)
        assert baseline.goal_type == GoalType.research
        assert "related_failures" in baseline.metrics
        assert "questions_asked" in baseline.metrics
        assert research_goal.baseline_captured is True
        assert research_goal.baseline_captured_at is not None
        db_session.commit.assert_called_once()

    def test_capture_baseline_improvement(self, outcome_tracker, improvement_goal):
        """Test capturing baseline for improvement goal."""
        baseline = outcome_tracker.capture_baseline(improvement_goal)

        assert baseline.goal_type == GoalType.improvement
        assert "failure_count_30d" in baseline.metrics
        assert "failure_rate" in baseline.metrics
        assert "technique_usage" in baseline.metrics

    def test_capture_baseline_optimization(self, outcome_tracker, optimization_goal):
        """Test capturing baseline for optimization goal."""
        baseline = outcome_tracker.capture_baseline(optimization_goal)

        assert baseline.goal_type == GoalType.optimization
        assert "frontier_cost_30d" in baseline.metrics
        assert "local_cost_30d" in baseline.metrics
        assert "total_queries" in baseline.metrics

    def test_measure_outcome_research(self, outcome_tracker, research_goal):
        """Test measuring outcome for research goal."""
        # Set baseline as captured
        research_goal.baseline_captured = True
        research_goal.baseline_captured_at = datetime.utcnow() - timedelta(days=30)

        outcome = outcome_tracker.measure_outcome(research_goal)

        assert isinstance(outcome, OutcomeMetrics)
        assert outcome.goal_type == GoalType.research
        assert "kb_article_views" in outcome.metrics
        assert "kb_article_references" in outcome.metrics
        assert "estimated_time_saved_hours" in outcome.metrics

    def test_measure_outcome_without_baseline(self, outcome_tracker, research_goal, db_session):
        """Test measuring outcome auto-captures baseline if missing."""
        research_goal.baseline_captured = False

        with patch.object(outcome_tracker, 'capture_baseline') as mock_capture:
            outcome_tracker.measure_outcome(research_goal)
            mock_capture.assert_called_once_with(research_goal)

    def test_calculate_effectiveness_research(self, outcome_tracker, research_goal):
        """Test effectiveness calculation for research goal."""
        baseline = BaselineMetrics(
            goal_type=GoalType.research,
            metrics={
                "related_failures": 10,
                "questions_asked": 15,
            }
        )

        outcome = OutcomeMetrics(
            goal_type=GoalType.research,
            metrics={
                "kb_article_views": 23,
                "kb_article_references": 5,
                "related_failures_after": 2,
                "estimated_time_saved_hours": 15.2,
            }
        )

        # Mock _get_goal_actual_cost to return $2.00
        with patch.object(outcome_tracker, '_get_goal_actual_cost', return_value=2.00):
            score = outcome_tracker.calculate_effectiveness(research_goal, baseline, outcome)

        assert isinstance(score, EffectivenessScore)
        # Impact: (10-2)/10 * 100 = 80%
        assert score.impact == 80.0
        # ROI should be positive (time saved > cost)
        assert score.roi > 0
        # Adoption based on views + references
        assert score.adoption > 0
        # Quality default
        assert score.quality == 80.0

    def test_calculate_effectiveness_improvement(self, outcome_tracker, improvement_goal):
        """Test effectiveness calculation for improvement goal."""
        baseline = BaselineMetrics(
            goal_type=GoalType.improvement,
            metrics={
                "failure_count_30d": 12,
                "failure_rate": 15.0,
                "technique_usage": 8,
            }
        )

        outcome = OutcomeMetrics(
            goal_type=GoalType.improvement,
            metrics={
                "failure_count_30d": 3,
                "failure_rate": 4.0,
                "failure_reduction_pct": 75.0,
                "technique_usage": 24,
            }
        )

        with patch.object(outcome_tracker, '_get_goal_actual_cost', return_value=1.50):
            score = outcome_tracker.calculate_effectiveness(improvement_goal, baseline, outcome)

        # Impact should match failure reduction
        assert score.impact == 75.0
        # ROI based on failures prevented
        assert score.roi > 0
        # Adoption based on technique usage increase
        assert score.adoption > 0

    def test_calculate_effectiveness_optimization(self, outcome_tracker, optimization_goal):
        """Test effectiveness calculation for optimization goal."""
        baseline = BaselineMetrics(
            goal_type=GoalType.optimization,
            metrics={
                "frontier_cost_30d": 45.00,
                "local_cost_30d": 5.00,
                "total_queries": 1250,
            }
        )

        outcome = OutcomeMetrics(
            goal_type=GoalType.optimization,
            metrics={
                "frontier_cost_30d": 12.00,
                "local_cost_30d": 5.50,
                "cost_savings_usd": 33.00,
                "total_queries": 1300,
                "performance_degradation_pct": 2,
            }
        )

        with patch.object(outcome_tracker, '_get_goal_actual_cost', return_value=3.00):
            score = outcome_tracker.calculate_effectiveness(optimization_goal, baseline, outcome)

        # Impact: (45-12)/45 * 100 = 73.3%
        assert score.impact > 70.0
        # ROI: 33/3 * 10 = 110, clamped to 100
        assert score.roi == 100.0
        # Adoption: 100 if perf < 5%
        assert score.adoption == 100.0
        # Quality: 100 - 2 = 98
        assert score.quality == 98.0

    def test_store_outcome(self, outcome_tracker, research_goal, db_session):
        """Test storing outcome in database."""
        baseline = BaselineMetrics(
            goal_type=GoalType.research,
            metrics={"related_failures": 10}
        )

        outcome = OutcomeMetrics(
            goal_type=GoalType.research,
            metrics={"kb_article_views": 23}
        )

        effectiveness = EffectivenessScore(
            impact=80.0,
            roi=70.0,
            adoption=60.0,
            quality=90.0
        )

        # Mock database query to return None (no existing outcome)
        db_session.execute.return_value.scalar_one_or_none.return_value = None

        outcome_record = outcome_tracker.store_outcome(
            research_goal,
            baseline,
            outcome,
            effectiveness
        )

        # Verify GoalOutcome was created
        db_session.add.assert_called_once()
        added_outcome = db_session.add.call_args[0][0]
        assert isinstance(added_outcome, GoalOutcome)
        assert added_outcome.goal_id == research_goal.id
        assert added_outcome.effectiveness_score == effectiveness.total
        assert added_outcome.impact_score == effectiveness.impact
        assert added_outcome.roi_score == effectiveness.roi
        assert added_outcome.adoption_score == effectiveness.adoption
        assert added_outcome.quality_score == effectiveness.quality

        # Verify goal was updated
        assert research_goal.effectiveness_score == effectiveness.total
        assert research_goal.outcome_measured_at is not None

        # Verify commit was called
        db_session.commit.assert_called()

    def test_store_outcome_update_existing(self, outcome_tracker, research_goal, db_session):
        """Test updating existing outcome record."""
        # Mock existing outcome
        existing_outcome = GoalOutcome(
            id="outcome_001",
            goal_id=research_goal.id,
            baseline_date=datetime.utcnow(),
            measurement_date=datetime.utcnow(),
            baseline_metrics={},
            outcome_metrics={},
            effectiveness_score=50.0,
        )

        db_session.execute.return_value.scalar_one_or_none.return_value = existing_outcome

        baseline = BaselineMetrics(GoalType.research, {"test": 1})
        outcome = OutcomeMetrics(GoalType.research, {"test": 2})
        effectiveness = EffectivenessScore(80.0, 70.0, 60.0, 90.0)

        outcome_tracker.store_outcome(research_goal, baseline, outcome, effectiveness)

        # Verify outcome was updated, not created
        db_session.add.assert_not_called()
        assert existing_outcome.effectiveness_score == effectiveness.total

    def test_get_goal_actual_cost(self, outcome_tracker, research_goal):
        """Test calculating actual goal cost from projects."""
        # Create mock projects with actual costs
        project1 = MagicMock()
        project1.actual_cost_usd = Decimal("1.20")

        project2 = MagicMock()
        project2.actual_cost_usd = Decimal("0.80")

        research_goal.projects = [project1, project2]

        cost = outcome_tracker._get_goal_actual_cost(research_goal)

        assert cost == 2.00  # 1.20 + 0.80

    def test_get_goal_actual_cost_no_projects(self, outcome_tracker, research_goal):
        """Test fallback to estimated budget when no projects."""
        research_goal.projects = []

        cost = outcome_tracker._get_goal_actual_cost(research_goal)

        assert cost == float(research_goal.estimated_budget)

    def test_get_goal_actual_cost_missing_actual(self, outcome_tracker, research_goal):
        """Test fallback when project has no actual_cost_usd."""
        project = MagicMock()
        project.actual_cost_usd = None

        research_goal.projects = [project]

        cost = outcome_tracker._get_goal_actual_cost(research_goal)

        # Should fall back to estimated budget / num projects
        expected = float(research_goal.estimated_budget) / 1
        assert cost == expected


class TestHelperMethods:
    """Test OutcomeTracker helper methods."""

    def test_extract_keywords(self, outcome_tracker):
        """Test keyword extraction from text."""
        text = "Research and document NYLON material properties for 3D printing"

        keywords = outcome_tracker._extract_keywords(text)

        assert isinstance(keywords, list)
        assert len(keywords) <= 5
        # Should filter stopwords
        assert "and" not in keywords
        assert "for" not in keywords
        # Should include meaningful words
        assert any(kw in keywords for kw in ["research", "nylon", "material", "properties", "printing"])

    def test_extract_technique(self, outcome_tracker):
        """Test technique extraction from description."""
        text = "Improve first layer adhesion for better print quality"

        technique = outcome_tracker._extract_technique(text)

        assert isinstance(technique, str)
        assert len(technique) > 0

    def test_extract_optimization_target(self, outcome_tracker):
        """Test optimization target detection."""
        cost_text = "Optimize routing to reduce API costs"
        perf_text = "Improve performance of inference engine"
        general_text = "Optimize the system"

        assert outcome_tracker._extract_optimization_target(cost_text) == "cost_reduction"
        assert outcome_tracker._extract_optimization_target(perf_text) == "performance_improvement"
        assert outcome_tracker._extract_optimization_target(general_text) == "general_optimization"

    def test_get_measurement_method(self, outcome_tracker):
        """Test measurement method mapping."""
        assert outcome_tracker._get_measurement_method(GoalType.research) == "kb_usage"
        assert outcome_tracker._get_measurement_method(GoalType.improvement) == "failure_rate"
        assert outcome_tracker._get_measurement_method(GoalType.optimization) == "cost_savings"
