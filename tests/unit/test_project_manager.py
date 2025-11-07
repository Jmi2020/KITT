"""
Unit tests for ProjectManager critical paths.

Tests state transitions, budget enforcement, and basic CRUD operations.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from common.db.models import GoalStatus, GoalType, ProjectStatus, TaskStatus, TaskPriority
from brain.projects.manager import ProjectManager


@pytest.fixture
def mock_session():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    return session


@pytest.fixture
def project_manager(mock_session):
    """ProjectManager with mocked session factory."""
    def session_factory():
        return mock_session

    manager = ProjectManager(session_factory=session_factory)
    return manager


class TestProjectStateTransitions:
    """Test project state transition rules."""

    def test_approve_proposed_project(self, project_manager, mock_session):
        """Test approving a proposed project."""
        # Mock project
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.proposed

        mock_session.query().filter().first.return_value = mock_project

        # Approve
        result = project_manager.approve_project("project-1", session=mock_session)

        assert result.status == ProjectStatus.approved
        mock_session.commit.assert_called_once()

    def test_approve_non_proposed_project_fails(self, project_manager, mock_session):
        """Test that approving non-proposed project raises error."""
        # Mock project in wrong state
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.in_progress

        mock_session.query().filter().first.return_value = mock_project

        # Should raise ValueError
        with pytest.raises(ValueError, match="cannot be approved"):
            project_manager.approve_project("project-1", session=mock_session)

    def test_start_approved_project(self, project_manager, mock_session):
        """Test starting an approved project."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.approved

        mock_session.query().filter().first.return_value = mock_project

        result = project_manager.start_project("project-1", session=mock_session)

        assert result.status == ProjectStatus.in_progress
        assert result.started_at is not None
        mock_session.commit.assert_called_once()

    def test_start_non_approved_project_fails(self, project_manager, mock_session):
        """Test that starting non-approved project raises error."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.proposed

        mock_session.query().filter().first.return_value = mock_project

        with pytest.raises(ValueError, match="cannot be started"):
            project_manager.start_project("project-1", session=mock_session)

    def test_complete_in_progress_project(self, project_manager, mock_session):
        """Test completing an in-progress project."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.in_progress
        mock_project.goal_id = None

        mock_session.query().filter().first.return_value = mock_project

        result = project_manager.complete_project("project-1", session=mock_session)

        assert result.status == ProjectStatus.completed
        assert result.completed_at is not None
        mock_session.commit.assert_called()

    def test_complete_marks_goal_completed(self, project_manager, mock_session):
        """Test that completing project also completes associated goal."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.status = ProjectStatus.in_progress
        mock_project.goal_id = "goal-1"

        mock_goal = MagicMock()
        mock_goal.id = "goal-1"
        mock_goal.status = GoalStatus.approved

        # First call returns project, second returns goal
        mock_session.query().filter().first.side_effect = [mock_project, mock_goal]

        result = project_manager.complete_project("project-1", session=mock_session)

        assert result.status == ProjectStatus.completed
        assert mock_goal.status == GoalStatus.completed


class TestBudgetEnforcement:
    """Test budget allocation and enforcement."""

    def test_record_cost_within_budget(self, project_manager, mock_session):
        """Test recording cost within allocated budget."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.budget_allocated = Decimal("10.00")
        mock_project.budget_spent = Decimal("5.00")

        mock_session.query().filter().first.return_value = mock_project

        result = project_manager.record_cost("project-1", 3.00, session=mock_session)

        assert result.budget_spent == Decimal("8.00")
        mock_session.commit.assert_called_once()

    def test_record_cost_exceeds_budget_fails(self, project_manager, mock_session):
        """Test that exceeding budget raises error."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.budget_allocated = Decimal("10.00")
        mock_project.budget_spent = Decimal("8.00")

        mock_session.query().filter().first.return_value = mock_project

        with pytest.raises(ValueError, match="would exceed project budget"):
            project_manager.record_cost("project-1", 5.00, session=mock_session)

    def test_record_cost_exact_budget(self, project_manager, mock_session):
        """Test recording cost that exactly meets budget."""
        mock_project = MagicMock()
        mock_project.id = "project-1"
        mock_project.budget_allocated = Decimal("10.00")
        mock_project.budget_spent = Decimal("7.00")

        mock_session.query().filter().first.return_value = mock_project

        result = project_manager.record_cost("project-1", 3.00, session=mock_session)

        assert result.budget_spent == Decimal("10.00")
        mock_session.commit.assert_called_once()


class TestGoalStateTransitions:
    """Test goal approval/rejection."""

    def test_approve_identified_goal(self, project_manager, mock_session):
        """Test approving an identified goal."""
        mock_goal = MagicMock()
        mock_goal.id = "goal-1"
        mock_goal.status = GoalStatus.identified

        mock_session.query().filter().first.return_value = mock_goal

        result = project_manager.approve_goal("goal-1", "user-1", session=mock_session)

        assert result.status == GoalStatus.approved
        assert result.approved_by == "user-1"
        assert result.approved_at is not None
        mock_session.commit.assert_called_once()

    def test_reject_identified_goal(self, project_manager, mock_session):
        """Test rejecting an identified goal."""
        mock_goal = MagicMock()
        mock_goal.id = "goal-1"
        mock_goal.status = GoalStatus.identified

        mock_session.query().filter().first.return_value = mock_goal

        result = project_manager.reject_goal("goal-1", session=mock_session)

        assert result.status == GoalStatus.rejected
        mock_session.commit.assert_called_once()

    def test_approve_non_identified_goal_fails(self, project_manager, mock_session):
        """Test that approving non-identified goal raises error."""
        mock_goal = MagicMock()
        mock_goal.id = "goal-1"
        mock_goal.status = GoalStatus.approved

        mock_session.query().filter().first.return_value = mock_goal

        with pytest.raises(ValueError, match="cannot be approved"):
            project_manager.approve_goal("goal-1", "user-1", session=mock_session)


class TestTaskStateTransitions:
    """Test task state transitions."""

    def test_start_pending_task(self, project_manager, mock_session):
        """Test starting a pending task."""
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.status = TaskStatus.pending

        mock_session.query().filter().first.return_value = mock_task

        result = project_manager.start_task("task-1", session=mock_session)

        assert result.status == TaskStatus.in_progress
        assert result.started_at is not None
        mock_session.commit.assert_called_once()

    def test_complete_in_progress_task(self, project_manager, mock_session):
        """Test completing an in-progress task."""
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.status = TaskStatus.in_progress

        mock_session.query().filter().first.return_value = mock_task

        result = project_manager.complete_task(
            "task-1", result={"output": "success"}, session=mock_session
        )

        assert result.status == TaskStatus.completed
        assert result.completed_at is not None
        assert result.result == {"output": "success"}
        mock_session.commit.assert_called_once()

    def test_fail_task_with_error(self, project_manager, mock_session):
        """Test marking task as failed."""
        mock_task = MagicMock()
        mock_task.id = "task-1"
        mock_task.status = TaskStatus.in_progress

        mock_session.query().filter().first.return_value = mock_task

        result = project_manager.fail_task(
            "task-1", error="API timeout", session=mock_session
        )

        assert result.status == TaskStatus.failed
        assert result.result == {"error": "API timeout"}
        mock_session.commit.assert_called_once()
