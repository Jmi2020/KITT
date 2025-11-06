# noqa: D401
"""Persist routing decisions for observability."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert

from sqlalchemy.orm import Session

from common.db import SessionLocal
from common.db.models import (
    ConversationSession,
    RoutingDecision,
    RoutingTier,
    User,
)


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
        try:
            conv_uuid = str(UUID(conversation_id))
        except Exception:
            return

        try:
            user_uuid = str(UUID(user_id)) if user_id else None
        except Exception:
            user_uuid = None

        bootstrap: Session = self._session_factory()
        try:
            bootstrap.execute(
                insert(ConversationSession)
                .values(
                    id=conv_uuid,
                    context_key=f"session:{conv_uuid}",
                    state={},
                    active_participants=[user_uuid] if user_uuid else [],
                    last_message_at=datetime.utcnow(),
                )
                .on_conflict_do_nothing()
            )

            if user_uuid:
                bootstrap.execute(
                    insert(User)
                    .values(
                        id=user_uuid,
                        display_name=user_uuid,
                        roles=["operator"],
                        created_at=datetime.utcnow(),
                    )
                    .on_conflict_do_nothing()
                )
            bootstrap.commit()
        except Exception:
            bootstrap.rollback()
            return
        finally:
            bootstrap.close()

        session: Session = self._session_factory()
        try:
            decision = RoutingDecision(
                id=request_id,
                conversation_id=conv_uuid,
                request_id=request_id,
                selected_tier=tier,
                confidence=confidence,
                latency_ms=latency_ms,
                cost_estimate=cost_estimate,
                escalation_reason=escalation_reason,
                created_at=datetime.utcnow(),
                user_id=user_uuid,
            )
            session.add(decision)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()


__all__ = ["RoutingAuditStore"]
