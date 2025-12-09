"""
Tests for ParallelLLMClient: slot-aware LLM generation with mocked HTTP.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from brain.agents.parallel.types import ModelTier
from brain.agents.parallel.registry import ModelEndpoint, KittyAgent
from brain.agents.parallel.slot_manager import SlotManager
from brain.agents.parallel.llm_adapter import (
    ParallelLLMClient,
    get_parallel_client,
    reset_parallel_client,
)


class TestParallelLLMClientInit:
    """Tests for client initialization."""

    def test_init_default(self):
        """Should initialize with default slot manager."""
        client = ParallelLLMClient()
        assert client._timeout == 120.0
        assert client._slot_manager is not None

    def test_init_custom_slot_manager(self, mock_endpoints):
        """Should accept custom slot manager."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        assert client._slot_manager is slot_manager

    def test_init_custom_timeout(self):
        """Should accept custom timeout."""
        client = ParallelLLMClient(timeout=60.0)
        assert client._timeout == 60.0


class TestGenerateLlamaCpp:
    """Tests for llama.cpp generation."""

    @pytest.mark.asyncio
    async def test_generate_llamacpp_success(self, mock_endpoints, mock_httpx_client):
        """Should generate via llama.cpp endpoint."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        response, metadata = await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Hello, world!",
            system_prompt="You are helpful.",
            max_tokens=100,
            temperature=0.5,
        )

        assert response == "Test response from llama.cpp"
        assert metadata["tokens"] == 50
        assert metadata["tokens_prompt"] == 100
        assert metadata["tier"] == "q4_tools"
        assert metadata["fallback_used"] is False
        assert "latency_ms" in metadata

    @pytest.mark.asyncio
    async def test_generate_llamacpp_formats_prompt(self, mock_endpoints, mock_httpx_client):
        """Should format prompt with chat template."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Test prompt",
            system_prompt="System message",
        )

        # Verify the request was made with formatted prompt
        call_args = mock_httpx_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert "<|system|>" in payload["prompt"]
        assert "System message" in payload["prompt"]
        assert "<|user|>" in payload["prompt"]
        assert "Test prompt" in payload["prompt"]
        assert "<|assistant|>" in payload["prompt"]


class TestGenerateOllama:
    """Tests for Ollama generation."""

    @pytest.mark.asyncio
    async def test_generate_ollama_success(self, mock_endpoints, mock_httpx_client):
        """Should generate via Ollama endpoint."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        response, metadata = await client.generate(
            tier=ModelTier.GPTOSS_REASON,
            prompt="Analyze this problem",
            system_prompt="You are a reasoner.",
            max_tokens=500,
        )

        assert response == "Test response from Ollama"
        assert metadata["tokens"] == 50
        assert metadata["tier"] == "gptoss_reason"
        assert "thinking" in metadata

    @pytest.mark.asyncio
    async def test_generate_ollama_with_thinking_mode(self, mock_endpoints, mock_httpx_client):
        """Should include thinking mode option for Ollama."""
        # Ensure GPTOSS has thinking mode
        mock_endpoints[ModelTier.GPTOSS_REASON].thinking_mode = "medium"

        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        await client.generate(
            tier=ModelTier.GPTOSS_REASON,
            prompt="Think deeply",
        )

        # Verify thinking mode was included
        call_args = mock_httpx_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert payload["options"]["think"] == "medium"


class TestSlotManagement:
    """Tests for automatic slot management."""

    @pytest.mark.asyncio
    async def test_slot_acquired_before_generation(self, mock_endpoints, mock_httpx_client):
        """Should acquire slot before making request."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        # Before generation
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0

        await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Test",
        )

        # After generation (slot should be released)
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0

    @pytest.mark.asyncio
    async def test_slot_released_on_success(self, mock_endpoints, mock_httpx_client):
        """Should release slot after successful generation."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        await client.generate(tier=ModelTier.Q4_TOOLS, prompt="Test")

        # Slot should be released
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0

    @pytest.mark.asyncio
    async def test_slot_released_on_error(self, mock_endpoints, mock_httpx_error_client):
        """Should release slot even when generation fails."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_error_client

        with pytest.raises(Exception):
            await client.generate(tier=ModelTier.Q4_TOOLS, prompt="Test")

        # Slot should still be released
        assert mock_endpoints[ModelTier.Q4_TOOLS].active_slots == 0

    @pytest.mark.asyncio
    async def test_slot_exhaustion_raises_error(self, mock_endpoints):
        """Should raise error when no slots available."""
        # Exhaust all Q4 slots
        for _ in range(mock_endpoints[ModelTier.Q4_TOOLS].max_slots):
            await mock_endpoints[ModelTier.Q4_TOOLS].acquire_slot()

        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)

        with pytest.raises(RuntimeError, match="Could not acquire slot"):
            await client.generate(
                tier=ModelTier.Q4_TOOLS,
                prompt="Test",
                allow_fallback=False,
            )


