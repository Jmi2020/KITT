# noqa: D401
"""Usage tracking endpoints."""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter

from ..usage_stats import UsageStats


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/metrics", response_model=dict)
async def usage_metrics() -> Dict[str, Dict[str, float | int | str]]:
    """Return usage metrics grouped by provider."""

    stats = UsageStats.snapshot()
    return stats


__all__ = ["router"]
