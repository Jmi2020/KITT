"""Voice command parsing using local or cloud models."""

from __future__ import annotations

from typing import Dict


SYSTEM_PROMPT = """You are KITTY, a fabrication orchestrator. Convert user speech into structured commands.
Output JSON objects. Supported command types:
- device command: {"type": "device", "intent": "light.turn_on", "payload": { ... }}
- routing request: {"type": "routing", "prompt": "..."}
- project note: {"type": "note", "summary": "..."}
If unclear, respond with {"type": "error", "message": "unclear"}.
"""


class VoiceParser:
    def __init__(self, system_prompt: str | None = None) -> None:
        self._system_prompt = system_prompt or SYSTEM_PROMPT

    def parse(self, transcript: str) -> Dict[str, str]:
        text = transcript.strip()
        lower = text.lower()

        if not text:
            return {"type": "error", "message": "empty transcript"}

        if "note" in lower or "remember" in lower or "log" in lower:
            return {"type": "note", "summary": text}

        if "unlock" in lower:
            return {
                "type": "device",
                "intent": "lock.unlock",
                "payload": {
                    "deviceId": "welding-bay-door",
                    "reason": text,
                },
            }

        if "turn on" in lower or "lights on" in lower:
            return {
                "type": "device",
                "intent": "light.turn_on",
                "payload": {
                    "deviceId": "welding-lights"
                    if "welding" in lower
                    else "shop-lights",
                },
            }

        if "turn off" in lower or "lights off" in lower:
            return {
                "type": "device",
                "intent": "light.turn_off",
                "payload": {
                    "deviceId": "welding-lights"
                    if "welding" in lower
                    else "shop-lights",
                },
            }

        # default to routing through KITTY brain
        return {
            "type": "routing",
            "prompt": text,
        }
