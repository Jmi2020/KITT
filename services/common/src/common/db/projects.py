"""Helpers for conversation project persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from . import SessionLocal
from .models import ConversationProject


def _apply_filters(stmt, conversation_id: Optional[str], artifact_type: Optional[str]):
    stmt = stmt.where(ConversationProject.deleted_at.is_(None))
    if conversation_id:
        stmt = stmt.where(ConversationProject.conversation_id == conversation_id)
    if artifact_type:
        stmt = stmt.where(ConversationProject.artifacts.contains([{"artifact_type": artifact_type}]))
    return stmt


def upsert_project(
    *,
    conversation_id: str,
    title: Optional[str],
    summary: Optional[str],
    artifacts: List[Dict[str, str]],
    metadata: Dict[str, str],
) -> ConversationProject:
    """Create or update a project keyed by conversation."""
    session: Session = SessionLocal()
    try:
        project = session.execute(
            select(ConversationProject).where(
                and_(
                    ConversationProject.conversation_id == conversation_id,
                    ConversationProject.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not project:
            project = ConversationProject(
                id=uuid4().hex,
                conversation_id=conversation_id,
                title=title,
                summary=summary,
                artifacts=artifacts,
                project_metadata=metadata or {},
            )
            session.add(project)
        else:
            if title is not None:
                project.title = title
            if summary is not None:
                project.summary = summary
            project.artifacts = artifacts or project.artifacts
            if metadata:
                project.project_metadata = {**(project.project_metadata or {}), **metadata}
            project.deleted_at = None
            project.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(project)
        return project
    finally:
        session.close()


def list_projects(
    conversation_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    artifact_type: Optional[str] = None,
) -> List[ConversationProject]:
    """Return projects sorted by updated_at desc with optional filters."""
    session: Session = SessionLocal()
    try:
        stmt = select(ConversationProject).order_by(ConversationProject.updated_at.desc())
        stmt = _apply_filters(stmt, conversation_id, artifact_type)
        stmt = stmt.offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return rows
    finally:
        session.close()


def get_project(project_id: str) -> Optional[ConversationProject]:
    session: Session = SessionLocal()
    try:
        return session.execute(
            select(ConversationProject).where(
                and_(ConversationProject.id == project_id, ConversationProject.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
    finally:
        session.close()


def append_artifacts(project_id: str, artifacts: List[Dict[str, str]]) -> Optional[ConversationProject]:
    session: Session = SessionLocal()
    try:
        project = session.execute(
            select(ConversationProject).where(
                and_(ConversationProject.id == project_id, ConversationProject.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not project:
            return None
        project.artifacts = (project.artifacts or []) + artifacts
        project.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(project)
        return project
    finally:
        session.close()


def update_project(
    project_id: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    artifacts: Optional[List[Dict[str, str]]] = None,
) -> Optional[ConversationProject]:
    session: Session = SessionLocal()
    try:
        project = session.execute(
            select(ConversationProject).where(
                and_(ConversationProject.id == project_id, ConversationProject.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if not project:
            return None
        if title is not None:
            project.title = title
        if summary is not None:
            project.summary = summary
        if metadata:
            project.project_metadata = {**(project.project_metadata or {}), **metadata}
        if artifacts is not None:
            project.artifacts = artifacts
        project.updated_at = datetime.utcnow()
        session.commit()
        session.refresh(project)
        return project
    finally:
        session.close()


def soft_delete_project(project_id: str) -> bool:
    session: Session = SessionLocal()
    try:
        project = session.execute(
            select(ConversationProject).where(ConversationProject.id == project_id)
        ).scalar_one_or_none()
        if not project or project.deleted_at is not None:
            return False
        project.deleted_at = datetime.utcnow()
        project.updated_at = datetime.utcnow()
        session.commit()
        return True
    finally:
        session.close()
