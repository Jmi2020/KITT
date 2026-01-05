# noqa: D401
"""FastAPI routes for prompt suggestion service."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .service import get_suggestion_service, SUGGEST_ENABLED
from .contexts import SuggestionContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/suggest", tags=["suggest"])


class SuggestRequest(BaseModel):
    """Request body for suggestion generation."""

    input: str = Field(..., description="The user's current input text", min_length=1)
    context: str = Field(
        default="chat",
        description="Context type: chat, coding, cad, image, research"
    )
    field_id: str = Field(
        default="",
        description="Optional field identifier for analytics"
    )
    history: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="Optional conversation history"
    )
    max_suggestions: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of suggestions to generate"
    )


class Suggestion(BaseModel):
    """A single suggestion."""

    text: str
    reason: str


class SuggestResponse(BaseModel):
    """Response for non-streaming suggestion request."""

    suggestions: List[Suggestion]
    request_id: str


class SuggestConfigRequest(BaseModel):
    """Request body for updating suggestion configuration."""

    enabled: Optional[bool] = None
    debounce_ms: Optional[int] = Field(default=None, ge=100, le=2000)
    min_input_length: Optional[int] = Field(default=None, ge=3, le=50)
    max_suggestions: Optional[int] = Field(default=None, ge=1, le=5)
    contexts: Optional[Dict[str, Dict[str, any]]] = None


class SuggestConfigResponse(BaseModel):
    """Current suggestion configuration."""

    enabled: bool
    debounce_ms: int
    min_input_length: int
    max_suggestions: int
    default_model: str
    coder_model: str
    contexts: Dict[str, Dict[str, any]]


@router.get("/status")
async def get_status() -> Dict[str, any]:
    """Get the status of the suggestion service."""
    return {
        "enabled": SUGGEST_ENABLED,
        "default_model": os.getenv("PROMPT_SUGGEST_MODEL", "gemma-3-21b"),
        "coder_model": os.getenv(
            "PROMPT_SUGGEST_CODER_MODEL",
            "/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF"
        ),
        "contexts": [c.value for c in SuggestionContext],
    }


@router.post("/stream")
async def suggest_stream(request: SuggestRequest) -> StreamingResponse:
    """Generate prompt suggestions as a Server-Sent Events stream.

    This endpoint streams suggestions as they are generated, allowing
    the frontend to display them progressively.

    Returns SSE events in the format:
    ```
    data: {"type": "start", "request_id": "abc123"}
    data: {"type": "suggestion", "index": 0, "text": "...", "reason": "..."}
    data: {"type": "complete", "suggestions_count": 2}
    ```
    """
    service = get_suggestion_service()

    async def event_generator():
        async for event in service.suggest(
            input_text=request.input,
            context=request.context,
            field_id=request.field_id,
            history=request.history,
            max_suggestions=request.max_suggestions,
        ):
            # Convert event to JSON
            event_data = {
                "type": event.type,
            }
            if event.request_id:
                event_data["request_id"] = event.request_id
            if event.index is not None:
                event_data["index"] = event.index
            if event.text:
                event_data["text"] = event.text
            if event.reason:
                event_data["reason"] = event.reason
            if event.suggestions_count is not None:
                event_data["suggestions_count"] = event.suggestions_count
            if event.error:
                event_data["error"] = event.error

            yield f"data: {json.dumps(event_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=SuggestResponse)
async def suggest(request: SuggestRequest) -> SuggestResponse:
    """Generate prompt suggestions (non-streaming).

    This endpoint collects all suggestions before returning them.
    For real-time display, use the /stream endpoint instead.
    """
    service = get_suggestion_service()

    suggestions: List[Suggestion] = []
    request_id = ""

    async for event in service.suggest(
        input_text=request.input,
        context=request.context,
        field_id=request.field_id,
        history=request.history,
        max_suggestions=request.max_suggestions,
    ):
        if event.type == "start":
            request_id = event.request_id or ""
        elif event.type == "suggestion":
            suggestions.append(Suggestion(
                text=event.text or "",
                reason=event.reason or "",
            ))
        elif event.type == "error":
            raise HTTPException(status_code=500, detail=event.error)

    return SuggestResponse(
        suggestions=suggestions,
        request_id=request_id,
    )


@router.get("/config", response_model=SuggestConfigResponse)
async def get_config() -> SuggestConfigResponse:
    """Get current suggestion service configuration."""
    return SuggestConfigResponse(
        enabled=SUGGEST_ENABLED,
        debounce_ms=int(os.getenv("PROMPT_SUGGEST_DEBOUNCE_MS", "300")),
        min_input_length=int(os.getenv("PROMPT_SUGGEST_MIN_LENGTH", "10")),
        max_suggestions=int(os.getenv("PROMPT_SUGGEST_MAX_SUGGESTIONS", "3")),
        default_model=os.getenv("PROMPT_SUGGEST_MODEL", "gemma-3-21b"),
        coder_model=os.getenv(
            "PROMPT_SUGGEST_CODER_MODEL",
            "/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF"
        ),
        contexts={
            "chat": {"model": "gemma-3-21b", "enabled": True},
            "coding": {"model": "qwen-coder", "enabled": True},
            "cad": {"model": "gemma-3-21b", "enabled": True},
            "image": {"model": "gemma-3-21b", "enabled": True},
            "research": {"model": "gemma-3-21b", "enabled": True},
        },
    )
