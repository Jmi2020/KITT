"""Autonomy management endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..autonomous.resource_manager import (
    AutonomousWorkload,
    ResourceManager,
    ResourceStatus,
)

router = APIRouter(prefix="/api/autonomy", tags=["autonomy"])


class AutonomyStatusResponse(BaseModel):
    budget_available: float = Field(..., description="Remaining budget for today (USD)")
    budget_used_today: float = Field(..., description="Budget spent today (USD)")
    is_idle: bool
    cpu_usage_percent: float
    memory_usage_percent: float
    gpu_available: bool
    can_run_autonomous: bool
    reason: str
    workload: AutonomousWorkload


class AutonomyBudgetDay(BaseModel):
    date: str
    cost_usd: float
    requests: int


class AutonomyBudgetSummary(BaseModel):
    days: int
    total_cost_usd: float
    total_requests: int
    average_cost_per_day: float
    budget_limit_per_day: float
    daily_breakdown: List[AutonomyBudgetDay]


def get_resource_manager() -> ResourceManager:
    """FastAPI dependency for ResourceManager instantiation."""
    return ResourceManager.from_settings()


def _decimal_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.0001"))) if isinstance(value, Decimal) else float(value)


def _status_to_response(status: ResourceStatus) -> AutonomyStatusResponse:
    return AutonomyStatusResponse(
        budget_available=_decimal_to_float(status.budget_available),
        budget_used_today=_decimal_to_float(status.budget_used_today),
        is_idle=status.is_idle,
        cpu_usage_percent=status.cpu_usage_percent,
        memory_usage_percent=status.memory_usage_percent,
        gpu_available=status.gpu_available,
        can_run_autonomous=status.can_run_autonomous,
        reason=status.reason,
        workload=status.workload,
    )


@router.get("/status", response_model=AutonomyStatusResponse)
async def autonomy_status(
    workload: AutonomousWorkload = Query(AutonomousWorkload.scheduled, description="Workload type to evaluate"),
    manager: ResourceManager = Depends(get_resource_manager),
) -> AutonomyStatusResponse:
    """Return readiness info for the requested autonomous workload."""
    status = manager.get_status(workload=workload)
    return _status_to_response(status)


@router.get("/budget", response_model=AutonomyBudgetSummary)
async def autonomy_budget(
    days: int = Query(7, ge=1, le=30, description="Number of days to summarize"),
    manager: ResourceManager = Depends(get_resource_manager),
) -> AutonomyBudgetSummary:
    """Return historical spending summary for autonomous operations."""
    summary: Dict[str, Any] = manager.get_autonomous_budget_summary(days=days)
    return AutonomyBudgetSummary(
        days=summary["days"],
        total_cost_usd=summary["total_cost_usd"],
        total_requests=summary["total_requests"],
        average_cost_per_day=summary["average_cost_per_day"],
        budget_limit_per_day=summary["budget_limit_per_day"],
        daily_breakdown=[
            AutonomyBudgetDay(**day) for day in summary.get("daily_breakdown", [])
        ],
    )


__all__ = ["router", "get_resource_manager"]
