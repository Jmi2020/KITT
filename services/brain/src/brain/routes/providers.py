# noqa: D401
"""HTTP routes for multi-provider collective status."""

from __future__ import annotations

from typing import Dict
from fastapi import APIRouter
from pydantic import BaseModel

from ..llm_client import ProviderRegistry, PROVIDER_COSTS

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderInfo(BaseModel):
    """Information about a provider."""

    enabled: bool
    name: str
    models: list[str]
    cost_per_1m_tokens: Dict[str, float]
    icon: str
    setup_url: str | None = None


@router.get("/available")
async def get_available_providers() -> Dict[str, Dict[str, ProviderInfo]]:
    """Get list of available providers with their status.

    Returns:
        Dictionary with 'providers' key containing provider info

    Example response:
        {
            "providers": {
                "local": {
                    "enabled": true,
                    "name": "Local (llama.cpp)",
                    "models": ["Q4", "F16", "CODER", "Q4B"],
                    "cost_per_1m_tokens": {"input": 0.0, "output": 0.0},
                    "icon": "🏠"
                },
                "openai": {
                    "enabled": false,
                    "name": "OpenAI",
                    "models": ["gpt-4o-mini", "gpt-4o", "o1-mini"],
                    "cost_per_1m_tokens": {"input": 0.15, "output": 0.60},
                    "icon": "🤖",
                    "setup_url": "https://platform.openai.com/api-keys"
                },
                ...
            }
        }
    """
    registry = ProviderRegistry()

    providers = {
        "local": ProviderInfo(
            enabled=True,
            name="Local (llama.cpp)",
            models=["Q4", "F16", "CODER", "Q4B"],
            cost_per_1m_tokens={"input": 0.0, "output": 0.0},
            icon="🏠",
        ),
        "openai": ProviderInfo(
            enabled=registry.is_enabled("openai"),
            name="OpenAI",
            models=["gpt-4o-mini", "gpt-4o", "o1-mini", "o1-preview"],
            cost_per_1m_tokens=PROVIDER_COSTS["openai"],
            icon="🤖",
            setup_url="https://platform.openai.com/api-keys",
        ),
        "anthropic": ProviderInfo(
            enabled=registry.is_enabled("anthropic"),
            name="Anthropic",
            models=["claude-3-5-haiku-20241022", "claude-3-5-sonnet-20241022"],
            cost_per_1m_tokens=PROVIDER_COSTS["anthropic"],
            icon="🧠",
            setup_url="https://console.anthropic.com/settings/keys",
        ),
        "mistral": ProviderInfo(
            enabled=registry.is_enabled("mistral"),
            name="Mistral AI",
            models=["mistral-small-latest", "mistral-large-latest"],
            cost_per_1m_tokens=PROVIDER_COSTS["mistral"],
            icon="🌀",
            setup_url="https://console.mistral.ai/api-keys",
        ),
        "perplexity": ProviderInfo(
            enabled=registry.is_enabled("perplexity"),
            name="Perplexity",
            models=["sonar", "sonar-pro", "sonar-reasoning-pro"],
            cost_per_1m_tokens=PROVIDER_COSTS["perplexity"],
            icon="🔍",
            setup_url="https://www.perplexity.ai/settings/api",
        ),
        "gemini": ProviderInfo(
            enabled=registry.is_enabled("gemini"),
            name="Google Gemini",
            models=["gemini-1.5-flash", "gemini-1.5-pro"],
            cost_per_1m_tokens=PROVIDER_COSTS["gemini"],
            icon="💎",
            setup_url="https://aistudio.google.com/app/apikey",
        ),
    }

    return {"providers": providers}
