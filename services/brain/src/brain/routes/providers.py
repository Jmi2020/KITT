# noqa: D401
"""HTTP routes for model selection and provider status.

Provides a flat list of available models for the Shell page model selector,
including local models (Ollama, llama.cpp) and cloud providers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..llm_client import ProviderRegistry, PROVIDER_COSTS
from ..data.model_cards import get_model_card, get_all_model_cards

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ModelInfo(BaseModel):
    """Individual model information for flat model list."""

    id: str
    name: str
    type: str  # "local" or "cloud"
    provider: str  # "ollama", "llamacpp", "openai", "anthropic", etc.
    enabled: bool
    default: bool = False
    icon: str
    description: str
    supports_vision: bool = False
    supports_tools: bool = False
    feature_flag: Optional[str] = None  # For cloud providers
    cost: Optional[str] = None  # Human-readable cost estimate
    setup_url: Optional[str] = None
    huggingface_url: Optional[str] = None  # Link to HuggingFace model card
    docs_url: Optional[str] = None  # Link to official documentation
    parameters: Optional[str] = None  # Model size (e.g., "70B")
    context_length: Optional[str] = None  # Context window size


class ModelsResponse(BaseModel):
    """Response containing flat list of all available models."""

    models: List[ModelInfo]
    default_model: str


class ProviderInfo(BaseModel):
    """Information about a provider (legacy format)."""

    enabled: bool
    name: str
    models: list[str]
    cost_per_1m_tokens: Dict[str, float]
    icon: str
    setup_url: str | None = None


@router.get("/models")
async def get_available_models() -> ModelsResponse:
    """Get flat list of all available models for Shell page selector.

    Returns models grouped visually by type (local vs cloud) with:
    - Individual model entries (not grouped by provider)
    - Inline toggle support for cloud providers via feature_flag
    - Vision support indicator for multimodal models

    Returns:
        ModelsResponse with flat model list and default model ID
    """
    registry = ProviderRegistry()

    # Build models list with data from model cards
    model_cards = get_all_model_cards()

    models = [
        # =====================================================================
        # LOCAL MODELS (Free)
        # =====================================================================
        ModelInfo(
            id="gpt-oss",
            name="GPT-OSS 120B",
            type="local",
            provider="ollama",
            enabled=True,
            default=True,
            icon="🧠",
            description="Primary reasoner with thinking mode",
            supports_tools=True,
            huggingface_url=model_cards["gpt-oss"].huggingface_url,
            docs_url=model_cards["gpt-oss"].docs_url,
            parameters=model_cards["gpt-oss"].parameters,
            context_length=model_cards["gpt-oss"].context_length,
        ),
        ModelInfo(
            id="athene-q4",
            name="Athene V2 Agent",
            type="local",
            provider="llamacpp",
            enabled=True,
            icon="🔧",
            description="Fast tool orchestrator (73B Q4)",
            supports_tools=True,
            huggingface_url=model_cards["athene-q4"].huggingface_url,
            docs_url=model_cards["athene-q4"].docs_url,
            parameters=model_cards["athene-q4"].parameters,
            context_length=model_cards["athene-q4"].context_length,
        ),
        ModelInfo(
            id="gemma-vision",
            name="Gemma 3 27B Vision",
            type="local",
            provider="llamacpp",
            enabled=True,
            icon="👁️",
            description="Multimodal image understanding",
            supports_vision=True,
            huggingface_url=model_cards["gemma-vision"].huggingface_url,
            docs_url=model_cards["gemma-vision"].docs_url,
            parameters=model_cards["gemma-vision"].parameters,
            context_length=model_cards["gemma-vision"].context_length,
        ),
        ModelInfo(
            id="hermes-summary",
            name="Hermes 3 8B",
            type="local",
            provider="llamacpp",
            enabled=True,
            icon="📝",
            description="Response summarization",
            supports_tools=True,
            huggingface_url=model_cards["hermes-summary"].huggingface_url,
            docs_url=model_cards["hermes-summary"].docs_url,
            parameters=model_cards["hermes-summary"].parameters,
            context_length=model_cards["hermes-summary"].context_length,
        ),

        # =====================================================================
        # CLOUD MODELS - OpenAI (December 2025)
        # =====================================================================
        ModelInfo(
            id="openai_gpt5",
            name="GPT-5 (OpenAI)",
            type="cloud",
            provider="openai",
            enabled=registry.is_enabled("openai"),
            icon="🤖",
            description="Latest GPT-5 model with full reasoning capabilities",
            supports_tools=True,
            feature_flag="enable_openai_collective",
            cost="$1.25-10.00/1M tokens",
            setup_url="https://platform.openai.com/api-keys",
        ),
        ModelInfo(
            id="openai_gpt52",
            name="GPT-5.2 (OpenAI)",
            type="cloud",
            provider="openai",
            enabled=registry.is_enabled("openai"),
            icon="🤖",
            description="Cutting-edge GPT-5.2 with 400K context and reasoning dial",
            supports_tools=True,
            feature_flag="enable_openai_collective",
            cost="$1.75-14.00/1M tokens",
            setup_url="https://platform.openai.com/api-keys",
            context_length="400,000 tokens",
        ),
        ModelInfo(
            id="openai_gpt5_mini",
            name="GPT-5-mini (OpenAI)",
            type="cloud",
            provider="openai",
            enabled=registry.is_enabled("openai"),
            icon="🤖",
            description="Cost-effective GPT-5 variant for faster responses",
            supports_tools=True,
            feature_flag="enable_openai_collective",
            cost="$0.25-2.00/1M tokens",
            setup_url="https://platform.openai.com/api-keys",
        ),
        ModelInfo(
            id="openai_gpt4o_mini",
            name="GPT-4o-mini (OpenAI)",
            type="cloud",
            provider="openai",
            enabled=registry.is_enabled("openai"),
            icon="🤖",
            description="Fast and affordable GPT-4o variant",
            supports_tools=True,
            feature_flag="enable_openai_collective",
            cost="$0.15-0.60/1M tokens",
            setup_url="https://platform.openai.com/api-keys",
        ),

        # =====================================================================
        # CLOUD MODELS - Anthropic (December 2025)
        # =====================================================================
        ModelInfo(
            id="anthropic_sonnet_45",
            name="Claude Sonnet 4.5 (Anthropic)",
            type="cloud",
            provider="anthropic",
            enabled=registry.is_enabled("anthropic"),
            icon="🧠",
            description="Best coding and agentic model with tool use",
            supports_tools=True,
            feature_flag="enable_anthropic_collective",
            cost="$3.00-15.00/1M tokens",
            setup_url="https://console.anthropic.com/settings/keys",
            context_length="200,000 tokens",
        ),
        ModelInfo(
            id="anthropic_opus_45",
            name="Claude Opus 4.5 (Anthropic)",
            type="cloud",
            provider="anthropic",
            enabled=registry.is_enabled("anthropic"),
            icon="🧠",
            description="Frontier Opus model for difficult reasoning tasks",
            supports_tools=True,
            feature_flag="enable_anthropic_collective",
            cost="$5.00-25.00/1M tokens",
            setup_url="https://console.anthropic.com/settings/keys",
            context_length="200,000 tokens",
        ),
        ModelInfo(
            id="anthropic_haiku_45",
            name="Claude Haiku 4.5 (Anthropic)",
            type="cloud",
            provider="anthropic",
            enabled=registry.is_enabled("anthropic"),
            icon="🧠",
            description="Fast and cost-effective Claude 4 model",
            supports_tools=True,
            feature_flag="enable_anthropic_collective",
            cost="$1.00-5.00/1M tokens",
            setup_url="https://console.anthropic.com/settings/keys",
            context_length="200,000 tokens",
        ),

        # =====================================================================
        # CLOUD MODELS - Perplexity (December 2025)
        # =====================================================================
        ModelInfo(
            id="perplexity_sonar",
            name="Sonar (Perplexity)",
            type="cloud",
            provider="perplexity",
            enabled=registry.is_enabled("perplexity"),
            icon="🔍",
            description="Search-augmented responses with real-time citations",
            feature_flag="enable_perplexity_collective",
            cost="$1.00/1M tokens",
            setup_url="https://www.perplexity.ai/settings/api",
            context_length="128,000 tokens",
        ),
        ModelInfo(
            id="perplexity_sonar_pro",
            name="Sonar Pro (Perplexity)",
            type="cloud",
            provider="perplexity",
            enabled=registry.is_enabled("perplexity"),
            icon="🔍",
            description="Advanced search-augmented reasoning with deeper analysis",
            feature_flag="enable_perplexity_collective",
            cost="$3.00-15.00/1M tokens",
            setup_url="https://www.perplexity.ai/settings/api",
            context_length="128,000 tokens",
        ),

        # =====================================================================
        # CLOUD MODELS - Google Gemini (December 2025)
        # =====================================================================
        ModelInfo(
            id="gemini_3_pro",
            name="Gemini 3 Pro (Google)",
            type="cloud",
            provider="gemini",
            enabled=registry.is_enabled("gemini"),
            icon="💎",
            description="Google's newest generation with 1M context",
            supports_vision=True,
            feature_flag="enable_gemini_collective",
            cost="$2.00-12.00/1M tokens",
            setup_url="https://aistudio.google.com/app/apikey",
            context_length="1,000,000 tokens",
        ),
        ModelInfo(
            id="gemini_25_pro",
            name="Gemini 2.5 Pro (Google)",
            type="cloud",
            provider="gemini",
            enabled=registry.is_enabled("gemini"),
            icon="💎",
            description="Advanced thinking model with multimodal support",
            supports_vision=True,
            feature_flag="enable_gemini_collective",
            cost="$1.25-5.00/1M tokens",
            setup_url="https://aistudio.google.com/app/apikey",
            context_length="2,000,000 tokens",
        ),
        ModelInfo(
            id="gemini_25_flash",
            name="Gemini 2.5 Flash (Google)",
            type="cloud",
            provider="gemini",
            enabled=registry.is_enabled("gemini"),
            icon="💎",
            description="Fast Google model with 1M context window",
            supports_vision=True,
            feature_flag="enable_gemini_collective",
            cost="$0.15-0.60/1M tokens",
            setup_url="https://aistudio.google.com/app/apikey",
            context_length="1,000,000 tokens",
        ),
    ]

    return ModelsResponse(models=models, default_model="gpt-oss")


@router.get("/available")
async def get_available_providers() -> Dict[str, Dict[str, ProviderInfo]]:
    """Get list of available providers with their status (legacy format).

    This endpoint is kept for backward compatibility.
    New code should use /api/providers/models instead.

    Returns:
        Dictionary with 'providers' key containing provider info
    """
    registry = ProviderRegistry()

    providers = {
        "local": ProviderInfo(
            enabled=True,
            name="Local (llama.cpp)",
            models=["Q4", "DEEP", "CODER", "Q4B"],
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


@router.get("/models/{model_id}/card")
async def get_model_card_endpoint(model_id: str) -> Dict[str, Any]:
    """Get detailed model card information for a specific model.

    Returns comprehensive information about the model including:
    - Full description from HuggingFace model card
    - Capabilities list
    - Technical specifications (parameters, context length, architecture)
    - Links to documentation and HuggingFace

    Args:
        model_id: Model identifier (e.g., "gpt-oss", "athene-q4")

    Returns:
        Model card dictionary with all available information

    Raises:
        HTTPException: 404 if model not found
    """
    card = get_model_card(model_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

    return card.to_dict()
