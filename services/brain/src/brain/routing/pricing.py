# noqa: D401
"""Provider pricing configuration and cost estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProviderName = Literal["perplexity", "openai", "anthropic", "google"]


@dataclass
class ProviderPricing:
    """Per-1K-token pricing for a provider."""

    input_cost: float  # USD per 1K input tokens
    output_cost: float  # USD per 1K output tokens


# Current pricing as of January 2025
# Updated manually when providers change prices (rare)
PRICING_CONFIG: dict[ProviderName, ProviderPricing] = {
    "perplexity": ProviderPricing(input_cost=0.005, output_cost=0.005),
    "openai": ProviderPricing(input_cost=0.03, output_cost=0.06),
    "anthropic": ProviderPricing(input_cost=0.015, output_cost=0.075),
    "google": ProviderPricing(input_cost=0.007, output_cost=0.021),
}


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Uses rough approximation: ~4 characters per token (conservative).

    Args:
        text: Input text to estimate

    Returns:
        Estimated token count
    """
    return max(1, len(text) // 4)


def estimate_cost(
    prompt: str,
    provider: ProviderName,
    max_output_tokens: int = 512,
) -> float:
    """Estimate API call cost before making the request.

    Args:
        prompt: Input prompt text
        provider: Provider name (perplexity, openai, anthropic, google)
        max_output_tokens: Expected maximum output tokens

    Returns:
        Estimated cost in USD
    """
    pricing = PRICING_CONFIG.get(provider)
    if not pricing:
        return 0.0

    input_tokens = estimate_tokens(prompt)

    # Cost = (input_tokens * input_price + output_tokens * output_price) / 1000
    cost = (input_tokens * pricing.input_cost + max_output_tokens * pricing.output_cost) / 1000

    return cost


def calculate_actual_cost(
    provider: ProviderName,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate actual cost from token usage in API response.

    Args:
        provider: Provider name
        input_tokens: Actual input tokens used
        output_tokens: Actual output tokens generated

    Returns:
        Actual cost in USD
    """
    pricing = PRICING_CONFIG.get(provider)
    if not pricing:
        return 0.0

    cost = (input_tokens * pricing.input_cost + output_tokens * pricing.output_cost) / 1000

    return cost


__all__ = [
    "ProviderName",
    "ProviderPricing",
    "PRICING_CONFIG",
    "estimate_tokens",
    "estimate_cost",
    "calculate_actual_cost",
]
