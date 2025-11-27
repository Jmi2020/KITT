"""Voice router integrates parser, KITTY brain, and MQTT bus."""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Dict, List, Any

from common.mqtt import MQTTClient, PublishOptions
from brain.orchestrator import BrainOrchestrator
from brain.routing.router import RoutingResult
from common.cache import SemanticCache
from common.db.projects import upsert_project

from .parser import VoiceParser


def _extract_tool_events(routing_result: RoutingResult) -> List[Dict[str, Any]]:
    """Extract tool execution events from agent steps metadata.

    Returns list of events in format:
    [
        {"type": "tool_call", "id": str, "name": str, "args": dict, "timestamp": str},
        {"type": "tool_result", "id": str, "name": str, "result": str, "status": str},
        ...
    ]
    """
    events = []
    metadata = routing_result.metadata or {}
    agent_steps = metadata.get("agent_steps", [])

    for i, step in enumerate(agent_steps):
        tool_id = str(uuid.uuid4())[:8]

        # Extract action (tool call)
        action = step.get("action")
        if action:
            action_input = step.get("action_input", {})
            events.append({
                "type": "tool_call",
                "id": tool_id,
                "name": action,
                "args": action_input if isinstance(action_input, dict) else {"input": action_input},
                "step": i + 1,
            })

            # Extract observation (tool result)
            observation = step.get("observation")
            if observation is not None:
                # Determine status based on observation content
                status = "completed"
                if isinstance(observation, str):
                    if "error" in observation.lower() or "failed" in observation.lower():
                        status = "error"
                    elif "blocked" in observation.lower() or "requires confirmation" in observation.lower():
                        status = "blocked"

                events.append({
                    "type": "tool_result",
                    "id": tool_id,
                    "name": action,
                    "result": str(observation)[:500] if observation else "",  # Truncate long results
                    "status": status,
                    "step": i + 1,
                })

    return events


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

    async def handle_transcript(
        self, conversation_id: str, user_id: str, transcript: str
    ) -> Dict:
        """Handle a voice transcript (non-streaming)."""
        command = self._parser.parse(transcript)
        if command["type"] == "device":
            payload = command.get("payload", {})
            self._mqtt.publish(
                f"kitty/devices/{payload.get('deviceId', 'unknown')}/cmd",
                {**payload, "intent": command["intent"], "initiatedBy": user_id},
                options=PublishOptions(qos=1, retain=False),
            )
            return {"status": "queued", "device": payload.get("deviceId")}

        if command["type"] == "routing":
            result: RoutingResult = await self._orchestrator.generate_response(
                conversation_id=conversation_id,
                request_id=user_id,
                prompt=command["prompt"],
                user_id=user_id,
            )
            return {
                "status": "routed",
                "tier": result.tier.value,
                "output": result.output,
            }

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

    async def handle_transcript_stream(
        self, conversation_id: str, user_id: str, transcript: str
    ) -> AsyncIterator[Dict]:
        """Handle a voice transcript with streaming response.

        Yields chunks in format:
        {
            "type": "device" | "text" | "done" | "error",
            "delta": str,      # Text content (for text type)
            "device": str,     # Device ID (for device type)
            "tier": str,       # Routing tier (for done type)
            "done": bool,      # Whether stream is complete
        }
        """
        command = self._parser.parse(transcript)

        if command["type"] == "device":
            payload = command.get("payload", {})
            device_id = payload.get("deviceId", "unknown")
            self._mqtt.publish(
                f"kitty/devices/{device_id}/cmd",
                {**payload, "intent": command["intent"], "initiatedBy": user_id},
                options=PublishOptions(qos=1, retain=False),
            )
            yield {
                "type": "device",
                "device": device_id,
                "intent": command["intent"],
                "done": True,
            }
            return

        if command["type"] == "routing":
            # Use streaming response from brain orchestrator
            # Collect routing result to extract tool events
            routing_result = None
            text_chunks = []

            async for chunk in self._orchestrator.generate_response_stream(
                conversation_id=conversation_id,
                request_id=user_id,
                prompt=command["prompt"],
                user_id=user_id,
            ):
                # Transform brain chunk format to voice format
                delta = chunk.get("delta", "")
                is_done = chunk.get("done", False)

                if delta:
                    text_chunks.append(delta)
                    yield {
                        "type": "text",
                        "delta": delta,
                        "done": False,
                    }

                if is_done:
                    routing_result = chunk.get("routing_result")

            # After streaming completes, yield tool events if present
            if routing_result:
                tool_events = _extract_tool_events(routing_result)
                for event in tool_events:
                    yield event

                # Yield final done event with tier info
                yield {
                    "type": "done",
                    "tier": routing_result.tier.value,
                    "tools_used": len([e for e in tool_events if e["type"] == "tool_call"]),
                    "done": True,
                }
            else:
                yield {
                    "type": "done",
                    "tier": "unknown",
                    "done": True,
                }
            return

        if command["type"] == "note":
            upsert_project(
                conversation_id=conversation_id,
                title=f"Conversation {conversation_id}",
                summary=command.get("summary"),
                artifacts=[],
                metadata={"source": "voice"},
            )
            yield {
                "type": "text",
                "delta": f"Noted: {command.get('summary', transcript)}",
                "done": True,
            }
            return

        yield {"type": "error", "message": "Unhandled command", "done": True}
