"""
Unit tests for TaskScheduler critical paths.

Tests dependency resolution, topological sorting, and priority-based execution.
"""

import pytest
from unittest.mock import MagicMock

from common.db.models import TaskStatus, TaskPriority
from brain.projects.task_scheduler import TaskScheduler


@pytest.fixture
def scheduler():
    """TaskScheduler instance."""
    return TaskScheduler()


def create_mock_task(
    task_id: str,
    status: TaskStatus = TaskStatus.pending,
    priority: TaskPriority = TaskPriority.medium,
    depends_on: str = None,
    title: str = None,
):
    """Helper to create mock task."""
    task = MagicMock()
    task.id = task_id
    task.status = status
    task.priority = priority
    task.depends_on = depends_on
    task.title = title or f"Task {task_id}"
    return task


class TestExecutableTasks:
    """Test identification of executable tasks."""

    def test_no_dependencies_all_executable(self, scheduler):
        """Test that tasks with no dependencies are all executable."""
        tasks = [
            create_mock_task("task-1"),
            create_mock_task("task-2"),
            create_mock_task("task-3"),
        ]

        executable = scheduler.get_executable_tasks(tasks)

        assert len(executable) == 3
        assert set(t.id for t in executable) == {"task-1", "task-2", "task-3"}

    def test_blocked_by_dependency(self, scheduler):
        """Test that tasks with unmet dependencies are not executable."""
        tasks = [
            create_mock_task("task-1"),  # No dependency, pending
            create_mock_task("task-2", depends_on="task-1"),  # Blocked by task-1
        ]

        executable = scheduler.get_executable_tasks(tasks)

        assert len(executable) == 1
        assert executable[0].id == "task-1"

    def test_dependency_completed_makes_executable(self, scheduler):
        """Test that completing dependency makes task executable."""
        tasks = [
            create_mock_task("task-1", status=TaskStatus.completed),
            create_mock_task("task-2", depends_on="task-1"),  # Now executable
        ]

        executable = scheduler.get_executable_tasks(tasks)

        assert len(executable) == 1
        assert executable[0].id == "task-2"

    def test_in_progress_tasks_not_executable(self, scheduler):
        """Test that in-progress tasks are not returned."""
        tasks = [
            create_mock_task("task-1", status=TaskStatus.in_progress),
            create_mock_task("task-2", status=TaskStatus.pending),
        ]

        executable = scheduler.get_executable_tasks(tasks)

        assert len(executable) == 1
        assert executable[0].id == "task-2"

    def test_priority_ordering(self, scheduler):
        """Test that tasks are ordered by priority."""
        tasks = [
            create_mock_task("task-low", priority=TaskPriority.low),
            create_mock_task("task-critical", priority=TaskPriority.critical),
            create_mock_task("task-medium", priority=TaskPriority.medium),
            create_mock_task("task-high", priority=TaskPriority.high),
        ]

        executable = scheduler.get_executable_tasks(tasks)

        # Should be ordered: critical, high, medium, low
        assert executable[0].id == "task-critical"
        assert executable[1].id == "task-high"
        assert executable[2].id == "task-medium"
        assert executable[3].id == "task-low"


class TestTopologicalSort:
    """Test dependency resolution via topological sorting."""

    def test_simple_dependency_chain(self, scheduler):
        """Test execution order for simple chain: A → B → C."""
        tasks = [
            create_mock_task("task-c", depends_on="task-b"),
            create_mock_task("task-a"),  # No dependency
            create_mock_task("task-b", depends_on="task-a"),
        ]

        ordered = scheduler.get_execution_order(tasks)

        # Extract IDs
        order = [t.id for t in ordered]

        # task-a must come before task-b, task-b before task-c
        assert order.index("task-a") < order.index("task-b")
        assert order.index("task-b") < order.index("task-c")

    def test_parallel_tasks(self, scheduler):
        """Test parallel tasks (no dependencies between them)."""
        tasks = [
            create_mock_task("task-1"),
            create_mock_task("task-2"),
            create_mock_task("task-3"),
        ]

        ordered = scheduler.get_execution_order(tasks)

        # All should be returned, order doesn't matter
        assert len(ordered) == 3

    def test_diamond_dependency(self, scheduler):
        """Test diamond dependency: A → B,C → D."""
        tasks = [
            create_mock_task("task-a"),  # Root
            create_mock_task("task-b", depends_on="task-a"),
            create_mock_task("task-c", depends_on="task-a"),
            create_mock_task("task-d", depends_on="task-b"),  # Could also depend on C
        ]

        ordered = scheduler.get_execution_order(tasks)
        order = [t.id for t in ordered]

        # task-a must be first
        assert order.index("task-a") < order.index("task-b")
        assert order.index("task-a") < order.index("task-c")
        # task-b must come before task-d
        assert order.index("task-b") < order.index("task-d")

    def test_circular_dependency_detected(self, scheduler):
        """Test that circular dependencies raise ValueError."""
        tasks = [
            create_mock_task("task-a", depends_on="task-b"),
            create_mock_task("task-b", depends_on="task-a"),  # Circular!
        ]

        with pytest.raises(ValueError, match="Circular dependency"):
            scheduler.get_execution_order(tasks)

    def test_complex_dag(self, scheduler):
        """Test complex DAG with multiple paths."""
        tasks = [
            create_mock_task("task-1"),  # Root
            create_mock_task("task-2", depends_on="task-1"),
            create_mock_task("task-3", depends_on="task-1"),
            create_mock_task("task-4", depends_on="task-2"),
            create_mock_task("task-5", depends_on="task-3"),
            create_mock_task("task-6", depends_on="task-4"),
            create_mock_task("task-7", depends_on="task-5"),
        ]

        ordered = scheduler.get_execution_order(tasks)
        order = [t.id for t in ordered]

        # Validate dependencies
        assert order.index("task-1") < order.index("task-2")
        assert order.index("task-1") < order.index("task-3")
        assert order.index("task-2") < order.index("task-4")
        assert order.index("task-3") < order.index("task-5")
        assert order.index("task-4") < order.index("task-6")
        assert order.index("task-5") < order.index("task-7")


