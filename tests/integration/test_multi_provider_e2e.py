"""E2E tests for multi-provider LLM integration.

These tests require:
- Running KITT services (brain, llama.cpp)
- Optional: API keys for cloud providers (skip tests if not configured)
"""

from __future__ import annotations

import os
import time
from typing import Optional

import pytest
import httpx

# Test configuration
BRAIN_API_BASE = os.getenv("BRAIN_API_BASE", "http://localhost:8000")
TIMEOUT = 30.0

# Provider availability (skip tests if providers not enabled)
OPENAI_ENABLED = os.getenv("ENABLE_OPENAI_COLLECTIVE", "false").lower() == "true"
ANTHROPIC_ENABLED = os.getenv("ENABLE_ANTHROPIC_COLLECTIVE", "false").lower() == "true"
MISTRAL_ENABLED = os.getenv("ENABLE_MISTRAL_COLLECTIVE", "false").lower() == "true"
PERPLEXITY_ENABLED = os.getenv("ENABLE_PERPLEXITY_COLLECTIVE", "false").lower() == "true"
GEMINI_ENABLED = os.getenv("ENABLE_GEMINI_COLLECTIVE", "false").lower() == "true"


@pytest.fixture
def http_client():
    """Create HTTP client for API calls."""
    return httpx.Client(base_url=BRAIN_API_BASE, timeout=TIMEOUT)


@pytest.mark.e2e
class TestProviderEndpoint:
    """Test /api/providers/available endpoint with live service."""

    def test_providers_endpoint_accessible(self, http_client):
        """Test providers endpoint is accessible."""
        response = http_client.get("/api/providers/available")
        assert response.status_code == 200

    def test_local_provider_always_enabled(self, http_client):
        """Test local provider is always enabled."""
        response = http_client.get("/api/providers/available")
        data = response.json()

        local = data["providers"]["local"]
        assert local["enabled"] is True
        assert local["cost_per_1m_tokens"]["input"] == 0.0

    def test_provider_status_matches_env(self, http_client):
        """Test provider status matches environment configuration."""
        response = http_client.get("/api/providers/available")
        data = response.json()

        providers = data["providers"]
        assert providers["openai"]["enabled"] == OPENAI_ENABLED
        assert providers["anthropic"]["enabled"] == ANTHROPIC_ENABLED
        assert providers["mistral"]["enabled"] == MISTRAL_ENABLED
        assert providers["perplexity"]["enabled"] == PERPLEXITY_ENABLED
        assert providers["gemini"]["enabled"] == GEMINI_ENABLED


