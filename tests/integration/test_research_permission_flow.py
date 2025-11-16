"""
Integration tests for complete research permission flow

Tests the end-to-end permission system:
I/O Control → Budget → UnifiedPermissionGate → ResearchToolExecutor → MCP Tools
"""

import pytest
import os
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from brain.research.permissions import UnifiedPermissionGate, PermissionResult
from brain.research.models.budget import BudgetManager, BudgetConfig
from brain.research.tools.mcp_integration import (
    ResearchToolExecutor,
    ToolExecutionContext,
    ToolType
)


class MockIOControlStateManager:
    """Mock I/O Control state manager"""

    def __init__(self, state: dict):
        self.state = state

    def get_current_state(self):
        return self.state


class MockResearchServer:
    """Mock Research MCP Server"""

    async def execute_tool(self, tool_name: str, arguments: dict):
        if tool_name == "web_search":
            return Mock(
                success=True,
                data={
                    "query": arguments["query"],
                    "results": [
                        {
                            "title": "Test Result 1",
                            "url": "https://example.com/1",
                            "description": "Description 1"
                        }
                    ],
                    "total_results": 1
                },
                error=None,
                metadata={"provider": "duckduckgo"}
            )
        elif tool_name == "research_deep":
            return Mock(
                success=True,
                data={
                    "query": arguments["query"],
                    "research": "This is deep research output with comprehensive analysis.",
                    "citations": [
                        "https://source1.com",
                        "https://source2.com"
                    ],
                    "usage": {
                        "total_tokens": 2500,
                        "input_tokens": 1000,
                        "output_tokens": 1500
                    }
                },
                error=None,
                metadata={"model": "sonar"}
            )
        else:
            return Mock(success=False, data={}, error=f"Unknown tool: {tool_name}", metadata={})


