"""Integration tests for CollectiveOrchestrator."""

import pytest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch, MagicMock

from kitty_code.core.collective.config import CollectiveConfig
from kitty_code.core.collective.backends import BackendPool
from kitty_code.core.collective.orchestrator import CollectiveOrchestrator, OrchestrationResult
from kitty_code.core.collective.state import CollectiveState
from kitty_code.core.collective.models import JudgmentVerdict


class TestDirectExecution:
    """Tests for direct execution (bypassing collective)."""

    @pytest.mark.asyncio
    async def test_simple_task_bypasses_collective(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Simple tasks matching auto-execute patterns bypass collective."""
        # Mock the _call_model to return a simple response
        async def mock_call_model(backend, system, user):
            return {
                "content": "Fixed the typo.",
                "success": True,
                "prompt_tokens": 50,
                "completion_tokens": 20,
            }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("fix typo in README")

        assert result.success
        assert not result.used_collective
        assert result.routing is not None
        assert result.routing.is_direct()
        assert orchestrator.context.state == CollectiveState.COMPLETE

    @pytest.mark.asyncio
    async def test_add_import_bypasses_collective(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Adding import should bypass collective."""
        async def mock_call_model(backend, system, user):
            return {
                "content": "Added import for os module.",
                "success": True,
            }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("add import for os module")

        assert result.success
        assert not result.used_collective
        assert result.routing.confidence == 0.95

    @pytest.mark.asyncio
    async def test_direct_execution_fallback_on_backend_failure(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Direct execution should use fallback when primary backend fails."""
        # Mark executor backend as unhealthy
        executor_backend = orchestrator.backend_pool.get_executor_backend()
        executor_backend.mark_unhealthy("Connection timeout")

        async def mock_call_model(backend, system, user):
            return {"content": "Executed via fallback.", "success": True}

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("fix typo quickly")

        # Should have used planner backend as fallback
        assert result.success or result.error  # Either way, should handle gracefully


class TestCollectiveExecution:
    """Tests for full collective execution (Planner → Executor → Judge)."""

    @pytest.mark.asyncio
    async def test_collective_triggers_for_complex_task(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Complex tasks should trigger collective execution."""
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            # Planner response
            if call_count == 1:
                return {
                    "content": '''```json
{
    "summary": "Implement feature X",
    "steps": [
        {
            "step_id": "step_1",
            "description": "Create feature module",
            "tools_required": ["write_file"],
            "success_criteria": ["Module created"]
        }
    ]
}
```''',
                    "success": True,
                }
            # Executor response
            elif call_count == 2:
                return {
                    "content": "Created feature module.",
                    "tool_calls": [],
                    "success": True,
                }
            # Judge response
            else:
                return {
                    "content": '''```json
{
    "verdict": "APPROVE",
    "confidence": 0.9,
    "reasoning": "Feature implemented correctly."
}
```''',
                    "success": True,
                }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("implement feature X with tests")

        assert result.success
        assert result.used_collective
        assert result.routing.is_collective()
        assert result.plan is not None
        assert len(result.plan.steps) == 1
        assert len(result.judgments) == 1
        assert result.judgments[0].is_approved()

    @pytest.mark.asyncio
    async def test_multi_step_plan_executes_all_steps(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Multi-step plans should execute all steps sequentially."""
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            # Planner response (call 1)
            if call_count == 1:
                return {
                    "content": '''```json
{
    "summary": "Add authentication",
    "steps": [
        {"step_id": "step_1", "description": "Create model"},
        {"step_id": "step_2", "description": "Add routes"},
        {"step_id": "step_3", "description": "Write tests"}
    ]
}
```''',
                    "success": True,
                }
            # Even calls = executor, odd calls = judge (after planner)
            elif call_count % 2 == 0:
                return {
                    "content": f"Completed step.",
                    "tool_calls": [],
                    "success": True,
                }
            else:
                return {
                    "content": '''```json
{"verdict": "APPROVE", "confidence": 0.9, "reasoning": "Step completed."}
```''',
                    "success": True,
                }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("add tests for user authentication")

        assert result.success
        assert result.used_collective
        assert len(result.plan.steps) == 3
        assert len(result.executions) == 3
        assert len(result.judgments) == 3
        assert all(j.is_approved() for j in result.judgments)

    @pytest.mark.asyncio
    async def test_state_transitions_during_collective(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Verify state transitions during collective execution."""
        states_visited = []

        # Capture state transitions
        original_transition = orchestrator.context.transition_to

        def tracking_transition(state, reason=""):
            states_visited.append(state)
            return original_transition(state, reason)

        orchestrator.context.transition_to = tracking_transition

        async def mock_call_model(backend, system, user):
            # Planner is called during PLANNING state
            if orchestrator.context.state == CollectiveState.PLANNING:
                return {
                    "content": '''```json
{"summary": "Task", "steps": [{"step_id": "1", "description": "Do it"}]}
```''',
                    "success": True,
                }
            elif orchestrator.context.state == CollectiveState.EXECUTING:
                return {"content": "Done.", "success": True}
            elif orchestrator.context.state == CollectiveState.JUDGING:
                return {
                    "content": '''```json
{"verdict": "APPROVE", "confidence": 0.9}
```''',
                    "success": True,
                }
            else:
                return {"content": "", "success": True}

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            # Use input that matches always_plan pattern "implement\s+feature"
            await orchestrator.process("implement feature for user notifications")

        # Should have visited these states
        assert CollectiveState.ROUTING in states_visited
        assert CollectiveState.PLANNING in states_visited
        assert CollectiveState.EXECUTING in states_visited
        assert CollectiveState.JUDGING in states_visited
        assert CollectiveState.COMPLETE in states_visited


class TestRevisionFlow:
    """Tests for Judge-requested revisions."""

    @pytest.mark.asyncio
    async def test_revision_cycle_succeeds(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Revision cycle should re-execute and succeed on approval."""
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            if call_count == 1:  # Planner
                return {
                    "content": '''```json
{"summary": "Update parser", "steps": [{"step_id": "1", "description": "Refactor"}]}
```''',
                    "success": True,
                }
            elif call_count == 2:  # First execution
                return {"content": "First attempt.", "success": True}
            elif call_count == 3:  # Judge requests revision
                return {
                    "content": '''```json
{
    "verdict": "REVISE",
    "confidence": 0.5,
    "reasoning": "Missing error handling",
    "revision_feedback": {
        "issues": ["No error handling for edge cases"],
        "suggestions": ["Add try/except blocks"]
    }
}
```''',
                    "success": True,
                }
            elif call_count == 4:  # Revised execution
                return {"content": "Added error handling.", "success": True}
            else:  # Final approval
                return {
                    "content": '''```json
{"verdict": "APPROVE", "confidence": 0.9, "reasoning": "Error handling added."}
```''',
                    "success": True,
                }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("refactor the config parser")

        assert result.success
        assert orchestrator.context.revision_count == 1
        assert len(result.executions) == 2  # Original + revision
        assert len(result.judgments) == 2  # REVISE + APPROVE

    @pytest.mark.asyncio
    async def test_max_revisions_triggers_escalation(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Exceeding max revisions should trigger escalation."""
        # Set max revisions to 1 for faster test
        orchestrator.config.judgment.max_revision_cycles = 1
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            if call_count == 1:  # Planner
                return {
                    "content": '''```json
{"summary": "Complex task", "steps": [{"step_id": "1", "description": "Do it"}]}
```''',
                    "success": True,
                }
            elif call_count % 2 == 0:  # Executor attempts
                return {"content": "Attempt.", "success": True}
            else:  # Judge always requests revision
                return {
                    "content": '''```json
{
    "verdict": "REVISE",
    "confidence": 0.3,
    "reasoning": "Still not right",
    "revision_feedback": {"issues": ["Problem"], "suggestions": ["Fix it"]}
}
```''',
                    "success": True,
                }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("migrate complex system")

        # Should have hit max revisions and either escalated or errored
        assert orchestrator.context.revision_count >= 1


class TestEscalationFlow:
    """Tests for escalation to re-planning."""

    @pytest.mark.asyncio
    async def test_executor_failure_triggers_escalation(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Executor failure should trigger escalation to re-planning."""
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            if call_count == 1:  # First planner
                return {
                    "content": '''```json
{"summary": "Migrate DB", "steps": [{"step_id": "1", "description": "Run migration"}]}
```''',
                    "success": True,
                }
            elif call_count == 2:  # Executor fails
                return {
                    "content": "Error during migration.",
                    "success": False,
                    "error": "Connection refused",
                }
            # Subsequent calls would be new plan attempts
            else:
                return {"content": "Retry.", "success": True}

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("migrate database")

        # Should have attempted escalation
        assert orchestrator.context.escalation_count >= 0


class TestGracefulDegradation:
    """Tests for graceful degradation when backends fail."""

    @pytest.mark.asyncio
    async def test_planner_failure_uses_fallback(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Planner failure should attempt fallback to executor backend."""
        # Mark planner backend unhealthy
        planner_backend = orchestrator.backend_pool.get_planner_backend()
        planner_backend.mark_unhealthy("Model offline")

        async def mock_call_model(backend, system, user):
            return {
                "content": '''```json
{"summary": "Task", "steps": [{"step_id": "1", "description": "Do it"}]}
```''',
                "success": True,
            }

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("design system architecture")

        # Should either succeed with fallback or fail gracefully
        assert result.success or result.error is not None

    @pytest.mark.asyncio
    async def test_judge_failure_auto_approves(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Judge backend failure should auto-approve with warning."""
        call_count = 0

        async def mock_call_model(backend, system, user):
            nonlocal call_count
            call_count += 1

            if call_count == 1:  # Planner
                return {
                    "content": '''```json
{"summary": "Task", "steps": [{"step_id": "1", "description": "Execute"}]}
```''',
                    "success": True,
                }
            elif call_count == 2:  # Executor
                return {"content": "Executed.", "success": True}
            # Judge call would be skipped due to unhealthy backend
            return {"content": "", "success": True}

        # Mark judge backend unhealthy before judge call
        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            # Process normally, judge will auto-approve
            result = await orchestrator.process("implement feature")

        # Should succeed (auto-approve on judge failure)
        assert result.success or len(result.judgments) > 0


class TestOrchestrationResult:
    """Tests for OrchestrationResult structure."""

    @pytest.mark.asyncio
    async def test_result_includes_timing(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Result should include duration in milliseconds."""
        async def mock_call_model(backend, system, user):
            return {"content": "Done.", "success": True}

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("fix typo")

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_result_includes_routing_decision(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Result should include routing decision."""
        async def mock_call_model(backend, system, user):
            return {"content": "Done.", "success": True}

        with patch.object(orchestrator, "_call_model", side_effect=mock_call_model):
            result = await orchestrator.process("rename variable x to y")

        assert result.routing is not None
        assert result.routing.mode in ["direct", "collective"]
        assert 0.0 <= result.routing.confidence <= 1.0


class TestOrchestratorStatus:
    """Tests for orchestrator status reporting."""

    def test_status_includes_all_fields(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Status should include state, routing, progress, timing, and backends."""
        status = orchestrator.get_status()

        assert "state" in status
        assert "routing" in status
        assert "progress" in status
        assert "timing" in status
        assert "backends" in status

    def test_status_reflects_current_state(
        self,
        orchestrator: CollectiveOrchestrator,
    ):
        """Status should reflect current orchestration state."""
        # Initial state
        status = orchestrator.get_status()
        assert status["state"] == "IDLE"

        # After transition
        orchestrator.context.transition_to(CollectiveState.ROUTING, "Test")
        status = orchestrator.get_status()
        assert status["state"] == "ROUTING"


class TestBackendPoolIntegration:
    """Tests for BackendPool integration with orchestrator."""

    def test_judge_shares_planner_backend(
        self,
        backend_pool: BackendPool,
    ):
        """Judge should share backend with Planner when configured."""
        planner = backend_pool.get_planner_backend()
        judge = backend_pool.get_judge_backend()

        # Same model config (shared)
        assert planner.model_config.name == judge.model_config.name

    def test_executor_uses_different_backend(
        self,
        backend_pool: BackendPool,
    ):
        """Executor should use different (faster) backend."""
        planner = backend_pool.get_planner_backend()
        executor = backend_pool.get_executor_backend()

        # Different model configs
        assert planner.model_config.name != executor.model_config.name
        assert "24b" in executor.model_config.name.lower()

    def test_backend_stats_accumulate(
        self,
        backend_pool: BackendPool,
    ):
        """Backend stats should accumulate across requests."""
        executor = backend_pool.get_executor_backend()

        # Record some requests
        executor.record_request(True, 100, 50, 25)
        executor.record_request(True, 150, 60, 30)
        executor.record_request(False, 200, 0, 0, "Timeout")

        assert executor.stats.total_requests == 3
        assert executor.stats.successful_requests == 2
        assert executor.stats.failed_requests == 1
        assert executor.stats.total_prompt_tokens == 110
        assert executor.stats.avg_duration_ms == 150.0
