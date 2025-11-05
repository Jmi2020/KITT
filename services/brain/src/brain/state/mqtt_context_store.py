# noqa: D401
"""Context store that mirrors state onto MQTT topics."""

from __future__ import annotations

from typing import Dict, Optional

from common.logging import get_logger
from common.messaging import MQTTClient, PublishOptions

from ..models.context import ConversationContext

LOGGER = get_logger(__name__)


class MQTTContextStore:
    """Persist conversational context locally and publish to MQTT for other clients."""

    def __init__(self, client: Optional[MQTTClient] = None) -> None:
        self._client = client or MQTTClient(client_id="brain-context-store")
        self._contexts: Dict[str, ConversationContext] = {}
        self._connected = False

    def _ensure_connection(self) -> None:
        if not self._connected:
            LOGGER.info("Connecting MQTT context store")
            self._client.connect()
            self._connected = True

    def set_context(self, context: ConversationContext) -> None:
        """Persist and broadcast context updates."""

        self._contexts[context.conversation_id] = context
        self._ensure_connection()
        topic = f"jarvis/ctx/{context.conversation_id}"
        payload = context.model_dump(mode="json")
        LOGGER.info("Publishing conversation context", topic=topic)
        self._client.publish(topic, payload, options=PublishOptions(qos=1, retain=True))

    def get_context(self, conversation_id: str) -> Optional[ConversationContext]:
        """Return stored context if available."""

        return self._contexts.get(conversation_id)


__all__ = ["MQTTContextStore"]
