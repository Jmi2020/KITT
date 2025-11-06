"""Helpers for conversation project persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import SessionLocal
from .models import ConversationProject


def upsert_project(
    *,
    conversation_id: str,
    title: Optional[str],
    summary: Optional[str],
    artifacts: List[Dict[str, str]],
    metadata: Dict[str, str],
) -> ConversationProject:
    session: Session = SessionLocal()
    try:
        project = session.execute(
            select(ConversationProject).where(
                ConversationProject.conversation_id == conversation_id
            )
        ).scalar_one_or_none()
        if not project:
            project = ConversationProject(
                id=uuid4().hex,
                conversation_id=conversation_id,
                title=title,
                summary=summary,
                artifacts=artifacts,
                metadata=metadata,
            )
            session.add(project)
        else:
            if title is not None:
                project.title = title
            if summary is not None:
                project.summary = summary
            project.artifacts = artifacts or project.artifacts
            if metadata:
                project.metadata.update(metadata)
            project.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(project)
        return project
    finally:
        session.close()


def list_projects(conversation_id: Optional[str] = None) -> List[ConversationProject]:
    session: Session = SessionLocal()
    try:
        stmt = select(ConversationProject).order_by(ConversationProject.updated_at.desc())
        if conversation_id:
            stmt = stmt.where(ConversationProject.conversation_id == conversation_id)
        rows = session.execute(stmt).scalars().all()
        return rows
    finally:
        session.close()