class TestFallbackBehavior:
    """Tests for fallback tier behavior."""

    @pytest.mark.asyncio
    async def test_uses_fallback_when_primary_full(self, mock_endpoints, mock_httpx_client):
        """Should use fallback tier when primary is exhausted."""
        # Exhaust Q4 slots
        q4 = mock_endpoints[ModelTier.Q4_TOOLS]
        for _ in range(q4.max_slots):
            await q4.acquire_slot()

        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        # Create agent with fallback
        agent = KittyAgent(
            name="test",
            role="Test",
            expertise="Testing",
            system_prompt="Test agent",
            primary_tier=ModelTier.Q4_TOOLS,
            fallback_tier=ModelTier.CODER,
        )

        response, metadata = await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Test",
            agent=agent,
            allow_fallback=True,
        )

        assert metadata["tier"] == "coder"
        assert metadata["fallback_used"] is True

    @pytest.mark.asyncio
    async def test_no_fallback_when_disabled(self, mock_endpoints):
        """Should not use fallback when disabled."""
        # Exhaust Q4 slots
        for _ in range(mock_endpoints[ModelTier.Q4_TOOLS].max_slots):
            await mock_endpoints[ModelTier.Q4_TOOLS].acquire_slot()

        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)

        with pytest.raises(RuntimeError):
            await client.generate(
                tier=ModelTier.Q4_TOOLS,
                prompt="Test",
                allow_fallback=False,
            )


class TestAgentToolGuidance:
    """Tests for soft tool allowlist injection."""

    @pytest.mark.asyncio
    async def test_injects_tool_guidance(self, mock_endpoints, mock_httpx_client):
        """Should inject tool recommendations for agent."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        agent = KittyAgent(
            name="researcher",
            role="Researcher",
            expertise="Research",
            system_prompt="Do research",
            primary_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=["web_search", "fetch_webpage"],
        )

        await client.generate(
            tier=ModelTier.Q4_TOOLS,
            prompt="Research AI",
            system_prompt="Base prompt",
            agent=agent,
        )

        # Verify tool guidance was added
        call_args = mock_httpx_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert "web_search" in payload["prompt"]
        assert "fetch_webpage" in payload["prompt"]


class TestGenerateForAgent:
    """Tests for agent-specific generation."""

    @pytest.mark.asyncio
    async def test_generate_for_agent_uses_defaults(self, mock_endpoints, mock_httpx_client):
        """Should use agent's default settings."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        agent = KittyAgent(
            name="coder",
            role="Coder",
            expertise="Coding",
            system_prompt="Write code",
            primary_tier=ModelTier.CODER,
            max_tokens=4096,
            temperature=0.2,
        )

        response, metadata = await client.generate_for_agent(
            agent=agent,
            prompt="Write a Python function",
        )

        assert response is not None
        # Verify it used the coder tier
        assert metadata["tier"] == "coder"

    @pytest.mark.asyncio
    async def test_generate_for_agent_with_context(self, mock_endpoints, mock_httpx_client):
        """Should prepend context to prompt."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        agent = KittyAgent(
            name="coder",
            role="Coder",
            expertise="Coding",
            system_prompt="Write code",
            primary_tier=ModelTier.CODER,
        )

        await client.generate_for_agent(
            agent=agent,
            prompt="Now implement the algorithm",
            context="Previous task found: quicksort is best",
        )

        call_args = mock_httpx_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert "Previous task found" in payload["prompt"]
        assert "Now implement the algorithm" in payload["prompt"]

    @pytest.mark.asyncio
    async def test_generate_for_agent_overrides(self, mock_endpoints, mock_httpx_client):
        """Should allow overriding agent defaults."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)
        client._http_client = mock_httpx_client

        agent = KittyAgent(
            name="coder",
            role="Coder",
            expertise="Coding",
            system_prompt="Write code",
            primary_tier=ModelTier.CODER,
            max_tokens=4096,
            temperature=0.2,
        )

        await client.generate_for_agent(
            agent=agent,
            prompt="Short answer only",
            max_tokens=100,  # Override
            temperature=0.5,  # Override (must be non-zero due to `or` logic)
        )

        call_args = mock_httpx_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")

        assert payload["n_predict"] == 100
        assert payload["temperature"] == 0.5  # Overridden value


class TestStatusAndCleanup:
    """Tests for status reporting and cleanup."""

    def test_get_slot_status(self, mock_endpoints):
        """Should return slot status from slot manager."""
        slot_manager = SlotManager(endpoints=mock_endpoints)
        client = ParallelLLMClient(slot_manager=slot_manager)

        status = client.get_slot_status()

        assert len(status) == len(mock_endpoints)
        for tier_name, info in status.items():
            assert "active" in info
            assert "max" in info

    @pytest.mark.asyncio
    async def test_close_http_client(self, mock_httpx_client):
        """Should close HTTP client."""
        client = ParallelLLMClient()
        client._http_client = mock_httpx_client

        await client.close()

        mock_httpx_client.aclose.assert_called_once()
        assert client._http_client is None


class TestSingleton:
    """Tests for singleton pattern."""

    @pytest.mark.asyncio
    async def test_get_parallel_client_singleton(self):
        """get_parallel_client should return same instance."""
        await reset_parallel_client()

        c1 = get_parallel_client()
        c2 = get_parallel_client()

        assert c1 is c2

    @pytest.mark.asyncio
    async def test_reset_parallel_client(self):
        """reset_parallel_client should create new instance."""
        c1 = get_parallel_client()

        await reset_parallel_client()

        c2 = get_parallel_client()
        assert c1 is not c2
