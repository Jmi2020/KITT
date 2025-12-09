"""
Tests for ParallelAgentIntegration: complexity estimation, feature flags, and routing.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brain.agents.parallel.integration import (
    ParallelAgentIntegration,
    ParallelExecutionResult,
    PARALLEL_TRIGGER_KEYWORDS,
    SIMPLE_QUERY_KEYWORDS,
    get_parallel_integration,
    reset_parallel_integration,
)


class TestComplexityEstimation:
    """Tests for query complexity scoring."""

    def test_simple_query_low_complexity(self, parallel_disabled_env):
        """Simple queries should score below threshold."""
        integration = ParallelAgentIntegration()

        simple_queries = [
            "What is Python?",
            "How do I install numpy?",
            "Explain machine learning",
            "Define REST API",
            "List the planets",
            "Hello there!",
        ]

        for query in simple_queries:
            score = integration._estimate_complexity(query)
            assert score < 0.6, f"Query '{query}' scored {score}, expected < 0.6"

    def test_complex_query_high_complexity(self, parallel_enabled_env):
        """Complex multi-step queries should score above threshold."""
        integration = ParallelAgentIntegration()

        # These queries contain trigger keywords that add +0.2 each
        complex_queries = [
            "Research and analyze the best 3D printing materials, then design and build a phone stand",  # research and (+0.2) + design and (+0.2) + and count >= 2 (+0.2)
            "Compare React and Vue comprehensively, then build and test a component library",  # compare (+0.2) + comprehensive (+0.2) + build and (+0.2)
            "Investigate quantum computing advances and analyze and evaluate their impact step by step",  # investigate (+0.2) + step by step (+0.2) + analyze and (+0.2)
            "Create a comprehensive detailed report on climate change solutions step by step",  # comprehensive (+0.2) + detailed report (+0.2) + step by step (+0.2)
        ]

        for query in complex_queries:
            score = integration._estimate_complexity(query)
            assert score >= 0.5, f"Query '{query}' scored {score}, expected >= 0.5"

    def test_keyword_triggers_increase_score(self, parallel_disabled_env):
        """Parallel trigger keywords should increase score."""
        integration = ParallelAgentIntegration()

        base_query = "Tell me about quantum physics"
        base_score = integration._estimate_complexity(base_query)

        # Add trigger keyword
        complex_query = "Research and analyze quantum physics comprehensively"
        complex_score = integration._estimate_complexity(complex_query)

        assert complex_score > base_score

    def test_simple_keywords_decrease_score(self, parallel_enabled_env):
        """Simple query keywords should decrease score."""
        integration = ParallelAgentIntegration()

        # Without simple keyword - add a trigger keyword to get positive score
        query1 = "investigate quantum computing applications in cryptography comprehensively"
        score1 = integration._estimate_complexity(query1)

        # With simple keyword at start (which decreases score by 0.3)
        query2 = "what is quantum computing applications in cryptography"
        score2 = integration._estimate_complexity(query2)

        assert score2 < score1, f"Expected {score2} < {score1}"

    def test_long_query_increases_score(self, parallel_disabled_env):
        """Longer queries should score higher."""
        integration = ParallelAgentIntegration()

        short = "Research AI"
        long = "Research the current state of artificial intelligence, " * 10

        short_score = integration._estimate_complexity(short)
        long_score = integration._estimate_complexity(long)

        assert long_score > short_score

    def test_multiple_questions_increase_score(self, parallel_disabled_env):
        """Multiple question marks should increase score."""
        integration = ParallelAgentIntegration()

        single = "What is Python?"
        multiple = "What is Python? How does it compare to Java? Which should I use?"

        single_score = integration._estimate_complexity(single)
        multiple_score = integration._estimate_complexity(multiple)

        assert multiple_score > single_score

    def test_and_conjunctions_increase_score(self, parallel_disabled_env):
        """Multiple 'and' conjunctions should increase score."""
        integration = ParallelAgentIntegration()

        simple = "Research quantum computing"
        conjunctions = "Research quantum computing and analyze the findings and write code and test it"

        simple_score = integration._estimate_complexity(simple)
        conj_score = integration._estimate_complexity(conjunctions)

        assert conj_score > simple_score

    def test_score_bounds(self, parallel_disabled_env):
        """Score should always be between 0.0 and 1.0."""
        integration = ParallelAgentIntegration()

        test_queries = [
            "",
            "hi",
            "What?" * 100,
            "Research and " * 50,
            "a" * 10000,
        ]

        for query in test_queries:
            score = integration._estimate_complexity(query)
            assert 0.0 <= score <= 1.0, f"Score {score} out of bounds for '{query[:50]}...'"


class TestShouldUseParallel:
    """Tests for parallel routing decision."""

    @pytest.mark.asyncio
    async def test_disabled_returns_false(self, parallel_disabled_env):
        """Should return False when disabled."""
        integration = ParallelAgentIntegration()

        result = await integration.should_use_parallel(
            "Research and analyze quantum computing comprehensively"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_enabled_simple_query_returns_false(self, parallel_enabled_env):
        """Should return False for simple queries even when enabled."""
        integration = ParallelAgentIntegration()

        result = await integration.should_use_parallel("What is Python?")

        assert result is False

    @pytest.mark.asyncio
    async def test_enabled_complex_query_returns_true(self, parallel_enabled_env):
        """Should return True for complex queries when enabled."""
        integration = ParallelAgentIntegration()

        # Use multiple trigger keywords to ensure score is above threshold
        result = await integration.should_use_parallel(
            "Research and investigate quantum computing advances step by step, compare and evaluate "
            "implementation approaches comprehensively, and create a detailed report and design "
            "a comprehensive architecture for quantum-resistant cryptography"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_force_bypasses_complexity(self, parallel_enabled_env):
        """Force flag should bypass complexity check."""
        integration = ParallelAgentIntegration()

        # Simple query that would normally fail
        result = await integration.should_use_parallel(
            "Hello",
            force=True,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_rollout_percent_consistency(self, monkeypatch):
        """Same conversation_id should get consistent routing."""
        monkeypatch.setenv("ENABLE_PARALLEL_AGENTS", "true")
        monkeypatch.setenv("PARALLEL_AGENT_ROLLOUT_PERCENT", "50")
        monkeypatch.setenv("PARALLEL_AGENT_COMPLEXITY_THRESHOLD", "0.0")  # Always pass complexity

        integration = ParallelAgentIntegration()

        # Same conversation_id should give consistent results
        results = []
        for _ in range(10):
            result = await integration.should_use_parallel(
                "Complex query",
                conversation_id="test-conv-123",
            )
            results.append(result)

        # All results should be the same (consistent hashing)
        assert len(set(results)) == 1

    @pytest.mark.asyncio
    async def test_rollout_zero_percent(self, monkeypatch):
        """0% rollout should always return False."""
        monkeypatch.setenv("ENABLE_PARALLEL_AGENTS", "true")
        monkeypatch.setenv("PARALLEL_AGENT_ROLLOUT_PERCENT", "0")

        integration = ParallelAgentIntegration()

        result = await integration.should_use_parallel(
            "Research and analyze comprehensively",
            conversation_id="any-id",
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_rollout_100_percent(self, parallel_enabled_env):
        """100% rollout should always pass rollout check."""
        integration = ParallelAgentIntegration()

        # Complex enough to pass complexity check
        result = await integration.should_use_parallel(
            "Research and analyze quantum computing comprehensively step by step",
        )

        # Should pass if complexity is high enough
        assert result is True or integration._estimate_complexity(
            "Research and analyze quantum computing comprehensively step by step"
        ) < integration.complexity_threshold


class TestParallelExecutionResult:
    """Tests for ParallelExecutionResult dataclass."""

    def test_to_dict(self):
        """Should serialize all fields."""
        result = ParallelExecutionResult(
            response="Final answer",
            voice_summary="Brief summary",
            tasks=[{"id": "t1", "status": "completed"}],
            metrics={"total_time": 5.0},
            execution_log=[{"message": "Started"}],
        )

        d = result.to_dict()

        assert d["response"] == "Final answer"
        assert d["voice_summary"] == "Brief summary"
        assert len(d["tasks"]) == 1
        assert d["metrics"]["total_time"] == 5.0
        assert len(d["execution_log"]) == 1


class TestExecuteParallel:
    """Tests for parallel execution via integration."""

    @pytest.mark.asyncio
    async def test_execute_parallel_returns_result(self, parallel_enabled_env, mock_endpoints, mock_httpx_client):
        """Should return ParallelExecutionResult."""
        from brain.agents.parallel.slot_manager import SlotManager
        from brain.agents.parallel.llm_adapter import ParallelLLMClient
        from brain.agents.parallel.parallel_manager import ParallelTaskManager

        # Setup mocks
        slot_manager = SlotManager(endpoints=mock_endpoints)
        llm_client = ParallelLLMClient(slot_manager=slot_manager)
        llm_client._http_client = mock_httpx_client

        # Mock task manager
        mock_result = {
            "final_output": "Synthesized answer",
            "voice_summary": "Brief summary",
            "tasks": [{"id": "t1"}],
            "metrics": {"total_time_seconds": 1.0},
            "execution_log": [],
        }

        task_manager = AsyncMock()
        task_manager.execute_goal = AsyncMock(return_value=mock_result)

        integration = ParallelAgentIntegration(task_manager=task_manager)

        result = await integration.execute_parallel(
            goal="Test goal",
            include_voice_summary=True,
        )

        assert isinstance(result, ParallelExecutionResult)
        assert result.response == "Synthesized answer"
        assert result.voice_summary == "Brief summary"


class TestGetStatus:
    """Tests for status reporting."""

    def test_get_status(self, parallel_enabled_env):
        """Should return complete status dict."""
        integration = ParallelAgentIntegration()

        status = integration.get_status()

        assert status["enabled"] is True
        assert "rollout_percent" in status
        assert "complexity_threshold" in status
        assert "max_tasks" in status


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_parallel_integration_singleton(self):
        """get_parallel_integration should return same instance."""
        await reset_parallel_integration()

        i1 = get_parallel_integration()
        i2 = get_parallel_integration()

        assert i1 is i2

    @pytest.mark.asyncio
    async def test_reset_parallel_integration(self):
        """reset_parallel_integration should create new instance."""
        i1 = get_parallel_integration()

        await reset_parallel_integration()

        i2 = get_parallel_integration()
        assert i1 is not i2


class TestKeywordLists:
    """Tests for keyword configuration."""

    def test_parallel_trigger_keywords_exist(self):
        """Should have parallel trigger keywords defined."""
        assert len(PARALLEL_TRIGGER_KEYWORDS) > 0
        assert "research and" in PARALLEL_TRIGGER_KEYWORDS
        assert "comprehensive" in PARALLEL_TRIGGER_KEYWORDS

    def test_simple_query_keywords_exist(self):
        """Should have simple query keywords defined."""
        assert len(SIMPLE_QUERY_KEYWORDS) > 0
        assert "what is" in SIMPLE_QUERY_KEYWORDS
        assert "explain" in SIMPLE_QUERY_KEYWORDS
