from fastapi import FastAPI

from .dependencies import get_router

app = FastAPI(title="KITTY Voice Service")


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/voice/transcript")
async def handle_transcript(payload: dict):
    router = get_router()
    conversation_id = payload.get("conversationId", "default")
    user_id = payload.get("userId", "anonymous")
    transcript = payload.get("transcript", "")
    result = await router.handle_transcript(conversation_id, user_id, transcript)
    return result
