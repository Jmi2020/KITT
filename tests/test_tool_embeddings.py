"""Tests for semantic tool selection using embeddings."""

import pytest
from unittest.mock import MagicMock, patch


# Sample tool definitions for testing
SAMPLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, facts, prices, or any real-time data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to execute"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_cad",
            "description": "Generate a 3D CAD model based on a text description for physical objects or parts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Detailed description of the object to design"},
                    "format": {"type": "string", "enum": ["step", "stl", "dxf"], "description": "Output format"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather conditions and forecast for a location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name or coordinates"}
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "control_lights",
            "description": "Control smart home lights - turn on, off, dim, or change color.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["on", "off", "dim", "color"]},
                    "room": {"type": "string", "description": "Room name"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to a recipient with subject and body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body content"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]


class TestToolEmbeddingManager:
    """Tests for ToolEmbeddingManager class."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        with patch("brain.tools.embeddings.redis") as mock:
            mock_client = MagicMock()
            mock.from_url.return_value = mock_client
            mock_client.get.return_value = None  # No cache hits
            yield mock_client

    def test_tool_to_text_conversion(self, mock_redis):
        """Test that tool definitions are converted to searchable text."""
        from brain.tools.embeddings import ToolEmbeddingManager

        manager = ToolEmbeddingManager()
        text = manager._tool_to_text(SAMPLE_TOOLS[0])

        assert "web_search" in text
        assert "Search the web" in text
        assert "query" in text

    def test_compute_embeddings(self, mock_redis):
        """Test embedding computation and caching."""
        from brain.tools.embeddings import ToolEmbeddingManager

        manager = ToolEmbeddingManager()
        manager.compute_embeddings(SAMPLE_TOOLS)

        # Should have embeddings for all tools
        assert len(manager._tool_embeddings) == len(SAMPLE_TOOLS)
        assert len(manager._tools_by_name) == len(SAMPLE_TOOLS)

        # Embeddings should be numpy arrays
        for name, embedding in manager._tool_embeddings.items():
            assert embedding.shape == (384,)  # all-MiniLM-L6-v2 dimension

    def test_search_returns_relevant_tools(self, mock_redis):
        """Test that search returns semantically relevant tools."""
        from brain.tools.embeddings import ToolEmbeddingManager

        manager = ToolEmbeddingManager()
        manager.compute_embeddings(SAMPLE_TOOLS)

        # Search for weather-related query
        results = manager.search("What's the weather like today?", top_k=2)

        tool_names = [t["function"]["name"] for t in results]
        assert "get_weather" in tool_names

        # Search for CAD-related query
        results = manager.search("Design a bracket for mounting", top_k=2)
        tool_names = [t["function"]["name"] for t in results]
        assert "generate_cad" in tool_names

        # Search for home automation query
        results = manager.search("Turn on the living room lights", top_k=2)
        tool_names = [t["function"]["name"] for t in results]
        assert "control_lights" in tool_names

    def test_search_threshold_filtering(self, mock_redis):
        """Test that threshold filtering works."""
        from brain.tools.embeddings import ToolEmbeddingManager

        manager = ToolEmbeddingManager()
        manager.compute_embeddings(SAMPLE_TOOLS)

        # High threshold should return fewer results
        results_high = manager.search("random gibberish xyz123", top_k=5, threshold=0.9)
        results_low = manager.search("random gibberish xyz123", top_k=5, threshold=0.1)

        # Low threshold should return more results
        assert len(results_low) >= len(results_high)


class TestSemanticToolRegistry:
    """Tests for semantic tool selection in tool_registry."""

    def test_get_tools_for_prompt_semantic_off_mode(self):
        """Test that 'off' mode returns empty list."""
        from brain.routing.tool_registry import get_tools_for_prompt_semantic

        result = get_tools_for_prompt_semantic(
            prompt="test",
            all_tools=SAMPLE_TOOLS,
            mode="off",
        )
        assert result == []

    def test_get_tools_for_prompt_semantic_on_mode(self):
        """Test that 'on' mode returns all tools."""
        from brain.routing.tool_registry import get_tools_for_prompt_semantic

        result = get_tools_for_prompt_semantic(
            prompt="test",
            all_tools=SAMPLE_TOOLS,
            mode="on",
        )
        assert result == SAMPLE_TOOLS

    def test_get_tools_for_prompt_semantic_auto_mode(self):
        """Test that 'auto' mode uses embedding search."""
        from brain.routing.tool_registry import get_tools_for_prompt_semantic

        # Patch the import inside the function
        with patch("brain.tools.embeddings.get_embedding_manager") as mock:
            manager = MagicMock()
            mock.return_value = manager
            manager.search.return_value = [SAMPLE_TOOLS[0]]

            result = get_tools_for_prompt_semantic(
                prompt="search for news",
                all_tools=SAMPLE_TOOLS,
                mode="auto",
            )

            manager.compute_embeddings.assert_called_once()
            manager.search.assert_called_once()
            assert len(result) >= 1


class TestContextSavings:
    """Tests to verify context savings."""

    def test_context_savings_calculation(self, mock_redis=None):
        """Demonstrate context savings with semantic selection."""
        import json

        # Calculate token estimate for all tools
        all_tools_json = json.dumps(SAMPLE_TOOLS)
        all_tools_chars = len(all_tools_json)
        all_tools_tokens_estimate = all_tools_chars // 4  # Rough estimate

        # Calculate for subset (top 2 tools)
        subset = SAMPLE_TOOLS[:2]
        subset_json = json.dumps(subset)
        subset_chars = len(subset_json)
        subset_tokens_estimate = subset_chars // 4

        savings_percent = (1 - subset_tokens_estimate / all_tools_tokens_estimate) * 100

        print(f"\nContext Savings Analysis:")
        print(f"  All tools: ~{all_tools_tokens_estimate} tokens")
        print(f"  Subset (2 tools): ~{subset_tokens_estimate} tokens")
        print(f"  Savings: ~{savings_percent:.1f}%")

        # With 5 tools, selecting 2 should save ~60%
        assert savings_percent > 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
