"""Voice service dependencies.

Provides lazy-initialized components for the voice service:
- STT (Whisper local + OpenAI fallback)
- TTS (Kokoro/Piper local + OpenAI fallback)
- Wake word detection (Porcupine)
- WebSocket handler for real-time streaming
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from string import Formatter
from typing import TYPE_CHECKING

from common.cache import SemanticCache
from common.config import settings
from common.mqtt import MQTTClient
from brain.dependencies import get_orchestrator

from .parser import VoiceParser
from .router import VoiceRouter

if TYPE_CHECKING:
    from .stt import HybridSTT
    from .tts import StreamingTTS
    from .websocket import VoiceWebSocketHandler
    from .wake_word import WakeWordManager

logger = logging.getLogger(__name__)


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


@lru_cache(maxsize=1)
def get_stt() -> HybridSTT | None:
    """Initialize hybrid STT with local Whisper and OpenAI fallback."""
    try:
        from .stt import HybridSTT

        whisper_model = os.getenv("WHISPER_MODEL", "base.en")
        whisper_path = os.getenv("WHISPER_MODEL_PATH")
        openai_key = os.getenv("OPENAI_API_KEY")
        prefer_local = os.getenv("VOICE_PREFER_LOCAL", "true").lower() == "true"

        stt = HybridSTT(
            local_model_path=whisper_path,
            local_model_size=whisper_model,
            openai_api_key=openai_key,
            prefer_local=prefer_local,
        )

        logger.info("STT initialized: %s", stt.get_status())
        return stt

    except Exception as e:
        logger.warning("Failed to initialize STT: %s", e)
        return None


@lru_cache(maxsize=1)
def get_tts() -> StreamingTTS | None:
    """Initialize hybrid TTS with Kokoro/Piper local and OpenAI fallback."""
    try:
        from .tts import StreamingTTS

        piper_dir = os.getenv("PIPER_MODEL_DIR")
        openai_key = os.getenv("OPENAI_API_KEY")
        openai_model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
        prefer_local = os.getenv("VOICE_PREFER_LOCAL", "true").lower() == "true"
        local_provider = os.getenv("LOCAL_TTS_PROVIDER", "kokoro")

        tts = StreamingTTS(
            piper_model_dir=piper_dir,
            openai_api_key=openai_key,
            openai_model=openai_model,
            prefer_local=prefer_local,
            local_provider=local_provider,
        )

        logger.info("TTS initialized: %s", tts.get_status())
        return tts

    except Exception as e:
        logger.warning("Failed to initialize TTS: %s", e)
        return None


@lru_cache(maxsize=1)
def get_wake_word_manager() -> WakeWordManager | None:
    """Initialize wake word manager for hands-free activation."""
    try:
        from .wake_word import WakeWordManager

        manager = WakeWordManager()

        if manager.enabled:
            logger.info("Wake word manager initialized (enabled)")
        else:
            logger.info("Wake word manager initialized (disabled by config)")

        return manager

    except Exception as e:
        logger.warning("Failed to initialize wake word manager: %s", e)
        return None


@lru_cache(maxsize=1)
def get_router_optional() -> VoiceRouter | None:
    """Try to initialize router, but allow graceful failure."""
    try:
        return get_router()
    except Exception as e:
        logger.warning("Router initialization failed (MQTT/Brain unavailable): %s", e)
        return None


@lru_cache(maxsize=1)
def get_websocket_handler() -> VoiceWebSocketHandler | None:
    """Initialize WebSocket handler for real-time voice streaming.

    Will work with just STT/TTS even if router/orchestrator unavailable.
    Includes wake word manager for hands-free activation if configured.
    """
    try:
        from .websocket import VoiceWebSocketHandler

        # Try to get router, but don't fail if services unavailable
        router = get_router_optional()
        stt = get_stt()
        tts = get_tts()
        wake_word_manager = get_wake_word_manager()

        # At minimum, we need STT or TTS to be useful
        if stt is None and tts is None:
            logger.warning("Neither STT nor TTS available, WebSocket handler limited")

        handler = VoiceWebSocketHandler(
            router=router,
            stt=stt,
            tts=tts,
            wake_word_manager=wake_word_manager,
        )

        logger.info(
            "Voice WebSocket handler initialized (STT: %s, TTS: %s, Router: %s, WakeWord: %s)",
            stt is not None,
            tts is not None,
            router is not None,
            wake_word_manager is not None and wake_word_manager.enabled,
        )
        return handler

    except Exception as e:
        logger.warning("Failed to initialize WebSocket handler: %s", e)
        return None
