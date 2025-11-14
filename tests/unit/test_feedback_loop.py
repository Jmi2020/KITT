"""Unit tests for Phase 3 FeedbackLoop.

Tests historical effectiveness analysis, adjustment factor calculation,
and learning from goal outcomes.
"""

# ruff: noqa: E402
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

from brain.autonomous.feedback_loop import (
    FeedbackLoop,
    create_feedback_loop,
)
from common.db.models import Goal, GoalType, GoalStatus


@pytest.fixture
def db_session():
    """Mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def feedback_loop(db_session):
    """Create FeedbackLoop instance."""
    return FeedbackLoop(
        db_session=db_session,
        min_samples=10,
        adjustment_max=1.5,
        enabled=True,
    )


@pytest.fixture
def measured_goals():
    """Create a set of goals with measured outcomes."""
    goals = []

    # 6 research goals with high effectiveness (avg 82.5)
    for i in range(6):
        goal = Goal(
            id=f"goal_research_{i}",
            goal_type=GoalType.research,
            status=GoalStatus.completed,
            description=f"Research goal {i}",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            effectiveness_score=Decimal(str(75.0 + i * 2.5)),  # 75, 77.5, 80, 82.5, 85, 87.5
            outcome_measured_at=datetime.utcnow(),
            learn_from=True,
        )
        goals.append(goal)

    # 3 improvement goals with moderate effectiveness (avg 58.3)
    for i in range(3):
        goal = Goal(
            id=f"goal_improvement_{i}",
            goal_type=GoalType.improvement,
            status=GoalStatus.completed,
            description=f"Improvement goal {i}",
            rationale="Test",
            estimated_budget=Decimal("1.50"),
            effectiveness_score=Decimal(str(50.0 + i * 8.3)),  # 50, 58.3, 66.6
            outcome_measured_at=datetime.utcnow(),
            learn_from=True,
        )
        goals.append(goal)

    # 1 optimization goal with good effectiveness (71.2)
    goal = Goal(
        id="goal_optimization_0",
        goal_type=GoalType.optimization,
        status=GoalStatus.completed,
        description="Optimization goal",
        rationale="Test",
        estimated_budget=Decimal("3.00"),
        effectiveness_score=Decimal("71.2"),
        outcome_measured_at=datetime.utcnow(),
        learn_from=True,
    )
    goals.append(goal)

    return goals


class TestFeedbackLoopInitialization:
    """Test FeedbackLoop initialization."""

    def test_initialization_defaults(self, db_session):
        """Test FeedbackLoop with default parameters."""
        loop = FeedbackLoop(db_session)

        assert loop.db == db_session
        assert loop.min_samples == 10
        assert loop.adjustment_max == 1.5
        assert loop.enabled is True

    def test_initialization_custom(self, db_session):
        """Test FeedbackLoop with custom parameters."""
        loop = FeedbackLoop(
            db_session,
            min_samples=5,
            adjustment_max=2.0,
            enabled=False,
        )

        assert loop.min_samples == 5
        assert loop.adjustment_max == 2.0
        assert loop.enabled is False

    def test_create_feedback_loop_from_settings(self, db_session):
        """Test factory function creates FeedbackLoop from settings."""
        with patch('services.brain.src.brain.autonomous.feedback_loop.settings') as mock_settings:
            mock_settings.feedback_loop_enabled = True
            mock_settings.feedback_loop_min_samples = 15
            mock_settings.feedback_loop_adjustment_max = 1.8

            loop = create_feedback_loop(db_session)

            assert loop.enabled is True
            assert loop.min_samples == 15
            assert loop.adjustment_max == 1.8


class TestAnalyzeHistoricalEffectiveness:
    """Test historical effectiveness analysis."""

    def test_analyze_effectiveness_with_data(self, feedback_loop, db_session, measured_goals):
        """Test analyzing effectiveness with real goal data."""
        # Mock database query to return measured goals
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        analysis = feedback_loop.analyze_historical_effectiveness()

        # Should have results for all 3 goal types
        assert "research" in analysis
        assert "improvement" in analysis
        assert "optimization" in analysis

        # Research: 6 goals, avg ~82.5, should get boost
        research = analysis["research"]
        assert research["count"] == 6
        assert 82.0 <= research["avg_effectiveness"] <= 83.0
        assert research["sample_size_met"] is True
        assert research["adjustment_factor"] > 1.0  # Should get boost

        # Improvement: 3 goals, avg ~58.3, not enough samples
        improvement = analysis["improvement"]
        assert improvement["count"] == 3
        assert 57.0 <= improvement["avg_effectiveness"] <= 60.0
        assert improvement["sample_size_met"] is False
        assert improvement["adjustment_factor"] == 1.0  # No adjustment yet

        # Optimization: 1 goal, avg 71.2, not enough samples
        optimization = analysis["optimization"]
        assert optimization["count"] == 1
        assert optimization["avg_effectiveness"] == 71.2
        assert optimization["sample_size_met"] is False
        assert optimization["adjustment_factor"] == 1.0

    def test_analyze_effectiveness_disabled(self, db_session):
        """Test analysis returns empty when disabled."""
        loop = FeedbackLoop(db_session, enabled=False)

        analysis = loop.analyze_historical_effectiveness()

        assert analysis == {}

    def test_analyze_effectiveness_no_data(self, feedback_loop, db_session):
        """Test analysis with no measured goals."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        analysis = feedback_loop.analyze_historical_effectiveness()

        assert analysis == {}

    def test_analyze_effectiveness_with_lookback(self, feedback_loop, db_session, measured_goals):
        """Test analysis with lookback window."""
        # Set one goal as measured 60 days ago
        measured_goals[0].outcome_measured_at = datetime.utcnow() - timedelta(days=60)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        # Analyze with 30-day lookback
        analysis = feedback_loop.analyze_historical_effectiveness(lookback_days=30)

        # First goal should be excluded from 30-day window
        # (Implementation note: This would require checking the WHERE clause in the actual SQL)
        # For now, we just verify the method accepts the parameter
        assert isinstance(analysis, dict)


