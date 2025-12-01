# ruff: noqa: E402
"""Integration tests for LangGraph RouterGraph."""
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

pytest.importorskip("pydantic_settings")
pytest.importorskip("pydantic")
pytest.importorskip("langgraph")

from common.db.models import RoutingTier  # type: ignore[import]
from brain.agents.graphs.router_graph import RouterGraph  # type: ignore[import]


class MockMultiServerClient:
    """Mock multi-server llama.cpp client."""

    def __init__(self, response_text: str = "Test response"):
        self.response_text = response_text
        self.call_count = 0
        self.last_prompt = None
        self.last_model = None

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        tools: List[Dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Mock generate method."""
        await asyncio.sleep(0)  # Simulate async
        self.call_count += 1
        self.last_prompt = prompt
        self.last_model = model
        return {
            "response": self.response_text,
            "tool_calls": [],
            "raw": {},
        }


class MockMemoryClient:
    """Mock memory client."""

    def __init__(self, memories: List[Any] | None = None):
        self.memories = memories or []
        self.search_count = 0

    async def search_memories(
        self,
        query: str,
        conversation_id: str,
        user_id: str | None = None,
        limit: int = 3,
        score_threshold: float = 0.75,
    ) -> List[Any]:
        """Mock search_memories method."""
        await asyncio.sleep(0)  # Simulate async
        self.search_count += 1

        # Return mock memory objects with required attributes
        class MockMemory:
            def __init__(self, content: str, score: float):
                self.content = content
                self.score = score
                self.metadata = {}

        return [MockMemory(m["content"], m.get("score", 0.9)) for m in self.memories]


class MockMCPClient:
    """Mock MCP tool client."""

    def __init__(self, tool_results: Dict[str, Any] | None = None):
        self.tool_results = tool_results or {}
        self.executed_tools = []

    async def execute_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Mock execute_tool method."""
        await asyncio.sleep(0)  # Simulate async
        self.executed_tools.append((tool_name, kwargs))
        return self.tool_results.get(tool_name, {"success": True, "output": f"Mock result from {tool_name}"})


@pytest.fixture
def mock_llm():
    """Create mock LLM client."""
    return MockMultiServerClient("This is a test response from Q4")


@pytest.fixture
def mock_memory():
    """Create mock memory client."""
    return MockMemoryClient([
        {"content": "User previously asked about bracket design", "score": 0.85},
        {"content": "10mm bolt holes are standard", "score": 0.80},
    ])


@pytest.fixture
def mock_mcp():
    """Create mock MCP client."""
    return MockMCPClient({
        "web_search": {"success": True, "output": "Search results: bracket designs"},
        "generate_cad": {"success": True, "output": "CAD model generated: bracket.step"},
    })


@pytest_asyncio.fixture
async def router_graph(mock_llm, mock_memory, mock_mcp):
    """Create RouterGraph instance with mocks."""
    return RouterGraph(
        llm_client=mock_llm,
        memory_client=mock_memory,
        mcp_client=mock_mcp,
        max_refinements=2,
    )


class TestRouterGraphInitialization:
    """Test RouterGraph initialization."""

    @pytest.mark.asyncio
    async def test_initialization(self, router_graph):
        """RouterGraph should initialize with correct components."""
        assert router_graph.llm is not None
        assert router_graph.memory is not None
        assert router_graph.mcp is not None
        assert router_graph.max_refinements == 2
        assert router_graph.complexity_analyzer is not None
        assert router_graph.graph is not None


class TestIntakeNode:
    """Test intake node behavior."""

    @pytest.mark.asyncio
    async def test_simple_query(self, router_graph):
        """Intake node should initialize state for simple query."""
        result = await router_graph.run(
            query="Hello KITTY",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "intake" in result["nodes_executed"]
        assert result["query"] == "Hello KITTY"
        assert result["user_id"] == "test_user"
        assert result["conversation_id"] == "test_conv"


class TestMemoryRetrievalNode:
    """Test memory retrieval node."""

    @pytest.mark.asyncio
    async def test_memory_retrieval_success(self, router_graph, mock_memory):
        """Memory retrieval should populate memories in state."""
        result = await router_graph.run(
            query="Tell me about brackets",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "memory_retrieval" in result["nodes_executed"]
        assert result["memory_search_attempted"] is True
        assert len(result["memories"]) == 2
        assert mock_memory.search_count == 1

    @pytest.mark.asyncio
    async def test_memory_retrieval_no_results(self, mock_llm, mock_mcp):
        """Memory retrieval with no results should continue workflow."""
        empty_memory = MockMemoryClient([])
        graph = RouterGraph(
            llm_client=mock_llm,
            memory_client=empty_memory,
            mcp_client=mock_mcp,
        )

        result = await graph.run(
            query="Random query",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "memory_retrieval" in result["nodes_executed"]
        assert len(result.get("memories", [])) == 0


class TestComplexityAnalysisNode:
    """Test complexity analysis node."""

    @pytest.mark.asyncio
    async def test_simple_query_low_complexity(self, router_graph):
        """Simple queries should have low complexity scores."""
        result = await router_graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "complexity_analysis" in result["nodes_executed"]
        assert "complexity_score" in result
        assert result["complexity_score"] < 0.5
        assert result["requires_deep_reasoning"] is False

    @pytest.mark.asyncio
    async def test_complex_query_high_complexity(self, router_graph):
        """Complex multi-step queries should have high complexity scores."""
        query = "Search for bracket designs, then create a parametric CAD model with FEA analysis"
        result = await router_graph.run(
            query=query,
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "complexity_analysis" in result["nodes_executed"]
        assert result["complexity_score"] > 0.3  # Should be medium-high


class TestToolSelectionNode:
    """Test tool selection node."""

    @pytest.mark.asyncio
    async def test_no_tools_for_simple_query(self, router_graph):
        """Simple queries should not require tools."""
        result = await router_graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Simple query shouldn't go through tool selection
        assert "tool_selection" not in result["nodes_executed"]
        assert "response_generation" in result["nodes_executed"]

    @pytest.mark.asyncio
    async def test_tool_selection_for_cad_query(self, router_graph):
        """CAD queries should select appropriate tools."""
        result = await router_graph.run(
            query="Design a parametric bracket",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Check if tools were considered
        if "tool_selection" in result["nodes_executed"]:
            assert "selected_tools" in result
            # Should select coding.generate for parametric CAD
            assert any("coding" in tool or "cad" in tool for tool in result["selected_tools"])


class TestToolExecutionNode:
    """Test tool execution node."""

    @pytest.mark.asyncio
    async def test_tool_execution_success(self, router_graph):
        """Tools should execute successfully."""
        result = await router_graph.run(
            query="Design a bracket",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        if "tool_execution" in result["nodes_executed"]:
            assert "tool_results" in result
            # All tools should succeed (mocked)
            for tool_result in result["tool_results"].values():
                assert tool_result.get("success", True) is True


class TestValidationNode:
    """Test validation node."""

    @pytest.mark.asyncio
    async def test_validation_high_confidence(self, router_graph):
        """Successful tool execution should result in high confidence."""
        result = await router_graph.run(
            query="Design a bracket",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        if "validation" in result["nodes_executed"]:
            assert "confidence" in result
            # Mocked tools always succeed, so confidence should be high
            assert result["confidence"] >= 0.5


class TestResponseGenerationNode:
    """Test response generation node."""

    @pytest.mark.asyncio
    async def test_response_generation(self, router_graph, mock_llm):
        """Response generation should produce output."""
        result = await router_graph.run(
            query="Hello KITTY",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "response_generation" in result["nodes_executed"]
        assert "response" in result
        assert len(result["response"]) > 0
        assert "tier_used" in result
        assert result["tier_used"] == RoutingTier.local
        assert mock_llm.call_count >= 1

    @pytest.mark.asyncio
    async def test_response_includes_tool_results(self, router_graph):
        """Response should reference tool results if tools were used."""
        result = await router_graph.run(
            query="Design a bracket and search for examples",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "response" in result
        # Response generation node receives tool results
        if "tool_results" in result and result["tool_results"]:
            assert len(result["response"]) > 0


class TestConditionalEdges:
    """Test conditional routing logic."""

    @pytest.mark.asyncio
    async def test_simple_query_skips_tools(self, router_graph):
        """Simple queries should skip tool workflow."""
        result = await router_graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        nodes = result["nodes_executed"]
        assert "intake" in nodes
        assert "memory_retrieval" in nodes
        assert "complexity_analysis" in nodes
        # Should skip directly to response
        assert "response_generation" in nodes
        # Should NOT execute tools
        assert "tool_selection" not in nodes
        assert "tool_execution" not in nodes


class TestRefinementLoop:
    """Test refinement loop behavior."""

    @pytest.mark.asyncio
    async def test_no_refinement_on_high_confidence(self, router_graph):
        """High confidence results should not trigger refinement."""
        result = await router_graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Check refinement count
        refinement_count = result.get("refinement_count", 0)
        assert refinement_count == 0  # No refinements for simple query


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    @pytest.mark.asyncio
    async def test_complete_workflow_simple_query(self, router_graph):
        """Test complete workflow for simple query."""
        result = await router_graph.run(
            query="Hello KITTY",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Verify all required fields are present
        assert "query" in result
        assert "user_id" in result
        assert "conversation_id" in result
        assert "request_id" in result
        assert "response" in result
        assert "confidence" in result
        assert "tier_used" in result
        assert "latency_ms" in result
        assert "nodes_executed" in result

        # Verify values are reasonable
        assert result["latency_ms"] >= 0
        assert 0.0 <= result["confidence"] <= 1.0
        assert len(result["nodes_executed"]) >= 3  # At least intake, memory, complexity, response

    @pytest.mark.asyncio
    async def test_complete_workflow_cad_query(self, router_graph):
        """Test complete workflow for CAD query."""
        result = await router_graph.run(
            query="Design a parametric bracket for 10mm bolts",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Verify workflow completion
        assert "response" in result
        assert result["tier_used"] in [RoutingTier.local, RoutingTier.mcp, RoutingTier.frontier]
        assert "complexity_score" in result

    @pytest.mark.asyncio
    async def test_complete_workflow_with_memory_context(self, router_graph, mock_memory):
        """Test workflow with memory context."""
        result = await router_graph.run(
            query="Continue with that bracket design",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Verify memories were retrieved
        assert len(result.get("memories", [])) > 0
        assert mock_memory.search_count >= 1


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_memory_failure_continues_workflow(self, mock_llm, mock_mcp):
        """Memory service failure should not stop workflow."""

        class FailingMemoryClient:
            async def search_memories(self, *args, **kwargs):
                raise Exception("Memory service unavailable")

        graph = RouterGraph(
            llm_client=mock_llm,
            memory_client=FailingMemoryClient(),
            mcp_client=mock_mcp,
        )

        result = await graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Should complete despite memory failure
        assert "response" in result
        assert result["memory_search_attempted"] is True

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error(self, mock_memory, mock_mcp):
        """LLM failure should return error result."""

        class FailingLLMClient:
            async def generate(self, *args, **kwargs):
                raise Exception("LLM service unavailable")

        graph = RouterGraph(
            llm_client=FailingLLMClient(),
            memory_client=mock_memory,
            mcp_client=mock_mcp,
        )

        result = await graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Should return error result
        assert "response" in result
        assert "error" in result["response"].lower() or result["confidence"] == 0.0


class TestStateTransitions:
    """Test state transitions between nodes."""

    @pytest.mark.asyncio
    async def test_state_accumulates_across_nodes(self, router_graph):
        """State should accumulate information as it flows through nodes."""
        result = await router_graph.run(
            query="Design a bracket",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Check that state accumulated data from each node
        nodes_executed = result["nodes_executed"]
        assert len(nodes_executed) >= 3

        # Each node should have added to state
        assert "query" in result  # From intake
        assert "memory_search_attempted" in result  # From memory_retrieval
        assert "complexity_score" in result  # From complexity_analysis
        assert "response" in result  # From response_generation


class TestMetadata:
    """Test metadata collection."""

    @pytest.mark.asyncio
    async def test_metadata_includes_execution_details(self, router_graph):
        """Result should include execution metadata."""
        result = await router_graph.run(
            query="Hello",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        # Check metadata fields
        assert "nodes_executed" in result
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], int)
        assert result["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_complexity_factors_in_result(self, router_graph):
        """Result should include complexity factor breakdown."""
        result = await router_graph.run(
            query="Design a bracket",
            user_id="test_user",
            conversation_id="test_conv",
            request_id="test_req",
        )

        assert "complexity_score" in result
        assert "complexity_factors" in result
        factors = result["complexity_factors"]
        assert "token_count" in factors
        assert "technical_density" in factors
        assert "multi_step" in factors
