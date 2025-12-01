# ruff: noqa: E402
"""Unit tests for Collective Meta-Agent LangGraph."""
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

pytest.importorskip("langgraph")

from brain.agents.collective.graph import (  # type: ignore[import]
    CollectiveState,
    build_collective_graph,
    n_plan,
    n_propose_council,
    n_propose_debate,
    n_judge,
)


class MockChat:
    """Mock chat function for testing."""

    def __init__(self, responses: Dict[str, str]):
        """Initialize with predefined responses.

        Args:
            responses: Dict mapping role patterns to responses
        """
        self.responses = responses
        self.call_count = 0
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, messages: List[Dict[str, str]], which: str = "Q4", tools: Any = None, temperature: float = 0.7, max_tokens: int = 500) -> str:
        """Mock chat interface."""
        self.call_count += 1
        self.calls.append({"messages": messages, "which": which, "tools": tools, "temperature": temperature, "max_tokens": max_tokens})

        # Return response based on which model and content
        if which == "DEEP":
            return self.responses.get("judge", "Mock judge verdict")
        elif "specialist" in str(messages):
            return self.responses.get(f"specialist_{self.call_count}", f"Specialist {self.call_count} proposal")
        elif "PRO" in str(messages):
            return self.responses.get("pro", "PRO argument")
        elif "CON" in str(messages):
            return self.responses.get("con", "CON argument")
        else:
            return self.responses.get("plan", "Mock plan")


@pytest.fixture
def mock_chat():
    """Fixture providing mock chat function."""
    return MockChat({
        "plan": "Plan: Use 3 specialists for material comparison",
        "specialist_1": "Specialist 1: PETG is best for outdoor use due to UV resistance",
        "specialist_2": "Specialist 2: ABS offers better heat resistance",
        "specialist_3": "Specialist 3: ASA combines benefits of both",
        "pro": "PRO: Tree supports reduce material usage and print time",
        "con": "CON: Linear supports are more reliable for critical overhangs",
        "judge": "JUDGE VERDICT: Based on proposals, PETG is recommended for outdoor use with ASA as secondary option"
    })


def test_n_plan(mock_chat):
    """Test plan node generates planning output."""
    with patch("brain.agents.collective.graph.chat", mock_chat):
        state: CollectiveState = {
            "task": "Compare PETG vs ABS",
            "pattern": "council",
            "k": 3
        }

        result = n_plan(state)

        assert "logs" in result
        assert "[plan]" in result["logs"]
        assert "Plan: Use 3 specialists" in result["logs"]
        assert mock_chat.call_count == 1
        assert mock_chat.calls[0]["which"] == "Q4"


def test_n_propose_council(mock_chat):
    """Test council proposal node generates k proposals."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        state: CollectiveState = {
            "task": "Compare materials",
            "pattern": "council",
            "k": 3
        }

        result = n_propose_council(state)

        assert "proposals" in result
        assert len(result["proposals"]) == 3
        assert mock_chat.call_count == 3
        # First proposal uses Q4B (diversity seat), rest use Q4
        assert mock_chat.calls[0]["which"] == "Q4B"
        assert all(call["which"] == "Q4" for call in mock_chat.calls[1:])


def test_n_propose_council_with_different_k(mock_chat):
    """Test council with different k values."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        # Test with k=2
        state: CollectiveState = {"task": "Test", "k": 2}
        result = n_propose_council(state)
        assert len(result["proposals"]) == 2

        # Reset mock
        mock_chat.call_count = 0
        mock_chat.calls = []

        # Test with k=5
        state = {"task": "Test", "k": 5}
        result = n_propose_council(state)
        assert len(result["proposals"]) == 5


def test_n_propose_debate(mock_chat):
    """Test debate proposal node generates PRO and CON arguments."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        state: CollectiveState = {
            "task": "Should I use tree supports?",
            "pattern": "debate"
        }

        result = n_propose_debate(state)

        assert "proposals" in result
        assert len(result["proposals"]) == 2
        # Debate now returns Proposal dicts with label/content/model
        assert "PRO:" in result["proposals"][0]["content"]
        assert "CON:" in result["proposals"][1]["content"]
        assert result["proposals"][0]["label"] == "Response A"
        assert result["proposals"][1]["label"] == "Response B"
        assert mock_chat.call_count == 2
        # Both should use Q4
        assert all(call["which"] == "Q4" for call in mock_chat.calls)


def test_n_judge(mock_chat):
    """Test judge node synthesizes proposals into verdict."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        state: CollectiveState = {
            "task": "Compare materials",
            "proposals": [
                {"label": "Response A", "content": "Specialist 1: PETG is best", "model": "Q4B"},
                {"label": "Response B", "content": "Specialist 2: ABS is better", "model": "Q4"},
                {"label": "Response C", "content": "Specialist 3: ASA is optimal", "model": "Q4"}
            ]
        }

        result = n_judge(state)

        assert "verdict" in result
        assert "JUDGE VERDICT:" in result["verdict"]
        assert mock_chat.call_count == 1
        # Judge should use DEEP
        assert mock_chat.calls[0]["which"] == "DEEP"


