# noqa: D401
"""HTTP routes for conversational orchestration."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from common.db.conversations import record_conversation_message
from common.db.models import ConversationRole, RoutingTier
from common.verbosity import VerbosityLevel, clamp_level, describe_level, get_verbosity_level
from ..dependencies import get_orchestrator
from ..models.context import DeviceSelection
from ..orchestrator import BrainOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])


def parse_inline_provider_syntax(prompt: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Parse query for inline provider/model syntax.

    Supports:
    - @provider: query text
    - #model: query text

    Args:
        prompt: User query that may contain inline syntax

    Returns:
        Tuple of (cleaned_prompt, provider, model)

    Examples:
        >>> parse_inline_provider_syntax("@openai: what is AI?")
        ("what is AI?", "openai", None)

        >>> parse_inline_provider_syntax("#gpt-4o-mini: explain quantum")
        ("explain quantum", "openai", "gpt-4o-mini")

        >>> parse_inline_provider_syntax("regular query")
        ("regular query", None, None)
    """
    # Check for @provider: syntax
    provider_match = re.match(r'^@(\w+):\s*(.+)$', prompt, re.DOTALL)
    if provider_match:
        provider = provider_match.group(1).lower()
        cleaned_prompt = provider_match.group(2)
        return cleaned_prompt, provider, None

    # Check for #model: syntax
    model_match = re.match(r'^#([\w\-\.]+):\s*(.+)$', prompt, re.DOTALL)
    if model_match:
        model = model_match.group(1).lower()
        cleaned_prompt = model_match.group(2)

        # Auto-detect provider from model name
        provider = _detect_provider_from_model(model)

        return cleaned_prompt, provider, model

    # No inline syntax
    return prompt, None, None


def _detect_provider_from_model(model: str) -> Optional[str]:
    """Detect provider from model name.

    Args:
        model: Model name (e.g., "gpt-4o-mini", "claude-3-5-haiku")

    Returns:
        Provider name if detected, None otherwise
    """
    patterns = {
        "gpt-": "openai",
        "o1-": "openai",
        "claude-": "anthropic",
        "mistral-": "mistral",
        "sonar": "perplexity",
        "gemini-": "gemini",
    }

    for pattern, provider in patterns.items():
        if model.startswith(pattern):
            return provider

    return None


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
    # Multi-provider support (new)
    provider: Optional[str] = None
    model: Optional[str] = None


class QueryResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversation_id: str = Field(..., alias="conversationId")
    intent: str
    result: Dict[str, Any]
    routing: Optional[Dict[str, Any]] = None
    requires_confirmation: bool = Field(False, alias="requiresConfirmation")
    confirmation_phrase: Optional[str] = Field(None, alias="confirmationPhrase")
    pending_tool: Optional[str] = Field(None, alias="pendingTool")
    hazard_class: Optional[str] = Field(None, alias="hazardClass")


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

    # Parse inline provider/model syntax (@provider: or #model:)
    cleaned_prompt, inline_provider, inline_model = parse_inline_provider_syntax(prompt)

    # Determine final provider/model (priority: inline > explicit > default)
    final_provider = inline_provider or body.provider
    final_model = inline_model or body.model

    try:
        record_conversation_message(
            conversation_id=body.conversation_id,
            role=ConversationRole.user,
            content=cleaned_prompt,
            user_id=body.user_id,
            metadata={
                "intent": body.intent,
                "provider": final_provider,
                "model": final_model,
                "toolMode": body.tool_mode,
            },
            title_hint=cleaned_prompt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record user message for %s: %s", body.conversation_id, exc)

    # TODO: Pass provider/model to orchestrator when multi-provider routing is integrated
    # For now, just use the cleaned prompt

    verbosity_level = clamp_level(body.verbosity) if body.verbosity else get_verbosity_level()

    routing_result = await orchestrator.generate_response(
        conversation_id=body.conversation_id,
        request_id=uuid4().hex,
        prompt=cleaned_prompt,
        user_id=body.user_id,
        force_tier=body.force_tier,
        freshness_required=body.freshness_required,
        model_hint=body.model_alias,
        use_agent=body.use_agent,
        tool_mode=body.tool_mode,
    )
    try:
        record_conversation_message(
            conversation_id=body.conversation_id,
            role=ConversationRole.assistant,
            content=routing_result.output or "",
            metadata={
                "tier": routing_result.tier.value,
                "confidence": routing_result.confidence,
                "latencyMs": routing_result.latency_ms,
                "cached": routing_result.cached,
                "routingMetadata": routing_result.metadata or {},
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to record assistant message for %s: %s", body.conversation_id, exc
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

    # Check if routing result metadata contains confirmation requirements
    requires_confirmation = False
    confirmation_phrase = None
    pending_tool = None
    hazard_class = None

    if routing_result.metadata:
        requires_confirmation = routing_result.metadata.get("requires_confirmation", False)
        confirmation_phrase = routing_result.metadata.get("confirmation_phrase")
        pending_tool = routing_result.metadata.get("pending_tool")
        pending_tool_args = routing_result.metadata.get("pending_tool_args")
        hazard_class = routing_result.metadata.get("hazard_class")

        # If confirmation is required, set it in the orchestrator state
        if requires_confirmation and pending_tool and confirmation_phrase:
            await orchestrator.set_pending_confirmation(
                conversation_id=body.conversation_id,
                user_id=body.user_id,
                tool_name=pending_tool,
                tool_args=pending_tool_args or {},
                confirmation_phrase=confirmation_phrase,
                hazard_class=hazard_class or "medium",
                reason=routing_result.metadata.get("confirmation_reason", "Tool requires confirmation"),
            )

    return QueryResponse(
        conversation_id=body.conversation_id,
        intent=body.intent,
        result=result_payload,
        routing=routing_details,
        requires_confirmation=requires_confirmation,
        confirmation_phrase=confirmation_phrase,
        pending_tool=pending_tool,
        hazard_class=hazard_class,
    )


@router.post("/query/stream")
async def post_query_stream(
    body: QueryInput, orchestrator: BrainOrchestrator = Depends(get_orchestrator)
) -> StreamingResponse:
    """Stream query response with real-time thinking traces.

    Returns SSE (Server-Sent Events) stream with:
    - thinking deltas (displayed separately)
    - content deltas (actual response)
    - metadata (when complete)

    Note: Only works with Ollama provider (LOCAL_REASONER_PROVIDER=ollama)
    """
    prompt = body.prompt or body.payload.get("prompt")
    if not prompt:
        raise ValueError("prompt is required")

    # Parse inline provider/model syntax
    cleaned_prompt, inline_provider, inline_model = parse_inline_provider_syntax(prompt)

    try:
        record_conversation_message(
            conversation_id=body.conversation_id,
            role=ConversationRole.user,
            content=cleaned_prompt,
            user_id=body.user_id,
            metadata={
                "intent": body.intent,
                "toolMode": body.tool_mode,
            },
            title_hint=cleaned_prompt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record user message: %s", exc)

    async def event_generator():
        """Generate SSE events for streaming response."""
        full_content = ""
        full_thinking = ""
        routing_result = None

        try:
            async for chunk in orchestrator.generate_response_stream(
                conversation_id=body.conversation_id,
                request_id=uuid4().hex,
                prompt=cleaned_prompt,
                user_id=body.user_id,
                force_tier=body.force_tier,
                freshness_required=body.freshness_required,
                model_hint=body.model_alias,
                use_agent=body.use_agent,
                tool_mode=body.tool_mode,
            ):
                # Accumulate for final storage
                if chunk.get("delta"):
                    full_content += chunk["delta"]
                if chunk.get("delta_thinking"):
                    full_thinking += chunk["delta_thinking"]

                # Send SSE event
                event_data = {
                    "type": "chunk",
                    "delta": chunk.get("delta", ""),
                    "delta_thinking": chunk.get("delta_thinking"),
                    "done": chunk.get("done", False),
                }

                yield f"data: {json.dumps(event_data)}\n\n"

                # Store routing result from final chunk
                if chunk.get("done") and chunk.get("routing_result"):
                    routing_result = chunk["routing_result"]

            # Record assistant message
            if routing_result:
                try:
                    record_conversation_message(
                        conversation_id=body.conversation_id,
                        role=ConversationRole.assistant,
                        content=full_content,
                        metadata={
                            "tier": routing_result.tier.value,
                            "confidence": routing_result.confidence,
                            "thinking_length": len(full_thinking) if full_thinking else 0,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to record assistant message: %s", exc)

            # Send completion event
            completion_data = {
                "type": "complete",
                "conversation_id": body.conversation_id,
                "routing": {
                    "tier": routing_result.tier.value if routing_result else "unknown",
                    "confidence": routing_result.confidence if routing_result else 0,
                } if routing_result else None
            }
            yield f"data: {json.dumps(completion_data)}\n\n"

        except Exception as exc:  # noqa: BLE001
            logger.error("Streaming error: %s", exc, exc_info=True)
            error_data = {
                "type": "error",
                "error": str(exc),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
