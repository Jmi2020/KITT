"""
Search Provider Configuration

Defines available search providers for research sessions,
following the pattern from Collective Intelligence specialists.

Users can select which search providers to use, similar to
selecting specialists in the Collective system.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Literal
from enum import Enum


class SearchProviderType(str, Enum):
    """Search provider types."""
    DUCKDUCKGO = "duckduckgo"
    BRAVE = "brave"
    TAVILY = "tavily"
    PERPLEXITY = "perplexity"
    SEARXNG = "searxng"  # Local SearXNG instance


@dataclass
class SearchProviderConfig:
    """
    Configuration for a search provider.

    Similar to SpecialistConfig in Collective Intelligence,
    but for search providers instead of LLM specialists.
    """

    id: str
    name: str
    provider_type: SearchProviderType
    cost_per_query: float  # Cost per search query in USD
    env_var: Optional[str]  # Environment variable for API key
    description: str
    icon: str = "🔍"
    max_results_per_query: int = 10
    supports_pagination: bool = False
    rate_limit_per_minute: int = 60

    @property
    def is_available(self) -> bool:
        """Check if provider is available (API key configured if needed)."""
        if self.env_var is None:
            # No API key required (e.g., DuckDuckGo, local SearXNG)
            return True
        return bool(os.getenv(self.env_var))

    @property
    def is_free(self) -> bool:
        """Check if provider is free to use."""
        return self.cost_per_query == 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "provider_type": self.provider_type.value,
            "cost_per_query": self.cost_per_query,
            "description": self.description,
            "icon": self.icon,
            "is_available": self.is_available,
            "is_free": self.is_free,
            "max_results_per_query": self.max_results_per_query,
        }


# Available search providers
SEARCH_PROVIDERS: List[SearchProviderConfig] = [
    # Free providers
    SearchProviderConfig(
        id="duckduckgo",
        name="DuckDuckGo",
        provider_type=SearchProviderType.DUCKDUCKGO,
        cost_per_query=0.0,
        env_var=None,  # No API key needed
        description="Privacy-focused search engine. Free, no API key required.",
        icon="🦆",
        max_results_per_query=10,
        rate_limit_per_minute=30,  # Conservative to avoid rate limiting
    ),
    SearchProviderConfig(
        id="searxng",
        name="SearXNG (Local)",
        provider_type=SearchProviderType.SEARXNG,
        cost_per_query=0.0,
        env_var=None,  # Uses local instance at localhost:8888
        description="Local meta-search engine. Free, aggregates multiple sources.",
        icon="🏠",
        max_results_per_query=20,
        rate_limit_per_minute=120,  # Local, so higher limit
    ),

    # Paid providers
    SearchProviderConfig(
        id="brave",
        name="Brave Search",
        provider_type=SearchProviderType.BRAVE,
        cost_per_query=0.003,  # ~$3/1000 queries
        env_var="BRAVE_API_KEY",
        description="Independent search with AI summaries. Better relevance than DDG.",
        icon="🦁",
        max_results_per_query=20,
        supports_pagination=True,
        rate_limit_per_minute=60,
    ),
    SearchProviderConfig(
        id="tavily",
        name="Tavily",
        provider_type=SearchProviderType.TAVILY,
        cost_per_query=0.005,  # ~$5/1000 queries
        env_var="TAVILY_API_KEY",
        description="AI-optimized search API. Best for research tasks.",
        icon="🔬",
        max_results_per_query=10,
        rate_limit_per_minute=100,
    ),
    SearchProviderConfig(
        id="perplexity",
        name="Perplexity",
        provider_type=SearchProviderType.PERPLEXITY,
        cost_per_query=0.005,  # ~$5/1000 queries (Sonar API)
        env_var="PERPLEXITY_API_KEY",
        description="Search-augmented AI responses with citations.",
        icon="🔍",
        max_results_per_query=5,  # Returns synthesized results
        rate_limit_per_minute=60,
    ),
]


def get_provider(provider_id: str) -> Optional[SearchProviderConfig]:
    """Get a specific provider by ID."""
    for provider in SEARCH_PROVIDERS:
        if provider.id == provider_id:
            return provider
    return None


def get_available_providers() -> List[SearchProviderConfig]:
    """Get list of providers that are currently available (API keys configured)."""
    return [p for p in SEARCH_PROVIDERS if p.is_available]


def get_free_providers() -> List[SearchProviderConfig]:
    """Get list of free providers."""
    return [p for p in SEARCH_PROVIDERS if p.is_free and p.is_available]


def estimate_search_cost(
    provider_ids: List[str],
    queries_per_iteration: int = 5,
    max_iterations: int = 10
) -> dict:
    """
    Estimate cost for a research session.

    Args:
        provider_ids: List of provider IDs to use
        queries_per_iteration: Expected queries per iteration
        max_iterations: Maximum iterations configured

    Returns:
        Cost estimation breakdown
    """
    total_queries = queries_per_iteration * max_iterations
    breakdown = {}
    total_cost = 0.0

    for pid in provider_ids:
        provider = get_provider(pid)
        if provider:
            queries_for_provider = total_queries // len(provider_ids)
            provider_cost = provider.cost_per_query * queries_for_provider
            breakdown[pid] = {
                "name": provider.name,
                "queries": queries_for_provider,
                "cost_usd": provider_cost,
            }
            total_cost += provider_cost

    return {
        "total_queries": total_queries,
        "total_cost_usd": total_cost,
        "breakdown": breakdown,
        "note": "Estimates assume even distribution across providers",
    }


def validate_provider_selection(provider_ids: List[str]) -> tuple[bool, str]:
    """
    Validate a provider selection.

    Args:
        provider_ids: List of provider IDs to validate

    Returns:
        (is_valid, error_message)
    """
    if not provider_ids:
        return False, "At least one search provider must be selected"

    unavailable = []
    invalid = []

    for pid in provider_ids:
        provider = get_provider(pid)
        if provider is None:
            invalid.append(pid)
        elif not provider.is_available:
            unavailable.append(f"{provider.name} (missing {provider.env_var})")

    if invalid:
        return False, f"Invalid provider IDs: {', '.join(invalid)}"

    if unavailable:
        return False, f"Unavailable providers: {', '.join(unavailable)}"

    return True, ""
