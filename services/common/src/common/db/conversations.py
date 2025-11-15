"""Helpers for conversation sessions and history persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import SessionLocal
from .models import ConversationMessage, ConversationRole, ConversationSession


def _normalize_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def _derive_title(text: str, limit: int = 80) -> str:
    normalized = _normalize_whitespace(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _ensure_session(
    session: Session,
    conversation_id: str,
    *,
    user_id: Optional[str] = None,
) -> ConversationSession:
    record = session.get(ConversationSession, conversation_id)
    if record:
        participants = record.active_participants or []
        if user_id and user_id not in participants:
            record.active_participants = participants + [user_id]
        return record

    now = datetime.utcnow()
    record = ConversationSession(
        id=conversation_id,
        context_key=f"session:{conversation_id}",
        state={},
        active_participants=[user_id] if user_id else [],
        last_message_at=now,
        created_at=now,
        message_count=0,
    )
    session.add(record)
    return record


def record_conversation_message(
    *,
    conversation_id: str,
    role: ConversationRole,
    content: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    title_hint: Optional[str] = None,
) -> ConversationMessage:
    """Persist a conversation message and update session metadata."""

    now = datetime.utcnow()
    db: Session = SessionLocal()
    try:
        session_row = _ensure_session(db, conversation_id, user_id=user_id)
        session_row.last_message_at = now
        session_row.message_count = (session_row.message_count or 0) + 1

        if role == ConversationRole.user:
            session_row.last_user_message = content
            if not session_row.title:
                session_row.title = title_hint or _derive_title(content)
        elif role == ConversationRole.assistant:
            session_row.last_assistant_message = content

        message = ConversationMessage(
            id=uuid4().hex,
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_metadata=metadata or {},
            created_at=now,
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def list_conversation_sessions(
    *,
    user_id: Optional[str] = None,
    limit: int = 20,
    search: Optional[str] = None,
) -> List[ConversationSession]:
    db: Session = SessionLocal()
    try:
        stmt = (
            select(ConversationSession)
            .order_by(ConversationSession.last_message_at.desc())
            .limit(limit)
        )
        if user_id:
            stmt = stmt.where(ConversationSession.active_participants.contains([user_id]))
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                func.lower(func.coalesce(ConversationSession.title, "")).like(pattern)
                | func.lower(func.coalesce(ConversationSession.last_user_message, "")).like(pattern)
                | func.lower(func.coalesce(ConversationSession.last_assistant_message, "")).like(pattern)
            )

        rows = db.execute(stmt).scalars().all()
        return rows
    finally:
        db.close()


def fetch_conversation_messages(
    conversation_id: str,
    *,
    limit: int = 50,
    before: Optional[datetime] = None,
) -> List[ConversationMessage]:
    db: Session = SessionLocal()
    try:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        if before:
            stmt = stmt.where(ConversationMessage.created_at < before)

        rows = db.execute(stmt).scalars().all()
        return list(reversed(rows))
    finally:
        db.close()


def get_conversation_session(conversation_id: str) -> Optional[ConversationSession]:
    db: Session = SessionLocal()
    try:
        return db.get(ConversationSession, conversation_id)
    finally:
        db.close()


def rename_conversation(conversation_id: str, title: str) -> Optional[ConversationSession]:
    db: Session = SessionLocal()
    try:
        session_row = db.get(ConversationSession, conversation_id)
        if not session_row:
            return None
        session_row.title = _derive_title(title) if title else None
        db.commit()
        db.refresh(session_row)
        return session_row
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


__all__ = [
    "record_conversation_message",
    "list_conversation_sessions",
    "fetch_conversation_messages",
    "get_conversation_session",
    "rename_conversation",
]
