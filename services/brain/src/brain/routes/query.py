# noqa: D401
"""HTTP routes for conversational orchestration."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from common.db.models import RoutingTier
from ..dependencies import get_orchestrator
from ..models.context import DeviceSelection
from ..orchestrator import BrainOrchestrator

router = APIRouter(prefix="/api", tags=["query"])


class QueryInput(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    user_id: str = Field(..., alias="userId")
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    device: Optional[DeviceSelection] = None
    prompt: Optional[str] = None
    force_tier: Optional[RoutingTier] = Field(default=None, alias="forceTier")
    freshness_required: bool = Field(False, alias="freshnessRequired")


class QueryResponse(BaseModel):
    conversation_id: str = Field(..., alias="conversationId")
    intent: str
    result: Dict[str, Any]
    routing: Optional[Dict[str, Any]] = None


@router.post("/query", response_model=QueryResponse)
async def post_query(body: QueryInput, orchestrator: BrainOrchestrator = Depends(get_orchestrator)) -> QueryResponse:
    device_intent = body.intent in {
        "light.turn_on",
        "light.turn_off",
        "scene.activate",
        "lock.unlock",
        "lock.lock",
    }

    if device_intent or body.device:
        result = await orchestrator.handle_device_intent(
            conversation_id=body.conversation_id,
            intent=body.intent,
            payload=body.payload,
            device=body.device.model_dump() if body.device else None,
        )
        return QueryResponse(conversation_id=body.conversation_id, intent=body.intent, result=result)

    prompt = body.prompt or body.payload.get("prompt")
    if not prompt:
        raise ValueError("prompt is required for non-device intents")

    routing_result = await orchestrator.generate_response(
        conversation_id=body.conversation_id,
        request_id=uuid4().hex,
        prompt=prompt,
        user_id=body.user_id,
        force_tier=body.force_tier,
        freshness_required=body.freshness_required,
    )
    routing_details = {
        "tier": routing_result.tier.value,
        "confidence": routing_result.confidence,
        "latencyMs": routing_result.latency_ms,
        "cached": routing_result.cached,
    }
    return QueryResponse(
        conversation_id=body.conversation_id,
        intent=body.intent,
        result={"output": routing_result.output},
        routing=routing_details,
    )
