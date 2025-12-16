from fastapi import FastAPI, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel

from .dependencies import get_router, get_websocket_handler, get_tts

app = FastAPI(title="KITTY Voice Service")


# Kokoro voice definitions with metadata
KOKORO_VOICES = [
    # Curated (shown by default)
    {"id": "bf_emma", "name": "Emma", "gender": "female", "accent": "British", "curated": True},
    {"id": "bf_isabella", "name": "Isabella", "gender": "female", "accent": "British", "curated": True},
    {"id": "am_michael", "name": "Michael", "gender": "male", "accent": "American", "curated": True},
    {"id": "am_adam", "name": "Adam", "gender": "male", "accent": "American", "curated": True},
    {"id": "af_sarah", "name": "Sarah", "gender": "female", "accent": "American", "curated": True},
    {"id": "af_bella", "name": "Bella", "gender": "female", "accent": "American", "curated": True},
    {"id": "bm_george", "name": "George", "gender": "male", "accent": "British", "curated": True},
    {"id": "bm_lewis", "name": "Lewis", "gender": "male", "accent": "British", "curated": True},
    # Extended voices
    {"id": "af_nicole", "name": "Nicole", "gender": "female", "accent": "American", "curated": False},
    {"id": "af_sky", "name": "Sky", "gender": "female", "accent": "American", "curated": False},
    {"id": "af_jessica", "name": "Jessica", "gender": "female", "accent": "American", "curated": False},
    {"id": "af_kailey", "name": "Kailey", "gender": "female", "accent": "American", "curated": False},
    {"id": "af_river", "name": "River", "gender": "female", "accent": "American", "curated": False},
    {"id": "af_luna", "name": "Luna", "gender": "female", "accent": "American", "curated": False},
    {"id": "am_fenrir", "name": "Fenrir", "gender": "male", "accent": "American", "curated": False},
    {"id": "am_puck", "name": "Puck", "gender": "male", "accent": "American", "curated": False},
    {"id": "am_echo", "name": "Echo", "gender": "male", "accent": "American", "curated": False},
    {"id": "am_eric", "name": "Eric", "gender": "male", "accent": "American", "curated": False},
    {"id": "am_liam", "name": "Liam", "gender": "male", "accent": "American", "curated": False},
    {"id": "bf_alice", "name": "Alice", "gender": "female", "accent": "British", "curated": False},
    {"id": "bf_lily", "name": "Lily", "gender": "female", "accent": "British", "curated": False},
    {"id": "bm_daniel", "name": "Daniel", "gender": "male", "accent": "British", "curated": False},
    {"id": "bm_fable", "name": "Fable", "gender": "male", "accent": "British", "curated": False},
]


class VoicePreviewRequest(BaseModel):
    voice: str
    text: str = "Hello! I'm your voice assistant. How can I help you today?"


@app.get("/healthz")
@app.get("/api/voice/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/voice/status")
async def voice_status() -> dict:
    """Get voice service status including STT/TTS provider info."""
    handler = get_websocket_handler()
    if handler is None:
        return {
            "status": "degraded",
            "websocket": False,
            "stt": None,
            "tts": None,
        }

    return {
        "status": "ok",
        "websocket": True,
        "stt": handler._stt.get_status() if handler._stt else None,
        "tts": handler._tts.get_status() if handler._tts else None,
    }


@app.post("/api/voice/transcript")
async def handle_transcript(payload: dict):
    """Handle text transcript (legacy endpoint for non-streaming use)."""
    router = get_router()
    conversation_id = payload.get("conversationId", "default")
    user_id = payload.get("userId", "anonymous")
    transcript = payload.get("transcript", "")
    result = await router.handle_transcript(conversation_id, user_id, transcript)
    return result


@app.websocket("/stream")
@app.websocket("/api/voice/stream")
async def voice_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time voice streaming.

    Protocol:
    - Client sends audio chunks or text messages
    - Server responds with transcripts, LLM responses, and TTS audio

    See websocket.py for message format documentation.
    """
    handler = get_websocket_handler()
    if handler is None:
        await websocket.close(code=1011, reason="Voice streaming not configured")
        return

    await handler.handle_connection(websocket)


@app.get("/api/voice/voices")
async def get_available_voices():
    """Get list of available TTS voices with metadata.

    Returns curated and extended voice lists for Kokoro TTS.
    """
    handler = get_websocket_handler()
    tts_status = handler._tts.get_status() if handler and handler._tts else {}
    active_provider = tts_status.get("active_provider", "unknown")

    # Get current default voice from environment
    import os
    current_voice = os.getenv("KOKORO_DEFAULT_VOICE", "bf_emma")
    current_speed = float(os.getenv("KOKORO_SPEED", "1.0"))

    return {
        "provider": active_provider,
        "voices": KOKORO_VOICES,
        "curated": [v for v in KOKORO_VOICES if v.get("curated")],
        "current_voice": current_voice,
        "current_speed": current_speed,
    }


@app.post("/api/voice/preview")
async def preview_voice(request: VoicePreviewRequest):
    """Generate preview audio for a voice.

    Returns WAV audio data that can be played in the browser.
    """
    import io
    import wave
    import numpy as np

    tts = get_tts()
    if tts is None:
        return Response(
            content=b"",
            status_code=503,
            headers={"Content-Type": "text/plain"},
        )

    try:
        # Synthesize the preview text with the requested voice
        audio_bytes = await tts.synthesize(request.text, voice=request.voice)

        # Determine sample rate based on active provider
        sample_rate = 24000 if tts.get_active_provider() == "kokoro" else 16000

        # Convert PCM bytes to WAV format for browser playback
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)

        wav_buffer.seek(0)
        return Response(
            content=wav_buffer.read(),
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=preview.wav"},
        )

    except Exception as e:
        return Response(
            content=str(e).encode(),
            status_code=500,
            headers={"Content-Type": "text/plain"},
        )
