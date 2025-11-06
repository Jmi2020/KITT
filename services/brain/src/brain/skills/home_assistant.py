# noqa: D401
"""Translate device intents into Home Assistant service calls."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from common.credentials import HomeAssistantCredentials

from ..clients.home_assistant import HomeAssistantClient
from ..models.context import ConversationContext


INTENT_MAP: Dict[str, Tuple[str, str]] = {
    "light.turn_on": ("light", "turn_on"),
    "light.turn_off": ("light", "turn_off"),
    "scene.activate": ("scene", "turn_on"),
    "lock.unlock": ("lock", "unlock"),
    "lock.lock": ("lock", "lock"),
}


class HomeAssistantSkill:
    """Execute intents via Home Assistant services."""

    def __init__(self, credentials: HomeAssistantCredentials) -> None:
        self._client = HomeAssistantClient(credentials)

    async def execute(
        self, context: ConversationContext, intent: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        if intent not in INTENT_MAP:
            raise ValueError(f"Unsupported Home Assistant intent: {intent}")

        domain, service = INTENT_MAP[intent]
        data = payload.copy()
        if context.device:
            data.setdefault("entity_id", context.device.friendly_name)
        return await self._client.call_service(domain, service, data)


__all__ = ["HomeAssistantSkill"]
