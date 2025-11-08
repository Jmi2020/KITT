"""Memory management routes for KITTY."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..memory import MemoryClient

router = APIRouter(prefix="/api/memory", tags=["memory"])
memory_client = MemoryClient()


class RememberInput(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    user_id: str = Field(..., alias="userId")
    content: str
    tags: Optional[List[str]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)


@router.post("/remember")
async def remember(body: RememberInput):
    metadata = {
        "tags": body.tags or [],
        "importance": body.importance,
    }
    memory = await memory_client.add_memory(
        conversation_id=body.conversation_id,
        content=body.content,
        user_id=body.user_id,
        metadata=metadata,
    )
    return memory.model_dump()


class MemorySearchInput(BaseModel):
    query: str
    conversation_id: Optional[str] = Field(default=None, alias="conversationId")
    user_id: Optional[str] = Field(default=None, alias="userId")
    limit: int = Field(default=5, ge=1, le=25)
    score_threshold: float = Field(default=0.7, ge=0.0, le=1.0)


@router.post("/search")
async def search(body: MemorySearchInput):
    memories = await memory_client.search_memories(
        query=body.query,
        conversation_id=body.conversation_id,
        user_id=body.user_id,
        limit=body.limit,
        score_threshold=body.score_threshold,
    )
    return {"memories": [m.model_dump() for m in memories]}


__all__ = ["router"]
