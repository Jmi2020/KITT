# noqa: D401
"""Conversation history routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from common.db.conversations import (
    delete_conversation,
    fetch_conversation_messages,
    get_conversation_session,
    list_conversation_sessions,
    rename_conversation,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    title: Optional[str] = None
    created_at: datetime = Field(..., alias="createdAt")
    last_message_at: Optional[datetime] = Field(None, alias="lastMessageAt")
    last_user_message: Optional[str] = Field(None, alias="lastUserMessage")
    last_assistant_message: Optional[str] = Field(None, alias="lastAssistantMessage")
    message_count: int = Field(..., alias="messageCount")
    participants: List[str] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]


class ConversationMessageModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message_id: str = Field(..., alias="messageId")
    conversation_id: str = Field(..., alias="conversationId")
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(..., alias="createdAt")


class ConversationMessagesResponse(BaseModel):
    messages: List[ConversationMessageModel]


class ConversationTitleUpdate(BaseModel):
    title: str


def _session_to_summary(session) -> ConversationSummary:
    created = session.created_at or session.last_message_at or datetime.utcnow()
    return ConversationSummary(
        conversation_id=session.id,
        title=session.title,
        created_at=created,
        last_message_at=session.last_message_at,
        last_user_message=session.last_user_message,
        last_assistant_message=session.last_assistant_message,
        message_count=session.message_count or 0,
        participants=session.active_participants or [],
    )


@router.get("", response_model=ConversationListResponse)
def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    user_id: Optional[str] = Query(default=None, alias="userId"),
    search: Optional[str] = Query(default=None),
) -> ConversationListResponse:
    sessions = list_conversation_sessions(user_id=user_id, limit=limit, search=search)
    return ConversationListResponse(conversations=[_session_to_summary(s) for s in sessions])


@router.get("/{conversation_id}", response_model=ConversationSummary)
def get_history(conversation_id: str) -> ConversationSummary:
    session = get_conversation_session(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _session_to_summary(session)


@router.get("/{conversation_id}/messages", response_model=ConversationMessagesResponse)
def get_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before: Optional[str] = Query(default=None),
) -> ConversationMessagesResponse:
    if before:
        before_value = before.replace("Z", "+00:00")
        try:
            before_dt = datetime.fromisoformat(before_value)
        except ValueError as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid 'before' timestamp") from exc
    else:
        before_dt = None
    rows = fetch_conversation_messages(conversation_id, limit=limit, before=before_dt)
    return ConversationMessagesResponse(
        messages=[
            ConversationMessageModel(
                message_id=row.id,
                conversation_id=row.conversation_id,
                role=row.role.value,
                content=row.content,
                metadata=row.message_metadata or {},
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post("/{conversation_id}/title", response_model=ConversationSummary)
def update_title(conversation_id: str, body: ConversationTitleUpdate) -> ConversationSummary:
    session = rename_conversation(conversation_id, body.title)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _session_to_summary(session)


@router.delete("/{conversation_id}")
def remove_conversation(conversation_id: str) -> Dict[str, Any]:
    """Delete a conversation and all its messages."""
    deleted = delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True, "conversation_id": conversation_id}


__all__ = ["router"]
