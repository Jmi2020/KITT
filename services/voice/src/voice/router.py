"""Voice router integrates parser, KITTY brain, and MQTT bus.

This module routes voice transcripts to either:
1. Device commands (via MQTT)
2. Brain API (via HTTP for LLM responses)

Using HTTP to Brain service ensures proper SlotManager lifecycle,
including auto-restart of idle llama.cpp servers.
"""

from __future__ import annotations

import logging
import uuid
from typing import AsyncIterator, Dict, List, Any, Optional

from common.mqtt import MQTTClient, PublishOptions
from common.cache import SemanticCache
from common.db.projects import upsert_project

from .parser import VoiceParser
from .brain_client import BrainClient, BrainResponse

logger = logging.getLogger(__name__)


class VoiceRouter:
    """Routes voice transcripts to Brain API or device commands.

    Uses HTTP to Brain service instead of direct orchestrator import.
    This ensures:
    1. Proper SlotManager lifecycle (auto-restart idle LLM servers)
    2. Clean separation between voice and brain services
    3. Consistent routing across all clients (UI, CLI, voice)
    """

    def __init__(
        self,
        parser: VoiceParser,
        mqtt_client: MQTTClient,
        brain_client: BrainClient,
        cache: Optional[SemanticCache] = None,
    ) -> None:
        self._parser = parser
        self._mqtt = mqtt_client
        self._brain = brain_client
        self._cache = cache
        self._mqtt_connected = False

    def _ensure_mqtt_connected(self) -> bool:
        """Lazily connect to MQTT broker when needed.

        Returns:
            True if connected, False if connection failed
        """
        if not self._mqtt_connected:
            try:
                self._mqtt.connect()
                self._mqtt_connected = True
            except Exception:
                # MQTT unavailable - device commands won't work but routing still will
                return False
        return True

    async def handle_transcript(
        self, conversation_id: str, user_id: str, transcript: str
    ) -> Dict:
        """Handle a voice transcript (non-streaming).

        Args:
            conversation_id: Conversation context ID
            user_id: User identifier
            transcript: Voice transcript text

        Returns:
            Response dict with status and output
        """
        command = self._parser.parse(transcript)

        if command["type"] == "device":
            payload = command.get("payload", {})
            if not self._ensure_mqtt_connected():
                return {"status": "error", "message": "MQTT broker unavailable for device control"}
            self._mqtt.publish(
                f"kitty/devices/{payload.get('deviceId', 'unknown')}/cmd",
                {**payload, "intent": command["intent"], "initiatedBy": user_id},
                options=PublishOptions(qos=1, retain=False),
            )
            return {"status": "queued", "device": payload.get("deviceId")}

        if command["type"] == "routing":
            # Use Brain HTTP API instead of direct orchestrator
            try:
                result: BrainResponse = await self._brain.query(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    prompt=command["prompt"],
                )
                return {
                    "status": "routed",
                    "tier": result.tier,
                    "output": result.output,
                }
            except Exception as e:
                logger.error(f"Brain query failed: {e}")
                return {"status": "error", "message": f"Brain service error: {e}"}

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
        self,
        conversation_id: str,
        user_id: str,
        transcript: str,
        allow_paid: bool = False,
        mode: str = "basic",
    ) -> AsyncIterator[Dict]:
        """Handle a voice transcript with streaming response.

        Args:
            conversation_id: Conversation ID
            user_id: User ID
            transcript: Voice transcript text
            allow_paid: Whether to allow paid API calls (CAD, deep research)
            mode: Voice mode (basic, maker, research, home, creative)

        Yields chunks in format:
        {
            "type": "device" | "text" | "tool_call" | "tool_result" | "done" | "error",
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
            if not self._ensure_mqtt_connected():
                yield {"type": "error", "message": "MQTT broker unavailable for device control", "done": True}
                return
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
            # Use Brain HTTP API instead of direct orchestrator
            # This ensures proper SlotManager lifecycle (auto-restart idle LLM servers)
            try:
                result: BrainResponse = await self._brain.query(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    prompt=command["prompt"],
                    allow_paid=allow_paid,
                )

                # Extract tool events from metadata if present
                tool_events = self._extract_tool_events(result.metadata)

                # Yield tool events first (for UI to show what tools were used)
                for event in tool_events:
                    yield event

                # Yield the complete response as a single text chunk
                yield {
                    "type": "text",
                    "delta": result.output,
                    "done": False,
                }

                # Yield final done event with tier info
                yield {
                    "type": "done",
                    "tier": result.tier,
                    "tools_used": len([e for e in tool_events if e["type"] == "tool_call"]),
                    "done": True,
                }

            except Exception as e:
                logger.error(f"Brain query failed: {e}")
                yield {"type": "error", "message": f"Brain service error: {e}", "done": True}
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

    def _extract_tool_events(self, metadata: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract tool execution events from Brain response metadata.

        Args:
            metadata: Response metadata from Brain API

        Returns:
            List of tool_call and tool_result events
        """
        if not metadata:
            return []

        events = []
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
                        "result": str(observation)[:500] if observation else "",
                        "status": status,
                        "step": i + 1,
                    })

        return events