class TestDependencyValidation:
    """Test dependency validation logic."""

    def test_valid_dependencies(self, scheduler):
        """Test that valid dependencies pass validation."""
        tasks = [
            create_mock_task("task-1"),
            create_mock_task("task-2", depends_on="task-1"),
        ]

        issues = scheduler.validate_dependencies(tasks)

        assert len(issues) == 0

    def test_invalid_dependency_reference(self, scheduler):
        """Test detection of invalid dependency reference."""
        tasks = [
            create_mock_task("task-1", depends_on="nonexistent-task"),
        ]

        issues = scheduler.validate_dependencies(tasks)

        assert "task-1" in issues
        assert any("does not exist" in issue for issue in issues["task-1"])

    def test_self_dependency_detected(self, scheduler):
        """Test detection of self-dependency."""
        tasks = [
            create_mock_task("task-1", depends_on="task-1"),  # Self-dependency
        ]

        issues = scheduler.validate_dependencies(tasks)

        assert "task-1" in issues
        assert any("cannot depend on itself" in issue for issue in issues["task-1"])

    def test_circular_dependency_detected_in_validation(self, scheduler):
        """Test that validation detects circular dependencies."""
        tasks = [
            create_mock_task("task-a", depends_on="task-b"),
            create_mock_task("task-b", depends_on="task-a"),
        ]

        issues = scheduler.validate_dependencies(tasks)

        # Both tasks should be flagged
        assert "task-a" in issues or "task-b" in issues


class TestNextTask:
    """Test next task selection."""

    def test_get_next_task_highest_priority(self, scheduler):
        """Test that next task returns highest priority."""
        tasks = [
            create_mock_task("task-low", priority=TaskPriority.low),
            create_mock_task("task-critical", priority=TaskPriority.critical),
            create_mock_task("task-medium", priority=TaskPriority.medium),
        ]

        next_task = scheduler.get_next_task(tasks)

        assert next_task.id == "task-critical"

    def test_get_next_task_skips_current(self, scheduler):
        """Test that next task skips currently executing task."""
        tasks = [
            create_mock_task("task-1", priority=TaskPriority.critical),
            create_mock_task("task-2", priority=TaskPriority.high),
        ]

        next_task = scheduler.get_next_task(tasks, current_task_id="task-1")

        assert next_task.id == "task-2"

    def test_get_next_task_no_executable(self, scheduler):
        """Test that next task returns None if no tasks executable."""
        tasks = [
            create_mock_task("task-1", status=TaskStatus.completed),
            create_mock_task("task-2", status=TaskStatus.in_progress),
        ]

        next_task = scheduler.get_next_task(tasks)

        assert next_task is None


class TestTaskStatistics:
    """Test task statistics calculation."""

    def test_statistics_counts(self, scheduler):
        """Test that statistics correctly count tasks."""
        tasks = [
            create_mock_task("task-1", status=TaskStatus.pending, priority=TaskPriority.high),
            create_mock_task("task-2", status=TaskStatus.in_progress, priority=TaskPriority.medium),
            create_mock_task("task-3", status=TaskStatus.completed, priority=TaskPriority.low),
            create_mock_task("task-4", status=TaskStatus.pending, depends_on="task-2"),
        ]

        stats = scheduler.get_task_statistics(tasks)

        assert stats["total"] == 4
        assert stats["by_status"]["pending"] == 2
        assert stats["by_status"]["in_progress"] == 1
        assert stats["by_status"]["completed"] == 1
        assert stats["by_priority"]["high"] == 1
        assert stats["by_priority"]["medium"] == 1
        assert stats["by_priority"]["low"] == 1
        assert stats["blocked_by_dependencies"] == 1
        assert stats["executable"] == 1  # Only task-1 is executable
