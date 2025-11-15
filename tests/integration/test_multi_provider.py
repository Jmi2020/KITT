"""Integration tests for multi-provider LLM support."""

from __future__ import annotations

import pytest
from services.brain.src.brain.routes.query import parse_inline_provider_syntax, _detect_provider_from_model


class TestInlineProviderSyntax:
    """Test inline provider/model syntax parsing."""

    def test_parse_provider_syntax(self):
        """Test @provider: syntax parsing."""
        prompt, provider, model = parse_inline_provider_syntax("@openai: What is AI?")
        assert prompt == "What is AI?"
        assert provider == "openai"
        assert model is None

    def test_parse_model_syntax(self):
        """Test #model: syntax parsing."""
        prompt, provider, model = parse_inline_provider_syntax("#gpt-4o-mini: Explain quantum computing")
        assert prompt == "Explain quantum computing"
        assert provider == "openai"  # Auto-detected from model name
        assert model == "gpt-4o-mini"

    def test_parse_no_syntax(self):
        """Test regular query without inline syntax."""
        prompt, provider, model = parse_inline_provider_syntax("What is the weather?")
        assert prompt == "What is the weather?"
        assert provider is None
        assert model is None

    def test_parse_multiline_query(self):
        """Test inline syntax with multiline query."""
        query = "@anthropic: Explain:\n1. Quantum mechanics\n2. Relativity"
        prompt, provider, model = parse_inline_provider_syntax(query)
        assert prompt == "Explain:\n1. Quantum mechanics\n2. Relativity"
        assert provider == "anthropic"
        assert model is None

    def test_detect_openai_models(self):
        """Test OpenAI model detection."""
        assert _detect_provider_from_model("gpt-4o-mini") == "openai"
        assert _detect_provider_from_model("gpt-4o") == "openai"
        assert _detect_provider_from_model("o1-preview") == "openai"
        assert _detect_provider_from_model("o1-mini") == "openai"

    def test_detect_anthropic_models(self):
        """Test Anthropic model detection."""
        assert _detect_provider_from_model("claude-3-5-haiku-20241022") == "anthropic"
        assert _detect_provider_from_model("claude-3-5-sonnet-20241022") == "anthropic"

    def test_detect_mistral_models(self):
        """Test Mistral model detection."""
        assert _detect_provider_from_model("mistral-small-latest") == "mistral"
        assert _detect_provider_from_model("mistral-large-latest") == "mistral"

    def test_detect_perplexity_models(self):
        """Test Perplexity model detection."""
        assert _detect_provider_from_model("sonar") == "perplexity"
        assert _detect_provider_from_model("sonar-pro") == "perplexity"
        assert _detect_provider_from_model("sonar-reasoning-pro") == "perplexity"

    def test_detect_gemini_models(self):
        """Test Gemini model detection."""
        assert _detect_provider_from_model("gemini-1.5-flash") == "gemini"
        assert _detect_provider_from_model("gemini-1.5-pro") == "gemini"

    def test_detect_unknown_model(self):
        """Test unknown model returns None."""
        assert _detect_provider_from_model("unknown-model-xyz") is None


@pytest.mark.integration
class TestProvidersEndpoint:
    """Test /api/providers/available endpoint."""

    @pytest.mark.asyncio
    async def test_providers_endpoint_structure(self, test_client):
        """Test providers endpoint returns correct structure."""
        response = test_client.get("/api/providers/available")
        assert response.status_code == 200

        data = response.json()
        assert "providers" in data

        providers = data["providers"]
        assert "local" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "mistral" in providers
        assert "perplexity" in providers
        assert "gemini" in providers

    @pytest.mark.asyncio
    async def test_local_provider_always_enabled(self, test_client):
        """Test local provider is always enabled."""
        response = test_client.get("/api/providers/available")
        data = response.json()

        local_provider = data["providers"]["local"]
        assert local_provider["enabled"] is True
        assert local_provider["name"] == "Local (llama.cpp)"
        assert "Q4" in local_provider["models"]
        assert "F16" in local_provider["models"]
        assert local_provider["cost_per_1m_tokens"]["input"] == 0.0
        assert local_provider["cost_per_1m_tokens"]["output"] == 0.0

    @pytest.mark.asyncio
    async def test_provider_info_fields(self, test_client):
        """Test provider info contains all required fields."""
        response = test_client.get("/api/providers/available")
        data = response.json()

        for provider_name, provider_info in data["providers"].items():
            assert "enabled" in provider_info
            assert "name" in provider_info
            assert "models" in provider_info
            assert "cost_per_1m_tokens" in provider_info
            assert "icon" in provider_info
            assert isinstance(provider_info["models"], list)
            assert len(provider_info["models"]) > 0


@pytest.mark.integration
class TestQueryWithProviderOverride:
    """Test query endpoint with provider/model overrides."""

    @pytest.mark.asyncio
    async def test_query_with_inline_provider(self, test_client):
        """Test query with @provider: syntax."""
        # Note: This test requires a running brain service
        # For now, just test the syntax parsing is integrated

        payload = {
            "conversationId": "test-123",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "@openai: What is 2+2?",
        }

        # Test would fail without proper orchestrator, but syntax should parse
        # In real integration test, would verify provider was used
        pass  # Placeholder for future full integration test

    @pytest.mark.asyncio
    async def test_query_with_explicit_provider(self, test_client):
        """Test query with explicit provider parameter."""
        payload = {
            "conversationId": "test-123",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "What is quantum computing?",
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
        }

        # Placeholder for future full integration test
        pass


# Fixture for test client (would be defined in conftest.py)
@pytest.fixture
def test_client():
    """Create test client for FastAPI app."""
    from fastapi.testclient import TestClient
    from services.brain.src.brain.app import app

    return TestClient(app)
