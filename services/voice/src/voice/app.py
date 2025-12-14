from fastapi import FastAPI, WebSocket

from .dependencies import get_router, get_websocket_handler

app = FastAPI(title="KITTY Voice Service")


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
