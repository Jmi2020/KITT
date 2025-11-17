"""Track routing costs for observability with token-based pricing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, Optional

from common.db.models import RoutingTier


# Token pricing per 1M tokens (in USD)
TOKEN_PRICING = {
    RoutingTier.local: {
        "prompt": 0.0001,  # Essentially free for local models
        "completion": 0.0001,
    },
    RoutingTier.mcp: {
        "prompt": 1.00,  # Perplexity Sonar pricing (~$1/1M prompt tokens)
        "completion": 1.00,
    },
    RoutingTier.frontier: {
        "prompt": 2.50,  # OpenAI GPT-4 pricing (~$2.50/1M prompt tokens)
        "completion": 10.00,  # ~$10/1M completion tokens
    },
}


@dataclass
class TokenUsage:
    """Track token usage for a request"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class CostTracker:
    """Track routing costs with both fixed and token-based pricing"""

    # Fixed cost totals (for backwards compatibility)
    totals: DefaultDict[RoutingTier, float] = field(default_factory=lambda: defaultdict(float))

    # Token-based tracking
    token_usage: DefaultDict[RoutingTier, TokenUsage] = field(
        default_factory=lambda: defaultdict(TokenUsage)
    )
    token_costs: DefaultDict[RoutingTier, float] = field(default_factory=lambda: defaultdict(float))

    # Request count tracking
    request_counts: DefaultDict[RoutingTier, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, tier: RoutingTier, cost: float) -> None:
        """Record a fixed cost (backwards compatible)"""
        self.totals[tier] += cost
        self.request_counts[tier] += 1

    def record_tokens(
        self,
        tier: RoutingTier,
        prompt_tokens: int,
        completion_tokens: int,
        usage_data: Optional[Dict] = None,
    ) -> float:
        """
        Record token usage and calculate cost.

        Args:
            tier: The routing tier used
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            usage_data: Optional raw usage data from API response

        Returns:
            Calculated cost in USD
        """
        # Update token counts
        usage = self.token_usage[tier]
        usage.prompt_tokens += prompt_tokens
        usage.completion_tokens += completion_tokens
        usage.total_tokens += (prompt_tokens + completion_tokens)

        # Calculate cost based on pricing
        pricing = TOKEN_PRICING.get(tier, TOKEN_PRICING[RoutingTier.local])
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
        total_cost = prompt_cost + completion_cost

        # Track the cost
        self.token_costs[tier] += total_cost
        self.request_counts[tier] += 1

        return total_cost

    def total_cost(self, tier: RoutingTier) -> float:
        """Get total fixed cost for a tier"""
        return self.totals[tier]

    def total_token_cost(self, tier: RoutingTier) -> float:
        """Get total token-based cost for a tier"""
        return self.token_costs[tier]

    def combined_cost(self, tier: RoutingTier) -> float:
        """Get combined fixed + token-based cost"""
        return self.totals[tier] + self.token_costs[tier]

    def grand_total(self) -> float:
        """Get total of all fixed costs"""
        return sum(self.totals.values())

    def grand_token_total(self) -> float:
        """Get total of all token-based costs"""
        return sum(self.token_costs.values())

    def grand_combined_total(self) -> float:
        """Get total of all costs (fixed + token-based)"""
        return self.grand_total() + self.grand_token_total()

    def get_usage(self, tier: RoutingTier) -> TokenUsage:
        """Get token usage for a tier"""
        return self.token_usage[tier]

    def get_stats(self) -> Dict[str, any]:
        """Get comprehensive cost statistics"""
        stats = {
            "total_requests": sum(self.request_counts.values()),
            "total_cost": self.grand_combined_total(),
            "total_token_cost": self.grand_token_total(),
            "total_fixed_cost": self.grand_total(),
            "by_tier": {},
        }

        for tier in RoutingTier:
            if self.request_counts[tier] > 0:
                usage = self.token_usage[tier]
                stats["by_tier"][tier.value] = {
                    "requests": self.request_counts[tier],
                    "fixed_cost": self.totals[tier],
                    "token_cost": self.token_costs[tier],
                    "combined_cost": self.combined_cost(tier),
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "avg_cost_per_request": (
                        self.combined_cost(tier) / self.request_counts[tier]
                        if self.request_counts[tier] > 0
                        else 0
                    ),
                }

        return stats
