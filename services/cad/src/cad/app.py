from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes.generate import router as generate_router
from .routes.print_integration import router as print_router
from .routes.artifacts import router as artifacts_router

app = FastAPI(title="KITTY CAD Service")
app.include_router(generate_router)
app.include_router(print_router)
app.include_router(artifacts_router)

# Serve artifact files (GLB, STL) for web UI downloads
# Note: Using /api/cad/files to avoid conflict with /api/cad/artifacts API routes
ARTIFACTS_DIR = Path(os.getenv("CAD_ARTIFACTS_DIR", "artifacts"))
if ARTIFACTS_DIR.exists():
    app.mount("/api/cad/files", StaticFiles(directory=str(ARTIFACTS_DIR)), name="artifact_files")


@app.get("/healthz")
async def health() -> dict[str, str]:
    return {"status": "ok"}
