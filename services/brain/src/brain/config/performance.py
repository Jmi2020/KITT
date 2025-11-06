"""Performance and routing tuning knobs for KITTY brain service."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field

from common.config import settings


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class PerformanceSettings(BaseModel):
    """Centralised performance thresholds and budgets."""

    local_confidence: float = Field(0.8, ge=0.0, le=1.0)
    frontier_confidence: float = Field(0.45, ge=0.0, le=1.0)
    local_latency_target_ms: int = Field(1200, ge=0)
    cloud_latency_budget_ms: int = Field(2500, ge=0)
    cache_ttl_seconds: int = Field(900, ge=0)
    max_retry_attempts: int = Field(2, ge=0)
    offline_mode: bool = Field(default=True)
    semantic_cache_enabled: bool = Field(default=True)
    budget_per_task_usd: float = Field(0.5, ge=0.0)
    hazard_confirmation_phrase: str = Field(default="Confirm: proceed")

    @property
    def allow_cloud(self) -> bool:
        """Return whether cloud escalation is allowed based on offline mode."""

        return not self.offline_mode


@lru_cache(maxsize=1)
def get_performance_settings() -> PerformanceSettings:
    """Load settings from environment with sensible fallbacks."""

    return PerformanceSettings(
        local_confidence=float(os.getenv("CONFIDENCE_THRESHOLD", "0.8")),
        frontier_confidence=float(os.getenv("FRONTIER_CONFIDENCE_THRESHOLD", "0.45")),
        local_latency_target_ms=int(os.getenv("LOCAL_LATENCY_TARGET_MS", "1200")),
        cloud_latency_budget_ms=int(os.getenv("CLOUD_LATENCY_BUDGET_MS", "2500")),
        cache_ttl_seconds=int(os.getenv("SEMANTIC_CACHE_TTL_SECONDS", "900")),
        max_retry_attempts=int(os.getenv("ROUTER_MAX_RETRY_ATTEMPTS", "2")),
        offline_mode=_as_bool(os.getenv("OFFLINE_MODE"), True),
        semantic_cache_enabled=settings.semantic_cache_enabled
        and _as_bool(os.getenv("SEMANTIC_CACHE_ENABLED"), True),
        budget_per_task_usd=float(os.getenv("BUDGET_PER_TASK_USD", "0.5")),
        hazard_confirmation_phrase=os.getenv("HAZARD_CONFIRMATION_PHRASE", "Confirm: proceed"),
    )
