"""WebSocket handler for real-time voice streaming.

Handles bidirectional audio streaming:
- Client → Server: Audio chunks for STT (Whisper)
- Server → Client: Response audio from TTS (Kokoro/Piper/OpenAI)

Features:
- Wake word detection (Porcupine) for hands-free activation
- Adaptive TTS with Kokoro ONNX optimized for Apple Silicon
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Optional

from fastapi import WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from .router import VoiceRouter
    from .stt import HybridSTT
    from .tts import StreamingTTS
    from .wake_word import WakeWordManager

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """WebSocket message types for voice protocol."""

    # Client → Server
    AUDIO_CHUNK = "audio.chunk"  # Raw audio bytes (base64 encoded)
    AUDIO_END = "audio.end"  # Client finished speaking
    CONFIG = "config"  # Session configuration
    CANCEL = "cancel"  # Cancel current response
    WAKE_WORD_TOGGLE = "wake_word.toggle"  # Enable/disable wake word

    # Server → Client
    TRANSCRIPT = "transcript"  # STT result (partial or final)
    RESPONSE_START = "response.start"  # Response generation started
    RESPONSE_TEXT = "response.text"  # Text chunk from LLM
    RESPONSE_AUDIO = "response.audio"  # TTS audio chunk (base64)
    RESPONSE_END = "response.end"  # Response complete
    FUNCTION_CALL = "function.call"  # Tool/function invocation
    FUNCTION_RESULT = "function.result"  # Tool result
    ERROR = "error"  # Error message
    STATUS = "status"  # Connection status updates
    WAKE_WORD_DETECTED = "wake_word.detected"  # Wake word triggered
    WAKE_WORD_STATUS = "wake_word.status"  # Wake word enabled/disabled


@dataclass
class VoiceSession:
    """Tracks state for a single voice WebSocket session."""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = "default"
    user_id: str = "anonymous"
    is_listening: bool = False
    is_responding: bool = False
    audio_buffer: bytearray = field(default_factory=bytearray)
    cancelled: bool = False

    # Configuration
    voice: str = "default"  # TTS voice (uses KOKORO_DEFAULT_VOICE env var)
    language: str = "en"  # STT language hint
    sample_rate: int = 16000  # Audio sample rate
    channels: int = 1  # Mono audio
    prefer_local: bool = True  # Prefer local STT/TTS over cloud

    # Mode and tool settings
    mode: str = "basic"  # Voice mode: basic, maker, research, home, creative
    allow_paid: bool = False  # Allow paid API calls (CAD, deep research)
    enabled_tools: list = field(default_factory=list)  # Enabled tool names

    # Wake word settings
    wake_word_enabled: bool = False  # Whether wake word detection is active
    activation_mode: str = "ptt"  # ptt (push-to-talk) or always_listening


class VoiceWebSocketHandler:
    """Handles WebSocket connections for real-time voice interaction."""

    def __init__(
        self,
        router: VoiceRouter | None = None,
        stt: HybridSTT | None = None,
        tts: StreamingTTS | None = None,
        wake_word_manager: Optional["WakeWordManager"] = None,
    ) -> None:
        self._router = router
        self._stt = stt
        self._tts = tts
        self._wake_word_manager = wake_word_manager
        self._sessions: dict[str, VoiceSession] = {}
        self._wake_word_websockets: dict[str, WebSocket] = {}  # Track WS for wake word callbacks

    async def handle_connection(self, websocket: WebSocket) -> None:
        """Main WebSocket connection handler."""
        await websocket.accept()
        session = VoiceSession()
        self._sessions[session.session_id] = session

        try:
            # Track websocket for wake word callbacks
            self._wake_word_websockets[session.session_id] = websocket

            # Check wake word availability
            wake_word_available = (
                self._wake_word_manager is not None
                and self._wake_word_manager.enabled
            )

            # Send initial status
            await self._send(
                websocket,
                MessageType.STATUS,
                {
                    "session_id": session.session_id,
                    "status": "connected",
                    "capabilities": {
                        "stt": self._stt is not None,
                        "tts": self._tts is not None,
                        "streaming": True,
                        "wake_word": wake_word_available,
                    },
                    "tts_provider": self._tts.get_active_provider() if self._tts else None,
                },
            )

            # Main message loop
            while True:
                try:
                    message = await websocket.receive()

                    if message["type"] == "websocket.disconnect":
                        break

                    if "text" in message:
                        await self._handle_text_message(
                            websocket, session, message["text"]
                        )
                    elif "bytes" in message:
                        await self._handle_binary_message(
                            websocket, session, message["bytes"]
                        )

                except WebSocketDisconnect:
                    break

        except Exception as e:
            logger.exception("WebSocket error: %s", e)
            await self._send(
                websocket, MessageType.ERROR, {"message": str(e), "code": "internal"}
            )
        finally:
            self._sessions.pop(session.session_id, None)
            self._wake_word_websockets.pop(session.session_id, None)

    async def _handle_text_message(
        self, websocket: WebSocket, session: VoiceSession, raw: str
    ) -> None:
        """Handle JSON text messages from client."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": "Invalid JSON", "code": "parse_error"},
            )
            return

        msg_type = data.get("type")

        if msg_type == MessageType.CONFIG:
            # Update session configuration
            config = data.get("config", {})
            session.conversation_id = config.get(
                "conversation_id", session.conversation_id
            )
            session.user_id = config.get("user_id", session.user_id)
            session.voice = config.get("voice", session.voice)
            session.language = config.get("language", session.language)
            session.sample_rate = config.get("sample_rate", session.sample_rate)
            if "prefer_local" in config:
                session.prefer_local = config.get("prefer_local", True)

            # Mode and tool settings
            if "mode" in config:
                session.mode = config.get("mode", "basic")
            if "allow_paid" in config:
                session.allow_paid = config.get("allow_paid", False)
            if "enabled_tools" in config:
                session.enabled_tools = config.get("enabled_tools", [])

            logger.info(
                f"Session {session.session_id} configured: "
                f"mode={session.mode}, allow_paid={session.allow_paid}"
            )

            await self._send(
                websocket,
                MessageType.STATUS,
                {
                    "status": "configured",
                    "session_id": session.session_id,
                    "prefer_local": session.prefer_local,
                    "mode": session.mode,
                    "allow_paid": session.allow_paid,
                },
            )

        elif msg_type == MessageType.AUDIO_CHUNK:
            # Base64 encoded audio chunk
            import base64

            audio_b64 = data.get("audio", "")
            if audio_b64:
                audio_bytes = base64.b64decode(audio_b64)
                session.audio_buffer.extend(audio_bytes)
                session.is_listening = True

        elif msg_type == MessageType.AUDIO_END:
            # Client finished speaking - process the audio
            session.is_listening = False
            if session.audio_buffer:
                await self._process_audio(websocket, session)

        elif msg_type == MessageType.CANCEL:
            # Cancel current response
            session.cancelled = True
            session.is_responding = False
            await self._send(
                websocket, MessageType.STATUS, {"status": "cancelled"}
            )

        elif msg_type == MessageType.WAKE_WORD_TOGGLE:
            # Toggle wake word detection
            await self._handle_wake_word_toggle(websocket, session, data)

        elif msg_type == "text":
            # Direct text input (bypass STT)
            text = data.get("content", "").strip()
            if text:
                await self._process_text(websocket, session, text)

    async def _handle_binary_message(
        self, websocket: WebSocket, session: VoiceSession, data: bytes
    ) -> None:
        """Handle raw binary audio data."""
        session.audio_buffer.extend(data)
        session.is_listening = True

    async def _process_audio(
        self, websocket: WebSocket, session: VoiceSession
    ) -> None:
        """Process buffered audio through STT and generate response."""
        audio_data = bytes(session.audio_buffer)
        session.audio_buffer.clear()

        if not self._stt:
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": "STT not configured", "code": "stt_unavailable"},
            )
            return

        try:
            # Transcribe audio (pass session preference for local/cloud)
            transcript = await self._stt.transcribe(
                audio_data,
                language=session.language,
                sample_rate=session.sample_rate,
                prefer_local=session.prefer_local,
            )

            # Send transcript to client
            await self._send(
                websocket,
                MessageType.TRANSCRIPT,
                {"text": transcript, "final": True, "prefer_local": session.prefer_local},
            )

            if transcript.strip():
                await self._process_text(websocket, session, transcript)

        except Exception as e:
            logger.exception("STT error: %s", e)
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": f"Transcription failed: {e}", "code": "stt_error"},
            )

    async def _process_text(
        self, websocket: WebSocket, session: VoiceSession, text: str
    ) -> None:
        """Process text input and generate streaming response."""
        session.is_responding = True
        session.cancelled = False

        await self._send(websocket, MessageType.RESPONSE_START, {"text": text})

        try:
            # Check if router is available
            if not self._router:
                # No router - just echo back the transcript
                echo_response = f"I heard: {text}"
                await self._send(
                    websocket,
                    MessageType.RESPONSE_TEXT,
                    {"delta": echo_response, "done": True, "tier": "stt_only"},
                )
                if self._tts and not session.cancelled:
                    await self._stream_tts(websocket, session, echo_response)
                return

            # Use streaming response from voice router
            full_response = ""

            async for chunk in self._router.handle_transcript_stream(
                session.conversation_id,
                session.user_id,
                text,
                allow_paid=session.allow_paid,
                mode=session.mode,
            ):
                if session.cancelled:
                    break

                chunk_type = chunk.get("type")

                if chunk_type == "device":
                    # Device command was sent
                    device_msg = f"Command sent to {chunk.get('device', 'device')}"
                    await self._send(
                        websocket,
                        MessageType.RESPONSE_TEXT,
                        {"delta": device_msg, "done": True},
                    )
                    full_response = device_msg

                elif chunk_type == "text":
                    # Streaming text response
                    delta = chunk.get("delta", "")
                    if delta:
                        full_response += delta
                        await self._send(
                            websocket,
                            MessageType.RESPONSE_TEXT,
                            {"delta": delta, "done": False},
                        )

                elif chunk_type == "tool_call":
                    # Tool/function invocation started
                    await self._send(
                        websocket,
                        MessageType.FUNCTION_CALL,
                        {
                            "id": chunk.get("id"),
                            "name": chunk.get("name"),
                            "args": chunk.get("args", {}),
                            "step": chunk.get("step"),
                        },
                    )

                elif chunk_type == "tool_result":
                    # Tool/function execution result
                    await self._send(
                        websocket,
                        MessageType.FUNCTION_RESULT,
                        {
                            "id": chunk.get("id"),
                            "name": chunk.get("name"),
                            "result": chunk.get("result"),
                            "status": chunk.get("status", "completed"),
                            "step": chunk.get("step"),
                        },
                    )

                elif chunk_type == "done":
                    # Response complete
                    await self._send(
                        websocket,
                        MessageType.RESPONSE_TEXT,
                        {
                            "delta": "",
                            "done": True,
                            "tier": chunk.get("tier"),
                            "tools_used": chunk.get("tools_used", 0),
                        },
                    )

                elif chunk_type == "error":
                    await self._send(
                        websocket,
                        MessageType.ERROR,
                        {
                            "message": chunk.get("message", "Unknown error"),
                            "code": "routing_error",
                        },
                    )

            # Generate TTS for the full response if available
            if self._tts and full_response and not session.cancelled:
                await self._stream_tts(websocket, session, full_response)

        except Exception as e:
            logger.exception("Processing error: %s", e)
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": str(e), "code": "processing_error"},
            )

        finally:
            session.is_responding = False
            await self._send(websocket, MessageType.RESPONSE_END, {})

    async def _stream_tts(
        self, websocket: WebSocket, session: VoiceSession, text: str
    ) -> None:
        """Stream TTS audio chunks to client."""
        if not self._tts:
            return

        try:
            import base64

            logger.info("Starting TTS - voice: %s, text: %s...", session.voice, text[:50] if len(text) > 50 else text)
            async for audio_chunk in self._tts.synthesize_stream(
                text, voice=session.voice
            ):
                if session.cancelled:
                    break

                # Send base64 encoded audio chunk
                # Kokoro outputs 24kHz audio, Piper outputs 16kHz
                audio_b64 = base64.b64encode(audio_chunk).decode("ascii")
                active_provider = self._tts.get_active_provider()
                tts_sample_rate = 24000 if active_provider == "kokoro" else 16000
                print(f"[TTS] Sending audio chunk - provider: {active_provider}, format: pcm_{tts_sample_rate}", flush=True)
                await self._send(
                    websocket,
                    MessageType.RESPONSE_AUDIO,
                    {"audio": audio_b64, "format": f"pcm_{tts_sample_rate}"},
                )

        except Exception as e:
            logger.exception("TTS error: %s", e)
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": f"TTS failed: {e}", "code": "tts_error"},
            )

    async def _handle_wake_word_toggle(
        self, websocket: WebSocket, session: VoiceSession, data: dict[str, Any]
    ) -> None:
        """Handle wake word enable/disable requests."""
        enable = data.get("enable", not session.wake_word_enabled)

        if not self._wake_word_manager:
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": "Wake word not available", "code": "wake_word_unavailable"},
            )
            return

        if not self._wake_word_manager.enabled:
            await self._send(
                websocket,
                MessageType.ERROR,
                {"message": "Wake word disabled in configuration", "code": "wake_word_disabled"},
            )
            return

        if enable:
            # Create callback that will notify this session
            def on_wake_word_detected():
                # Schedule coroutine on event loop
                asyncio.create_task(
                    self._notify_wake_word_detected(session.session_id)
                )

            success = self._wake_word_manager.start(on_wake_word_detected)
            session.wake_word_enabled = success
            session.activation_mode = "always_listening" if success else "ptt"
        else:
            self._wake_word_manager.stop()
            session.wake_word_enabled = False
            session.activation_mode = "ptt"

        await self._send(
            websocket,
            MessageType.WAKE_WORD_STATUS,
            {
                "enabled": session.wake_word_enabled,
                "activation_mode": session.activation_mode,
            },
        )

    async def _notify_wake_word_detected(self, session_id: str) -> None:
        """Notify a session that wake word was detected."""
        websocket = self._wake_word_websockets.get(session_id)
        session = self._sessions.get(session_id)

        if not websocket or not session:
            return

        try:
            await self._send(
                websocket,
                MessageType.WAKE_WORD_DETECTED,
                {"session_id": session_id},
            )
            # Optionally start listening immediately
            session.is_listening = True
            logger.info(f"Wake word detected for session {session_id}")
        except Exception as e:
            logger.error(f"Error notifying wake word detection: {e}")

    async def _send(
        self, websocket: WebSocket, msg_type: MessageType, data: dict[str, Any]
    ) -> None:
        """Send a typed message to the client.

        Safely handles cases where the connection may have been closed.
        """
        try:
            message = {"type": msg_type.value, **data}
            await websocket.send_json(message)
        except RuntimeError as e:
            # Connection already closed - log but don't raise
            if "close message has been sent" in str(e):
                logger.debug("WebSocket already closed, skipping send: %s", msg_type.value)
            else:
                raise


# Singleton handler instance (initialized in dependencies)
_handler: VoiceWebSocketHandler | None = None


def get_websocket_handler() -> VoiceWebSocketHandler | None:
    """Get the WebSocket handler instance."""
    return _handler


def set_websocket_handler(handler: VoiceWebSocketHandler) -> None:
    """Set the WebSocket handler instance."""
    global _handler
    _handler = handler
