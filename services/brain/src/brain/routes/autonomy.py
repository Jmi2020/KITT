"""Autonomy management endpoints."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db import get_db
from common.db.models import Goal, GoalStatus, GoalType

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


# Goal Management Models

class GoalResponse(BaseModel):
    """Response model for Goal objects."""
    id: str
    goal_type: str
    description: str
    rationale: str
    estimated_budget: float
    estimated_duration_hours: Optional[int]
    status: str
    identified_at: datetime
    approved_at: Optional[datetime]
    approved_by: Optional[str]
    goal_metadata: Dict[str, Any]


class GoalListResponse(BaseModel):
    """Response model for list of goals."""
    goals: List[GoalResponse]
    total_count: int
    pending_count: int


class GoalApprovalRequest(BaseModel):
    """Request model for goal approval/rejection."""
    user_id: str = Field(..., description="ID of user approving/rejecting")
    notes: Optional[str] = Field(None, description="Optional approval notes")


class GoalApprovalResponse(BaseModel):
    """Response model for goal approval action."""
    goal_id: str
    status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    message: str


# Goal Management Endpoints

@router.get("/goals", response_model=GoalListResponse)
async def list_goals(
    status: Optional[str] = Query(None, description="Filter by status (identified, approved, rejected, completed)"),
    goal_type: Optional[str] = Query(None, description="Filter by type (research, fabrication, improvement, optimization)"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of goals to return"),
    db: Session = Depends(get_db),
) -> GoalListResponse:
    """List autonomous goals with optional filtering.

    By default, returns goals with status=identified (awaiting approval).
    """
    # Build query
    stmt = select(Goal)

    # Apply filters
    if status:
        try:
            status_enum = GoalStatus[status]
            stmt = stmt.where(Goal.status == status_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    else:
        # Default: only show identified goals (pending approval)
        stmt = stmt.where(Goal.status == GoalStatus.identified)

    if goal_type:
        try:
            type_enum = GoalType[goal_type]
            stmt = stmt.where(Goal.goal_type == type_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid goal_type: {goal_type}")

    # Order by identified_at descending (newest first)
    stmt = stmt.order_by(Goal.identified_at.desc()).limit(limit)

    # Execute query
    result = db.execute(stmt)
    goals = result.scalars().all()

    # Count pending goals
    pending_stmt = select(Goal).where(Goal.status == GoalStatus.identified)
    pending_count = len(db.execute(pending_stmt).scalars().all())

    # Convert to response models
    goal_responses = [
        GoalResponse(
            id=g.id,
            goal_type=g.goal_type.value,
            description=g.description,
            rationale=g.rationale,
            estimated_budget=float(g.estimated_budget),
            estimated_duration_hours=g.estimated_duration_hours,
            status=g.status.value,
            identified_at=g.identified_at,
            approved_at=g.approved_at,
            approved_by=g.approved_by,
            goal_metadata=g.goal_metadata or {},
        )
        for g in goals
    ]

    return GoalListResponse(
        goals=goal_responses,
        total_count=len(goal_responses),
        pending_count=pending_count,
    )


@router.post("/goals/{goal_id}/approve", response_model=GoalApprovalResponse)
async def approve_goal(
    goal_id: str,
    request: GoalApprovalRequest,
    db: Session = Depends(get_db),
) -> GoalApprovalResponse:
    """Approve an autonomous goal.

    Approving a goal allows KITTY to proceed with creating projects and tasks
    to achieve the goal objective.
    """
    # Fetch goal
    stmt = select(Goal).where(Goal.id == goal_id)
    result = db.execute(stmt)
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")

    if goal.status != GoalStatus.identified:
        raise HTTPException(
            status_code=400,
            detail=f"Goal {goal_id} has status {goal.status.value}, cannot approve"
        )

    # Update goal status
    goal.status = GoalStatus.approved
    goal.approved_at = datetime.utcnow()
    goal.approved_by = request.user_id

    # Add approval notes to metadata
    if request.notes:
        if not goal.goal_metadata:
            goal.goal_metadata = {}
        goal.goal_metadata["approval_notes"] = request.notes

    db.commit()
    db.refresh(goal)

    return GoalApprovalResponse(
        goal_id=goal.id,
        status=goal.status.value,
        approved_by=goal.approved_by,
        approved_at=goal.approved_at,
        message=f"Goal approved: {goal.description}",
    )


@router.post("/goals/{goal_id}/reject", response_model=GoalApprovalResponse)
async def reject_goal(
    goal_id: str,
    request: GoalApprovalRequest,
    db: Session = Depends(get_db),
) -> GoalApprovalResponse:
    """Reject an autonomous goal.

    Rejecting a goal prevents KITTY from pursuing the objective.
    """
    # Fetch goal
    stmt = select(Goal).where(Goal.id == goal_id)
    result = db.execute(stmt)
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")

    if goal.status != GoalStatus.identified:
        raise HTTPException(
            status_code=400,
            detail=f"Goal {goal_id} has status {goal.status.value}, cannot reject"
        )

    # Update goal status
    goal.status = GoalStatus.rejected
    goal.approved_by = request.user_id
    goal.approved_at = datetime.utcnow()

    # Add rejection notes to metadata
    if request.notes:
        if not goal.goal_metadata:
            goal.goal_metadata = {}
        goal.goal_metadata["rejection_notes"] = request.notes

    db.commit()
    db.refresh(goal)

    return GoalApprovalResponse(
        goal_id=goal.id,
        status=goal.status.value,
        approved_by=goal.approved_by,
        approved_at=goal.approved_at,
        message=f"Goal rejected: {goal.description}",
    )


@router.get("/goals/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: str,
    db: Session = Depends(get_db),
) -> GoalResponse:
    """Get details for a specific goal."""
    stmt = select(Goal).where(Goal.id == goal_id)
    result = db.execute(stmt)
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")

    return GoalResponse(
        id=goal.id,
        goal_type=goal.goal_type.value,
        description=goal.description,
        rationale=goal.rationale,
        estimated_budget=float(goal.estimated_budget),
        estimated_duration_hours=goal.estimated_duration_hours,
        status=goal.status.value,
        identified_at=goal.identified_at,
        approved_at=goal.approved_at,
        approved_by=goal.approved_by,
        goal_metadata=goal.goal_metadata or {},
    )


__all__ = ["router", "get_resource_manager"]
