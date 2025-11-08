# noqa: D401
"""HTTP routes for conversational orchestration."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ConfigDict

from common.db.models import RoutingTier
from common.verbosity import VerbosityLevel, clamp_level, describe_level, get_verbosity_level
from ..dependencies import get_orchestrator
from ..models.context import DeviceSelection
from ..orchestrator import BrainOrchestrator

router = APIRouter(prefix="/api", tags=["query"])


class QueryInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    user_id: str = Field(..., alias="userId")
    intent: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    device: Optional[DeviceSelection] = None
    prompt: Optional[str] = None
    force_tier: Optional[RoutingTier] = Field(default=None, alias="forceTier")
    freshness_required: bool = Field(False, alias="freshnessRequired")
    verbosity: Optional[int] = None
    model_alias: Optional[str] = Field(default=None, alias="modelAlias")
    use_agent: bool = Field(default=True, alias="useAgent")
    tool_mode: str = Field(default="auto", alias="toolMode")


class QueryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    intent: str
    result: Dict[str, Any]
    routing: Optional[Dict[str, Any]] = None


@router.post("/query", response_model=QueryResponse)
async def post_query(
    body: QueryInput, orchestrator: BrainOrchestrator = Depends(get_orchestrator)
) -> QueryResponse:
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
        return QueryResponse(
            conversation_id=body.conversation_id, intent=body.intent, result=result
        )

    prompt = body.prompt or body.payload.get("prompt")
    if not prompt:
        raise ValueError("prompt is required for non-device intents")

    verbosity_level = clamp_level(body.verbosity) if body.verbosity else get_verbosity_level()

    routing_result = await orchestrator.generate_response(
        conversation_id=body.conversation_id,
        request_id=uuid4().hex,
        prompt=prompt,
        user_id=body.user_id,
        force_tier=body.force_tier,
        freshness_required=body.freshness_required,
        model_hint=body.model_alias,
        use_agent=body.use_agent,
        tool_mode=body.tool_mode,
    )
    routing_details = None
    if verbosity_level >= VerbosityLevel.CONCISE:
        routing_details = {"tier": routing_result.tier.value}
        if verbosity_level >= VerbosityLevel.DETAILED:
            routing_details["confidence"] = routing_result.confidence
            routing_details["latencyMs"] = routing_result.latency_ms
        if verbosity_level >= VerbosityLevel.COMPREHENSIVE:
            routing_details["cached"] = routing_result.cached
            if routing_result.metadata:
                routing_details["metadata"] = routing_result.metadata
        if verbosity_level >= VerbosityLevel.EXHAUSTIVE:
            routing_details["verbosityLevel"] = int(verbosity_level)
            routing_details["verbosityDescription"] = describe_level(verbosity_level)

    result_payload: Dict[str, Any] = {"output": routing_result.output}
    if verbosity_level >= VerbosityLevel.COMPREHENSIVE:
        result_payload["verbosityLevel"] = int(verbosity_level)

    return QueryResponse(
        conversation_id=body.conversation_id,
        intent=body.intent,
        result=result_payload,
        routing=routing_details,
    )
