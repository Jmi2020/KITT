# noqa: D401
"""Core orchestration logic for conversational device control."""

from __future__ import annotations

from typing import Any, Dict

from common.credentials import HomeAssistantCredentials
from common.db.models import RoutingTier

from .models.context import ConversationContext, DeviceSelection
from .routing.router import BrainRouter, RoutingRequest, RoutingResult
from .skills.home_assistant import HomeAssistantSkill
from .state.mqtt_context_store import MQTTContextStore
from safety.workflows.hazard import HazardWorkflow


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
        safety_workflow: HazardWorkflow | None = None,
    ) -> None:
        self._context_store = context_store
        self._ha_skill = HomeAssistantSkill(ha_credentials)
        self._router = router
        self._safety = safety_workflow

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
    ) -> RoutingResult:
        routing_request = RoutingRequest(
            conversation_id=conversation_id,
            request_id=request_id,
            prompt=prompt,
            user_id=user_id,
            force_tier=force_tier,
            freshness_required=freshness_required,
            model_hint=model_hint,
        )
        return await self._router.route(routing_request)


__all__ = ["BrainOrchestrator"]
