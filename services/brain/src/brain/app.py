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
    project_generation_cycle,
    task_execution_cycle,
    outcome_measurement_cycle,
)
from .logging_config import setup_reasoning_logging
from .metrics import router as metrics_router
from .routes.autonomy import router as autonomy_router
from .routes.collective import router as collective_router
from .routes.models import router as models_router
from .routes.projects import router as projects_router
from .routes.providers import router as providers_router
from .routes.query import router as query_router
from .routes.memory import router as memory_router
from .routes.usage import router as usage_router
from .routes.conversations import router as conversations_router
from .research.routes import router as research_router

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
    - PostgreSQL connection pool and checkpointer for research sessions
    - Research session manager initialization
    - Starting/stopping autonomous scheduler
    - Registering scheduled jobs
    """
    # Startup
    logger.info("Brain service starting up")

    # Initialize research infrastructure if DATABASE_URL is configured
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        logger.info("Initializing research infrastructure")
        try:
            from brain.research.checkpoint import create_connection_pool, init_checkpointer
            from brain.research.session_manager import ResearchSessionManager

            # Create PostgreSQL connection pool
            app.state.pg_pool = create_connection_pool(database_url)
            logger.info("PostgreSQL connection pool created")

            # Initialize checkpointer (async)
            app.state.checkpointer = await init_checkpointer(app.state.pg_pool, auto_setup=True)
            logger.info("PostgreSQL checkpointer initialized")

            # Initialize session manager (graph will be built in Phase 5)
            # For now, pass None for graph - it will be updated when graph is ready
            app.state.research_graph = None
            app.state.session_manager = ResearchSessionManager(
                graph=app.state.research_graph,
                checkpointer=app.state.checkpointer,
                connection_pool=app.state.pg_pool
            )
            logger.info("Research session manager initialized")

        except Exception as e:
            logger.error(f"Failed to initialize research infrastructure: {e}")
            logger.warning("Research endpoints will not be available")
            app.state.pg_pool = None
            app.state.checkpointer = None
            app.state.session_manager = None
    else:
        logger.warning("DATABASE_URL not configured, research infrastructure disabled")
        app.state.pg_pool = None
        app.state.checkpointer = None
        app.state.session_manager = None

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

        # Project generation - Daily at 4:30am PST (12:30 UTC)
        scheduler.add_cron_job(
            func=project_generation_cycle,
            hour=12,
            minute=30,
            job_id="project_generation_cycle",
        )

        # Task execution - Every 15 minutes (executes ready tasks)
        scheduler.add_interval_job(
            func=task_execution_cycle,
            minutes=15,
            job_id="task_execution_cycle",
        )

        # Outcome measurement (Phase 3) - Daily at 6:00am PST (14:00 UTC)
        scheduler.add_cron_job(
            func=outcome_measurement_cycle,
            hour=14,
            minute=0,
            job_id="outcome_measurement_cycle",
        )

        logger.info("Autonomous scheduler started with 7 jobs registered (4am-6am PST / 12pm-2pm UTC)")
    else:
        logger.info("Autonomous mode disabled (AUTONOMOUS_ENABLED=false)")

    yield

    # Shutdown
    logger.info("Brain service shutting down")

    # Cleanup research infrastructure
    if hasattr(app.state, 'pg_pool') and app.state.pg_pool is not None:
        logger.info("Closing PostgreSQL connection pool")
        try:
            await app.state.pg_pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")

    if autonomous_enabled:
        logger.info("Stopping autonomous scheduler")
        scheduler = get_scheduler()
        scheduler.stop(wait=True)
        logger.info("Autonomous scheduler stopped")


app = FastAPI(title="KITTY Brain API", lifespan=lifespan)
app.include_router(query_router)
app.include_router(conversations_router)
app.include_router(projects_router)
app.include_router(models_router)
app.include_router(autonomy_router)
app.include_router(collective_router)
app.include_router(memory_router)
app.include_router(usage_router)
app.include_router(providers_router)
app.include_router(metrics_router)
app.include_router(research_router)  # Autonomous research sessions


@app.get("/healthz")
@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


__all__ = ["app"]