def test_build_collective_graph():
    """Test graph construction."""
    graph = build_collective_graph()

    # Verify graph has all required nodes
    nodes = graph.nodes
    assert "plan" in nodes
    assert "propose_pipeline" in nodes
    assert "propose_council" in nodes
    assert "propose_debate" in nodes
    assert "judge" in nodes


def test_graph_execution_council(mock_chat):
    """Test full graph execution with council pattern."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"), \
         patch("brain.agents.collective.graph.PEER_REVIEW_ENABLED", False):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Compare PETG vs ABS for outdoor use",
            "pattern": "council",
            "k": 3
        }

        result = graph.invoke(state)

        # Should have plan logs
        assert "logs" in result
        assert "[plan]" in result["logs"]

        # Should have 3 proposals
        assert "proposals" in result
        assert len(result["proposals"]) == 3

        # Should have verdict
        assert "verdict" in result
        assert len(result["verdict"]) > 0

        # Verify Q4B+Q4 used for proposals, DEEP for judge (peer review disabled)
        # 1 plan (Q4) + 1 proposal (Q4B) + 2 proposals (Q4) + 1 judge (DEEP) = 5 total
        assert mock_chat.call_count == 5
        # Check model usage: plan=Q4, proposals=Q4B/Q4/Q4, judge=DEEP
        model_sequence = [call["which"] for call in mock_chat.calls]
        assert model_sequence == ["Q4", "Q4B", "Q4", "Q4", "DEEP"]


def test_graph_execution_debate(mock_chat):
    """Test full graph execution with debate pattern."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"), \
         patch("brain.agents.collective.graph.PEER_REVIEW_ENABLED", False):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Should I use tree supports?",
            "pattern": "debate"
        }

        result = graph.invoke(state)

        # Should have 2 proposals (PRO and CON) - debate returns Proposal dicts
        assert "proposals" in result
        assert len(result["proposals"]) == 2

        # Should have verdict
        assert "verdict" in result

        # 1 plan + 2 debate + 1 judge = 4 calls
        assert mock_chat.call_count == 4


def test_graph_execution_pipeline(mock_chat):
    """Test full graph execution with pipeline pattern."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"), \
         patch("brain.agents.collective.graph.PEER_REVIEW_ENABLED", False):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Generate a test",
            "pattern": "pipeline"
        }

        result = graph.invoke(state)

        # Pipeline should have placeholder proposal as Proposal dict
        assert "proposals" in result
        assert len(result["proposals"]) >= 1
        # Pipeline returns Proposal dict with content field
        assert "<pipeline result inserted by router>" in result["proposals"][0]["content"]

        # Should still have verdict
        assert "verdict" in result


def test_graph_execution_invalid_pattern_defaults_to_pipeline(mock_chat):
    """Test invalid pattern defaults to pipeline."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"), \
         patch("brain.agents.collective.graph.PEER_REVIEW_ENABLED", False):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Test",
            "pattern": "invalid_pattern"  # type: ignore
        }

        result = graph.invoke(state)

        # Should default to pipeline (placeholder) with Proposal dict
        assert "proposals" in result
        assert "<pipeline result inserted by router>" in result["proposals"][0]["content"]


def test_state_accumulation():
    """Test that state accumulates across nodes."""
    responses = {
        "plan": "Initial plan",
        "specialist_1": "Proposal 1",
        "judge": "Final verdict"
    }

    with patch("brain.agents.collective.graph.chat", MockChat(responses)), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Test accumulation",
            "pattern": "council",
            "k": 1
        }

        result = graph.invoke(state)

        # Original state should be preserved
        assert result["task"] == "Test accumulation"
        assert result["pattern"] == "council"
        assert result["k"] == 1

        # New state should be added
        assert "logs" in result
        assert "proposals" in result
        assert "verdict" in result


def test_empty_task_handling(mock_chat):
    """Test handling of empty task."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "",
            "pattern": "council",
            "k": 2
        }

        # Should not raise error
        result = graph.invoke(state)
        assert "verdict" in result


def test_k_boundary_values(mock_chat):
    """Test k at boundary values (2 and 7)."""
    with patch("brain.agents.collective.graph.chat", mock_chat), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        # Test k=2 (minimum)
        state: CollectiveState = {"task": "Test", "k": 2}
        result = n_propose_council(state)
        assert len(result["proposals"]) == 2

        # Reset
        mock_chat.call_count = 0
        mock_chat.calls = []

        # Test k=7 (maximum)
        state = {"task": "Test", "k": 7}
        result = n_propose_council(state)
        assert len(result["proposals"]) == 7


@pytest.mark.asyncio
async def test_concurrent_execution():
    """Test that council proposals could be parallelized (future enhancement)."""
    # This test documents current behavior (sequential) and desired behavior (parallel)
    responses = {f"specialist_{i}": f"Proposal {i}" for i in range(1, 4)}
    responses["judge"] = "Verdict"
    responses["plan"] = "Plan"

    with patch("brain.agents.collective.graph.chat", MockChat(responses)), \
         patch("brain.agents.collective.graph.fetch_domain_context", return_value="Mock context"):
        graph = build_collective_graph()
        state: CollectiveState = {
            "task": "Test",
            "pattern": "council",
            "k": 3
        }

        # Currently sequential - future: could use asyncio.gather for proposals
        result = graph.invoke(state)
        assert len(result["proposals"]) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
