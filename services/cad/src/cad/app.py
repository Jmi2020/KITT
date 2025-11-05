from __future__ import annotations

from fastapi import FastAPI

from .routes.generate import router as generate_router

app = FastAPI(title="KITTY CAD Service")
app.include_router(generate_router)


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