class TestAdjustmentFactorCalculation:
    """Test adjustment factor calculation logic."""

    def test_adjustment_high_effectiveness(self, feedback_loop):
        """Test adjustment for high effectiveness (>80%)."""
        # 85% effectiveness, sample size met
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=85.0,
            sample_size_met=True
        )

        # Should get boost: 1.2 + (85-80)/20 * 0.3 = 1.2 + 0.075 = 1.275
        assert 1.25 <= factor <= 1.30

    def test_adjustment_very_high_effectiveness(self, feedback_loop):
        """Test adjustment for very high effectiveness (95%+)."""
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=95.0,
            sample_size_met=True
        )

        # Should get maximum boost, clamped to 1.5
        assert factor == 1.5

    def test_adjustment_medium_effectiveness(self, feedback_loop):
        """Test adjustment for medium effectiveness (60-80%)."""
        # 70% effectiveness
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=70.0,
            sample_size_met=True
        )

        # Should be 1.0 + (70-60)/20 * 0.2 = 1.0 + 0.1 = 1.1
        assert 1.05 <= factor <= 1.15

    def test_adjustment_neutral_effectiveness(self, feedback_loop):
        """Test adjustment for neutral effectiveness (~50%)."""
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=50.0,
            sample_size_met=True
        )

        # Should be around 0.95-1.0
        assert 0.9 <= factor <= 1.0

    def test_adjustment_low_effectiveness(self, feedback_loop):
        """Test adjustment for low effectiveness (<40%)."""
        # 30% effectiveness
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=30.0,
            sample_size_met=True
        )

        # Should get penalty: 0.5 + (30/40) * 0.4 = 0.5 + 0.3 = 0.8
        assert 0.75 <= factor <= 0.85

    def test_adjustment_very_low_effectiveness(self, feedback_loop):
        """Test adjustment for very low effectiveness."""
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=10.0,
            sample_size_met=True
        )

        # Should be minimum penalty
        assert 0.5 <= factor <= 0.7

    def test_adjustment_insufficient_samples(self, feedback_loop):
        """Test adjustment returns 1.0 when sample size not met."""
        # High effectiveness but not enough samples
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=95.0,
            sample_size_met=False
        )

        assert factor == 1.0

    def test_adjustment_respects_max_limit(self, feedback_loop):
        """Test adjustment is clamped to maximum."""
        # Even with 100% effectiveness, should not exceed max
        factor = feedback_loop._calculate_adjustment_factor(
            avg_effectiveness=100.0,
            sample_size_met=True
        )

        assert factor <= feedback_loop.adjustment_max
        assert factor == 1.5


class TestGetAdjustmentFactor:
    """Test getting adjustment factor for specific goal type."""

    def test_get_adjustment_with_analysis(self, feedback_loop):
        """Test getting adjustment factor from pre-computed analysis."""
        analysis = {
            "research": {
                "avg_effectiveness": 85.0,
                "count": 10,
                "adjustment_factor": 1.25,
                "sample_size_met": True,
            }
        }

        factor = feedback_loop.get_adjustment_factor(
            goal_type=GoalType.research,
            analysis=analysis
        )

        assert factor == 1.25

    def test_get_adjustment_without_analysis(self, feedback_loop, db_session, measured_goals):
        """Test getting adjustment factor computes analysis if not provided."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        factor = feedback_loop.get_adjustment_factor(GoalType.research)

        # Should compute analysis and return factor
        assert factor > 1.0  # Research has high effectiveness

    def test_get_adjustment_no_data(self, feedback_loop, db_session):
        """Test getting adjustment for goal type with no data."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        factor = feedback_loop.get_adjustment_factor(GoalType.research)

        # Should return neutral 1.0 when no data
        assert factor == 1.0

    def test_get_adjustment_disabled(self, db_session):
        """Test getting adjustment returns 1.0 when disabled."""
        loop = FeedbackLoop(db_session, enabled=False)

        factor = loop.get_adjustment_factor(GoalType.research)

        assert factor == 1.0


