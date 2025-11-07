# noqa: D401
"""FastAPI application for the brain service."""

from __future__ import annotations

import os

from fastapi import FastAPI

from common.logging import configure_logging

from .logging_config import setup_reasoning_logging
from .metrics import router as metrics_router
from .routes.projects import router as projects_router
from .routes.query import router as query_router
from .routes.models import router as models_router

# Configure standard logging
configure_logging()

# Configure enhanced reasoning/routing logging
reasoning_log_level = os.getenv("REASONING_LOG_LEVEL", "INFO")
reasoning_log_file = os.getenv("REASONING_LOG_FILE", ".logs/reasoning.log")
reasoning_jsonl_file = os.getenv("REASONING_JSONL_FILE", ".logs/reasoning.jsonl")
setup_reasoning_logging(
    level=reasoning_log_level,
    log_file=reasoning_log_file,
    jsonl_file=reasoning_jsonl_file,
)

app = FastAPI(title="KITTY Brain API")
app.include_router(query_router)
app.include_router(projects_router)
app.include_router(models_router)
app.include_router(metrics_router)


@app.get("/healthz")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
