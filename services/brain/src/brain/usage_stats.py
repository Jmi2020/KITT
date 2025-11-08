"""In-memory usage tracking for providers/tools."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict


@dataclass
class UsageEntry:
    provider: str
    tier: str
    calls: int = 0
    total_cost: float = 0.0
    last_used_iso: str = ""

    def to_dict(self) -> Dict[str, float | int | str]:
        return {
            "provider": self.provider,
            "tier": self.tier,
            "calls": self.calls,
            "total_cost": round(self.total_cost, 6),
            "last_used": self.last_used_iso,
        }


class UsageStats:
    _lock = threading.Lock()
    _providers: Dict[str, UsageEntry] = {}

    @classmethod
    def record(cls, provider: str, tier: str, cost: float = 0.0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with cls._lock:
            entry = cls._providers.get(provider)
            if not entry:
                entry = UsageEntry(provider=provider, tier=tier)
                cls._providers[provider] = entry
            entry.calls += 1
            entry.total_cost += cost
            entry.last_used_iso = now

    @classmethod
    def snapshot(cls) -> "UsageStatsSnapshot":
        with cls._lock:
            return {name: entry.to_dict() for name, entry in cls._providers.items()}

    @classmethod
    def reset(cls) -> None:
        """Clear all recorded usage metrics (primarily for tests)."""

        with cls._lock:
            cls._providers.clear()


UsageStatsSnapshot = Dict[str, Dict[str, float | int | str]]


__all__ = ["UsageStats", "UsageStatsSnapshot"]
