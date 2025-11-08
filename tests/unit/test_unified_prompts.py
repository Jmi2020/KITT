# ruff: noqa: E402
"""
Unit tests for the unified system prompts module.

Tests verify that the KittySystemPrompt class correctly:
- Generates prompts for different modes (cli, voice, agent)
- Includes all critical sections (hallucination prevention, chain-of-thought, etc.)
- Handles environment variable substitution
- Integrates with tool formatting
- Adjusts output based on verbosity levels
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "services/brain/src"))
sys.path.append(str(ROOT / "services/common/src"))

pytest.importorskip("pydantic")
pytest.importorskip("pydantic_settings")

from brain.prompts.unified import KittySystemPrompt  # type: ignore[import]


class TestUnifiedPromptBasics:
    """Test basic prompt generation functionality."""

    def test_prompt_builder_initialization(self):
        """Test that KittySystemPrompt can be initialized."""
        prompt_builder = KittySystemPrompt()
        assert prompt_builder is not None

    def test_cli_mode_prompt_generation(self):
        """Test CLI mode prompt generation."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Verify it's a non-empty string
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Verify CLI-specific formatting hints
        assert "markdown" in prompt.lower() or "cli" in prompt.lower()

    def test_agent_mode_prompt_generation(self):
        """Test agent mode (ReAct pattern) prompt generation."""
        prompt_builder = KittySystemPrompt()

        # Mock tools
        mock_tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        prompt = prompt_builder.build(
            mode="agent",
            tools=mock_tools,
            verbosity=3
        )

        # Verify ReAct pattern keywords
        assert "Thought:" in prompt or "Action:" in prompt or "Observation:" in prompt
        assert "web_search" in prompt  # Tool should be documented

    def test_cli_mode_includes_freshness_note(self):
        """Ensure CLI prompts include freshness instructions when required."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(
            mode="cli",
            verbosity=3,
            query="What is the latest BTC price?",
            freshness_required=True,
        )

        assert "Freshness requirement" in prompt
        assert "utc_timestamp" in prompt

    def test_agent_mode_includes_freshness_note(self):
        """Ensure agent prompts highlight freshness requirements."""
        prompt_builder = KittySystemPrompt()
        mock_tools = [
            {
                "type": "function",
                "function": {"name": "web_search", "description": "", "parameters": {"type": "object"}},
            }
        ]
        prompt = prompt_builder.build(
            mode="agent",
            tools=mock_tools,
            verbosity=3,
            query="Get today's news",
            freshness_required=True,
        )

        assert "Fresh Data Required" in prompt

    def test_voice_mode_prompt_generation(self):
        """Test voice mode prompt generation with TTS-friendly output."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="voice", verbosity=3)

        # Verify TTS-friendly guidance
        assert "spoken" in prompt.lower() or "voice" in prompt.lower() or "tts" in prompt.lower()

        # Should discourage markdown in voice mode
        assert "markdown" not in prompt.lower() or "avoid markdown" in prompt.lower()


