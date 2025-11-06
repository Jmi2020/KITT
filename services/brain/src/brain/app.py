# noqa: D401
"""FastAPI application for the brain service."""

from __future__ import annotations

from fastapi import FastAPI

from common.logging import configure_logging

from .metrics import router as metrics_router
from .routes.projects import router as projects_router
from .routes.query import router as query_router
from .routes.models import router as models_router

configure_logging()

app = FastAPI(title="KITTY Brain API")
app.include_router(query_router)
app.include_router(projects_router)
app.include_router(models_router)
app.include_router(metrics_router)


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
