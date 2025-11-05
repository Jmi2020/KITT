# noqa: D401
"""Expose routing decision logs."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db import SessionLocal
from common.db.models import RoutingDecision

router = APIRouter(prefix="/api/routing", tags=["routing"])


@router.get("/logs")
def get_routing_logs(
    conversation_id: Optional[str] = Query(default=None),
    selected_tier: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> List[dict]:
    session: Session = SessionLocal()
    try:
        stmt = select(RoutingDecision).order_by(RoutingDecision.created_at.desc()).limit(limit)
        if conversation_id:
            stmt = stmt.where(RoutingDecision.conversation_id == conversation_id)
        if selected_tier:
            stmt = stmt.where(RoutingDecision.selected_tier == selected_tier)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "decisionId": row.id,
                "conversationId": row.conversation_id,
                "tier": row.selected_tier.value,
                "confidence": float(row.confidence),
                "latencyMs": row.latency_ms,
                "costEstimate": float(row.cost_estimate),
                "createdAt": row.created_at.isoformat(),
                "escalationReason": row.escalation_reason,
            }
            for row in rows
        ]
    finally:
        session.close()
