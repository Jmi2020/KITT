# noqa: D401
"""FastAPI application for the brain service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.config import settings
from common.logging import configure_logging

from .autonomous.scheduler import get_scheduler
from .autonomous.jobs import (
    daily_health_check,
    weekly_research_cycle,
    knowledge_base_update,
    printer_fleet_health_check,
)
from .logging_config import setup_reasoning_logging
from .metrics import router as metrics_router
from .routes.autonomy import router as autonomy_router
from .routes.collective import router as collective_router
from .routes.models import router as models_router
from .routes.projects import router as projects_router
from .routes.query import router as query_router
from .routes.memory import router as memory_router
from .routes.usage import router as usage_router

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

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for brain service startup/shutdown.

    Handles:
    - Starting/stopping autonomous scheduler
    - Registering scheduled jobs
    """
    # Startup
    logger.info("Brain service starting up")

    # Start autonomous scheduler if enabled
    autonomous_enabled = getattr(settings, "autonomous_enabled", False)
    if autonomous_enabled:
        logger.info("Autonomous mode enabled, starting scheduler")
        scheduler = get_scheduler()
        scheduler.start()

        # Register autonomous jobs (4am-6am PST = 12pm-2pm UTC)

        # Daily health check at 4:00 PST (12:00 UTC)
        scheduler.add_cron_job(
            func=daily_health_check,
            hour=12,
            minute=0,
            job_id="daily_health_check",
        )

        # Weekly research cycle - Monday at 5:00 PST (13:00 UTC)
        scheduler.add_cron_job(
            func=weekly_research_cycle,
            day_of_week="mon",
            hour=13,
            minute=0,
            job_id="weekly_research_cycle",
        )

        # Knowledge base update - Monday at 6:00 PST (14:00 UTC)
        scheduler.add_cron_job(
            func=knowledge_base_update,
            day_of_week="mon",
            hour=14,
            minute=0,
            job_id="knowledge_base_update",
        )

        # Printer fleet health check - Every 4 hours
        scheduler.add_interval_job(
            func=printer_fleet_health_check,
            hours=4,
            job_id="printer_fleet_health_check",
        )

        logger.info("Autonomous scheduler started with 4 jobs registered (4am-6am PST / 12pm-2pm UTC)")
    else:
        logger.info("Autonomous mode disabled (AUTONOMOUS_ENABLED=false)")

    yield

    # Shutdown
    logger.info("Brain service shutting down")

    if autonomous_enabled:
        logger.info("Stopping autonomous scheduler")
        scheduler = get_scheduler()
        scheduler.stop(wait=True)
        logger.info("Autonomous scheduler stopped")


app = FastAPI(title="KITTY Brain API", lifespan=lifespan)
app.include_router(query_router)
app.include_router(projects_router)
app.include_router(models_router)
app.include_router(autonomy_router)
app.include_router(collective_router)
app.include_router(memory_router)
app.include_router(usage_router)
app.include_router(metrics_router)


@app.get("/healthz")
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
