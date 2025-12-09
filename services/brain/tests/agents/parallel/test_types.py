"""
Tests for parallel agent types: ModelTier, TaskStatus, KittyTask, AgentExecutionMetrics.
"""

import time
from datetime import datetime, timezone

import pytest

from brain.agents.parallel.types import (
    ModelTier,
    TaskStatus,
    KittyTask,
    AgentExecutionMetrics,
)


class TestModelTier:
    """Tests for ModelTier enum."""

    def test_enum_has_all_tiers(self):
        """All 6 model tiers should exist."""
        tiers = list(ModelTier)
        assert len(tiers) == 6

        expected = {"q4_tools", "gptoss_reason", "vision", "coder", "summary", "mcp_external"}
        actual = {t.value for t in tiers}
        assert actual == expected

    def test_tier_values_are_strings(self):
        """All tier values should be lowercase strings."""
        for tier in ModelTier:
            assert isinstance(tier.value, str)
            assert tier.value == tier.value.lower()

    def test_q4_tools_is_default_orchestrator(self):
        """Q4_TOOLS should be the fast tool calling tier."""
        assert ModelTier.Q4_TOOLS.value == "q4_tools"

    def test_gptoss_is_reasoning_tier(self):
        """GPTOSS_REASON should be the deep reasoning tier."""
        assert ModelTier.GPTOSS_REASON.value == "gptoss_reason"


class TestTaskStatus:
    """Tests for TaskStatus enum."""

    def test_all_statuses_exist(self):
        """All 5 task statuses should exist."""
        statuses = list(TaskStatus)
        assert len(statuses) == 5

        expected = {"pending", "in_progress", "completed", "failed", "skipped"}
        actual = {s.value for s in statuses}
        assert actual == expected

    def test_pending_is_initial_state(self):
        """PENDING should be the initial state."""
        assert TaskStatus.PENDING.value == "pending"

    def test_terminal_states(self):
        """COMPLETED, FAILED, SKIPPED are terminal states."""
        terminals = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED}
        for status in terminals:
            assert status in TaskStatus


class TestKittyTask:
    """Tests for KittyTask dataclass."""

    def test_initialization_defaults(self):
        """Task should initialize with sensible defaults."""
        task = KittyTask(
            id="test_1",
            description="Test task",
            assigned_to="researcher",
        )

        assert task.id == "test_1"
        assert task.description == "Test task"
        assert task.assigned_to == "researcher"
        assert task.status == TaskStatus.PENDING
        assert task.dependencies == []
        assert task.result is None
        assert task.error is None
        assert task.started_at is None
        assert task.completed_at is None
        assert task.latency_ms == 0
        assert task.tokens_used == 0
        assert task.cost_usd == 0.0
        assert task.model_used == ""
        assert task.fallback_used is False

    def test_initialization_with_dependencies(self):
        """Task should accept dependencies list."""
        task = KittyTask(
            id="test_2",
            description="Dependent task",
            assigned_to="reasoner",
            dependencies=["task_1", "task_3"],
        )

        assert task.dependencies == ["task_1", "task_3"]

    def test_mark_started(self):
        """mark_started should set status and timestamp."""
        task = KittyTask(id="t1", description="Test", assigned_to="test")

        assert task.status == TaskStatus.PENDING
        assert task.started_at is None

        task.mark_started()

        assert task.status == TaskStatus.IN_PROGRESS
        assert task.started_at is not None
        assert isinstance(task.started_at, datetime)
        assert task.started_at.tzinfo == timezone.utc

    def test_mark_completed(self):
        """mark_completed should set result, status, and metrics."""
        task = KittyTask(id="t1", description="Test", assigned_to="test")
        task.mark_started()

        # Small delay to ensure measurable duration
        time.sleep(0.01)

        task.mark_completed(result="Success!", model="kitty-q4", tokens=150)

        assert task.status == TaskStatus.COMPLETED
        assert task.result == "Success!"
        assert task.model_used == "kitty-q4"
        assert task.tokens_used == 150
        assert task.completed_at is not None
        assert task.latency_ms > 0

    def test_mark_failed(self):
        """mark_failed should set error and status."""
        task = KittyTask(id="t1", description="Test", assigned_to="test")
        task.mark_started()

        task.mark_failed(error="Connection timeout")

        assert task.status == TaskStatus.FAILED
        assert task.error == "Connection timeout"
        assert task.completed_at is not None
        assert task.result is None

    def test_duration_ms_calculation(self):
        """duration_ms should calculate correctly from timestamps."""
        task = KittyTask(id="t1", description="Test", assigned_to="test")
        task.mark_started()

        # Wait a measurable amount
        time.sleep(0.05)

        task.mark_completed("Done", "model", 10)

        # Duration should be at least 50ms
        assert task.duration_ms >= 50

    def test_duration_ms_fallback(self):
        """duration_ms should fallback to latency_ms if no timestamps."""
        task = KittyTask(id="t1", description="Test", assigned_to="test", latency_ms=1234)

        assert task.duration_ms == 1234

    def test_is_ready(self):
        """is_ready should return True only for PENDING tasks."""
        task = KittyTask(id="t1", description="Test", assigned_to="test")
        assert task.is_ready is True

        task.mark_started()
        assert task.is_ready is False

        task.mark_completed("Done", "model", 10)
        assert task.is_ready is False

    def test_to_dict(self):
        """to_dict should serialize all fields."""
        task = KittyTask(
            id="t1",
            description="Test",
            assigned_to="researcher",
            dependencies=["t0"],
        )
        task.mark_started()
        task.mark_completed("Result", "kitty-q4", 100)

        d = task.to_dict()

        assert d["id"] == "t1"
        assert d["description"] == "Test"
        assert d["assigned_to"] == "researcher"
        assert d["status"] == "completed"
        assert d["dependencies"] == ["t0"]
        assert d["result"] == "Result"
        assert d["model_used"] == "kitty-q4"
        assert d["tokens_used"] == 100
        assert d["started_at"] is not None
        assert d["completed_at"] is not None