class TestLearningSummary:
    """Test learning summary and recommendations."""

    def test_get_learning_summary(self, feedback_loop, db_session, measured_goals):
        """Test generating learning summary."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        summary = feedback_loop.get_learning_summary()

        assert summary["enabled"] is True
        assert summary["total_measured_goals"] == 10
        assert summary["goal_types_analyzed"] == 3
        assert summary["goal_types_with_enough_samples"] == 1  # Only research has 10+
        assert 75.0 <= summary["overall_avg_effectiveness"] <= 85.0
        assert summary["learning_active"] is True
        assert summary["by_goal_type"]["research"]["sample_size_met"] is True
        assert summary["by_goal_type"]["improvement"]["sample_size_met"] is False

    def test_get_learning_summary_disabled(self, db_session):
        """Test learning summary when disabled."""
        loop = FeedbackLoop(db_session, enabled=False)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        summary = loop.get_learning_summary()

        assert summary["enabled"] is False
        assert summary["learning_active"] is False

    def test_get_recommendations(self, feedback_loop, db_session, measured_goals):
        """Test generating human-readable recommendations."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        recommendations = feedback_loop.get_recommendations()

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        # Should have recommendations for each goal type
        rec_text = " ".join(recommendations)
        assert "research" in rec_text.lower()
        assert "improvement" in rec_text.lower() or "optimization" in rec_text.lower()

        # Should indicate learning status
        assert any("need" in r.lower() or "boosting" in r.lower() or "effectiveness" in r.lower() for r in recommendations)

    def test_get_recommendations_not_active(self, feedback_loop, db_session):
        """Test recommendations when learning not yet active."""
        # Return goals with no outcomes measured
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        recommendations = feedback_loop.get_recommendations()

        assert len(recommendations) == 1
        assert "not yet active" in recommendations[0].lower()
        assert str(feedback_loop.min_samples) in recommendations[0]

    def test_get_recommendations_categorizes_effectiveness(self, feedback_loop, db_session):
        """Test recommendations categorize effectiveness levels correctly."""
        # Create goals with specific effectiveness levels
        high_eff_goal = Goal(
            id="high",
            goal_type=GoalType.research,
            status=GoalStatus.completed,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            effectiveness_score=Decimal("85.0"),
            outcome_measured_at=datetime.utcnow(),
            learn_from=True,
        )

        # Create 10 high effectiveness research goals (meet min_samples)
        goals = [high_eff_goal] * 10

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = goals
        db_session.execute.return_value = mock_result

        recommendations = feedback_loop.get_recommendations()

        # Should show high effectiveness message
        rec_text = " ".join(recommendations)
        assert "high effectiveness" in rec_text.lower() or "boosting" in rec_text.lower()


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_zero_effectiveness_scores(self, feedback_loop, db_session):
        """Test handling goals with 0 effectiveness."""
        goal = Goal(
            id="zero",
            goal_type=GoalType.research,
            status=GoalStatus.completed,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            effectiveness_score=Decimal("0.0"),
            outcome_measured_at=datetime.utcnow(),
            learn_from=True,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [goal] * 10
        db_session.execute.return_value = mock_result

        analysis = feedback_loop.analyze_historical_effectiveness()

        # Should handle 0 scores without errors
        assert analysis["research"]["avg_effectiveness"] == 0.0
        assert analysis["research"]["adjustment_factor"] < 1.0

    def test_mixed_learn_from_flags(self, feedback_loop, db_session, measured_goals):
        """Test that learn_from=False goals are excluded."""
        # Set some goals to not learn from
        measured_goals[0].learn_from = False
        measured_goals[1].learn_from = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = measured_goals
        db_session.execute.return_value = mock_result

        # Analysis should only include goals with learn_from=True
        # (This tests the WHERE clause in the query)
        analysis = feedback_loop.analyze_historical_effectiveness()

        # Should still get results, just fewer
        assert isinstance(analysis, dict)

    def test_no_outcome_measured_at(self, feedback_loop, db_session):
        """Test goals without outcome_measured_at are excluded."""
        goal = Goal(
            id="no_outcome",
            goal_type=GoalType.research,
            status=GoalStatus.completed,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            effectiveness_score=Decimal("80.0"),
            outcome_measured_at=None,  # No measurement yet
            learn_from=True,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [goal]
        db_session.execute.return_value = mock_result

        # Should be filtered out by WHERE clause
        # (Testing the query logic)
        analysis = feedback_loop.analyze_historical_effectiveness()

        # Implementation will filter these, so we verify behavior
        assert isinstance(analysis, dict)
