# noqa: D401
"""HTTP routes for conversational orchestration."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from common.db.conversations import record_conversation_message, fetch_conversation_messages
from common.db.models import ConversationRole, RoutingTier
from common.verbosity import VerbosityLevel, clamp_level, describe_level, get_verbosity_level
from ..dependencies import get_orchestrator
from ..models.context import DeviceSelection
from ..orchestrator import BrainOrchestrator

logger = logging.getLogger(__name__)

# Vision model configuration
LLAMACPP_VISION_HOST = os.getenv("LLAMACPP_VISION_HOST", "http://localhost:8086")

# Cloud model ID to provider+model mapping
# Maps UI model IDs (from /api/providers/models) to actual cloud provider and model names
# Uses December 2025 model names - must match collective providers.py
CLOUD_MODEL_MAP = {
    # OpenAI models (December 2025)
    "openai_gpt5": ("openai", "gpt-5"),              # GPT-5 - full reasoning
    "openai_gpt52": ("openai", "gpt-5.2"),           # GPT-5.2 - 400K context
    "openai_gpt5_mini": ("openai", "gpt-5-mini"),    # GPT-5-mini - cost-effective
    "openai_gpt4o_mini": ("openai", "gpt-4o-mini"),  # GPT-4o-mini - fast/affordable
    # Legacy aliases for backward compatibility
    "gpt5": ("openai", "gpt-5.2"),
    "gpt4": ("openai", "gpt-4o-mini"),
    # Anthropic models (December 2025)
    "anthropic_sonnet_45": ("anthropic", "claude-sonnet-4-5"),  # Sonnet 4.5 - best coding
    "anthropic_opus_45": ("anthropic", "claude-opus-4-5"),      # Opus 4.5 - difficult reasoning
    "anthropic_haiku_45": ("anthropic", "claude-haiku-4-5"),    # Haiku 4.5 - fast/cheap
    # Legacy aliases
    "claude": ("anthropic", "claude-sonnet-4-5"),
    "claude_haiku": ("anthropic", "claude-haiku-4-5"),
    "claude_opus": ("anthropic", "claude-opus-4-5"),
    # Perplexity models
    "perplexity_sonar": ("perplexity", "sonar"),        # Sonar - search-augmented
    "perplexity_sonar_pro": ("perplexity", "sonar-pro"),  # Sonar Pro - deeper analysis
    # Legacy aliases
    "perplexity": ("perplexity", "sonar"),
    "perplexity_pro": ("perplexity", "sonar-pro"),
    # Google Gemini models (December 2025)
    "gemini_3_pro": ("gemini", "gemini-3-pro-preview"),  # Gemini 3 Pro - 1M context
    "gemini_25_pro": ("gemini", "gemini-2.5-pro"),       # Gemini 2.5 Pro - thinking model
    "gemini_25_flash": ("gemini", "gemini-2.5-flash"),   # Gemini 2.5 Flash - fast
    # Legacy aliases
    "gemini": ("gemini", "gemini-2.5-flash"),
    "gemini_pro": ("gemini", "gemini-2.5-pro"),
}

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


def _build_conversation_history(conversation_id: str, max_tokens: int = 8000) -> str:
    """Load recent messages and format for LLM context.

    Fetches conversation history from the database and formats it for inclusion
    in the LLM prompt. Uses token estimation to stay within budget.

    Args:
        conversation_id: The conversation to load history for
        max_tokens: Maximum token budget for history (default 8k for 32k context models)

    Returns:
        Formatted conversation history string wrapped in XML tags, or empty string
    """
    try:
        messages = fetch_conversation_messages(conversation_id, limit=50)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch conversation history for %s: %s", conversation_id, exc)
        return ""

    if not messages:
        return ""

    # Simple token estimation: ~4 chars per token (conservative)
    history_parts = []
    estimated_tokens = 0

    for msg in messages:
        role = "User" if msg.role.value == "user" else "Assistant"
        entry = f"[{role}]: {msg.content}"
        entry_tokens = len(entry) // 4

        if estimated_tokens + entry_tokens > max_tokens:
            break
        history_parts.append(entry)
        estimated_tokens += entry_tokens

    if not history_parts:
        return ""

    return "<conversation_history>\n" + "\n\n".join(history_parts) + "\n</conversation_history>"


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
    # Multi-provider support
    provider: Optional[str] = None
    model: Optional[str] = None
    # Vision support - list of base64 encoded images
    images: Optional[List[str]] = None


async def vision_query(prompt: str, images: List[str]) -> str:
    """Send prompt + images to Gemma Vision model.

    Args:
        prompt: Text prompt for the vision model
        images: List of base64 encoded images (data:image/png;base64,...)

    Returns:
        Vision model response text
    """
    # Build multimodal content array
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": img}  # data:image/png;base64,...
        })

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{LLAMACPP_VISION_HOST}/v1/chat/completions",
                json={
                    "model": "gemma-vision",
                    "messages": [{"role": "user", "content": content}],
                    "temperature": 0.7,
                    "max_tokens": 2048,
                }
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        logger.error(f"Vision query failed: {e}")
        raise ValueError(f"Vision model unavailable: {e}")
    except (KeyError, IndexError) as e:
        logger.error(f"Unexpected vision response format: {e}")
        raise ValueError("Invalid vision model response")


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
                "imageCount": len(body.images) if body.images else 0,
            },
            title_hint=cleaned_prompt,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to record user message for %s: %s", body.conversation_id, exc)

    verbosity_level = clamp_level(body.verbosity) if body.verbosity else get_verbosity_level()

    # Route to vision model if images are present and gemma-vision selected
    if body.images and len(body.images) > 0 and final_model == "gemma-vision":
        try:
            vision_response = await vision_query(cleaned_prompt, body.images)

            # Record assistant response
            try:
                record_conversation_message(
                    conversation_id=body.conversation_id,
                    role=ConversationRole.assistant,
                    content=vision_response,
                    metadata={
                        "tier": "vision",
                        "model": "gemma-vision",
                        "imageCount": len(body.images),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to record vision response: %s", exc)

            return QueryResponse(
                conversation_id=body.conversation_id,
                intent=body.intent,
                result={"output": vision_response},
                routing={"tier": "vision", "model": "gemma-vision", "imageCount": len(body.images)},
                requires_confirmation=False,
            )
        except ValueError as e:
            # Vision model failed, return error
            return QueryResponse(
                conversation_id=body.conversation_id,
                intent=body.intent,
                result={"output": f"Vision processing failed: {str(e)}"},
                routing={"tier": "error", "model": "gemma-vision"},
                requires_confirmation=False,
            )

    # Use model from UI (body.model) or legacy model_alias for routing
    effective_model_hint = body.model or body.model_alias

    # Check if selected model is a cloud provider
    cloud_provider = None
    cloud_model = None
    if effective_model_hint and effective_model_hint in CLOUD_MODEL_MAP:
        cloud_provider, cloud_model = CLOUD_MODEL_MAP[effective_model_hint]
        logger.info(f"Cloud model selected: {effective_model_hint} -> {cloud_provider}/{cloud_model}")
    else:
        # Map UI model IDs to internal aliases for local models
        model_id_to_alias = {
            "athene-q4": "kitty-q4",
            "gpt-oss": "kitty-f16",
            "gemma-vision": "kitty-vision",
            "hermes-summary": "kitty-summary",
        }
        if effective_model_hint:
            effective_model_hint = model_id_to_alias.get(effective_model_hint, effective_model_hint)

    # Load conversation history for context continuity
    conversation_history = _build_conversation_history(body.conversation_id)
    prompt_with_history = (
        f"{conversation_history}\n\n{cleaned_prompt}"
        if conversation_history
        else cleaned_prompt
    )

    routing_result = await orchestrator.generate_response(
        conversation_id=body.conversation_id,
        request_id=uuid4().hex,
        prompt=prompt_with_history,
        user_id=body.user_id,
        force_tier=body.force_tier,
        freshness_required=body.freshness_required,
        model_hint=effective_model_hint,
        use_agent=body.use_agent,
        tool_mode=body.tool_mode,
        cloud_provider=cloud_provider,
        cloud_model=cloud_model,
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

    # Use model from UI or legacy model_alias for routing
    stream_model_hint = body.model or body.model_alias

    # Check if selected model is a cloud provider
    stream_cloud_provider = None
    stream_cloud_model = None
    if stream_model_hint and stream_model_hint in CLOUD_MODEL_MAP:
        stream_cloud_provider, stream_cloud_model = CLOUD_MODEL_MAP[stream_model_hint]
        logger.info(f"Stream cloud model selected: {stream_model_hint} -> {stream_cloud_provider}/{stream_cloud_model}")
    else:
        # Map UI model IDs to internal aliases for local models
        model_id_to_alias = {
            "athene-q4": "kitty-q4",
            "gpt-oss": "kitty-f16",
            "gemma-vision": "kitty-vision",
            "hermes-summary": "kitty-summary",
        }
        if stream_model_hint:
            stream_model_hint = model_id_to_alias.get(stream_model_hint, stream_model_hint)

    # Load conversation history for context continuity
    conversation_history = _build_conversation_history(body.conversation_id)
    prompt_with_history = (
        f"{conversation_history}\n\n{cleaned_prompt}"
        if conversation_history
        else cleaned_prompt
    )

    async def event_generator():
        """Generate SSE events for streaming response."""
        full_content = ""
        full_thinking = ""
        routing_result = None

        try:
            async for chunk in orchestrator.generate_response_stream(
                conversation_id=body.conversation_id,
                request_id=uuid4().hex,
                prompt=prompt_with_history,
                user_id=body.user_id,
                force_tier=body.force_tier,
                freshness_required=body.freshness_required,
                model_hint=stream_model_hint,
                use_agent=body.use_agent,
                tool_mode=body.tool_mode,
                cloud_provider=stream_cloud_provider,
                cloud_model=stream_cloud_model,
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