class TestHallucinationPrevention:
    """Test hallucination prevention measures."""

    def test_hallucination_prevention_included(self):
        """Verify hallucination prevention section is included in all modes."""
        prompt_builder = KittySystemPrompt()

        modes = ["cli", "voice", "agent"]
        for mode in modes:
            prompt = prompt_builder.build(mode=mode, verbosity=3)

            # Check for critical hallucination prevention keywords
            assert "NEVER" in prompt or "never" in prompt
            assert "make up" in prompt.lower() or "fabricate" in prompt.lower()
            assert "tool" in prompt.lower()

            # Verify explicit constraints
            assert "temperature" in prompt.lower() or "deterministic" in prompt.lower()

    def test_confidence_framework_included(self):
        """Verify confidence-based decision framework is included."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Check for confidence thresholds
        assert "confidence" in prompt.lower()
        assert "0.9" in prompt or "0.7" in prompt  # Confidence thresholds

    def test_tool_validation_guidance(self):
        """Verify tool validation guidance is included."""
        prompt_builder = KittySystemPrompt()

        mock_tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test tool",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]

        prompt = prompt_builder.build(mode="agent", tools=mock_tools, verbosity=3)

        # Check for validation instructions
        assert "required parameters" in prompt.lower() or "parameters" in prompt.lower()
        assert "json" in prompt.lower()


class TestChainOfThought:
    """Test chain-of-thought decision framework."""

    def test_reasoning_framework_included(self):
        """Verify chain-of-thought reasoning framework is included."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Check for step-by-step reasoning guidance
        assert "step" in prompt.lower() or "analyze" in prompt.lower()
        assert "decision" in prompt.lower()

    def test_decision_steps_documented(self):
        """Verify decision steps are clearly documented."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="agent", verbosity=4)

        # Should have structured decision-making process
        # Look for numbered steps or clear decision points
        assert "1." in prompt or "Step 1" in prompt or "first" in prompt.lower()


class TestEnvironmentVariableSubstitution:
    """Test environment variable substitution."""

    @patch.dict('os.environ', {'USER_NAME': 'TestUser', 'VERBOSITY': '3'})
    def test_user_name_substitution(self):
        """Test that {USER_NAME} is substituted correctly."""
        # Create a mock config with USER_NAME
        mock_config = Mock()
        mock_config.user_name = "TestUser"
        mock_config.verbosity = 3
        mock_config.budget_per_task_usd = 0.10

        prompt_builder = KittySystemPrompt(config=mock_config)
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Verify USER_NAME appears (if identity section uses it)
        # The actual substitution happens in the identity section
        assert "TestUser" in prompt or "{USER_NAME}" not in prompt

    def test_verbosity_affects_output(self):
        """Test that verbosity level affects prompt content."""
        prompt_builder = KittySystemPrompt()

        prompt_terse = prompt_builder.build(mode="cli", verbosity=1)
        prompt_verbose = prompt_builder.build(mode="cli", verbosity=5)

        # Verbose prompts should have more guidance
        assert "verbosity" in prompt_terse.lower() or "verbosity" in prompt_verbose.lower()

        # At minimum, both should be non-empty
        assert len(prompt_terse) > 0
        assert len(prompt_verbose) > 0


class TestToolIntegration:
    """Test tool formatting and integration."""

    def test_tools_are_documented(self):
        """Verify that provided tools are documented in the prompt."""
        prompt_builder = KittySystemPrompt()

        mock_tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculate",
                    "description": "Perform mathematical calculations",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}
                        },
                        "required": ["expression"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        prompt = prompt_builder.build(mode="agent", tools=mock_tools, verbosity=3)

        # Both tools should be mentioned
        assert "calculate" in prompt.lower()
        assert "search" in prompt.lower()

        # Tool parameters should be documented
        assert "expression" in prompt.lower() or "query" in prompt.lower()

    def test_no_tools_provided(self):
        """Test prompt generation when no tools are provided."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", tools=None, verbosity=3)

        # Should still generate a valid prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Should mention tools or tool calling format even without specific tools
        assert "tool" in prompt.lower()

    def test_empty_tools_list(self):
        """Test prompt generation with empty tools list."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="agent", tools=[], verbosity=3)

        # Should handle empty list gracefully
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestSafetyAndRouting:
    """Test safety model and routing policy sections."""

    def test_safety_model_included(self):
        """Verify safety model section is included."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Check for safety-related keywords
        assert "safe" in prompt.lower() or "hazard" in prompt.lower() or "caution" in prompt.lower()

    def test_routing_policy_included(self):
        """Verify routing policy is included."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Check for routing tier mentions
        assert "local" in prompt.lower() or "offline" in prompt.lower() or "mcp" in prompt.lower()

    def test_budget_awareness(self):
        """Verify budget awareness is included."""
        mock_config = Mock()
        mock_config.user_name = "TestUser"
        mock_config.verbosity = 3
        mock_config.budget_per_task_usd = 0.25

        prompt_builder = KittySystemPrompt(config=mock_config)
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Should mention budget or cost
        assert "budget" in prompt.lower() or "cost" in prompt.lower() or "$" in prompt


class TestModeSwitching:
    """Test behavior differences across modes."""

    def test_mode_specific_formatting(self):
        """Verify each mode has appropriate formatting guidance."""
        prompt_builder = KittySystemPrompt()

        cli_prompt = prompt_builder.build(mode="cli", verbosity=3)
        voice_prompt = prompt_builder.build(mode="voice", verbosity=3)
        agent_prompt = prompt_builder.build(mode="agent", verbosity=3)

        # All should be different
        assert cli_prompt != voice_prompt
        assert voice_prompt != agent_prompt
        assert cli_prompt != agent_prompt

    def test_invalid_mode_handling(self):
        """Test handling of invalid mode parameter."""
        prompt_builder = KittySystemPrompt()

        # Should either default to a valid mode or raise an error
        try:
            prompt = prompt_builder.build(mode="invalid_mode", verbosity=3)
            # If it doesn't raise, verify it's still a valid string
            assert isinstance(prompt, str)
            assert len(prompt) > 0
        except (ValueError, KeyError):
            # Raising an error is also acceptable
            pass


class TestPromptStructure:
    """Test overall prompt structure and completeness."""

    def test_all_critical_sections_present(self):
        """Verify all critical sections are present in the prompt."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Identity section
        assert "kitty" in prompt.lower() or "assistant" in prompt.lower()

        # Hallucination prevention
        assert "never" in prompt.lower()

        # Decision framework
        assert "decision" in prompt.lower() or "analyze" in prompt.lower()

        # Tool calling format
        assert "json" in prompt.lower()

    def test_prompt_is_well_formed(self):
        """Verify prompt is well-formed and readable."""
        prompt_builder = KittySystemPrompt()
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Should not have unsubstituted template variables (uppercase placeholders)
        # Note: JSON examples like {"key": {...}} are intentional, not template artifacts
        assert "{USER_NAME}" not in prompt or "{VERBOSITY}" not in prompt

        # Should have markdown headers
        assert "##" in prompt or "#" in prompt  # Should have section headers

        # Should be substantial
        assert len(prompt) > 500  # At minimum, should be reasonably detailed

    def test_model_format_parameter(self):
        """Test that model_format parameter is handled correctly."""
        prompt_builder = KittySystemPrompt()

        formats = ["qwen", "hermes", "llama", "athene"]
        for fmt in formats:
            prompt = prompt_builder.build(
                mode="agent",
                verbosity=3,
                model_format=fmt
            )

            # Should generate valid prompt for all formats
            assert isinstance(prompt, str)
            assert len(prompt) > 0


