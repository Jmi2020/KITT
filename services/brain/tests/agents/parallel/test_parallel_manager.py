"""
Tests for ParallelTaskManager: decomposition, parallel execution, and synthesis.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agents.parallel.types import ModelTier, TaskStatus, KittyTask
from brain.agents.parallel.registry import KittyAgent, KITTY_AGENTS
from brain.agents.parallel.parallel_manager import (
    ParallelTaskManager,
    get_task_manager,
    reset_task_manager,
)


class TestParallelTaskManagerInit:
    """Tests for manager initialization."""

    def test_init_defaults(self):
        """Should initialize with default agents and settings."""
        manager = ParallelTaskManager()

        assert manager.agents == KITTY_AGENTS
        assert manager.max_parallel >= 1
        assert manager._tasks == {}
        assert manager._execution_log == []

    def test_init_custom_agents(self, mock_agent):
        """Should accept custom agent registry."""
        custom_agents = {"custom": mock_agent}
        manager = ParallelTaskManager(agents=custom_agents)

        assert manager.agents == custom_agents

    def test_init_custom_max_parallel(self, monkeypatch):
        """Should read max_parallel from env."""
        monkeypatch.setenv("PARALLEL_AGENT_MAX_CONCURRENT", "4")
        manager = ParallelTaskManager()

        assert manager.max_parallel == 4


class TestDecomposeGoal:
    """Tests for goal decomposition."""

    @pytest.mark.asyncio
    async def test_decompose_creates_tasks(self, mock_endpoints, mock_httpx_client):
        """Should create task list from goal."""
        # Mock LLM response with valid JSON
        mock_httpx_client.post = AsyncMock(return_value=AsyncMock(
            status_code=200,
            json=MagicMock(return_value={
                "content": '''[
                    {"id": "task_1", "description": "Research quantum computing", "assigned_to": "researcher", "dependencies": []},
                    {"id": "task_2", "description": "Analyze findings", "assigned_to": "analyst", "dependencies": ["task_1"]}
                ]''',
                "tokens_predicted": 100,
                "tokens_evaluated": 50,
            }),
        ))

        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        tasks = await manager.decompose_goal("Research quantum computing and analyze")

        assert len(tasks) >= 1
        assert all(isinstance(t, KittyTask) for t in tasks)

    @pytest.mark.asyncio
    async def test_decompose_fallback_on_parse_error(self, mock_endpoints, mock_httpx_client):
        """Should use fallback tasks when JSON parsing fails."""
        # Mock LLM response with invalid JSON
        mock_httpx_client.post = AsyncMock(return_value=AsyncMock(
            status_code=200,
            json=MagicMock(return_value={
                "content": "This is not valid JSON",
                "tokens_predicted": 50,
                "tokens_evaluated": 20,
            }),
        ))

        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        tasks = await manager.decompose_goal("Research something")

        # Should have fallback tasks
        assert len(tasks) >= 2
        assert any(t.assigned_to == "researcher" for t in tasks)


class TestCreateFallbackTasks:
    """Tests for fallback task generation."""

    def test_fallback_code_goal(self):
        """Should create code-focused tasks for code goals."""
        manager = ParallelTaskManager()

        tasks = manager._create_fallback_tasks("Implement a Python script for sorting")

        assert len(tasks) == 3
        assert tasks[0].assigned_to == "researcher"
        assert tasks[1].assigned_to == "coder"
        assert tasks[2].assigned_to == "reasoner"
        assert "task_1" in tasks[2].dependencies

    def test_fallback_design_goal(self):
        """Should create CAD-focused tasks for design goals."""
        manager = ParallelTaskManager()

        tasks = manager._create_fallback_tasks("Design a 3D printed phone stand")

        assert len(tasks) == 3
        assert tasks[0].assigned_to == "researcher"
        assert tasks[1].assigned_to == "cad_designer"
        assert tasks[2].assigned_to == "fabricator"

    def test_fallback_general_goal(self):
        """Should create research-focused tasks for general goals."""
        manager = ParallelTaskManager()

        tasks = manager._create_fallback_tasks("Tell me about climate change")

        assert len(tasks) == 3
        assert tasks[0].assigned_to == "researcher"
        assert tasks[1].assigned_to == "analyst"
        assert tasks[2].assigned_to == "reasoner"


class TestParseTasks:
    """Tests for task parsing from LLM response."""

    def test_parse_valid_json(self):
        """Should parse valid JSON array."""
        manager = ParallelTaskManager()

        response = '''Some text before
        [
            {"id": "t1", "description": "Task 1", "assigned_to": "researcher", "dependencies": []},
            {"id": "t2", "description": "Task 2", "assigned_to": "coder", "dependencies": ["t1"]}
        ]
        Some text after'''

        tasks = manager._parse_tasks(response, "Test goal")

        assert len(tasks) == 2
        assert tasks[0].id == "t1"
        assert tasks[1].dependencies == ["t1"]

    def test_parse_invalid_agent_fallback(self):
        """Should fallback to researcher for unknown agents."""
        manager = ParallelTaskManager()

        response = '[{"id": "t1", "description": "Task", "assigned_to": "unknown_agent", "dependencies": []}]'

        tasks = manager._parse_tasks(response, "Test")

        assert tasks[0].assigned_to == "researcher"

    def test_parse_max_6_tasks(self):
        """Should limit to 6 tasks maximum."""
        manager = ParallelTaskManager()

        # Create response with 10 tasks
        tasks_data = [
            {"id": f"t{i}", "description": f"Task {i}", "assigned_to": "researcher", "dependencies": []}
            for i in range(10)
        ]
        response = json.dumps(tasks_data)

        tasks = manager._parse_tasks(response, "Test")

        assert len(tasks) == 6


class TestExecuteParallel:
    """Tests for parallel task execution."""

    @pytest.mark.asyncio
    async def test_execute_independent_tasks_parallel(self, mock_endpoints, mock_httpx_client):
        """Should execute independent tasks in parallel."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        # Create 3 independent tasks
        tasks = [
            KittyTask(id="t1", description="Research", assigned_to="researcher"),
            KittyTask(id="t2", description="Code", assigned_to="coder"),
            KittyTask(id="t3", description="Analyze", assigned_to="analyst"),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        results = await manager.execute_parallel(tasks)

        assert len(results) == 3
        assert all(tid in results for tid in ["t1", "t2", "t3"])
        # All should complete (or fail gracefully)
        for task in tasks:
            assert task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

    @pytest.mark.asyncio
    async def test_execute_respects_dependencies(self, mock_endpoints, mock_httpx_client):
        """Should execute tasks in dependency order."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        # Task 3 depends on 1 and 2
        tasks = [
            KittyTask(id="t1", description="First", assigned_to="researcher"),
            KittyTask(id="t2", description="Second", assigned_to="coder"),
            KittyTask(id="t3", description="Third", assigned_to="reasoner", dependencies=["t1", "t2"]),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        results = await manager.execute_parallel(tasks)

        # Task 3 should have executed after 1 and 2
        assert "t3" in results

    @pytest.mark.asyncio
    async def test_execute_handles_task_failure(self, mock_endpoints, mock_httpx_error_client):
        """Should handle individual task failures gracefully."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_error_client

        manager = ParallelTaskManager(llm_client=llm_client)

        tasks = [
            KittyTask(id="t1", description="Will fail", assigned_to="researcher"),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        results = await manager.execute_parallel(tasks)

        # Should complete with failure marker
        assert "t1" in results
        assert "[Task failed:" in results["t1"]


class TestSynthesize:
    """Tests for result synthesis."""

    @pytest.mark.asyncio
    async def test_synthesize_combines_results(self, mock_endpoints, mock_httpx_client):
        """Should combine all task results."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        results = {
            "t1": "Research found quantum computing is complex",
            "t2": "Analysis shows practical applications",
        }

        output = await manager.synthesize("Research quantum computing", results)

        assert len(output) > 0

    @pytest.mark.asyncio
    async def test_synthesize_uses_gptoss_by_default(self, mock_endpoints, mock_httpx_client):
        """Should use GPTOSS tier for deep reasoning."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        await manager.synthesize("Goal", {"t1": "Result"}, use_deep_reasoning=True)

        # Verify it used Ollama endpoint (GPTOSS)
        call_args = mock_httpx_client.post.call_args
        url = call_args[0][0] if call_args[0] else ""
        # Should have called Ollama
        assert "11434" in url or "api/generate" in str(call_args)


class TestExecuteGoal:
    """Tests for full goal execution pipeline."""

    @pytest.mark.asyncio
    async def test_execute_goal_full_pipeline(self, mock_endpoints, mock_httpx_client):
        """Should execute full decompose -> execute -> synthesize pipeline."""
        # Mock LLM to return valid task decomposition
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            response = AsyncMock()
            response.status_code = 200
            response.raise_for_status = MagicMock()

            if call_count == 1:
                # Decomposition response
                response.json = MagicMock(return_value={
                    "content": '''[
                        {"id": "t1", "description": "Research", "assigned_to": "researcher", "dependencies": []}
                    ]''',
                    "tokens_predicted": 50,
                    "tokens_evaluated": 20,
                })
            else:
                # Task execution / synthesis response
                response.json = MagicMock(return_value={
                    "content": "Task result",
                    "response": "Synthesized output",
                    "tokens_predicted": 100,
                    "tokens_evaluated": 50,
                    "eval_count": 100,
                    "prompt_eval_count": 50,
                })

            return response

        mock_httpx_client.post = AsyncMock(side_effect=mock_post)

        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        manager = ParallelTaskManager(llm_client=llm_client)

        result = await manager.execute_goal(
            goal="Research and analyze quantum computing",
            include_summary=False,  # Skip voice summary for faster test
        )

        assert "goal" in result
        assert "tasks" in result
        assert "final_output" in result
        assert "metrics" in result
        assert result["metrics"]["task_count"] >= 1


class TestCountParallelBatches:
    """Tests for batch counting."""

    def test_count_all_parallel(self):
        """Should count 1 batch when all tasks are independent."""
        manager = ParallelTaskManager()

        tasks = [
            KittyTask(id="t1", description="A", assigned_to="researcher"),
            KittyTask(id="t2", description="B", assigned_to="coder"),
            KittyTask(id="t3", description="C", assigned_to="analyst"),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        batches = manager._count_parallel_batches(tasks)

        assert batches == 1

    def test_count_sequential(self):
        """Should count multiple batches for sequential dependencies."""
        manager = ParallelTaskManager()

        tasks = [
            KittyTask(id="t1", description="A", assigned_to="researcher"),
            KittyTask(id="t2", description="B", assigned_to="analyst", dependencies=["t1"]),
            KittyTask(id="t3", description="C", assigned_to="reasoner", dependencies=["t2"]),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        batches = manager._count_parallel_batches(tasks)

        assert batches == 3

    def test_count_mixed(self):
        """Should count correct batches for mixed dependencies."""
        manager = ParallelTaskManager()

        # t1, t2 parallel -> t3 depends on both
        tasks = [
            KittyTask(id="t1", description="A", assigned_to="researcher"),
            KittyTask(id="t2", description="B", assigned_to="coder"),
            KittyTask(id="t3", description="C", assigned_to="reasoner", dependencies=["t1", "t2"]),
        ]
        for t in tasks:
            manager._tasks[t.id] = t

        batches = manager._count_parallel_batches(tasks)

        assert batches == 2


class TestStatusAndCleanup:
    """Tests for status reporting and cleanup."""

    def test_get_status(self, mock_endpoints):
        """Should return current status."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient

        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)

        manager = ParallelTaskManager(llm_client=llm_client)

        status = manager.get_status()

        assert "tasks" in status
        assert "slots" in status
        assert "log" in status

    @pytest.mark.asyncio
    async def test_close(self):
        """Should close LLM client."""
        mock_llm = AsyncMock()
        mock_llm.get_slot_status = MagicMock(return_value={})

        manager = ParallelTaskManager(llm_client=mock_llm)

        await manager.close()

        mock_llm.close.assert_called_once()


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_task_manager_singleton(self):
        """get_task_manager should return same instance."""
        await reset_task_manager()

        m1 = get_task_manager()
        m2 = get_task_manager()

        assert m1 is m2

    @pytest.mark.asyncio
    async def test_reset_task_manager(self):
        """reset_task_manager should create new instance."""
        m1 = get_task_manager()

        await reset_task_manager()

        m2 = get_task_manager()
        assert m1 is not m2
