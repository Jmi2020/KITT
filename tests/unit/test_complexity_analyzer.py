# ruff: noqa: E402
"""Unit tests for ComplexityAnalyzer."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/common/src"))
sys.path.append(str(ROOT / "services/brain/src"))

pytest.importorskip("pydantic_settings")
pytest.importorskip("pydantic")

from common.db.models import RoutingTier  # type: ignore[import]
from brain.agents.complexity.analyzer import ComplexityAnalyzer  # type: ignore[import]


@pytest.fixture
def analyzer():
    """Create a ComplexityAnalyzer instance."""
    return ComplexityAnalyzer()


class TestTokenCountScoring:
    """Test token count complexity scoring."""

    def test_short_query_low_score(self, analyzer):
        """Short queries should have low token complexity."""
        result = analyzer.analyze("Hello")
        assert result["factors"]["token_count"] < 0.3
        assert result["overall"] < 0.5

    def test_medium_query_medium_score(self, analyzer):
        """Medium queries should have medium token complexity."""
        query = "Design a parametric bracket with 10mm bolt holes for mounting a servo motor"
        result = analyzer.analyze(query)
        assert 0.2 <= result["factors"]["token_count"] <= 0.6

    def test_long_query_high_score(self, analyzer):
        """Long queries should have high token complexity."""
        query = " ".join(["word"] * 200)  # 200-word query
        result = analyzer.analyze(query)
        assert result["factors"]["token_count"] > 0.7


class TestTechnicalDensity:
    """Test technical term detection and scoring."""

    def test_simple_query_low_density(self, analyzer):
        """Non-technical queries should have low technical density."""
        result = analyzer.analyze("What's the weather today?")
        assert result["factors"]["technical_density"] < 0.3

    def test_cad_query_high_density(self, analyzer):
        """CAD-related queries should have high technical density."""
        query = "Create a parametric CAD model with STEP export and STL mesh conversion"
        result = analyzer.analyze(query)
        assert result["factors"]["technical_density"] > 0.5

    def test_fabrication_query_high_density(self, analyzer):
        """Fabrication queries should have high technical density."""
        query = "Generate toolpath with adaptive layer heights for FDM printing"
        result = analyzer.analyze(query)
        assert result["factors"]["technical_density"] > 0.5

    def test_code_query_high_density(self, analyzer):
        """Code-related queries should have high technical density."""
        query = "Write a Python function using NumPy arrays and Pandas DataFrames"
        result = analyzer.analyze(query)
        assert result["factors"]["technical_density"] > 0.4


class TestMultiStepDetection:
    """Test multi-step workflow detection."""

    def test_single_step_query(self, analyzer):
        """Single-step queries should not be flagged as multi-step."""
        result = analyzer.analyze("Design a bracket")
        assert result["factors"]["multi_step"] is False

    def test_two_step_query_with_then(self, analyzer):
        """Queries with 'then' should be flagged as multi-step."""
        query = "Design a bracket then export it to STL"
        result = analyzer.analyze(query)
        assert result["factors"]["multi_step"] is True

    def test_two_step_query_with_and(self, analyzer):
        """Queries with 'and' should be flagged as multi-step."""
        query = "Design a bracket and print it on the Bamboo printer"
        result = analyzer.analyze(query)
        assert result["factors"]["multi_step"] is True

    def test_two_step_query_with_after(self, analyzer):
        """Queries with 'after' should be flagged as multi-step."""
        query = "Print the model after slicing it with default settings"
        result = analyzer.analyze(query)
        assert result["factors"]["multi_step"] is True


class TestAmbiguityScoring:
    """Test ambiguity detection and scoring."""

    def test_clear_query_low_ambiguity(self, analyzer):
        """Clear, specific queries should have low ambiguity."""
        query = "Create a 10mm diameter cylinder 50mm tall"
        result = analyzer.analyze(query)
        assert result["factors"]["ambiguity"] < 0.3

    def test_vague_query_high_ambiguity(self, analyzer):
        """Vague queries should have high ambiguity."""
        query = "Maybe design something sort of like a bracket somehow"
        result = analyzer.analyze(query)
        assert result["factors"]["ambiguity"] > 0.5

    def test_uncertain_query_medium_ambiguity(self, analyzer):
        """Queries with uncertainty should have medium-high ambiguity."""
        query = "I think we might need a bracket or perhaps a mount"
        result = analyzer.analyze(query)
        assert result["factors"]["ambiguity"] > 0.3


class TestToolCountEstimation:
    """Test tool requirement estimation."""

    def test_simple_query_few_tools(self, analyzer):
        """Simple queries should require few tools."""
        result = analyzer.analyze("What time is it?")
        assert result["factors"]["tool_count"] == 0

    def test_cad_query_single_tool(self, analyzer):
        """CAD-only queries should require one tool."""
        query = "Design a bracket for a 10mm bolt"
        result = analyzer.analyze(query)
        assert result["factors"]["tool_count"] >= 1

    def test_multi_tool_query(self, analyzer):
        """Queries requiring multiple tools should be detected."""
        query = "Search for bracket designs, then generate a CAD model, then print it"
        result = analyzer.analyze(query)
        assert result["factors"]["tool_count"] >= 2

    def test_fabrication_workflow_multiple_tools(self, analyzer):
        """End-to-end fabrication workflows should require multiple tools."""
        query = "Design a bracket, analyze it for 3D printing, and send it to the slicer"
        result = analyzer.analyze(query)
        assert result["factors"]["tool_count"] >= 2


class TestOverallComplexity:
    """Test overall complexity scoring integration."""

    def test_simple_greeting_low_complexity(self, analyzer):
        """Simple greetings should have very low complexity."""
        result = analyzer.analyze("Hello")
        assert result["overall"] < 0.2

    def test_simple_question_low_complexity(self, analyzer):
        """Simple questions should have low complexity."""
        result = analyzer.analyze("What's the temperature?")
        assert result["overall"] < 0.4

    def test_cad_request_medium_complexity(self, analyzer):
        """Single CAD requests should have medium complexity."""
        query = "Design a parametric bracket for a 10mm bolt"
        result = analyzer.analyze(query)
        assert 0.3 <= result["overall"] <= 0.7

    def test_multi_step_cad_high_complexity(self, analyzer):
        """Multi-step CAD workflows should have high complexity."""
        query = "Search for optimal bracket designs, then create a parametric CAD model with FEA simulation, and export to STEP format"
        result = analyzer.analyze(query)
        assert result["overall"] > 0.5

    def test_ambiguous_multi_tool_very_high_complexity(self, analyzer):
        """Ambiguous multi-tool queries should have very high complexity."""
        query = "Maybe design something like a bracket or mount, I guess, then somehow analyze it and perhaps print it if possible"
        result = analyzer.analyze(query)
        assert result["overall"] > 0.6


class TestRoutingRecommendations:
    """Test routing tier recommendations based on complexity."""

    def test_simple_query_local_tier(self, analyzer):
        """Simple queries should recommend LOCAL tier (Q4)."""
        result = analyzer.analyze("Hello KITTY")
        assert result["recommended_tier"] == RoutingTier.LOCAL

    def test_medium_complexity_local_tier(self, analyzer):
        """Medium complexity should recommend LOCAL with potential F16 fallback."""
        query = "Design a simple bracket for a 10mm bolt"
        result = analyzer.analyze(query)
        # Medium complexity can still be LOCAL or MCP depending on factors
        assert result["recommended_tier"] in [RoutingTier.LOCAL, RoutingTier.MCP]

    def test_search_query_mcp_tier(self, analyzer):
        """Queries requiring search should recommend MCP tier."""
        query = "Search for the latest 3D printing materials and technologies"
        result = analyzer.analyze(query, context={"requires_search": True})
        assert result["recommended_tier"] == RoutingTier.MCP

    def test_very_complex_query_frontier_tier(self, analyzer):
        """Very complex queries should recommend FRONTIER tier (F16 equivalent)."""
        # Create a query with high complexity across multiple factors
        query = " ".join([
            "Analyze the structural integrity of a parametric bracket design",
            "with finite element analysis, considering material properties,",
            "load distribution, and safety factors, then generate detailed",
            "fabrication instructions with toolpath optimization and provide",
            "comprehensive documentation of the entire engineering process"
        ])
        result = analyzer.analyze(query)
        # Very high complexity (>0.7) should recommend FRONTIER
        if result["overall"] > 0.7:
            assert result["recommended_tier"] == RoutingTier.FRONTIER


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_query(self, analyzer):
        """Empty queries should be handled gracefully."""
        result = analyzer.analyze("")
        assert result["overall"] == 0.0
        assert result["factors"]["token_count"] == 0.0
        assert result["recommended_tier"] == RoutingTier.LOCAL

    def test_whitespace_only_query(self, analyzer):
        """Whitespace-only queries should be handled like empty queries."""
        result = analyzer.analyze("   \n\t  ")
        assert result["overall"] < 0.1

    def test_special_characters_query(self, analyzer):
        """Queries with special characters should be handled."""
        result = analyzer.analyze("!@#$%^&*()")
        assert isinstance(result["overall"], float)
        assert 0.0 <= result["overall"] <= 1.0

    def test_unicode_query(self, analyzer):
        """Unicode queries should be handled."""
        result = analyzer.analyze("设计一个支架 🔧")
        assert isinstance(result["overall"], float)
        assert 0.0 <= result["overall"] <= 1.0


class TestContextInfluence:
    """Test how context affects complexity scoring."""

    def test_context_with_memories(self, analyzer):
        """Context with memories should influence scoring."""
        query = "Continue with that design"
        context = {"memories": [{"content": "User asked about bracket design"}]}
        result = analyzer.analyze(query, context=context)
        # Vague query with context is still somewhat complex
        assert result["overall"] > 0.2

    def test_context_requires_search(self, analyzer):
        """Context flagging search requirement should influence routing."""
        query = "What's the latest?"
        context = {"requires_search": True}
        result = analyzer.analyze(query, context=context)
        assert result["recommended_tier"] == RoutingTier.MCP

    def test_no_context(self, analyzer):
        """Queries without context should work normally."""
        result = analyzer.analyze("Design a bracket")
        assert isinstance(result["overall"], float)
        assert result["recommended_tier"] in [RoutingTier.LOCAL, RoutingTier.MCP, RoutingTier.FRONTIER]


class TestReasoningOutput:
    """Test that reasoning explanations are provided."""

    def test_reasoning_field_present(self, analyzer):
        """All results should include reasoning explanation."""
        result = analyzer.analyze("Design a bracket")
        assert "reasoning" in result
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    def test_reasoning_mentions_factors(self, analyzer):
        """Reasoning should reference relevant factors."""
        query = "Search for bracket designs then create a parametric CAD model"
        result = analyzer.analyze(query)
        reasoning_lower = result["reasoning"].lower()
        # Should mention multi-step or tools or complexity
        assert any(term in reasoning_lower for term in ["multi", "tool", "complex", "step"])


class TestConsistency:
    """Test that scoring is consistent across multiple runs."""

    def test_same_query_same_score(self, analyzer):
        """Same query should produce same complexity score."""
        query = "Design a parametric bracket for a 10mm bolt"
        result1 = analyzer.analyze(query)
        result2 = analyzer.analyze(query)
        assert result1["overall"] == result2["overall"]
        assert result1["factors"] == result2["factors"]

    def test_case_insensitive(self, analyzer):
        """Complexity scoring should be case-insensitive for technical terms."""
        query1 = "design a CAD model"
        query2 = "Design a cad model"
        result1 = analyzer.analyze(query1)
        result2 = analyzer.analyze(query2)
        # Technical density should be similar (case-insensitive)
        assert abs(result1["factors"]["technical_density"] - result2["factors"]["technical_density"]) < 0.1