class TestAgentExecutionMetrics:
    """Tests for AgentExecutionMetrics dataclass."""

    def test_from_tasks_empty(self):
        """from_tasks should handle empty task list."""
        metrics = AgentExecutionMetrics.from_tasks(
            goal="Test goal",
            tasks=[],
            total_time=1.5,
            parallel_batches=0,
        )

        assert metrics.goal == "Test goal"
        assert metrics.total_time_seconds == 1.5
        assert metrics.task_count == 0
        assert metrics.completed_count == 0
        assert metrics.failed_count == 0
        assert metrics.total_tokens == 0
        assert metrics.avg_task_latency_ms == 0
        assert metrics.max_task_latency_ms == 0

    def test_from_tasks_with_completed(self):
        """from_tasks should aggregate completed task metrics."""
        # Create completed tasks
        t1 = KittyTask(id="t1", description="T1", assigned_to="researcher")
        t1.mark_started()
        t1.latency_ms = 100
        t1.tokens_used = 50
        t1.model_used = "kitty-q4"
        t1.status = TaskStatus.COMPLETED

        t2 = KittyTask(id="t2", description="T2", assigned_to="coder")
        t2.mark_started()
        t2.latency_ms = 200
        t2.tokens_used = 75
        t2.model_used = "kitty-coder"
        t2.status = TaskStatus.COMPLETED

        metrics = AgentExecutionMetrics.from_tasks(
            goal="Complex query",
            tasks=[t1, t2],
            total_time=0.5,
            parallel_batches=1,
        )

        assert metrics.task_count == 2
        assert metrics.completed_count == 2
        assert metrics.failed_count == 0
        assert metrics.total_tokens == 125
        assert metrics.avg_task_latency_ms == 150.0
        assert metrics.max_task_latency_ms == 200
        assert set(metrics.endpoints_used) == {"kitty-q4", "kitty-coder"}

    def test_from_tasks_with_failures(self):
        """from_tasks should count failed tasks."""
        t1 = KittyTask(id="t1", description="T1", assigned_to="researcher")
        t1.status = TaskStatus.COMPLETED

        t2 = KittyTask(id="t2", description="T2", assigned_to="coder")
        t2.status = TaskStatus.FAILED
        t2.error = "Timeout"

        metrics = AgentExecutionMetrics.from_tasks(
            goal="Partial failure",
            tasks=[t1, t2],
            total_time=2.0,
            parallel_batches=1,
        )

        assert metrics.completed_count == 1
        assert metrics.failed_count == 1

    def test_from_tasks_with_fallbacks(self):
        """from_tasks should count fallback usage."""
        t1 = KittyTask(id="t1", description="T1", assigned_to="researcher")
        t1.status = TaskStatus.COMPLETED
        t1.fallback_used = True

        t2 = KittyTask(id="t2", description="T2", assigned_to="coder")
        t2.status = TaskStatus.COMPLETED
        t2.fallback_used = False

        metrics = AgentExecutionMetrics.from_tasks(
            goal="With fallback",
            tasks=[t1, t2],
            total_time=1.0,
            parallel_batches=2,
        )

        assert metrics.fallback_count == 1
        assert metrics.parallel_batches == 2

    def test_to_dict(self):
        """to_dict should serialize all metrics."""
        metrics = AgentExecutionMetrics(
            goal="Test",
            total_time_seconds=5.5,
            total_tokens=500,
            total_cost_usd=0.01,
            task_count=3,
            completed_count=2,
            failed_count=1,
            parallel_batches=2,
            avg_task_latency_ms=150.5,
            max_task_latency_ms=300,
            endpoints_used=["kitty-q4", "kitty-coder"],
            fallback_count=1,
        )

        d = metrics.to_dict()

        assert d["goal"] == "Test"
        assert d["total_time_seconds"] == 5.5
        assert d["total_tokens"] == 500
        assert d["task_count"] == 3
        assert d["completed_count"] == 2
        assert d["failed_count"] == 1
        assert d["parallel_batches"] == 2
        assert d["fallback_count"] == 1
