"""
Unit tests for ResearchToolExecutor with permission integration

Tests tool execution with UnifiedPermissionGate integration.
"""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from brain.research.tools.mcp_integration import (
    ResearchToolExecutor,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolType
)
from brain.research.permissions import UnifiedPermissionGate, PermissionResult, ApprovalTier


class MockMCPServer:
    """Mock MCP server for testing"""

    async def execute_tool(self, tool_name: str, arguments: dict):
        """Mock tool execution"""
        if tool_name == "web_search":
            return Mock(
                success=True,
                data={
                    "query": arguments.get("query"),
                    "results": [
                        {"title": "Test Result", "url": "https://test.com", "description": "Test"}
                    ]
                },
                error=None,
                metadata={"provider": "duckduckgo"}
            )
        elif tool_name == "research_deep":
            return Mock(
                success=True,
                data={
                    "query": arguments.get("query"),
                    "research": "Test research output",
                    "citations": ["https://source1.com"],
                    "usage": {
                        "total_tokens": 1000,
                        "input_tokens": 500,
                        "output_tokens": 500
                    }
                },
                error=None,
                metadata={}
            )
        elif tool_name == "fetch_webpage":
            return Mock(
                success=True,
                data={
                    "url": arguments.get("url"),
                    "content": "Test webpage content",
                    "title": "Test Page"
                },
                error=None,
                metadata={}
            )
        elif tool_name == "store_memory":
            return Mock(
                success=True,
                data={"memory_id": "test_123"},
                error=None,
                metadata={}
            )
        elif tool_name == "recall_memory":
            return Mock(
                success=True,
                data={
                    "memories": [
                        {"content": "Test memory", "score": 0.95}
                    ]
                },
                error=None,
                metadata={}
            )
        else:
            return Mock(
                success=False,
                data={},
                error=f"Unknown tool: {tool_name}",
                metadata={}
            )


