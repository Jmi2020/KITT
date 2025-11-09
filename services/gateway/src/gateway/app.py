from __future__ import annotations

from fastapi import FastAPI

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


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
