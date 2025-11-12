"""Tests for autonomous goal generator."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from services.brain.src.brain.autonomous.goal_generator import (
    GoalGenerator,
    OpportunityScore,
)
from common.db.models import (
    Goal,
    GoalType,
    GoalStatus,
    FabricationJob,
    JobStatus,
)


class TestOpportunityScore:
    """Tests for OpportunityScore calculation."""

    def test_score_initialization(self):
        """Test OpportunityScore initializes with components."""
        score = OpportunityScore(
            frequency=0.8,
            severity=0.9,
            cost_savings=0.5,
            knowledge_gap=0.3,
            strategic_value=0.7,
        )

        assert score.frequency == 0.8
        assert score.severity == 0.9
        assert score.cost_savings == 0.5
        assert score.knowledge_gap == 0.3
        assert score.strategic_value == 0.7

    def test_total_score_calculation(self):
        """Test weighted total score calculation."""
        score = OpportunityScore(
            frequency=1.0,  # 20 points
            severity=1.0,   # 25 points
            cost_savings=1.0,  # 20 points
            knowledge_gap=1.0,  # 20 points
            strategic_value=1.0,  # 15 points
        )

        # Total: 20 + 25 + 20 + 20 + 15 = 100
        assert score.total_score == 100.0

    def test_partial_score_calculation(self):
        """Test partial score calculation."""
        score = OpportunityScore(
            frequency=0.5,  # 10 points
            severity=0.8,   # 20 points
            cost_savings=0.0,  # 0 points
            knowledge_gap=0.6,  # 12 points
            strategic_value=0.4,  # 6 points
        )

        # Total: 10 + 20 + 0 + 12 + 6 = 48
        assert score.total_score == 48.0

    def test_score_to_dict(self):
        """Test score export to dictionary."""
        score = OpportunityScore(
            frequency=0.7,
            severity=0.8,
            cost_savings=0.5,
            knowledge_gap=0.4,
            strategic_value=0.6,
        )

        score_dict = score.to_dict()

        assert score_dict["frequency"] == 0.7
        assert score_dict["severity"] == 0.8
        assert score_dict["cost_savings"] == 0.5
        assert score_dict["knowledge_gap"] == 0.4
        assert score_dict["strategic_value"] == 0.6
        assert "total_score" in score_dict


class TestGoalGenerator:
    """Tests for GoalGenerator class."""

    @pytest.fixture
    def mock_session(self):
        """Mock database session."""
        session = MagicMock()
        session.execute = MagicMock()
        session.add = MagicMock()
        session.commit = MagicMock()
        session.rollback = MagicMock()
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Mock session factory."""
        def factory():
            class ContextManager:
                def __enter__(self):
                    return mock_session
                def __exit__(self, *args):
                    pass
            return ContextManager()
        return factory

    def test_generator_initialization(self, mock_session_factory):
        """Test GoalGenerator initializes with correct defaults."""
        generator = GoalGenerator(
            session_factory=mock_session_factory,
            lookback_days=30,
            min_failure_count=3,
            min_impact_score=50.0,
        )

        assert generator.lookback_days == 30
        assert generator.min_failure_count == 3
        assert generator.min_impact_score == 50.0

    @patch('services.brain.src.brain.autonomous.goal_generator.KnowledgeUpdater')
    def test_detect_knowledge_gaps(self, mock_kb_class, mock_session_factory):
        """Test knowledge gap detection."""
        # Setup mock KB
        mock_kb = MagicMock()
        mock_kb_class.return_value = mock_kb
        mock_kb.list_materials.return_value = ["pla", "petg", "abs"]

        generator = GoalGenerator(session_factory=mock_session_factory)

        with generator._session_factory() as session:
            goals = generator._detect_knowledge_gaps(session)

        # Should detect missing common materials (nylon, pc, tpu)
        assert len(goals) >= 1
        assert all(isinstance(g, Goal) for g in goals)
        assert all(g.goal_type == GoalType.research for g in goals)

    def test_detect_print_failures_insufficient_data(self, mock_session_factory, mock_session):
        """Test print failure detection with insufficient failures."""
        # Mock query to return only 2 failures (below min_failure_count=3)
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "first_layer"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "warping"}),
        ]
        mock_session.execute.return_value = mock_result

        generator = GoalGenerator(
            session_factory=mock_session_factory,
            min_failure_count=3
        )

        with generator._session_factory() as session:
            goals = generator._detect_print_failures(session)

        # Should return empty list (not enough failures)
        assert len(goals) == 0

    def test_detect_print_failures_creates_goals(self, mock_session_factory, mock_session):
        """Test print failure detection creates goals for patterns."""
        # Mock query to return sufficient failures
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "first_layer"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "first_layer"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "first_layer"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "warping"}),
        ]
        mock_session.execute.return_value = mock_result

        generator = GoalGenerator(
            session_factory=mock_session_factory,
            min_failure_count=3
        )

        with generator._session_factory() as session:
            goals = generator._detect_print_failures(session)

        # Should create goal for "first_layer" (3 occurrences)
        assert len(goals) >= 1
        first_layer_goal = [g for g in goals if "first_layer" in g.description.lower()]
        assert len(first_layer_goal) >= 1
        assert first_layer_goal[0].goal_type == GoalType.improvement

    def test_detect_cost_opportunities_low_usage(self, mock_session_factory, mock_session):
        """Test cost opportunity detection with low frontier usage."""
        # Mock query to return low frontier tier usage
        mock_session.execute.return_value = [
            ("local", 80, Decimal("0.50")),
            ("mcp", 15, Decimal("1.00")),
            ("frontier", 5, Decimal("2.00")),  # <30% of total
        ]

        generator = GoalGenerator(session_factory=mock_session_factory)

        with generator._session_factory() as session:
            goals = generator._detect_cost_opportunities(session)

        # Should not create goal (frontier usage is acceptable)
        assert len(goals) == 0

    def test_detect_cost_opportunities_high_usage(self, mock_session_factory, mock_session):
        """Test cost opportunity detection with high frontier usage."""
        # Mock query to return high frontier tier usage
        mock_session.execute.return_value = [
            ("local", 30, Decimal("2.00")),
            ("mcp", 20, Decimal("3.00")),
            ("frontier", 50, Decimal("10.00")),  # >30% of total, >$5
        ]

        generator = GoalGenerator(session_factory=mock_session_factory)

        with generator._session_factory() as session:
            goals = generator._detect_cost_opportunities(session)

        # Should create optimization goal
        assert len(goals) == 1
        assert goals[0].goal_type == GoalType.optimization
        assert "frontier" in goals[0].description.lower()

    @patch('services.brain.src.brain.autonomous.goal_generator.KnowledgeUpdater')
    def test_generate_goals_integration(self, mock_kb_class, mock_session_factory, mock_session):
        """Test full goal generation pipeline."""
        # Setup mocks
        mock_kb = MagicMock()
        mock_kb_class.return_value = mock_kb
        mock_kb.list_materials.return_value = ["pla", "petg"]  # Missing common materials

        # Mock fabrication failures
        mock_fab_result = MagicMock()
        mock_fab_result.scalars().all.return_value = [
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "warping"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "warping"}),
            MagicMock(spec=FabricationJob, job_metadata={"failure_reason": "warping"}),
        ]

        # Mock routing stats (low frontier usage)
        mock_routing_result = [
            ("local", 80, Decimal("2.00")),
            ("mcp", 15, Decimal("1.00")),
            ("frontier", 5, Decimal("0.50")),
        ]

        # Setup execute to return different results based on query
        def execute_side_effect(stmt):
            # Check if it's the fabrication query or routing query
            if hasattr(stmt, '__str__'):
                stmt_str = str(stmt).lower()
                if 'fabrication' in stmt_str:
                    return mock_fab_result
            # Default to routing stats
            return mock_routing_result

        mock_session.execute.side_effect = execute_side_effect

        generator = GoalGenerator(
            session_factory=mock_session_factory,
            min_impact_score=30.0,  # Lower threshold for testing
        )

        goals = generator.generate_goals(max_goals=5)

        # Should generate goals from failures and knowledge gaps
        assert len(goals) >= 1
        assert all(isinstance(g, Goal) for g in goals)
        assert all(g.status == GoalStatus.identified for g in goals)

    def test_calculate_impact_score_print_failure(self, mock_session_factory, mock_session):
        """Test impact score calculation for print failure goal."""
        goal = Goal(
            id=str(uuid.uuid4()),
            goal_type=GoalType.improvement,
            description="Reduce warping failures",
            rationale="Test",
            estimated_budget=Decimal("2.00"),
            estimated_duration_hours=4,
            status=GoalStatus.identified,
            goal_metadata={
                "source": "print_failure_analysis",
                "failure_count": 8,
            },
        )

        generator = GoalGenerator(session_factory=mock_session_factory)

        with generator._session_factory() as session:
            score = generator._calculate_impact_score(goal, session)

        # Print failures should score high on frequency and severity
        assert score.frequency > 0.5
        assert score.severity > 0.5
        assert score.total_score > 40.0

    def test_calculate_impact_score_knowledge_gap(self, mock_session_factory, mock_session):
        """Test impact score calculation for knowledge gap goal."""
        goal = Goal(
            id=str(uuid.uuid4()),
            goal_type=GoalType.research,
            description="Document nylon material",
            rationale="Test",
            estimated_budget=Decimal("1.50"),
            estimated_duration_hours=3,
            status=GoalStatus.identified,
            goal_metadata={
                "source": "knowledge_gap_analysis",
                "material": "nylon",
            },
        )

        generator = GoalGenerator(session_factory=mock_session_factory)

        with generator._session_factory() as session:
            score = generator._calculate_impact_score(goal, session)

        # Knowledge gaps should score high on knowledge_gap and strategic_value
        assert score.knowledge_gap > 0.8
        assert score.strategic_value > 0.7
        assert score.total_score > 40.0

    def test_persist_goals_success(self, mock_session_factory, mock_session):
        """Test successful goal persistence."""
        goals = [
            Goal(
                id=str(uuid.uuid4()),
                goal_type=GoalType.research,
                description="Test goal",
                rationale="Test",
                estimated_budget=Decimal("1.00"),
                estimated_duration_hours=2,
                status=GoalStatus.identified,
            )
        ]

        generator = GoalGenerator(session_factory=mock_session_factory)
        saved_count = generator.persist_goals(goals)

        assert saved_count == 1
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_persist_goals_handles_errors(self, mock_session_factory, mock_session):
        """Test goal persistence handles database errors."""
        goals = [
            Goal(
                id=str(uuid.uuid4()),
                goal_type=GoalType.research,
                description="Test goal",
                rationale="Test",
                estimated_budget=Decimal("1.00"),
                estimated_duration_hours=2,
                status=GoalStatus.identified,
            )
        ]

        # Mock commit to raise error
        mock_session.commit.side_effect = Exception("Database error")

        generator = GoalGenerator(session_factory=mock_session_factory)
        saved_count = generator.persist_goals(goals)

        # Should return 0 (no goals saved) and call rollback
        assert saved_count == 0
        mock_session.rollback.assert_called()


@pytest.mark.integration
class TestGoalGeneratorIntegration:
    """Integration tests for goal generator with real database."""

    def test_end_to_end_goal_generation(self):
        """Test complete goal generation workflow (requires test database)."""
        # This test would require a test database setup
        # Placeholder for future integration testing
        pytest.skip("Requires test database setup")