class TestResearchToolExecutor:
    """Test suite for ResearchToolExecutor"""

    @pytest.fixture
    def mock_research_server(self):
        """Mock research MCP server"""
        return MockMCPServer()

    @pytest.fixture
    def mock_memory_server(self):
        """Mock memory MCP server"""
        return MockMCPServer()

    @pytest.fixture
    async def mock_permission_gate_allow(self):
        """Permission gate that allows all calls"""
        gate = Mock(spec=UnifiedPermissionGate)
        gate.check_permission = AsyncMock(return_value=PermissionResult(
            approved=True,
            reason="Auto-approved (trivial cost)",
            approval_tier=ApprovalTier.TRIVIAL,
            estimated_cost=Decimal("0.005"),
            provider="perplexity"
        ))
        gate.record_actual_cost = Mock()
        return gate

    @pytest.fixture
    async def mock_permission_gate_deny(self):
        """Permission gate that denies calls"""
        gate = Mock(spec=UnifiedPermissionGate)
        gate.check_permission = AsyncMock(return_value=PermissionResult(
            approved=False,
            reason="Perplexity API disabled in I/O Control",
            prompt_user=False,
            estimated_cost=Decimal("0.005"),
            provider="perplexity"
        ))
        return gate

    @pytest.fixture
    async def mock_permission_gate_prompt(self):
        """Permission gate that requires user prompt"""
        gate = Mock(spec=UnifiedPermissionGate)
        gate.check_permission = AsyncMock(return_value=PermissionResult(
            approved=False,
            reason="Requires approval (low-cost call)",
            prompt_user=True,
            approval_tier=ApprovalTier.LOW,
            estimated_cost=Decimal("0.05"),
            provider="perplexity"
        ))
        gate.prompt_user_for_approval = AsyncMock(return_value=False)
        return gate

    @pytest.fixture
    def mock_budget_manager(self):
        """Mock budget manager"""
        budget = Mock()
        budget.record_call = AsyncMock()
        return budget

    @pytest.fixture
    def execution_context(self):
        """Standard execution context"""
        return ToolExecutionContext(
            session_id="test_session",
            user_id="test_user",
            iteration=1,
            budget_remaining=Decimal("2.0"),
            external_calls_remaining=10,
            perplexity_enabled=True,
            offline_mode=False,
            cloud_routing_enabled=True
        )

    # ===== Free Tool Tests (web_search, fetch_webpage) =====

    @pytest.mark.asyncio
    async def test_execute_web_search(
        self,
        mock_research_server,
        execution_context
    ):
        """Test free web search execution"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.WEB_SEARCH,
            arguments={"query": "test query"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "web_search"
        assert result.cost_usd == Decimal("0.0")
        assert result.is_external is False

    @pytest.mark.asyncio
    async def test_execute_fetch_webpage(
        self,
        mock_research_server,
        execution_context
    ):
        """Test fetch webpage execution"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.FETCH_WEBPAGE,
            arguments={"url": "https://test.com"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "fetch_webpage"
        assert result.cost_usd == Decimal("0.0")

    # ===== Paid Tool Tests (research_deep) =====

    @pytest.mark.asyncio
    async def test_execute_research_deep_approved(
        self,
        mock_research_server,
        mock_permission_gate_allow,
        mock_budget_manager,
        execution_context
    ):
        """Test research_deep with approved permission"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=mock_permission_gate_allow,
            budget_manager=mock_budget_manager
        )

        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test deep research"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "research_deep"
        assert result.is_external is True
        assert result.cost_usd > Decimal("0.0")

        # Verify permission check was called
        mock_permission_gate_allow.check_permission.assert_called_once()

        # Verify cost recording
        mock_permission_gate_allow.record_actual_cost.assert_called_once()
        mock_budget_manager.record_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_research_deep_denied_io_control(
        self,
        mock_research_server,
        mock_permission_gate_deny,
        execution_context
    ):
        """Test research_deep blocked by I/O Control"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=mock_permission_gate_deny,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        assert result.success is False
        assert "perplexity api disabled" in result.error.lower() or "i/o control" in result.error.lower()
        assert result.is_external is False  # Didn't execute

        # Verify permission check was called
        mock_permission_gate_deny.check_permission.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_research_deep_user_denied(
        self,
        mock_research_server,
        mock_permission_gate_prompt,
        execution_context
    ):
        """Test research_deep when user denies prompt"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=mock_permission_gate_prompt,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        assert result.success is False
        assert "permission denied" in result.error.lower()

        # Verify user was prompted
        mock_permission_gate_prompt.prompt_user_for_approval.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_research_deep_user_approved(
        self,
        mock_research_server,
        mock_budget_manager,
        execution_context
    ):
        """Test research_deep when user approves prompt"""
        # Create permission gate that requires prompt but user approves
        gate = Mock(spec=UnifiedPermissionGate)
        gate.check_permission = AsyncMock(return_value=PermissionResult(
            approved=False,
            reason="Requires approval",
            prompt_user=True,
            estimated_cost=Decimal("0.05"),
            provider="perplexity"
        ))
        gate.prompt_user_for_approval = AsyncMock(return_value=True)  # User approves
        gate.record_actual_cost = Mock()

        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=gate,
            budget_manager=mock_budget_manager
        )

        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "research_deep"

        # Verify prompt was shown and approved
        gate.prompt_user_for_approval.assert_called_once()

    # ===== Memory Tool Tests =====

    @pytest.mark.asyncio
    async def test_execute_store_memory(
        self,
        mock_research_server,
        mock_memory_server,
        execution_context
    ):
        """Test store memory execution"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=mock_memory_server,
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.STORE_MEMORY,
            arguments={"content": "test memory"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "store_memory"
        assert result.cost_usd == Decimal("0.0")

    @pytest.mark.asyncio
    async def test_execute_recall_memory(
        self,
        mock_research_server,
        mock_memory_server,
        execution_context
    ):
        """Test recall memory execution"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=mock_memory_server,
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.RECALL_MEMORY,
            arguments={"query": "test query"},
            context=execution_context
        )

        assert result.success is True
        assert result.tool_name == "recall_memory"
        assert result.cost_usd == Decimal("0.0")

    @pytest.mark.asyncio
    async def test_execute_memory_no_server(
        self,
        mock_research_server,
        execution_context
    ):
        """Test memory tools when server not available"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,  # No memory server
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.STORE_MEMORY,
            arguments={"content": "test"},
            context=execution_context
        )

        assert result.success is False
        assert "memory server not available" in result.error.lower()

    # ===== Error Handling Tests =====

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(
        self,
        mock_research_server,
        execution_context
    ):
        """Test execution with unknown tool"""
        executor = ResearchToolExecutor(
            research_server=mock_research_server,
            memory_server=None,
            permission_gate=None,
            budget_manager=None
        )

        # This should trigger the else clause in execute()
        with pytest.raises(ValueError):
            # ToolType is an enum, so we can't create invalid values
            # Instead test with a tool that the mock doesn't handle
            pass

    @pytest.mark.asyncio
    async def test_execute_tool_failure(
        self,
        execution_context
    ):
        """Test handling of tool execution failures"""
        # Create server that returns failure
        failing_server = Mock()
        failing_server.execute_tool = AsyncMock(return_value=Mock(
            success=False,
            data={},
            error="Tool execution failed",
            metadata={}
        ))

        executor = ResearchToolExecutor(
            research_server=failing_server,
            memory_server=None,
            permission_gate=None,
            budget_manager=None
        )

        result = await executor.execute(
            tool_name=ToolType.WEB_SEARCH,
            arguments={"query": "test"},
            context=execution_context
        )

        assert result.success is False
        assert result.error is not None

    # ===== I/O Control Integration Tests =====

    @pytest.mark.asyncio
    async def test_is_tool_allowed_offline_mode(self):
        """Test tool blocking in offline mode"""
        context = ToolExecutionContext(
            session_id="test",
            user_id="test",
            iteration=1,
            budget_remaining=Decimal("2.0"),
            external_calls_remaining=10,
            perplexity_enabled=True,
            offline_mode=True,  # Offline mode
            cloud_routing_enabled=True
        )

        executor = ResearchToolExecutor(
            research_server=MockMCPServer(),
            memory_server=None,
            permission_gate=None,
            budget_manager=None
        )

        # Research deep should be blocked in offline mode
        result = await executor.execute(
            tool_name=ToolType.RESEARCH_DEEP,
            arguments={"query": "test"},
            context=context
        )

        assert result.success is False
        assert "offline mode" in result.error.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