@pytest.mark.integration
class TestResearchPermissionFlowIntegration:
    """Integration tests for complete permission flow"""

    @pytest.fixture
    def io_control_all_enabled(self):
        """I/O Control with all providers enabled"""
        return MockIOControlStateManager({
            "perplexity_api": True,
            "openai_api": True,
            "anthropic_api": True,
            "offline_mode": False,
            "cloud_routing": True,
        })

    @pytest.fixture
    def io_control_perplexity_disabled(self):
        """I/O Control with Perplexity disabled"""
        return MockIOControlStateManager({
            "perplexity_api": False,  # Disabled
            "openai_api": True,
            "anthropic_api": True,
            "offline_mode": False,
            "cloud_routing": True,
        })

    @pytest.fixture
    def io_control_offline_mode(self):
        """I/O Control in offline mode"""
        return MockIOControlStateManager({
            "perplexity_api": True,
            "openai_api": True,
            "anthropic_api": True,
            "offline_mode": True,  # Offline
            "cloud_routing": False,
        })

    @pytest.fixture
    async def budget_manager_ample(self):
        """Budget manager with ample budget"""
        config = BudgetConfig(
            max_total_cost_usd=Decimal("5.0"),
            max_external_calls=20
        )
        return BudgetManager(config=config)

    @pytest.fixture
    async def budget_manager_limited(self):
        """Budget manager with limited budget"""
        config = BudgetConfig(
            max_total_cost_usd=Decimal("0.10"),
            max_external_calls=2
        )
        return BudgetManager(config=config)

    @pytest.fixture
    def research_server(self):
        """Mock research server"""
        return MockResearchServer()

    @pytest.fixture
    def execution_context(self):
        """Standard execution context"""
        return ToolExecutionContext(
            session_id="integration_test_session",
            user_id="integration_test_user",
            iteration=1,
            budget_remaining=Decimal("5.0"),
            external_calls_remaining=20,
            perplexity_enabled=True,
            offline_mode=False,
            cloud_routing_enabled=True
        )

    # ===== Happy Path: All Allowed =====

    @pytest.mark.asyncio
    async def test_full_flow_web_search_allowed(
        self,
        io_control_all_enabled,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test complete flow: free web search (should always work)"""

        # Setup complete infrastructure
        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_all_enabled,
            budget_manager=budget_manager_ample,
            auto_approve_trivial=True
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Execute web search (free tool)
        result = await executor.execute(
            tool_name=ToolType.WEB_SEARCH,
            arguments={"query": "llama.cpp optimization"},
            context=execution_context
        )

        # Verify success
        assert result.success is True
        assert result.cost_usd == Decimal("0.0")
        assert result.is_external is False
        assert len(result.data["results"]) > 0

        # Budget should be unchanged (free tool)
        budget_status = await budget_manager_ample.get_status()
        assert budget_status.total_cost_usd == Decimal("0.0")

    @pytest.mark.asyncio
    async def test_full_flow_research_deep_auto_approved(
        self,
        io_control_all_enabled,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test complete flow: research_deep with auto-approval (trivial cost)"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_all_enabled,
            budget_manager=budget_manager_ample,
            auto_approve_trivial=True  # Auto-approve < $0.01
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Execute research_deep (paid tool, but trivial cost)
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "best practices for vector databases"},
            context=execution_context
        )

        # Verify success
        assert result.success is True
        assert result.cost_usd > Decimal("0.0")
        assert result.is_external is True
        assert "research" in result.data

        # Verify budget tracking
        budget_status = await budget_manager_ample.get_status()
        assert budget_status.total_cost_usd > Decimal("0.0")
        assert budget_status.external_calls_used == 1

    # ===== Blocked by I/O Control =====

    @pytest.mark.asyncio
    async def test_full_flow_blocked_by_io_control_provider_disabled(
        self,
        io_control_perplexity_disabled,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test flow blocked by I/O Control (provider disabled)"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_perplexity_disabled,
            budget_manager=budget_manager_ample
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Try to execute research_deep
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        # Verify blocked
        assert result.success is False
        assert "perplexity" in result.error.lower()
        assert "i/o control" in result.error.lower() or "disabled" in result.error.lower()

        # Verify no budget consumed
        budget_status = await budget_manager_ample.get_status()
        assert budget_status.total_cost_usd == Decimal("0.0")
        assert budget_status.external_calls_used == 0

    @pytest.mark.asyncio
    async def test_full_flow_blocked_by_io_control_offline_mode(
        self,
        io_control_offline_mode,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test flow blocked by I/O Control (offline mode)"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_offline_mode,
            budget_manager=budget_manager_ample
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Try to execute research_deep
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        # Verify blocked
        assert result.success is False
        assert "offline" in result.error.lower()

        # Verify no budget consumed
        budget_status = await budget_manager_ample.get_status()
        assert budget_status.total_cost_usd == Decimal("0.0")

    # ===== Blocked by Budget =====

    @pytest.mark.asyncio
    async def test_full_flow_blocked_by_budget_insufficient_funds(
        self,
        io_control_all_enabled,
        budget_manager_limited,
        research_server,
        execution_context
    ):
        """Test flow blocked by insufficient budget"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_all_enabled,
            budget_manager=budget_manager_limited
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_limited
        )

        # Deplete budget first
        await budget_manager_limited.record_call(
            model_id="test",
            cost_usd=Decimal("0.09"),
            success=True
        )

        # Try to execute research_deep (estimated $0.005)
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        # Should succeed (budget = $0.10, used = $0.09, remaining = $0.01 > $0.005)
        assert result.success is True

        # Now deplete completely
        await budget_manager_limited.record_call(
            model_id="test2",
            cost_usd=Decimal("0.02"),
            success=True
        )

        # Try again - should fail
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test2"},
            context=execution_context
        )

        assert result.success is False
        assert "budget" in result.error.lower()

    # ===== Multiple Tool Execution =====

    @pytest.mark.asyncio
    async def test_full_flow_multiple_tools_mixed_success(
        self,
        io_control_all_enabled,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test executing multiple tools with mixed success"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_all_enabled,
            budget_manager=budget_manager_ample,
            auto_approve_trivial=True
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Execute web_search (free)
        result1 = await executor.execute(
            tool_name=ToolType.WEB_SEARCH,
            arguments={"query": "test 1"},
            context=execution_context
        )
        assert result1.success is True

        # Execute research_deep (paid)
        result2 = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test 2"},
            context=execution_context
        )
        assert result2.success is True

        # Execute another web_search (free)
        result3 = await executor.execute(
            tool_name=ToolType.WEB_SEARCH,
            arguments={"query": "test 3"},
            context=execution_context
        )
        assert result3.success is True

        # Verify budget tracking
        budget_status = await budget_manager_ample.get_status()
        assert budget_status.total_cost_usd > Decimal("0.0")  # From research_deep
        assert budget_status.external_calls_used == 1  # Only research_deep

    # ===== Cost Tracking Accuracy =====

    @pytest.mark.asyncio
    async def test_full_flow_accurate_cost_tracking(
        self,
        io_control_all_enabled,
        budget_manager_ample,
        research_server,
        execution_context
    ):
        """Test that costs are accurately tracked"""

        permission_gate = UnifiedPermissionGate(
            io_control_state_manager=io_control_all_enabled,
            budget_manager=budget_manager_ample,
            auto_approve_trivial=True
        )

        executor = ResearchToolExecutor(
            research_server=research_server,
            memory_server=None,
            permission_gate=permission_gate,
            budget_manager=budget_manager_ample
        )

        # Get initial budget
        initial_status = await budget_manager_ample.get_status()
        initial_cost = initial_status.total_cost_usd

        # Execute research_deep
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        assert result.success is True

        # Verify cost was recorded
        final_status = await budget_manager_ample.get_status()
        cost_recorded = final_status.total_cost_usd - initial_cost

        # Cost should match result
        assert cost_recorded == result.cost_usd
        assert cost_recorded > Decimal("0.0")

        # Cost should be based on token usage (2500 tokens in mock)
        # Formula: $0.001 + (tokens * $0.00001)
        expected_cost = Decimal("0.001") + (Decimal("2500") * Decimal("0.00001"))
        assert cost_recorded == expected_cost


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
