"""
Budget Management for Model Calls

Tracks costs, enforces budgets, and optimizes spending across research sessions.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class BudgetConfig:
    """Budget configuration for a research session"""
    max_total_cost_usd: Decimal = Decimal("2.0")
    max_external_calls: int = 10

    # Cost limits per tier
    max_cost_per_trivial: Decimal = Decimal("0.0")
    max_cost_per_low: Decimal = Decimal("0.0")
    max_cost_per_medium: Decimal = Decimal("0.0")
    max_cost_per_high: Decimal = Decimal("0.10")
    max_cost_per_critical: Decimal = Decimal("0.50")

    # Warnings
    warn_at_percentage: float = 0.8  # Warn at 80% budget
    warn_at_calls_remaining: int = 2  # Warn when 2 external calls left


@dataclass
class CostTracker:
    """Tracks costs for a single model call"""
    model_id: str
    timestamp: datetime
    cost_usd: Decimal
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    tier: Optional[str] = None


@dataclass
class BudgetStatus:
    """Current budget status"""
    total_cost_usd: Decimal
    external_calls_used: int
    budget_remaining: Decimal
    external_calls_remaining: int
    percentage_used: float
    is_over_budget: bool
    should_warn: bool


class BudgetManager:
    """
    Manages budget for autonomous research sessions.

    Features:
    - Cost tracking per model/tier
    - Budget enforcement
    - Spending optimization
    - Warnings and alerts
    """

    def __init__(self, config: Optional[BudgetConfig] = None):
        self.config = config or BudgetConfig()
        self.calls: List[CostTracker] = []
        self._lock = asyncio.Lock()

        logger.info(
            f"Initialized budget manager: "
            f"max_cost=${self.config.max_total_cost_usd}, "
            f"max_external_calls={self.config.max_external_calls}"
        )

    async def record_call(
        self,
        model_id: str,
        cost_usd: Decimal,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool = True,
        tier: Optional[str] = None
    ):
        """
        Record a model call and its cost.

        Args:
            model_id: Model that was called
            cost_usd: Cost in USD
            input_tokens: Input tokens used
            output_tokens: Output tokens generated
            latency_ms: Latency in milliseconds
            success: Whether call was successful
            tier: Consultation tier
        """
        async with self._lock:
            tracker = CostTracker(
                model_id=model_id,
                timestamp=datetime.now(),
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=success,
                tier=tier
            )

            self.calls.append(tracker)

            logger.debug(
                f"Recorded call: {model_id} cost=${cost_usd} "
                f"tokens={input_tokens}+{output_tokens} "
                f"latency={latency_ms:.0f}ms"
            )

    async def get_status(self) -> BudgetStatus:
        """Get current budget status"""
        async with self._lock:
            total_cost = sum(call.cost_usd for call in self.calls)
            external_calls = sum(
                1 for call in self.calls
                if call.cost_usd > 0  # External calls have cost
            )

            budget_remaining = self.config.max_total_cost_usd - total_cost
            external_remaining = self.config.max_external_calls - external_calls

            percentage_used = float(total_cost / self.config.max_total_cost_usd) if self.config.max_total_cost_usd > 0 else 0.0

            is_over_budget = (
                total_cost > self.config.max_total_cost_usd or
                external_calls > self.config.max_external_calls
            )

            should_warn = (
                percentage_used >= self.config.warn_at_percentage or
                external_remaining <= self.config.warn_at_calls_remaining
            )

            return BudgetStatus(
                total_cost_usd=total_cost,
                external_calls_used=external_calls,
                budget_remaining=budget_remaining,
                external_calls_remaining=external_remaining,
                percentage_used=percentage_used,
                is_over_budget=is_over_budget,
                should_warn=should_warn
            )

    async def can_afford(
        self,
        estimated_cost: Decimal,
        is_external: bool = False
    ) -> bool:
        """
        Check if we can afford a call.

        Args:
            estimated_cost: Estimated cost of the call
            is_external: Whether this is an external API call

        Returns:
            True if call can be afforded
        """
        status = await self.get_status()

        # Check budget
        if status.budget_remaining < estimated_cost:
            logger.warning(
                f"Insufficient budget: need ${estimated_cost}, "
                f"have ${status.budget_remaining}"
            )
            return False

        # Check external call limit
        if is_external and status.external_calls_remaining <= 0:
            logger.warning(
                f"External call limit reached: "
                f"{status.external_calls_used}/{self.config.max_external_calls}"
            )
            return False

        return True

    async def get_spending_by_model(self) -> Dict[str, Decimal]:
        """Get spending breakdown by model"""
        async with self._lock:
            spending = {}
            for call in self.calls:
                if call.model_id not in spending:
                    spending[call.model_id] = Decimal("0.0")
                spending[call.model_id] += call.cost_usd
            return spending

    async def get_spending_by_tier(self) -> Dict[str, Decimal]:
        """Get spending breakdown by consultation tier"""
        async with self._lock:
            spending = {}
            for call in self.calls:
                tier = call.tier or "unknown"
                if tier not in spending:
                    spending[tier] = Decimal("0.0")
                spending[tier] += call.cost_usd
            return spending

    async def get_call_count_by_model(self) -> Dict[str, int]:
        """Get call count by model"""
        async with self._lock:
            counts = {}
            for call in self.calls:
                if call.model_id not in counts:
                    counts[call.model_id] = 0
                counts[call.model_id] += 1
            return counts

    async def get_success_rate_by_model(self) -> Dict[str, float]:
        """Get success rate by model"""
        async with self._lock:
            success_counts = {}
            total_counts = {}

            for call in self.calls:
                if call.model_id not in success_counts:
                    success_counts[call.model_id] = 0
                    total_counts[call.model_id] = 0

                total_counts[call.model_id] += 1
                if call.success:
                    success_counts[call.model_id] += 1

            return {
                model_id: success_counts[model_id] / total_counts[model_id]
                for model_id in total_counts
            }

    async def get_average_latency_by_model(self) -> Dict[str, float]:
        """Get average latency by model"""
        async with self._lock:
            latency_sums = {}
            counts = {}

            for call in self.calls:
                if call.model_id not in latency_sums:
                    latency_sums[call.model_id] = 0.0
                    counts[call.model_id] = 0

                latency_sums[call.model_id] += call.latency_ms
                counts[call.model_id] += 1

            return {
                model_id: latency_sums[model_id] / counts[model_id]
                for model_id in counts
            }

    async def get_total_tokens_by_model(self) -> Dict[str, Dict[str, int]]:
        """Get total tokens (input/output) by model"""
        async with self._lock:
            tokens = {}

            for call in self.calls:
                if call.model_id not in tokens:
                    tokens[call.model_id] = {"input": 0, "output": 0}

                tokens[call.model_id]["input"] += call.input_tokens
                tokens[call.model_id]["output"] += call.output_tokens

            return tokens

    async def get_cost_efficiency_score(self) -> float:
        """
        Calculate cost efficiency score.

        Score = (successful_calls / total_calls) * (local_calls / total_calls) * 100

        Higher score = more efficient (more success, more local usage)
        """
        async with self._lock:
            if not self.calls:
                return 100.0  # Perfect efficiency with no calls

            total_calls = len(self.calls)
            successful_calls = sum(1 for call in self.calls if call.success)
            local_calls = sum(1 for call in self.calls if call.cost_usd == 0)

            success_rate = successful_calls / total_calls
            local_rate = local_calls / total_calls

            # Weight success more heavily than local usage
            score = (success_rate * 0.7 + local_rate * 0.3) * 100

            return round(score, 2)

    async def optimize_spending(self) -> Dict[str, Any]:
        """
        Analyze spending and provide optimization recommendations.

        Returns:
            Dict with recommendations
        """
        status = await self.get_status()
        spending_by_model = await self.get_spending_by_model()
        success_rates = await self.get_success_rate_by_model()
        call_counts = await self.get_call_count_by_model()

        recommendations = []

        # Check for expensive models with low success rate
        for model_id, cost in spending_by_model.items():
            if cost > Decimal("0.10"):  # Significant spending
                success_rate = success_rates.get(model_id, 1.0)
                if success_rate < 0.8:
                    recommendations.append({
                        "type": "warning",
                        "message": f"Model {model_id} has low success rate ({success_rate:.1%}) with high cost (${cost})",
                        "action": "Consider using alternative model"
                    })

        # Check for budget concerns
        if status.percentage_used > 0.9:
            recommendations.append({
                "type": "critical",
                "message": f"Budget {status.percentage_used:.0%} depleted",
                "action": "Switch to local-only models"
            })
        elif status.should_warn:
            recommendations.append({
                "type": "warning",
                "message": f"Budget {status.percentage_used:.0%} used",
                "action": "Monitor spending closely"
            })

        # Check external call usage
        if status.external_calls_remaining <= 2:
            recommendations.append({
                "type": "warning",
                "message": f"Only {status.external_calls_remaining} external calls remaining",
                "action": "Reserve for critical decisions only"
            })

        # Identify most used models
        if call_counts:
            most_used = max(call_counts.items(), key=lambda x: x[1])
            recommendations.append({
                "type": "info",
                "message": f"Most used model: {most_used[0]} ({most_used[1]} calls)",
                "action": None
            })

        efficiency = await self.get_cost_efficiency_score()
        recommendations.append({
            "type": "info",
            "message": f"Cost efficiency score: {efficiency:.1f}/100",
            "action": "Higher is better (success rate + local usage)"
        })

        return {
            "status": status,
            "efficiency_score": efficiency,
            "recommendations": recommendations,
            "spending_by_model": {k: float(v) for k, v in spending_by_model.items()},
            "success_rates": success_rates,
        }

    async def reset(self):
        """Reset budget tracker (for new session)"""
        async with self._lock:
            self.calls.clear()
            logger.info("Budget tracker reset")

    async def export_summary(self) -> Dict[str, Any]:
        """Export summary statistics"""
        status = await self.get_status()
        spending_by_model = await self.get_spending_by_model()
        spending_by_tier = await self.get_spending_by_tier()
        call_counts = await self.get_call_count_by_model()
        success_rates = await self.get_success_rate_by_model()
        avg_latencies = await self.get_average_latency_by_model()
        total_tokens = await self.get_total_tokens_by_model()
        efficiency = await self.get_cost_efficiency_score()

        return {
            "status": {
                "total_cost_usd": float(status.total_cost_usd),
                "budget_remaining": float(status.budget_remaining),
                "external_calls_used": status.external_calls_used,
                "external_calls_remaining": status.external_calls_remaining,
                "percentage_used": status.percentage_used,
                "is_over_budget": status.is_over_budget,
            },
            "spending_by_model": {k: float(v) for k, v in spending_by_model.items()},
            "spending_by_tier": {k: float(v) for k, v in spending_by_tier.items()},
            "call_counts": call_counts,
            "success_rates": success_rates,
            "average_latencies_ms": avg_latencies,
            "total_tokens": total_tokens,
            "efficiency_score": efficiency,
            "total_calls": len(self.calls),
        }
