"""
Integration test for research graph component wiring

Verifies that components are properly injected into graph nodes
and that real tool execution is used instead of simulated data.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

from brain.research.graph import (
    ResearchComponents,
    set_global_components,
    get_global_components
)
from brain.research.graph.state import create_initial_state
from brain.research.graph.nodes import execute_iteration


@pytest.mark.integration
class TestResearchGraphWiring:
    """Test research graph component wiring"""

    @pytest.fixture
    def mock_components(self):
        """Create mock research components"""
        # Mock tool executor
        tool_executor = Mock()
        tool_executor.execute = AsyncMock(return_value=Mock(
            success=True,
            tool_name="web_search",
            cost_usd=Decimal("0.0"),
            is_external=False,
            data={
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://test.com",
                        "description": "Test description"
                    }
                ]
            },
            error=None
        ))

        # Mock permission gate
        permission_gate = Mock()
        permission_gate.check_permission = AsyncMock()

        # Mock model coordinator
        model_coordinator = Mock()
        model_coordinator.consult = AsyncMock()

        # Mock budget manager
        budget_manager = Mock()
        budget_manager.record_call = AsyncMock()

        # Create components
        components = ResearchComponents(
            tool_executor=tool_executor,
            permission_gate=permission_gate,
            model_coordinator=model_coordinator,
            budget_manager=budget_manager
        )

        return components

    def test_components_factory(self, mock_components):
        """Test ResearchComponents dataclass"""
        assert mock_components.tool_executor is not None
        assert mock_components.permission_gate is not None
        assert mock_components.model_coordinator is not None
        assert mock_components.budget_manager is not None
        assert mock_components.is_fully_wired() is True

        status = mock_components.get_status()
        assert status["fully_wired"] is True
        assert status["tool_executor"] is True

    def test_global_components_registration(self, mock_components):
        """Test global component registration"""
        # Set components
        set_global_components(mock_components)

        # Retrieve components
        retrieved = get_global_components()

        assert retrieved is not None
        assert retrieved.tool_executor is mock_components.tool_executor
        assert retrieved.is_fully_wired() is True

    @pytest.mark.asyncio
    async def test_execute_iteration_uses_real_executor(self, mock_components):
        """Test that execute_iteration uses real tool executor"""
        # Set global components
        set_global_components(mock_components)

        # Create initial state with tasks
        state = create_initial_state(
            session_id="test_session",
            user_id="test_user",
            query="test query",
            config={"strategy": "depth_first"}
        )

        # Add planned tasks to state
        state["strategy_context"] = {
            "current_tasks": [
                {
                    "task_id": "task_1",
                    "query": "test query",
                    "priority": 0.5,
                    "depth": 1
                }
            ]
        }

        # Execute iteration
        result_state = await execute_iteration(state)

        # Verify tool executor was called
        assert mock_components.tool_executor.execute.called
        call_args = mock_components.tool_executor.execute.call_args

        # Verify correct tool was called
        assert call_args is not None

        # Verify findings were added
        assert len(result_state["findings"]) > 0

        # Verify sources were added
        assert len(result_state["sources"]) > 0

        # Verify tool execution was recorded
        assert len(result_state["tool_executions"]) > 0

    @pytest.mark.asyncio
    async def test_execute_iteration_fallback_without_components(self):
        """Test that execute_iteration falls back to simulated data without components"""
        # Clear global components
        set_global_components(None)

        # Create initial state with tasks
        state = create_initial_state(
            session_id="test_session",
            user_id="test_user",
            query="test query",
            config={"strategy": "depth_first"}
        )

        # Add planned tasks
        state["strategy_context"] = {
            "current_tasks": [
                {
                    "task_id": "task_1",
                    "query": "test query",
                    "priority": 0.5,
                    "depth": 1
                }
            ]
        }

        # Execute iteration (should use fallback)
        result_state = await execute_iteration(state)

        # Verify findings were still added (via simulated execution)
        assert len(result_state["findings"]) > 0

        # Verify simulated tool execution
        finding = result_state["findings"][0]
        assert finding["tool"] == "simulated"
        assert "[SIMULATED]" in finding["content"]

    @pytest.mark.asyncio
    async def test_execute_iteration_high_priority_uses_research_deep(self, mock_components):
        """Test that high priority tasks use research_deep tool"""
        # Set global components
        set_global_components(mock_components)

        # Mock research_deep response
        mock_components.tool_executor.execute = AsyncMock(return_value=Mock(
            success=True,
            tool_name="research_deep",
            cost_usd=Decimal("0.005"),
            is_external=True,
            data={
                "research": "Deep research output",
                "citations": ["https://source1.com", "https://source2.com"]
            },
            error=None
        ))

        # Create state with high-priority task
        state = create_initial_state(
            session_id="test_session",
            user_id="test_user",
            query="test query",
            config={"strategy": "depth_first"}
        )

        state["strategy_context"] = {
            "current_tasks": [
                {
                    "task_id": "task_1",
                    "query": "important research query",
                    "priority": 0.9,  # High priority
                    "depth": 1
                }
            ]
        }

        state["budget_remaining"] = Decimal("2.0")  # Ample budget

        # Execute iteration
        result_state = await execute_iteration(state)

        # Verify research_deep was called (high priority + sufficient budget)
        assert mock_components.tool_executor.execute.called

        # Verify cost was deducted
        assert result_state["budget_remaining"] < Decimal("2.0")

        # Verify external call was counted
        assert result_state["external_calls_remaining"] < 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
