from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes.generate import router as generate_router

app = FastAPI(title="KITTY CAD Service")
app.include_router(generate_router)

# Serve artifact files (GLB, STL) for web UI downloads
ARTIFACTS_DIR = Path(os.getenv("CAD_ARTIFACTS_DIR", "artifacts"))
if ARTIFACTS_DIR.exists():
    app.mount("/api/cad/artifacts", StaticFiles(directory=str(ARTIFACTS_DIR)), name="artifacts")


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
