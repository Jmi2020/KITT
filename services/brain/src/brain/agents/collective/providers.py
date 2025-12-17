"""
Specialist provider configurations for Collective Meta-Agent.

Defines available specialists (local and cloud) with their models,
costs, and availability status based on API keys.
"""

import os
from dataclasses import dataclass, field
from typing import List, Literal

ProviderType = Literal["local", "openai", "anthropic", "perplexity", "gemini"]


@dataclass
class SpecialistConfig:
    """Configuration for a specialist in the collective."""

    id: str                      # Unique identifier: "openai_gpt4o", "local_q4"
    display_name: str            # Human-readable: "GPT-4o-mini (OpenAI)"
    provider: ProviderType       # Provider type for routing
    model: str                   # Model identifier for API calls
    description: str             # What this specialist is good at
    cost_per_1m_in: float = 0.0  # Cost per 1M input tokens (USD)
    cost_per_1m_out: float = 0.0 # Cost per 1M output tokens (USD)
    local_which: str | None = None  # For local models: which param for chat_async
    is_available: bool = field(init=False, default=False)

    def __post_init__(self):
        """Check availability based on API keys."""
        self.is_available = self._check_availability()

    def _check_availability(self) -> bool:
        """Check if this specialist is available (API key present for cloud)."""
        if self.provider == "local":
            return True  # Local models always available

        env_vars = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "perplexity": "PERPLEXITY_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }
        env_var = env_vars.get(self.provider)
        if env_var:
            return bool(os.getenv(env_var))
        return False

    def estimate_cost(self, input_tokens: int = 2000, output_tokens: int = 2000) -> float:
        """Estimate cost for a proposal generation."""
        in_cost = (input_tokens / 1_000_000) * self.cost_per_1m_in
        out_cost = (output_tokens / 1_000_000) * self.cost_per_1m_out
        return in_cost + out_cost


# ============================================================================
# Available Specialists
# ============================================================================

LOCAL_SPECIALISTS: List[SpecialistConfig] = [
    SpecialistConfig(
        id="local_q4",
        display_name="Athene V2 (Local)",
        provider="local",
        model="Athene V2 Q4",
        local_which="Q4",
        description="Tool orchestration and general reasoning",
        cost_per_1m_in=0.0,
        cost_per_1m_out=0.0,
    ),
    SpecialistConfig(
        id="local_coder",
        display_name="Qwen Coder 32B (Local)",
        provider="local",
        model="Qwen 2.5 Coder 32B",
        local_which="CODER",
        description="Code generation and analysis",
        cost_per_1m_in=0.0,
        cost_per_1m_out=0.0,
    ),
    SpecialistConfig(
        id="local_q4b",
        display_name="Mistral 7B (Local)",
        provider="local",
        model="Mistral 7B",
        local_which="Q4B",
        description="Fast responses and diverse perspectives",
        cost_per_1m_in=0.0,
        cost_per_1m_out=0.0,
    ),
]