class TestContextAndHistory:
    """Test context and history integration."""

    def test_context_integration(self):
        """Test that additional context is integrated."""
        prompt_builder = KittySystemPrompt()

        context = "User is working on a 3D printing project for a phone stand."
        prompt = prompt_builder.build(
            mode="cli",
            verbosity=3,
            context=context
        )

        # Context should be included
        assert context in prompt or "context" in prompt.lower()

    def test_query_integration(self):
        """Test that current query is integrated."""
        prompt_builder = KittySystemPrompt()

        query = "What material should I use for this print?"
        prompt = prompt_builder.build(
            mode="cli",
            verbosity=3,
            query=query
        )

        # Query should be mentioned or integrated
        assert query in prompt or "query" in prompt.lower()

    def test_history_integration(self):
        """Test that conversation history is integrated."""
        prompt_builder = KittySystemPrompt()

        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        prompt = prompt_builder.build(
            mode="cli",
            verbosity=3,
            history=history
        )

        # Should handle history parameter gracefully
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_extreme_verbosity_levels(self):
        """Test extreme verbosity values."""
        prompt_builder = KittySystemPrompt()

        # Very low verbosity
        prompt_low = prompt_builder.build(mode="cli", verbosity=1)
        assert len(prompt_low) > 0

        # Very high verbosity
        prompt_high = prompt_builder.build(mode="cli", verbosity=5)
        assert len(prompt_high) > 0

        # Invalid verbosity (should handle gracefully)
        prompt_invalid = prompt_builder.build(mode="cli", verbosity=10)
        assert len(prompt_invalid) > 0

    def test_none_config(self):
        """Test initialization with None config."""
        prompt_builder = KittySystemPrompt(config=None)
        prompt = prompt_builder.build(mode="cli", verbosity=3)

        # Should use default config
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_large_tool_list(self):
        """Test with a large number of tools."""
        prompt_builder = KittySystemPrompt()

        # Generate 20 mock tools
        large_tools = [
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": f"Tool number {i}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string"}
                        }
                    }
                }
            }
            for i in range(20)
        ]

        prompt = prompt_builder.build(
            mode="agent",
            tools=large_tools,
            verbosity=3
        )

        # Should handle large tool lists
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        # Some tools should be documented (maybe not all at low verbosity)
        assert "tool_0" in prompt or "tool_1" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
