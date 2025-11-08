# noqa: D401
"""Core orchestration logic for conversational device control."""

from __future__ import annotations

from typing import Any, Dict

from common.credentials import HomeAssistantCredentials
from common.db.models import RoutingTier
from common.config import settings

from .memory import MemoryClient
from .models.context import ConversationContext, DeviceSelection
from .routing.router import BrainRouter, RoutingRequest, RoutingResult
from .routing.freshness import is_time_sensitive_query
from .skills.home_assistant import HomeAssistantSkill
from .state.mqtt_context_store import MQTTContextStore


class BrainOrchestrator:
    """Coordinate conversation context updates and device skill execution."""

    _HAZARD_INTENTS = {
        "lock.unlock": "unlock",
        "power.enable": "power_enable",
    }

    def __init__(
        self,
        context_store: MQTTContextStore,
        ha_credentials: HomeAssistantCredentials,
        router: BrainRouter,
        safety_workflow: Any | None = None,
        memory_client: MemoryClient | None = None,
    ) -> None:
        self._context_store = context_store
        self._ha_skill = HomeAssistantSkill(ha_credentials)
        self._router = router
        self._safety = safety_workflow
        self._memory = memory_client or MemoryClient()

    async def handle_device_intent(
        self,
        conversation_id: str,
        intent: str,
        payload: Dict[str, Any],
        device: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        context = self._context_store.get_context(conversation_id) or ConversationContext(
            conversation_id=conversation_id
        )
        context.last_intent = intent
        if device:
            context.device = DeviceSelection(**device)
        self._context_store.set_context(context)

        hazard_key = self._HAZARD_INTENTS.get(intent)
        if hazard_key and self._safety:
            signature = payload.get("signature")
            zone_id = context.device.zone_id if context.device else None
            allowed, response = await self._safety.process_device_intent(
                intent=hazard_key,
                device_id=context.device.device_id if context.device else None,
                zone_id=zone_id,
                user_id=payload.get("initiatedBy", "unknown"),
                signature=signature,
            )
            if not allowed:
                return response

        return await self._ha_skill.execute(context, intent, payload)

    async def generate_response(
        self,
        conversation_id: str,
        request_id: str,
        prompt: str,
        *,
        user_id: str | None = None,
        force_tier: RoutingTier | None = None,
        freshness_required: bool = False,
        model_hint: str | None = None,
        use_agent: bool = False,
        tool_mode: str = "auto",
    ) -> RoutingResult:
        # Retrieve relevant memories
        enriched_prompt = prompt
        try:
            memories = await self._memory.search_memories(
                query=prompt,
                conversation_id=conversation_id,
                user_id=user_id,
                limit=3,
                score_threshold=0.75,
            )
            if not memories and user_id:
                memories = await self._memory.search_memories(
                    query=prompt,
                    conversation_id=None,
                    user_id=user_id,
                    limit=3,
                    score_threshold=0.7,
                )
            if memories:
                memory_context = "\n".join(
                    [f"[Memory {i+1}]: {m.content}" for i, m in enumerate(memories)]
                )
                enriched_prompt = (
                    f"<relevant_context>\n{memory_context}\n</relevant_context>\n\n" f"{prompt}"
                )
        except Exception:
            # If memory service is unavailable, continue without memories
            pass

        agentic_mode = use_agent or settings.agentic_mode_enabled

        time_sensitive = is_time_sensitive_query(prompt)
        requires_fresh = freshness_required or time_sensitive

        routing_request = RoutingRequest(
            conversation_id=conversation_id,
            request_id=request_id,
            prompt=enriched_prompt,
            user_id=user_id,
            force_tier=force_tier,
            freshness_required=requires_fresh,
            model_hint=model_hint,
            use_agent=agentic_mode,
            tool_mode=tool_mode,
        )
        result = await self._router.route(routing_request)

        # Store the interaction as a new memory
        try:
            memory_content = f"User: {prompt}\nAssistant: {result.output}"
            await self._memory.add_memory(
                conversation_id=conversation_id,
                content=memory_content,
                user_id=user_id,
                metadata={
                    "request_id": request_id,
                    "tier": result.tier.value,
                    "confidence": result.confidence,
                },
            )
        except Exception:
            # If memory storage fails, log but don't fail the request
            pass

        return result


__all__ = ["BrainOrchestrator"]
