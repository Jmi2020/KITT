"""Voice service dependencies."""

from __future__ import annotations

from functools import lru_cache

from common.cache import SemanticCache
from common.config import settings
from common.messaging import MQTTClient
from brain.dependencies import get_orchestrator

from .parser import VoiceParser
from .router import VoiceRouter


@lru_cache(maxsize=1)
def get_parser() -> VoiceParser:
    return VoiceParser(settings.voice_system_prompt)


@lru_cache(maxsize=1)
def get_router() -> VoiceRouter:
    mqtt_client = MQTTClient(client_id="voice")
    return VoiceRouter(get_parser(), mqtt_client, get_orchestrator(), SemanticCache())
*** End Patch
