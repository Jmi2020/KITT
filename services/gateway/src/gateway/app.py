from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .middleware.remote_mode import RemoteModeMiddleware
from .routes.routing import router as routing_router
from .routes.token import router as token_router
from .routes.devices import router as devices_router
from .routes.remote import router as remote_router
from .routes.vision import router as vision_router

app = FastAPI(title="KITTY Gateway")
app.add_middleware(RemoteModeMiddleware)
app.include_router(token_router)
app.include_router(routing_router)
app.include_router(devices_router)
app.include_router(remote_router)
app.include_router(vision_router)

storage_root = Path(os.getenv("KITTY_STORAGE_ROOT", "storage"))
storage_root.mkdir(parents=True, exist_ok=True)
app.mount("/storage", StaticFiles(directory=storage_root), name="storage")


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
