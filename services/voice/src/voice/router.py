"""Voice router integrates parser, KITTY brain, and MQTT bus."""

from __future__ import annotations

from typing import Dict

from common.messaging import MQTTClient, PublishOptions
from brain.orchestrator import BrainOrchestrator
from brain.routing.router import RoutingResult
from common.cache import SemanticCache
from common.db.projects import upsert_project

from .parser import VoiceParser


class VoiceRouter:
    def __init__(
        self,
        parser: VoiceParser,
        mqtt_client: MQTTClient,
        orchestrator: BrainOrchestrator,
        cache: SemanticCache,
    ) -> None:
        self._parser = parser
        self._mqtt = mqtt_client
        self._orchestrator = orchestrator
        self._cache = cache
        self._mqtt.connect()

    async def handle_transcript(self, conversation_id: str, user_id: str, transcript: str) -> Dict:
        command = self._parser.parse(transcript)
        if command["type"] == "device":
            payload = command.get("payload", {})
            self._mqtt.publish(
                f"kitty/devices/{payload.get('deviceId', 'unknown')}/cmd",
                {**payload, "intent": command["intent"], "initiatedBy": user_id},
                options=PublishOptions(qos=1, retain=False),
            )
            return {"status": "queued"}

        if command["type"] == "routing":
            result: RoutingResult = await self._orchestrator.generate_response(
                conversation_id=conversation_id,
                request_id=user_id,
                prompt=command["prompt"],
                user_id=user_id,
            )
            return {"status": "routed", "tier": result.tier.value, "output": result.output}

        if command["type"] == "note":
            upsert_project(
                conversation_id=conversation_id,
                title=f"Conversation {conversation_id}",
                summary=command.get("summary"),
                artifacts=[],
                metadata={"source": "voice"},
            )
            return {"status": "noted", "summary": command.get("summary")}

        return {"status": "error", "message": "Unhandled command"}
