"""Unit tests for Phase 3 OutcomeMeasurementCycle.

Tests the scheduled job that measures outcomes for goals completed 30 days ago.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

from services.brain.src.brain.autonomous.outcome_measurement_cycle import (
    OutcomeMeasurementCycle,
    run_outcome_measurement_cycle,
)
from services.brain.src.brain.autonomous.outcome_tracker import (
    BaselineMetrics,
    OutcomeMetrics,
    EffectivenessScore,
)
from common.db.models import Goal, GoalType, GoalStatus


@pytest.fixture
def db_session():
    """Mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def measurement_cycle(db_session):
    """Create OutcomeMeasurementCycle instance."""
    return OutcomeMeasurementCycle(
        db_session=db_session,
        measurement_window_days=30,
        enabled=True,
    )


@pytest.fixture
def completed_goal_30_days_ago():
    """Create a goal completed exactly 30 days ago."""
    completed_at = datetime.utcnow() - timedelta(days=30)
    goal = Goal(
        id="goal_001",
        goal_type=GoalType.research,
        description="Research NYLON material",
        rationale="KB gap",
        estimated_budget=Decimal("2.00"),
        status=GoalStatus.completed,
        created_by="system-autonomous",
        completed_at=completed_at,
        baseline_captured=True,
        baseline_captured_at=completed_at - timedelta(days=2),
        outcome_measured_at=None,  # Not yet measured
        learn_from=True,
    )
    return goal


class TestOutcomeMeasurementCycleInit:
    """Test OutcomeMeasurementCycle initialization."""

    def test_initialization_defaults(self, db_session):
        """Test initialization with default parameters."""
        cycle = OutcomeMeasurementCycle(db_session)

        assert cycle.db == db_session
        assert cycle.measurement_window_days == 30
        assert cycle.enabled is True
        assert cycle.tracker is not None

    def test_initialization_custom(self, db_session):
        """Test initialization with custom parameters."""
        cycle = OutcomeMeasurementCycle(
            db_session,
            measurement_window_days=45,
            enabled=False,
        )

        assert cycle.measurement_window_days == 45
        assert cycle.enabled is False


