"""SLO helper for routing success ratios."""

from __future__ import annotations

from dataclasses import dataclass

from common.db.models import RoutingTier


@dataclass
class SLOCalculator:
    total: int = 0
    local: int = 0

    def update(self, tier: RoutingTier) -> float:
        self.total += 1
        if tier == RoutingTier.local:
            self.local += 1
        if self.total == 0:
            return 0.0
        return self.local / self.total