CLOUD_SPECIALISTS: List[SpecialistConfig] = [
    # OpenAI Models (December 2025)
    SpecialistConfig(
        id="openai_gpt5",
        display_name="GPT-5 (OpenAI)",
        provider="openai",
        model="gpt-5",
        description="Latest GPT-5 model with full reasoning capabilities",
        cost_per_1m_in=1.25,
        cost_per_1m_out=10.00,
    ),
    SpecialistConfig(
        id="openai_gpt52",
        display_name="GPT-5.2 (OpenAI)",
        provider="openai",
        model="gpt-5.2",
        description="Cutting-edge GPT-5.2 with 400K context and reasoning dial",
        cost_per_1m_in=1.75,
        cost_per_1m_out=14.00,
    ),
    SpecialistConfig(
        id="openai_gpt5_mini",
        display_name="GPT-5-mini (OpenAI)",
        provider="openai",
        model="gpt-5-mini",
        description="Cost-effective GPT-5 variant for faster responses",
        cost_per_1m_in=0.25,
        cost_per_1m_out=2.00,
    ),
    SpecialistConfig(
        id="openai_gpt4o_mini",
        display_name="GPT-4o-mini (OpenAI)",
        provider="openai",
        model="gpt-4o-mini",
        description="Fast and affordable GPT-4o variant",
        cost_per_1m_in=0.15,
        cost_per_1m_out=0.60,
    ),
    # Anthropic Models (December 2025)
    SpecialistConfig(
        id="anthropic_sonnet_45",
        display_name="Claude Sonnet 4.5 (Anthropic)",
        provider="anthropic",
        model="claude-sonnet-4-5",
        description="Best coding and agentic model with tool use",
        cost_per_1m_in=3.00,
        cost_per_1m_out=15.00,
    ),
    SpecialistConfig(
        id="anthropic_opus_45",
        display_name="Claude Opus 4.5 (Anthropic)",
        provider="anthropic",
        model="claude-opus-4-5",
        description="Frontier Opus model for difficult reasoning tasks",
        cost_per_1m_in=5.00,
        cost_per_1m_out=25.00,
    ),
    SpecialistConfig(
        id="anthropic_haiku_45",
        display_name="Claude Haiku 4.5 (Anthropic)",
        provider="anthropic",
        model="claude-haiku-4-5",
        description="Fast and cost-effective Claude 4 model",
        cost_per_1m_in=1.00,
        cost_per_1m_out=5.00,
    ),
    # Perplexity Models (December 2025)
    SpecialistConfig(
        id="perplexity_sonar",
        display_name="Sonar (Perplexity)",
        provider="perplexity",
        model="sonar",
        description="Search-augmented responses with real-time citations",
        cost_per_1m_in=1.00,
        cost_per_1m_out=1.00,
    ),
    SpecialistConfig(
        id="perplexity_sonar_pro",
        display_name="Sonar Pro (Perplexity)",
        provider="perplexity",
        model="sonar-pro",
        description="Advanced search-augmented reasoning with deeper analysis",
        cost_per_1m_in=3.00,
        cost_per_1m_out=15.00,
    ),
    # Google Gemini Models (December 2025)
    SpecialistConfig(
        id="gemini_3_pro",
        display_name="Gemini 3 Pro (Google)",
        provider="gemini",
        model="gemini-3-pro-preview",
        description="Google's newest generation with 1M context",
        cost_per_1m_in=2.00,
        cost_per_1m_out=12.00,
    ),
    SpecialistConfig(
        id="gemini_25_pro",
        display_name="Gemini 2.5 Pro (Google)",
        provider="gemini",
        model="gemini-2.5-pro",
        description="Advanced thinking model with multimodal support",
        cost_per_1m_in=1.25,
        cost_per_1m_out=5.00,
    ),
    SpecialistConfig(
        id="gemini_25_flash",
        display_name="Gemini 2.5 Flash (Google)",
        provider="gemini",
        model="gemini-2.5-flash",
        description="Fast Google model with 1M context window",
        cost_per_1m_in=0.15,
        cost_per_1m_out=0.60,
    ),
]

# Combined list of all specialists
ALL_SPECIALISTS: List[SpecialistConfig] = LOCAL_SPECIALISTS + CLOUD_SPECIALISTS


def get_available_specialists(include_unavailable: bool = True) -> List[SpecialistConfig]:
    """
    Get list of specialists with current availability status.

    Args:
        include_unavailable: If True, include specialists without API keys
                            (they'll have is_available=False)

    Returns:
        List of SpecialistConfig with updated availability
    """
    # Re-check availability (in case env vars changed)
    specialists = []
    for spec in ALL_SPECIALISTS:
        # Create fresh instance to re-check availability
        new_spec = SpecialistConfig(
            id=spec.id,
            display_name=spec.display_name,
            provider=spec.provider,
            model=spec.model,
            description=spec.description,
            cost_per_1m_in=spec.cost_per_1m_in,
            cost_per_1m_out=spec.cost_per_1m_out,
            local_which=spec.local_which,
        )
        if include_unavailable or new_spec.is_available:
            specialists.append(new_spec)

    return specialists


def get_specialist_by_id(specialist_id: str) -> SpecialistConfig | None:
    """Get a specialist configuration by its ID."""
    for spec in ALL_SPECIALISTS:
        if spec.id == specialist_id:
            # Return fresh instance with current availability
            return SpecialistConfig(
                id=spec.id,
                display_name=spec.display_name,
                provider=spec.provider,
                model=spec.model,
                description=spec.description,
                cost_per_1m_in=spec.cost_per_1m_in,
                cost_per_1m_out=spec.cost_per_1m_out,
                local_which=spec.local_which,
            )
    return None


def get_specialists_by_ids(specialist_ids: List[str]) -> List[SpecialistConfig]:
    """Get multiple specialists by their IDs, preserving order."""
    return [
        spec for spec in [get_specialist_by_id(sid) for sid in specialist_ids]
        if spec is not None
    ]


def estimate_total_cost(specialist_ids: List[str], tokens_per_proposal: int = 4000) -> float:
    """
    Estimate total cost for running a collective with given specialists.

    Args:
        specialist_ids: List of specialist IDs to include
        tokens_per_proposal: Estimated total tokens (in+out) per proposal

    Returns:
        Estimated cost in USD
    """
    total = 0.0
    input_tokens = tokens_per_proposal // 2
    output_tokens = tokens_per_proposal // 2

    for spec in get_specialists_by_ids(specialist_ids):
        total += spec.estimate_cost(input_tokens, output_tokens)

    return total
