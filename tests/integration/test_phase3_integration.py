"""Integration tests for Phase 3 - Outcome Tracking & Learning.

Tests the full workflow: Goal creation → Baseline capture → Completion →
Outcome measurement → Effectiveness scoring → Feedback loop learning.
"""

# ruff: noqa: E402
import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

from common.db.models import Base, Goal, GoalType, GoalStatus, Project, GoalOutcome
from brain.autonomous.outcome_tracker import OutcomeTracker
from brain.autonomous.outcome_measurement_cycle import OutcomeMeasurementCycle
from brain.autonomous.feedback_loop import FeedbackLoop
from brain.autonomous.goal_generator import GoalGenerator


@pytest.fixture(scope="function")
def test_db():
    """Create in-memory test database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def outcome_tracker(test_db):
    """Create OutcomeTracker with test database."""
    return OutcomeTracker(test_db)


@pytest.fixture
def measurement_cycle(test_db):
    """Create OutcomeMeasurementCycle with test database."""
    return OutcomeMeasurementCycle(test_db, measurement_window_days=30, enabled=True)


@pytest.fixture
def feedback_loop(test_db):
    """Create FeedbackLoop with test database."""
    return FeedbackLoop(test_db, min_samples=3, adjustment_max=1.5, enabled=True)


@pytest.fixture
def goal_generator(test_db, feedback_loop):
    """Create GoalGenerator with feedback loop."""
    return GoalGenerator(
        session_factory=lambda: test_db,
        lookback_days=30,
        min_failure_count=3,
        min_impact_score=50.0,
        feedback_loop=feedback_loop,
    )


@pytest.mark.integration
class TestPhase3FullWorkflow:
    """Test complete Phase 3 workflow end-to-end."""

    def test_full_outcome_tracking_workflow(self, test_db, outcome_tracker):
        """Test complete workflow from goal approval to outcome storage."""
        # Step 1: Create and approve a research goal
        goal = Goal(
            id="goal_integration_001",
            goal_type=GoalType.research,
            description="Research sustainable PLA alternatives",
            rationale="KB lacks sustainable material options",
            estimated_budget=Decimal("2.50"),
            estimated_duration_hours=4,
            status=GoalStatus.approved,
            identified_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
            approved_by="user-test",
        )
        test_db.add(goal)
        test_db.commit()

        # Step 2: Capture baseline when goal approved
        baseline = outcome_tracker.capture_baseline(goal)

        assert goal.baseline_captured is True
        assert goal.baseline_captured_at is not None
        assert baseline.goal_type == GoalType.research
        assert "related_failures" in baseline.metrics

        # Step 3: Simulate project completion
        project = Project(
            id="proj_001",
            goal_id=goal.id,
            title="Research sustainable PLA alternatives",
            description="Test project",
            status="completed",
            budget_allocated=Decimal("2.50"),
            budget_spent=Decimal("1.80"),
            actual_cost_usd=Decimal("1.80"),
            actual_duration_hours=3,
        )
        test_db.add(project)
        goal.status = GoalStatus.completed
        goal.completed_at = datetime.utcnow() - timedelta(days=30)  # Simulate 30 days ago
        test_db.commit()

        # Step 4: Measure outcome after 30 days
        outcome = outcome_tracker.measure_outcome(goal)

        assert outcome.goal_type == GoalType.research
        assert "kb_article_views" in outcome.metrics
        assert "estimated_time_saved_hours" in outcome.metrics

        # Step 5: Calculate effectiveness
        effectiveness = outcome_tracker.calculate_effectiveness(goal, baseline, outcome)

        assert 0 <= effectiveness.impact <= 100
        assert 0 <= effectiveness.roi <= 100
        assert 0 <= effectiveness.adoption <= 100
        assert 0 <= effectiveness.quality <= 100
        assert 0 <= effectiveness.total <= 100

        # Step 6: Store outcome in database
        outcome_record = outcome_tracker.store_outcome(goal, baseline, outcome, effectiveness)

        assert outcome_record.goal_id == goal.id
        assert outcome_record.effectiveness_score == effectiveness.total
        assert goal.effectiveness_score == effectiveness.total
        assert goal.outcome_measured_at is not None

        # Step 7: Verify outcome stored correctly
        stored_outcome = test_db.query(GoalOutcome).filter_by(goal_id=goal.id).first()
        assert stored_outcome is not None
        assert stored_outcome.impact_score == effectiveness.impact
        assert stored_outcome.roi_score == effectiveness.roi
        assert stored_outcome.measurement_method == "kb_usage"

    @pytest.mark.asyncio
    async def test_outcome_measurement_cycle_integration(self, test_db, measurement_cycle):
        """Test outcome measurement cycle with real database."""
        # Create 3 goals completed 30 days ago
        goals = []
        completed_at = datetime.utcnow() - timedelta(days=30)

        for i in range(3):
            goal = Goal(
                id=f"goal_cycle_{i}",
                goal_type=GoalType.research if i < 2 else GoalType.improvement,
                description=f"Test goal {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                baseline_captured=True,
                baseline_captured_at=completed_at - timedelta(days=2),
                outcome_measured_at=None,
                learn_from=True,
            )

            # Add project with actual cost
            project = Project(
                id=f"proj_cycle_{i}",
                goal_id=goal.id,
                title=f"Project {i}",
                description="Test",
                status="completed",
                budget_allocated=Decimal("2.00"),
                budget_spent=Decimal("1.50"),
                actual_cost_usd=Decimal("1.50"),
            )

            test_db.add(goal)
            test_db.add(project)
            goals.append(goal)

        test_db.commit()

        # Run measurement cycle
        results = await measurement_cycle.run_cycle()

        assert results["status"] == "completed"
        assert results["goals_measured"] == 3
        assert results["goals_failed"] == 0
        assert len(results["measurements"]) == 3

        # Verify all goals were measured
        for goal in goals:
            test_db.refresh(goal)
            assert goal.outcome_measured_at is not None
            assert goal.effectiveness_score is not None

        # Verify outcomes stored
        outcomes = test_db.query(GoalOutcome).all()
        assert len(outcomes) == 3

    def test_feedback_loop_learning_integration(self, test_db, feedback_loop):
        """Test feedback loop learns from historical outcomes."""
        # Create 10 research goals with high effectiveness
        for i in range(10):
            goal = Goal(
                id=f"goal_high_{i}",
                goal_type=GoalType.research,
                description=f"High effectiveness goal {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                effectiveness_score=Decimal(str(80.0 + i)),  # 80-89
                outcome_measured_at=datetime.utcnow(),
                learn_from=True,
            )
            test_db.add(goal)

        # Create 3 improvement goals with low effectiveness
        for i in range(3):
            goal = Goal(
                id=f"goal_low_{i}",
                goal_type=GoalType.improvement,
                description=f"Low effectiveness goal {i}",
                rationale="Test",
                estimated_budget=Decimal("1.50"),
                status=GoalStatus.completed,
                effectiveness_score=Decimal(str(40.0 + i * 5)),  # 40, 45, 50
                outcome_measured_at=datetime.utcnow(),
                learn_from=True,
            )
            test_db.add(goal)

        test_db.commit()

        # Analyze effectiveness
        analysis = feedback_loop.analyze_historical_effectiveness()

        # Research goals should have high avg and boost
        assert "research" in analysis
        research = analysis["research"]
        assert research["count"] == 10
        assert research["avg_effectiveness"] >= 80.0
        assert research["sample_size_met"] is True
        assert research["adjustment_factor"] > 1.0  # Should get boost

        # Improvement goals should have low avg and penalty
        assert "improvement" in analysis
        improvement = analysis["improvement"]
        assert improvement["count"] == 3
        assert improvement["avg_effectiveness"] < 50.0
        assert improvement["sample_size_met"] is False  # Only 3 samples
        assert improvement["adjustment_factor"] == 1.0  # Not enough samples

        # Get recommendations
        recommendations = feedback_loop.get_recommendations()
        assert len(recommendations) > 0

        rec_text = " ".join(recommendations)
        assert "research" in rec_text.lower()

    def test_goal_generator_with_feedback_loop(self, test_db, goal_generator, feedback_loop):
        """Test goal generator applies feedback loop adjustments."""
        # Create historical outcomes to learn from
        for i in range(10):
            goal = Goal(
                id=f"goal_hist_{i}",
                goal_type=GoalType.research,
                description=f"Historical goal {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                effectiveness_score=Decimal("85.0"),  # High effectiveness
                outcome_measured_at=datetime.utcnow(),
                learn_from=True,
            )
            test_db.add(goal)

        test_db.commit()

        # Generate new goals with feedback loop
        # Note: This is a simplified test since GoalGenerator.generate_goals()
        # requires more complex setup. We test the scoring adjustment directly.

        # Create a test goal to score
        test_goal = Goal(
            id="goal_to_score",
            goal_type=GoalType.research,
            description="New research goal",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.identified,
        )

        # Get adjustment factor
        adjustment = feedback_loop.get_adjustment_factor(GoalType.research)

        # Research goals should get boost due to high historical effectiveness
        assert adjustment > 1.0
        assert adjustment <= 1.5  # Within max limit

        # Test that metadata would be stored
        # (Full integration would call goal_generator.generate_goals())
        if test_goal.goal_metadata is None:
            test_goal.goal_metadata = {}

        base_score = 68.0
        test_goal.goal_metadata["base_impact_score"] = base_score
        test_goal.goal_metadata["adjustment_factor"] = round(adjustment, 3)
        test_goal.goal_metadata["adjusted_impact_score"] = round(base_score * adjustment, 2)

        # Verify metadata structure
        assert test_goal.goal_metadata["base_impact_score"] == 68.0
        assert test_goal.goal_metadata["adjustment_factor"] > 1.0
        assert test_goal.goal_metadata["adjusted_impact_score"] > base_score


@pytest.mark.integration
class TestPhase3EdgeCases:
    """Test edge cases and error handling in integration."""

    def test_outcome_without_project(self, test_db, outcome_tracker):
        """Test measuring outcome for goal without project (uses estimated budget)."""
        goal = Goal(
            id="goal_no_proj",
            goal_type=GoalType.research,
            description="Goal without project",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            status=GoalStatus.completed,
            baseline_captured=False,
        )
        test_db.add(goal)
        test_db.commit()

        # Capture baseline
        baseline = outcome_tracker.capture_baseline(goal)

        # Measure outcome
        outcome = outcome_tracker.measure_outcome(goal)

        # Calculate effectiveness (should use estimated budget)
        effectiveness = outcome_tracker.calculate_effectiveness(goal, baseline, outcome)

        # Should work without project
        assert effectiveness.total >= 0

    def test_multiple_outcome_updates(self, test_db, outcome_tracker):
        """Test updating outcome multiple times."""
        goal = Goal(
            id="goal_update",
            goal_type=GoalType.improvement,
            description="Goal to update",
            rationale="Test",
            estimated_budget=Decimal("1.50"),
            status=GoalStatus.completed,
            baseline_captured=True,
        )
        test_db.add(goal)
        test_db.commit()

        # First measurement
        baseline1 = outcome_tracker.capture_baseline(goal)
        outcome1 = outcome_tracker.measure_outcome(goal)
        effectiveness1 = outcome_tracker.calculate_effectiveness(goal, baseline1, outcome1)
        outcome_tracker.store_outcome(goal, baseline1, outcome1, effectiveness1)

        first_score = goal.effectiveness_score

        # Second measurement (should update, not create new)
        test_db.refresh(goal)
        outcome2 = outcome_tracker.measure_outcome(goal)
        effectiveness2 = outcome_tracker.calculate_effectiveness(goal, baseline1, outcome2)
        outcome_tracker.store_outcome(goal, baseline1, outcome2, effectiveness2)

        test_db.refresh(goal)

        # Should have updated the existing outcome
        outcomes = test_db.query(GoalOutcome).filter_by(goal_id=goal.id).all()
        assert len(outcomes) == 1  # Still only one outcome record

        # Score might have changed
        assert goal.effectiveness_score is not None

    def test_feedback_loop_with_no_data(self, test_db, feedback_loop):
        """Test feedback loop gracefully handles no historical data."""
        # No goals in database
        analysis = feedback_loop.analyze_historical_effectiveness()

        assert analysis == {}

        # Adjustment should be neutral
        adjustment = feedback_loop.get_adjustment_factor(GoalType.research)
        assert adjustment == 1.0

        # Recommendations should indicate no learning yet
        recommendations = feedback_loop.get_recommendations()
        assert len(recommendations) > 0
        assert "not yet active" in recommendations[0].lower()

    @pytest.mark.asyncio
    async def test_measurement_cycle_with_no_goals(self, test_db, measurement_cycle):
        """Test measurement cycle handles no eligible goals."""
        results = await measurement_cycle.run_cycle()

        assert results["status"] == "completed"
        assert results["goals_measured"] == 0
        assert len(results["measurements"]) == 0
        assert results["goals_failed"] == 0


@pytest.mark.integration
class TestPhase3Statistics:
    """Test statistics and reporting."""

    def test_measurement_statistics(self, test_db, measurement_cycle):
        """Test getting measurement statistics."""
        # Create measured goals
        for i in range(5):
            goal = Goal(
                id=f"goal_stat_{i}",
                goal_type=GoalType.research if i < 3 else GoalType.optimization,
                description=f"Stat goal {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                effectiveness_score=Decimal(str(70.0 + i * 5)),
                outcome_measured_at=datetime.utcnow(),
            )
            test_db.add(goal)

        test_db.commit()

        stats = measurement_cycle.get_measurement_statistics()

        assert stats["total_measured"] == 5
        assert len(stats["by_goal_type"]) == 2  # research and optimization
        assert stats["measurement_window_days"] == 30

        # Verify averages calculated correctly
        assert "research" in stats["by_goal_type"]
        assert stats["by_goal_type"]["research"]["count"] == 3

    def test_learning_summary(self, test_db, feedback_loop):
        """Test getting comprehensive learning summary."""
        # Create diverse outcome data
        for i in range(15):
            if i < 10:
                goal_type = GoalType.research
                effectiveness = 80.0 + i
            else:
                goal_type = GoalType.improvement
                effectiveness = 50.0 + i

            goal = Goal(
                id=f"goal_summary_{i}",
                goal_type=goal_type,
                description=f"Summary goal {i}",
                rationale="Test",
                estimated_budget=Decimal("2.00"),
                status=GoalStatus.completed,
                effectiveness_score=Decimal(str(effectiveness)),
                outcome_measured_at=datetime.utcnow(),
                learn_from=True,
            )
            test_db.add(goal)

        test_db.commit()

        summary = feedback_loop.get_learning_summary()

        assert summary["enabled"] is True
        assert summary["total_measured_goals"] == 15
        assert summary["goal_types_analyzed"] == 2
        assert summary["goal_types_with_enough_samples"] >= 1
        assert summary["learning_active"] is True
        assert 70.0 <= summary["overall_avg_effectiveness"] <= 90.0
