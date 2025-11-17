"""Voice service dependencies."""

from __future__ import annotations

import os
from functools import lru_cache
from string import Formatter

from common.cache import SemanticCache
from common.config import settings
from common.mqtt import MQTTClient
from brain.dependencies import get_orchestrator

from .parser import VoiceParser
from .router import VoiceRouter


@lru_cache(maxsize=1)
def get_parser() -> VoiceParser:
    template = settings.voice_system_prompt or ""
    if not template:
        return VoiceParser(None)

    class PromptContext(dict):
        def __missing__(self, key: str) -> str:
            env_value = os.getenv(key)
            if env_value is not None:
                return env_value
            attr = key.lower()
            if hasattr(settings, attr):
                value = getattr(settings, attr)
                return str(value)
            return f"{{{key}}}"

    formatter = Formatter()
    context = PromptContext()
    for _, field, _, _ in formatter.parse(template):
        if field and field not in context:
            context[field] = context[field]

    rendered = template.format_map(context)
    return VoiceParser(rendered)


@lru_cache(maxsize=1)
def get_router() -> VoiceRouter:
    mqtt_client = MQTTClient(client_id="voice")
    return VoiceRouter(get_parser(), mqtt_client, get_orchestrator(), SemanticCache())