@pytest.mark.e2e
class TestLocalProviderQuery:
    """Test queries using local provider (always available)."""

    def test_simple_query_local(self, http_client):
        """Test simple query with local provider."""
        payload = {
            "conversationId": "test-e2e-local",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "What is 2+2? Answer with just the number.",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "result" in data
        # Should contain "4" in the response
        result_text = str(data["result"])
        assert "4" in result_text

    def test_query_with_local_fallback(self, http_client):
        """Test query falls back to local when provider disabled."""
        payload = {
            "conversationId": "test-e2e-fallback",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Count to 3.",
            "provider": "openai",  # Request OpenAI (likely disabled)
            "model": "gpt-4o-mini",
        }

        response = http_client.post("/api/query", json=payload)
        # Should succeed even if OpenAI is disabled (fallback to local)
        assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.skipif(not OPENAI_ENABLED, reason="OpenAI provider not enabled")
class TestOpenAIProvider:
    """Test OpenAI provider integration (requires API key)."""

    def test_openai_simple_query(self, http_client):
        """Test simple query with OpenAI provider."""
        payload = {
            "conversationId": "test-e2e-openai",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Say exactly: 'OpenAI test successful'",
            "provider": "openai",
            "model": "gpt-4o-mini",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200

        data = response.json()
        result_text = str(data["result"]).lower()
        assert "openai" in result_text or "successful" in result_text

    def test_openai_inline_syntax(self, http_client):
        """Test inline @openai: syntax."""
        payload = {
            "conversationId": "test-e2e-openai-inline",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "@openai: What is 5+5? Answer with just the number.",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200

        data = response.json()
        result_text = str(data["result"])
        assert "10" in result_text


@pytest.mark.e2e
@pytest.mark.skipif(not ANTHROPIC_ENABLED, reason="Anthropic provider not enabled")
class TestAnthropicProvider:
    """Test Anthropic provider integration (requires API key)."""

    def test_anthropic_simple_query(self, http_client):
        """Test simple query with Anthropic provider."""
        payload = {
            "conversationId": "test-e2e-anthropic",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Say exactly: 'Anthropic test successful'",
            "provider": "anthropic",
            "model": "claude-3-5-haiku-20241022",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200

        data = response.json()
        result_text = str(data["result"]).lower()
        assert "anthropic" in result_text or "successful" in result_text

    def test_anthropic_model_inline_syntax(self, http_client):
        """Test inline #claude: syntax."""
        payload = {
            "conversationId": "test-e2e-anthropic-inline",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "#claude-3-5-haiku-20241022: What is 7+3? Answer with just the number.",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200

        data = response.json()
        result_text = str(data["result"])
        assert "10" in result_text


@pytest.mark.e2e
class TestPerformanceOverhead:
    """Test performance overhead of multi-provider system."""

    def test_local_query_latency(self, http_client):
        """Test local query has acceptable latency."""
        payload = {
            "conversationId": "test-perf-local",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Count to 3.",
        }

        # Warm up (first call may be slower)
        http_client.post("/api/query", json=payload)

        # Measure latency
        start = time.time()
        response = http_client.post("/api/query", json=payload)
        latency_ms = (time.time() - start) * 1000

        assert response.status_code == 200
        # Local query should be fast (< 5 seconds for simple query)
        assert latency_ms < 5000, f"Local query too slow: {latency_ms:.0f}ms"

    def test_providers_endpoint_latency(self, http_client):
        """Test /api/providers/available has low latency."""
        # Warm up
        http_client.get("/api/providers/available")

        # Measure latency
        start = time.time()
        response = http_client.get("/api/providers/available")
        latency_ms = (time.time() - start) * 1000

        assert response.status_code == 200
        # Endpoint should be very fast (< 100ms)
        assert latency_ms < 100, f"Providers endpoint too slow: {latency_ms:.0f}ms"

    @pytest.mark.skipif(not OPENAI_ENABLED, reason="OpenAI provider not enabled")
    def test_cloud_provider_latency(self, http_client):
        """Test cloud provider has expected latency."""
        payload = {
            "conversationId": "test-perf-cloud",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Say: 'OK'",
            "provider": "openai",
            "model": "gpt-4o-mini",
        }

        start = time.time()
        response = http_client.post("/api/query", json=payload)
        latency_ms = (time.time() - start) * 1000

        assert response.status_code == 200
        # Cloud query expected to be slower (network latency)
        # But should complete within reasonable time (< 10 seconds)
        assert latency_ms < 10000, f"Cloud query too slow: {latency_ms:.0f}ms"
        # Should be slower than local (network overhead)
        assert latency_ms > 100, f"Cloud query suspiciously fast: {latency_ms:.0f}ms"


@pytest.mark.e2e
class TestFallbackBehavior:
    """Test automatic fallback to local provider."""

    def test_disabled_provider_fallback(self, http_client):
        """Test requesting disabled provider falls back to local."""
        # Request a provider that's likely disabled
        payload = {
            "conversationId": "test-fallback-disabled",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "Count to 3.",
            "provider": "mistral",  # Likely disabled
            "model": "mistral-small-latest",
        }

        response = http_client.post("/api/query", json=payload)
        # Should succeed (fallback to local)
        assert response.status_code == 200

        data = response.json()
        assert "result" in data
        # Result should contain counting
        result_text = str(data["result"])
        assert any(str(i) in result_text for i in [1, 2, 3])

    def test_invalid_provider_fallback(self, http_client):
        """Test requesting invalid provider falls back to local."""
        payload = {
            "conversationId": "test-fallback-invalid",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "What is 1+1?",
            "provider": "nonexistent-provider",
            "model": "fake-model",
        }

        response = http_client.post("/api/query", json=payload)
        # Should succeed (fallback to local)
        assert response.status_code == 200


@pytest.mark.e2e
class TestInlineSyntaxIntegration:
    """Test inline syntax parsing in live system."""

    def test_inline_provider_syntax_parsed(self, http_client):
        """Test @provider: syntax is parsed correctly."""
        payload = {
            "conversationId": "test-inline-provider",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "@local: What is 3+3?",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200
        # Should work (local always available)

    def test_inline_model_syntax_parsed(self, http_client):
        """Test #model: syntax is parsed correctly."""
        payload = {
            "conversationId": "test-inline-model",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "#gpt-4o-mini: What is 4+4?",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200
        # Should work (fallback to local if OpenAI disabled)

    def test_multiline_inline_syntax(self, http_client):
        """Test inline syntax with multiline query."""
        payload = {
            "conversationId": "test-inline-multiline",
            "userId": "test-user",
            "intent": "conversation.chat",
            "prompt": "@local: Count:\n1\n2\n3",
        }

        response = http_client.post("/api/query", json=payload)
        assert response.status_code == 200


if __name__ == "__main__":
    """Run E2E tests manually."""
    pytest.main([__file__, "-v", "-m", "e2e"])