class TestFindGoalsForMeasurement:
    """Test finding goals eligible for measurement."""

    def test_find_goals_completed_30_days_ago(self, measurement_cycle, db_session, completed_goal_30_days_ago):
        """Test finding goals completed in measurement window."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [completed_goal_30_days_ago]
        db_session.execute.return_value = mock_result

        goals = measurement_cycle._find_goals_for_measurement()

        assert len(goals) == 1
        assert goals[0].id == "goal_001"

    def test_find_goals_excludes_already_measured(self, measurement_cycle, db_session, completed_goal_30_days_ago):
        """Test that goals with outcome_measured_at are excluded."""
        # Set outcome as already measured
        completed_goal_30_days_ago.outcome_measured_at = datetime.utcnow()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # Should be filtered out
        db_session.execute.return_value = mock_result

        goals = measurement_cycle._find_goals_for_measurement()

        assert len(goals) == 0

    def test_find_goals_excludes_learn_from_false(self, measurement_cycle, db_session, completed_goal_30_days_ago):
        """Test that goals with learn_from=False are excluded."""
        completed_goal_30_days_ago.learn_from = False

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        goals = measurement_cycle._find_goals_for_measurement()

        assert len(goals) == 0

    def test_find_goals_excludes_not_completed(self, measurement_cycle, db_session):
        """Test that non-completed goals are excluded."""
        goal = Goal(
            id="goal_pending",
            goal_type=GoalType.research,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.approved,  # Not completed
            created_by="system-autonomous",
            outcome_measured_at=None,
            learn_from=True,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        goals = measurement_cycle._find_goals_for_measurement()

        assert len(goals) == 0

    def test_find_goals_excludes_wrong_date(self, measurement_cycle, db_session):
        """Test that goals completed outside window are excluded."""
        # Goal completed 20 days ago (not 30)
        goal = Goal(
            id="goal_recent",
            goal_type=GoalType.research,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            completed_at=datetime.utcnow() - timedelta(days=20),
            outcome_measured_at=None,
            learn_from=True,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        goals = measurement_cycle._find_goals_for_measurement()

        assert len(goals) == 0

    def test_find_goals_multiple_eligible(self, measurement_cycle, db_session):
        """Test finding multiple goals eligible for measurement."""
        # Create 3 goals completed 30 days ago
        completed_at = datetime.utcnow() - timedelta(days=30)
        goals = []
        for i in range(3):
            goal = Goal(
                id=f"goal_{i}",
                goal_type=GoalType.research,
                description=f"Test {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                created_by="system-autonomous",
                completed_at=completed_at + timedelta(hours=i),  # Within 24h window
                baseline_captured=True,
                outcome_measured_at=None,
                learn_from=True,
            )
            goals.append(goal)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = goals
        db_session.execute.return_value = mock_result

        found_goals = measurement_cycle._find_goals_for_measurement()

        assert len(found_goals) == 3


class TestMeasureGoalOutcome:
    """Test measuring outcome for a single goal."""

    @pytest.mark.asyncio
    async def test_measure_goal_with_baseline(self, measurement_cycle, completed_goal_30_days_ago):
        """Test measuring outcome for goal with existing baseline."""
        # Mock tracker methods
        with patch.object(measurement_cycle.tracker, 'measure_outcome') as mock_measure, \
             patch.object(measurement_cycle.tracker, 'calculate_effectiveness') as mock_calc, \
             patch.object(measurement_cycle.tracker, 'store_outcome') as mock_store:

            # Setup mocks
            baseline = BaselineMetrics(GoalType.research, {"test": 1})
            baseline.captured_at = datetime.utcnow() - timedelta(days=32)

            outcome = OutcomeMetrics(GoalType.research, {"test": 2})
            outcome.measured_at = datetime.utcnow()

            effectiveness = EffectivenessScore(80.0, 70.0, 60.0, 90.0)

            mock_outcome_record = MagicMock()
            mock_outcome_record.measurement_method = "kb_usage"

            mock_measure.return_value = outcome
            mock_calc.return_value = effectiveness
            mock_store.return_value = mock_outcome_record

            # Mock capture_baseline to return baseline
            with patch.object(measurement_cycle.tracker, 'capture_baseline', return_value=baseline):
                result = await measurement_cycle._measure_goal_outcome(completed_goal_30_days_ago)

            assert result["goal_id"] == "goal_001"
            assert result["goal_type"] == "research"
            assert result["effectiveness_score"] == 74.0  # Weighted average
            assert result["impact_score"] == 80.0
            assert result["roi_score"] == 70.0
            assert result["adoption_score"] == 60.0
            assert result["quality_score"] == 90.0

    @pytest.mark.asyncio
    async def test_measure_goal_without_baseline(self, measurement_cycle):
        """Test measuring outcome auto-captures baseline if missing."""
        goal = Goal(
            id="goal_no_baseline",
            goal_type=GoalType.improvement,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("1.50"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            completed_at=datetime.utcnow() - timedelta(days=30),
            baseline_captured=False,  # No baseline yet
            outcome_measured_at=None,
            learn_from=True,
        )

        with patch.object(measurement_cycle.tracker, 'capture_baseline') as mock_capture, \
             patch.object(measurement_cycle.tracker, 'measure_outcome') as mock_measure, \
             patch.object(measurement_cycle.tracker, 'calculate_effectiveness') as mock_calc, \
             patch.object(measurement_cycle.tracker, 'store_outcome') as mock_store:

            baseline = BaselineMetrics(GoalType.improvement, {"test": 1})
            outcome = OutcomeMetrics(GoalType.improvement, {"test": 2})
            effectiveness = EffectivenessScore(75.0, 65.0, 55.0, 85.0)
            mock_outcome_record = MagicMock()
            mock_outcome_record.measurement_method = "failure_rate"

            mock_capture.return_value = baseline
            mock_measure.return_value = outcome
            mock_calc.return_value = effectiveness
            mock_store.return_value = mock_outcome_record

            result = await measurement_cycle._measure_goal_outcome(goal)

            # Should have called capture_baseline
            mock_capture.assert_called_once_with(goal)
            assert result["goal_id"] == "goal_no_baseline"


class TestRunCycle:
    """Test running the full measurement cycle."""

    @pytest.mark.asyncio
    async def test_run_cycle_with_eligible_goals(self, measurement_cycle, db_session, completed_goal_30_days_ago):
        """Test running cycle with eligible goals."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [completed_goal_30_days_ago]
        db_session.execute.return_value = mock_result

        # Mock _measure_goal_outcome
        with patch.object(measurement_cycle, '_measure_goal_outcome', new_callable=AsyncMock) as mock_measure:
            mock_measure.return_value = {
                "goal_id": "goal_001",
                "goal_type": "research",
                "goal_description": "Research NYLON material",
                "baseline_captured_at": datetime.utcnow().isoformat(),
                "outcome_measured_at": datetime.utcnow().isoformat(),
                "impact_score": 80.0,
                "roi_score": 70.0,
                "adoption_score": 60.0,
                "quality_score": 90.0,
                "effectiveness_score": 74.0,
                "measurement_method": "kb_usage",
            }

            results = await measurement_cycle.run_cycle()

        assert results["status"] == "completed"
        assert results["goals_measured"] == 1
        assert results["goals_failed"] == 0
        assert len(results["measurements"]) == 1
        assert results["measurements"][0]["goal_id"] == "goal_001"
        assert "duration_seconds" in results

    @pytest.mark.asyncio
    async def test_run_cycle_disabled(self, db_session):
        """Test cycle returns early when disabled."""
        cycle = OutcomeMeasurementCycle(db_session, enabled=False)

        results = await cycle.run_cycle()

        assert results["status"] == "disabled"
        assert results["goals_measured"] == 0

    @pytest.mark.asyncio
    async def test_run_cycle_no_eligible_goals(self, measurement_cycle, db_session):
        """Test cycle with no eligible goals."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        results = await measurement_cycle.run_cycle()

        assert results["status"] == "completed"
        assert results["goals_measured"] == 0
        assert len(results["measurements"]) == 0

    @pytest.mark.asyncio
    async def test_run_cycle_with_failures(self, measurement_cycle, db_session):
        """Test cycle handles measurement failures gracefully."""
        # Create 2 goals
        goal1 = Goal(
            id="goal_001",
            goal_type=GoalType.research,
            description="Test 1",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            completed_at=datetime.utcnow() - timedelta(days=30),
            baseline_captured=True,
            outcome_measured_at=None,
            learn_from=True,
        )

        goal2 = Goal(
            id="goal_002",
            goal_type=GoalType.research,
            description="Test 2",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            completed_at=datetime.utcnow() - timedelta(days=30),
            baseline_captured=True,
            outcome_measured_at=None,
            learn_from=True,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [goal1, goal2]
        db_session.execute.return_value = mock_result

        # Mock _measure_goal_outcome to succeed for first, fail for second
        with patch.object(measurement_cycle, '_measure_goal_outcome', new_callable=AsyncMock) as mock_measure:
            async def measure_side_effect(goal):
                if goal.id == "goal_001":
                    return {
                        "goal_id": "goal_001",
                        "goal_type": "research",
                        "goal_description": "Test 1",
                        "effectiveness_score": 74.0,
                        "measurement_method": "kb_usage",
                    }
                else:
                    raise Exception("Measurement failed")

            mock_measure.side_effect = measure_side_effect

            results = await measurement_cycle.run_cycle()

        assert results["status"] == "completed"
        assert results["goals_measured"] == 1  # Only first succeeded
        assert results["goals_failed"] == 1
        assert len(results["errors"]) == 1
        assert results["errors"][0]["goal_id"] == "goal_002"


class TestGetMeasurementStatistics:
    """Test getting measurement statistics."""

    def test_get_statistics_with_data(self, measurement_cycle, db_session):
        """Test getting statistics with measured goals."""
        # Create measured goals
        goals = []
        for i in range(5):
            goal = Goal(
                id=f"goal_{i}",
                goal_type=GoalType.research,
                description=f"Test {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                created_by="system-autonomous",
                effectiveness_score=Decimal(str(70.0 + i * 5)),  # 70, 75, 80, 85, 90
                outcome_measured_at=datetime.utcnow(),
            )
            goals.append(goal)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = goals
        db_session.execute.return_value = mock_result

        stats = measurement_cycle.get_measurement_statistics()

        assert stats["total_measured"] == 5
        assert "research" in stats["by_goal_type"]

        research_stats = stats["by_goal_type"]["research"]
        assert research_stats["count"] == 5
        assert research_stats["avg_effectiveness"] == 80.0  # Average of 70,75,80,85,90
        assert research_stats["min_effectiveness"] == 70.0
        assert research_stats["max_effectiveness"] == 90.0

    def test_get_statistics_no_data(self, measurement_cycle, db_session):
        """Test getting statistics with no measured goals."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        stats = measurement_cycle.get_measurement_statistics()

        assert stats["total_measured"] == 0
        assert stats["by_goal_type"] == {}

    def test_get_statistics_multiple_types(self, measurement_cycle, db_session):
        """Test statistics with multiple goal types."""
        research_goal = Goal(
            id="research",
            goal_type=GoalType.research,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            effectiveness_score=Decimal("80.0"),
            outcome_measured_at=datetime.utcnow(),
        )

        improvement_goal = Goal(
            id="improvement",
            goal_type=GoalType.improvement,
            description="Test",
            rationale="Test",
            estimated_budget=Decimal("1.50"),
            status=GoalStatus.completed,
            created_by="system-autonomous",
            effectiveness_score=Decimal("65.0"),
            outcome_measured_at=datetime.utcnow(),
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [research_goal, improvement_goal]
        db_session.execute.return_value = mock_result

        stats = measurement_cycle.get_measurement_statistics()

        assert stats["total_measured"] == 2
        assert "research" in stats["by_goal_type"]
        assert "improvement" in stats["by_goal_type"]
        assert stats["by_goal_type"]["research"]["avg_effectiveness"] == 80.0
        assert stats["by_goal_type"]["improvement"]["avg_effectiveness"] == 65.0


class TestRunOutcomeMeasurementCycle:
    """Test the entry point function for scheduler."""

    @pytest.mark.asyncio
    async def test_run_entry_point(self, db_session):
        """Test run_outcome_measurement_cycle entry point."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        with patch('services.brain.src.brain.autonomous.outcome_measurement_cycle.settings') as mock_settings:
            mock_settings.outcome_measurement_enabled = True
            mock_settings.outcome_measurement_window_days = 30

            results = await run_outcome_measurement_cycle(db_session)

        assert results["status"] == "completed"
        assert "goals_measured" in results

    @pytest.mark.asyncio
    async def test_run_entry_point_custom_window(self, db_session):
        """Test entry point with custom measurement window."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db_session.execute.return_value = mock_result

        with patch('services.brain.src.brain.autonomous.outcome_measurement_cycle.settings') as mock_settings:
            mock_settings.outcome_measurement_enabled = True

            # Custom window overrides settings
            results = await run_outcome_measurement_cycle(db_session, measurement_window_days=45)

        assert results["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_entry_point_disabled(self, db_session):
        """Test entry point when disabled in settings."""
        with patch('services.brain.src.brain.autonomous.outcome_measurement_cycle.settings') as mock_settings:
            mock_settings.outcome_measurement_enabled = False

            results = await run_outcome_measurement_cycle(db_session)

        assert results["status"] == "disabled"
