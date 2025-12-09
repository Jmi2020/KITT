"""
Tests for agent and endpoint registry: ModelEndpoint, KittyAgent, ENDPOINTS, KITTY_AGENTS.
"""

import asyncio

import pytest

from brain.agents.parallel.types import ModelTier
from brain.agents.parallel.registry import (
    ModelEndpoint,
    KittyAgent,
    ENDPOINTS,
    KITTY_AGENTS,
    get_agent,
    get_endpoint,
    list_agents,
    list_endpoints,
)


class TestModelEndpoint:
    """Tests for ModelEndpoint dataclass."""

    @pytest.mark.asyncio
    async def test_acquire_slot_success(self, mock_endpoint):
        """acquire_slot should return True when slots available."""
        assert mock_endpoint.active_slots == 0
        assert mock_endpoint.available_slots == 3

        result = await mock_endpoint.acquire_slot()

        assert result is True
        assert mock_endpoint.active_slots == 1
        assert mock_endpoint.available_slots == 2

    @pytest.mark.asyncio
    async def test_acquire_slot_multiple(self, mock_endpoint):
        """Should acquire multiple slots up to max."""
        for i in range(3):
            result = await mock_endpoint.acquire_slot()
            assert result is True
            assert mock_endpoint.active_slots == i + 1

        assert mock_endpoint.available_slots == 0

    @pytest.mark.asyncio
    async def test_acquire_slot_exhausted(self, mock_endpoint):
        """acquire_slot should return False when at capacity."""
        # Fill all slots
        for _ in range(mock_endpoint.max_slots):
            await mock_endpoint.acquire_slot()

        # Try to acquire one more
        result = await mock_endpoint.acquire_slot()

        assert result is False
        assert mock_endpoint.active_slots == mock_endpoint.max_slots

    @pytest.mark.asyncio
    async def test_release_slot(self, mock_endpoint):
        """release_slot should decrement active count."""
        await mock_endpoint.acquire_slot()
        await mock_endpoint.acquire_slot()
        assert mock_endpoint.active_slots == 2

        await mock_endpoint.release_slot()

        assert mock_endpoint.active_slots == 1
        assert mock_endpoint.available_slots == 2

    @pytest.mark.asyncio
    async def test_release_slot_floor(self, mock_endpoint):
        """release_slot should not go below 0."""
        assert mock_endpoint.active_slots == 0

        await mock_endpoint.release_slot()

        assert mock_endpoint.active_slots == 0

    @pytest.mark.asyncio
    async def test_concurrent_acquire_race_safe(self, mock_endpoint):
        """Concurrent acquires should be race-safe."""
        # Try to acquire more slots than available concurrently
        tasks = [mock_endpoint.acquire_slot() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # Only max_slots should succeed
        assert sum(results) == mock_endpoint.max_slots
        assert mock_endpoint.active_slots == mock_endpoint.max_slots

    def test_is_available_property(self, mock_endpoint):
        """is_available should reflect slot availability."""
        assert mock_endpoint.is_available is True

    def test_status_returns_dict(self, mock_endpoint):
        """status() should return monitoring dict."""
        status = mock_endpoint.status()

        assert status["name"] == "Test Endpoint"
        assert status["url"] == "http://localhost:9999"
        assert status["active"] == 0
        assert status["max"] == 3
        assert status["available"] == 3


class TestKittyAgent:
    """Tests for KittyAgent dataclass."""

    def test_initialization(self, mock_agent):
        """Agent should initialize with all fields."""
        assert mock_agent.name == "test_agent"
        assert mock_agent.role == "Test Agent"
        assert mock_agent.primary_tier == ModelTier.Q4_TOOLS
        assert mock_agent.fallback_tier == ModelTier.CODER
        assert mock_agent.tool_allowlist == ["test_tool"]
        assert mock_agent.max_tokens == 1024
        assert mock_agent.temperature == 0.5

    def test_build_system_prompt_with_tools(self, mock_agent):
        """build_system_prompt should include tool guidance."""
        prompt = mock_agent.build_system_prompt(include_tools=True)

        assert "You are a test agent." in prompt
        assert "test_tool" in prompt
        assert "Recommended tools" in prompt

    def test_build_system_prompt_without_tools(self, mock_agent):
        """build_system_prompt should exclude tools when disabled."""
        prompt = mock_agent.build_system_prompt(include_tools=False)

        assert "You are a test agent." in prompt
        assert "Recommended tools" not in prompt

    def test_build_system_prompt_empty_allowlist(self):
        """build_system_prompt should skip tool section for empty allowlist."""
        agent = KittyAgent(
            name="reasoner",
            role="Reasoner",
            expertise="Thinking",
            system_prompt="Think deeply.",
            primary_tier=ModelTier.GPTOSS_REASON,
            tool_allowlist=[],  # Empty
        )

        prompt = agent.build_system_prompt(include_tools=True)

        assert "Think deeply." in prompt
        assert "Recommended tools" not in prompt


class TestEndpointsRegistry:
    """Tests for global ENDPOINTS registry."""

    def test_has_all_tiers(self):
        """ENDPOINTS should have entries for all tiers except MCP_EXTERNAL."""
        # MCP_EXTERNAL is not in ENDPOINTS (no slot tracking)
        expected_tiers = {
            ModelTier.Q4_TOOLS,
            ModelTier.GPTOSS_REASON,
            ModelTier.VISION,
            ModelTier.CODER,
            ModelTier.SUMMARY,
        }

        actual_tiers = set(ENDPOINTS.keys())
        assert actual_tiers == expected_tiers

    def test_q4_endpoint_config(self):
        """Q4 endpoint should have correct default config."""
        endpoint = ENDPOINTS.get(ModelTier.Q4_TOOLS)
        assert endpoint is not None
        assert "8083" in endpoint.base_url
        assert endpoint.supports_tools is True
        assert endpoint.max_slots >= 1

    def test_gptoss_endpoint_config(self):
        """GPTOSS endpoint should have Ollama config."""
        endpoint = ENDPOINTS.get(ModelTier.GPTOSS_REASON)
        assert endpoint is not None
        assert "11434" in endpoint.base_url
        assert endpoint.thinking_mode is not None

    def test_vision_endpoint_config(self):
        """Vision endpoint should support vision."""
        endpoint = ENDPOINTS.get(ModelTier.VISION)
        assert endpoint is not None
        assert endpoint.supports_vision is True


class TestAgentRegistry:
    """Tests for global KITTY_AGENTS registry."""

    def test_has_8_agents(self):
        """KITTY_AGENTS should have exactly 8 agents."""
        assert len(KITTY_AGENTS) == 8

    def test_all_agent_names(self):
        """All expected agent names should exist."""
        expected = {
            "researcher",
            "reasoner",
            "cad_designer",
            "fabricator",
            "coder",
            "vision_analyst",
            "analyst",
            "summarizer",
        }
        actual = set(KITTY_AGENTS.keys())
        assert actual == expected

    def test_researcher_config(self):
        """Researcher should use Q4 tier with web tools."""
        agent = KITTY_AGENTS.get("researcher")
        assert agent is not None
        assert agent.primary_tier == ModelTier.Q4_TOOLS
        assert "web_search" in agent.tool_allowlist

    def test_reasoner_config(self):
        """Reasoner should use GPTOSS with fallback."""
        agent = KITTY_AGENTS.get("reasoner")
        assert agent is not None
        assert agent.primary_tier == ModelTier.GPTOSS_REASON
        assert agent.fallback_tier == ModelTier.Q4_TOOLS
        assert agent.tool_allowlist == []  # Pure reasoning

    def test_coder_config(self):
        """Coder should use CODER tier."""
        agent = KITTY_AGENTS.get("coder")
        assert agent is not None
        assert agent.primary_tier == ModelTier.CODER
        assert agent.fallback_tier == ModelTier.Q4_TOOLS
        assert agent.temperature == 0.2  # Low for code

    def test_summarizer_config(self):
        """Summarizer should use SUMMARY tier."""
        agent = KITTY_AGENTS.get("summarizer")
        assert agent is not None
        assert agent.primary_tier == ModelTier.SUMMARY
        assert agent.max_tokens == 512  # Short summaries


class TestRegistryFunctions:
    """Tests for registry helper functions."""

    def test_get_agent_valid(self):
        """get_agent should return agent by name."""
        agent = get_agent("researcher")
        assert agent is not None
        assert agent.name == "researcher"

    def test_get_agent_invalid(self):
        """get_agent should return None for unknown name."""
        agent = get_agent("nonexistent_agent")
        assert agent is None

    def test_get_endpoint_valid(self):
        """get_endpoint should return endpoint by tier."""
        endpoint = get_endpoint(ModelTier.Q4_TOOLS)
        assert endpoint is not None
        assert "8083" in endpoint.base_url

    def test_get_endpoint_invalid(self):
        """get_endpoint should return None for unknown tier."""
        endpoint = get_endpoint(ModelTier.MCP_EXTERNAL)
        assert endpoint is None  # Not in registry

    def test_list_agents(self):
        """list_agents should return all agent names."""
        names = list_agents()
        assert len(names) == 8
        assert "researcher" in names
        assert "coder" in names

    def test_list_endpoints(self):
        """list_endpoints should return status for all endpoints."""
        endpoints = list_endpoints()
        assert len(endpoints) == 5

        # Check structure
        for tier_name, status in endpoints.items():
            assert "name" in status
            assert "active" in status
            assert "max" in status
            assert "available" in status
