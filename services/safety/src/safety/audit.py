"""Audit helpers for safety events."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from common.db import SessionLocal
from common.db.models import SafetyEvent, SafetyEventStatus, SafetyEventType


def create_event(
    *,
    event_type: SafetyEventType,
    device_id: str | None,
    zone_id: str | None,
    initiated_by: str,
    signature: str,
) -> SafetyEvent:
    session: Session = SessionLocal()
    try:
        event = SafetyEvent(
            id=uuid4().hex,
            event_type=event_type,
            device_id=device_id,
            zone_id=zone_id,
            initiated_by=initiated_by,
            signature=signature,
            status=SafetyEventStatus.pending,
            created_at=datetime.utcnow(),
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event
    finally:
        session.close()


def update_event(
    event_id: str, *, approved_by: str | None, status: SafetyEventStatus
) -> None:
    session: Session = SessionLocal()
    try:
        event = session.get(SafetyEvent, event_id)
        if not event:
            return
        event.status = status
        event.approved_by = approved_by
        event.resolved_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()
