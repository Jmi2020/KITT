"""Calendar schedule management endpoints (Phase 1 backend)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db import get_db
from common.db.models import AutonomousSchedule, JobExecutionHistory

router = APIRouter(prefix="/api/autonomy/calendar", tags=["autonomy-calendar"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_simple_nl(text: str) -> Optional[str]:
    """
    Very small NL → cron helper for common phrases.

    Supports:
      - "every monday at 5"
      - "every monday at 5:30"
      - "daily at 4"
    Returns cron string or None if not matched.
    """
    text = text.strip().lower()
    # daily
    daily = re.match(r"(daily|every day) at (\d{1,2})(?::(\d{1,2}))?", text)
    if daily:
        hour = int(daily.group(2))
        minute = int(daily.group(3) or 0)
        return f"{minute} {hour} * * *"

    weekly = re.match(r"every (\w+) at (\d{1,2})(?::(\d{1,2}))?", text)
    if weekly:
        day = weekly.group(1)
        day_map = {
            "sunday": 0,
            "sun": 0,
            "monday": 1,
            "mon": 1,
            "tuesday": 2,
            "tue": 2,
            "wednesday": 3,
            "wed": 3,
            "thursday": 4,
            "thu": 4,
            "friday": 5,
            "fri": 5,
            "saturday": 6,
            "sat": 6,
        }
        day_num = day_map.get(day)
        if day_num is None:
            return None
        hour = int(weekly.group(2))
        minute = int(weekly.group(3) or 0)
        return f"{minute} {hour} * * {day_num}"

    return None


def _next_run_from_cron(cron_expr: str) -> Optional[datetime]:
    """Best-effort next run calculator; returns None if croniter is unavailable."""
    try:
        from croniter import croniter  # type: ignore
    except Exception:
        return None

    try:
        now = datetime.utcnow()
        return croniter(cron_expr, now).get_next(datetime)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScheduleCreateRequest(BaseModel):
    job_type: str
    job_name: str
    description: Optional[str] = None
    natural_language_schedule: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: str = "UTC"
    budget_limit_usd: Optional[float] = None
    priority: int = Field(default=5, ge=1, le=10)
    enabled: bool = True
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None
    user_id: str = Field(default="cli-user")


class ScheduleUpdateRequest(BaseModel):
    job_name: Optional[str] = None
    description: Optional[str] = None
    natural_language_schedule: Optional[str] = None
    cron_expression: Optional[str] = None
    timezone: Optional[str] = None
    budget_limit_usd: Optional[float] = None
    priority: Optional[int] = Field(default=None, ge=1, le=10)
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    metadata: Optional[dict] = None


class ScheduleResponse(BaseModel):
    id: str
    user_id: str
    job_type: str
    job_name: str
    description: Optional[str]
    natural_language_schedule: Optional[str]
    cron_expression: str
    timezone: str
    enabled: bool
    budget_limit_usd: Optional[float]
    priority: int
    tags: Optional[List[str]]
    metadata: dict
    created_at: datetime
    updated_at: datetime
    last_execution_at: Optional[datetime]
    next_execution_at: Optional[datetime]

    class Config:
        orm_mode = True


class ExecutionHistoryResponse(BaseModel):
    id: str
    job_id: str
    job_name: str
    execution_time: datetime
    duration_seconds: Optional[float]
    status: str
    budget_spent_usd: Optional[float]
    error_message: Optional[str]
    result_summary: Optional[dict]

    class Config:
        orm_mode = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _resolve_cron(req: ScheduleCreateRequest) -> str:
    if req.cron_expression:
        return req.cron_expression
    if req.natural_language_schedule:
        cron = _parse_simple_nl(req.natural_language_schedule)
        if cron:
            return cron
        raise HTTPException(status_code=400, detail="Could not parse natural language schedule; provide cron_expression instead.")
    raise HTTPException(status_code=400, detail="Provide either cron_expression or natural_language_schedule.")


@router.post("/schedules", response_model=ScheduleResponse)
async def create_schedule(req: ScheduleCreateRequest, db: Session = Depends(get_db)) -> ScheduleResponse:
    cron = _resolve_cron(req)
    next_run = _next_run_from_cron(cron)

    schedule = AutonomousSchedule(
        user_id=req.user_id,
        job_type=req.job_type,
        job_name=req.job_name,
        description=req.description,
        natural_language_schedule=req.natural_language_schedule,
        cron_expression=cron,
        timezone=req.timezone,
        enabled=req.enabled,
        budget_limit_usd=req.budget_limit_usd,
        priority=req.priority,
        tags=req.tags,
        metadata=req.metadata or {},
        next_execution_at=next_run,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return ScheduleResponse.from_orm(schedule)


@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    user_id: str = Query(..., description="User ID"),
    enabled: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> List[ScheduleResponse]:
    stmt = select(AutonomousSchedule).where(AutonomousSchedule.user_id == user_id)
    if enabled is not None:
        stmt = stmt.where(AutonomousSchedule.enabled == enabled)
    if job_type:
        stmt = stmt.where(AutonomousSchedule.job_type == job_type)
    result = db.execute(stmt.order_by(AutonomousSchedule.created_at.desc()))
    schedules = result.scalars().all()
    return [ScheduleResponse.from_orm(s) for s in schedules]


@router.get("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str, db: Session = Depends(get_db)) -> ScheduleResponse:
    schedule = db.get(AutonomousSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return ScheduleResponse.from_orm(schedule)


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: str,
    req: ScheduleUpdateRequest,
    db: Session = Depends(get_db),
) -> ScheduleResponse:
    schedule: AutonomousSchedule | None = db.get(AutonomousSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    data = req.dict(exclude_unset=True)
    if "natural_language_schedule" in data and data["natural_language_schedule"]:
        cron = _parse_simple_nl(data["natural_language_schedule"])
        if cron:
            data["cron_expression"] = cron
        else:
            raise HTTPException(status_code=400, detail="Could not parse natural language schedule; provide cron_expression.")
    if "cron_expression" in data and data["cron_expression"]:
        data["next_execution_at"] = _next_run_from_cron(data["cron_expression"])

    for field, value in data.items():
        setattr(schedule, field, value)
    schedule.updated_at = datetime.utcnow()
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return ScheduleResponse.from_orm(schedule)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, db: Session = Depends(get_db)) -> dict:
    schedule = db.get(AutonomousSchedule, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(schedule)
    db.commit()
    return {"status": "deleted", "id": schedule_id}


@router.get("/history", response_model=List[ExecutionHistoryResponse])
async def list_history(
    job_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> List[ExecutionHistoryResponse]:
    stmt = select(JobExecutionHistory)
    if job_id:
        stmt = stmt.where(JobExecutionHistory.job_id == job_id)
    if status:
        stmt = stmt.where(JobExecutionHistory.status == status)
    stmt = stmt.order_by(JobExecutionHistory.execution_time.desc()).limit(limit)
    result = db.execute(stmt)
    history = result.scalars().all()
    return [ExecutionHistoryResponse.from_orm(h) for h in history]
