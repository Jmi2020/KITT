# noqa: D401
"""Persist routing decisions for observability."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from common.db import SessionLocal
from common.db.models import RoutingDecision, RoutingTier


class RoutingAuditStore:
    """Persist routing decisions to Postgres via SQLAlchemy models."""

    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        conversation_id: str,
        request_id: str,
        tier: RoutingTier,
        confidence: float,
        latency_ms: int,
        cost_estimate: float = 0.0,
        escalation_reason: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        session: Session = self._session_factory()
        try:
            decision = RoutingDecision(
                id=request_id,
                conversation_id=conversation_id,
                request_id=request_id,
                selected_tier=tier,
                confidence=confidence,
                latency_ms=latency_ms,
                cost_estimate=cost_estimate,
                escalation_reason=escalation_reason,
                created_at=datetime.utcnow(),
                user_id=user_id,
            )
            session.add(decision)
            session.commit()
        finally:
            session.close()


__all__ = ["RoutingAuditStore"]
