"""Track routing costs for observability."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict

from common.db.models import RoutingTier


@dataclass
class CostTracker:
    totals: DefaultDict[RoutingTier, float] = field(default_factory=lambda: defaultdict(float))

    def record(self, tier: RoutingTier, cost: float) -> None:
        self.totals[tier] += cost

    def total_cost(self, tier: RoutingTier) -> float:
        return self.totals[tier]

    def grand_total(self) -> float:
        return sum(self.totals.values())
