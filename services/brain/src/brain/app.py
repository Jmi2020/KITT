# noqa: D401
"""FastAPI application for the brain service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from .routes.autonomy_calendar import router as autonomy_calendar_router
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
            from decimal import Decimal
            import redis
            from brain.research.checkpoint import create_connection_pool, init_checkpointer
            from brain.research.session_manager import ResearchSessionManager
            from brain.research.permissions import UnifiedPermissionGate
            from brain.research.models.budget import BudgetManager, BudgetConfig
            from brain.research.models.coordinator import ModelCoordinator
            from brain.research.tools.mcp_integration import ResearchToolExecutor
            from common.io_control.state_manager import FeatureStateManager

            # Create PostgreSQL connection pool
            app.state.pg_pool = create_connection_pool(database_url)
            logger.info("PostgreSQL connection pool created")

            # Initialize checkpointer (async)
            app.state.checkpointer = await init_checkpointer(app.state.pg_pool, auto_setup=True)
            logger.info("PostgreSQL checkpointer initialized")

            # Initialize persistent conversation state manager
            from brain.conversation.persistent_state import PersistentConversationStateManager
            from brain.conversation.auto_persist import AutoPersistStateManager
            from brain.conversation.sync_wrapper import SyncPersistentStateManager

            persistent_conv_manager = PersistentConversationStateManager(app.state.pg_pool)
            async_manager = AutoPersistStateManager(persistent_conv_manager)
            app.state.conversation_state_manager = SyncPersistentStateManager(async_manager)
            logger.info("Persistent conversation state manager initialized (sync wrapper)")

            # Initialize I/O Control state manager (Redis)
            try:
                redis_client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "redis"),
                    port=int(os.getenv("REDIS_PORT", "6379")),
                    db=0,
                    decode_responses=False
                )
                redis_client.ping()
                app.state.io_control = FeatureStateManager(redis_client=redis_client)
                logger.info("I/O Control state manager initialized")
            except Exception as redis_err:
                logger.warning(f"Redis not available for I/O Control: {redis_err}")
                app.state.io_control = None

            # Initialize async Redis client for distributed locking
            try:
                import redis.asyncio as aioredis
                from brain.autonomous.distributed_lock import set_lock_manager

                async_redis_client = aioredis.Redis(
                    host=os.getenv("REDIS_HOST", "redis"),
                    port=int(os.getenv("REDIS_PORT", "6379")),
                    db=0,
                    decode_responses=True  # Async client uses decode_responses=True
                )
                # Initialize global lock manager
                set_lock_manager(async_redis_client)
                app.state.async_redis = async_redis_client
                logger.info("Async Redis client and distributed lock manager initialized")
            except Exception as async_redis_err:
                logger.warning(f"Async Redis not available for distributed locking: {async_redis_err}")
                app.state.async_redis = None

            # Initialize budget manager with I/O Control defaults
            budget_config = BudgetConfig(
                max_total_cost_usd=Decimal(os.getenv("RESEARCH_BUDGET_USD", "2.0")),
                max_external_calls=int(os.getenv("RESEARCH_EXTERNAL_CALL_LIMIT", "10"))
            )
            app.state.budget_manager = BudgetManager(config=budget_config)
            logger.info(f"Budget manager initialized: ${budget_config.max_total_cost_usd}, {budget_config.max_external_calls} calls")

            # Initialize unified permission gate
            app.state.permission_gate = UnifiedPermissionGate(
                io_control_state_manager=app.state.io_control,
                budget_manager=app.state.budget_manager,
                omega_password=os.getenv("API_OVERRIDE_PASSWORD", "omega"),
                auto_approve_trivial=os.getenv("AUTO_APPROVE_TRIVIAL", "true").lower() == "true",
                auto_approve_low_cost=os.getenv("AUTO_APPROVE_LOW_COST", "false").lower() == "true"
            )
            logger.info("Unified permission gate initialized")

            # Initialize MCP servers (research & memory)
            from brain.routing.cloud_clients import MCPClient
            from mcp.servers.research_server import ResearchMCPServer
            from mcp.servers.memory_server import MemoryMCPServer

            # Create Perplexity client for research_deep tool
            perplexity_client = None
            perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
            if perplexity_api_key:
                perplexity_base_url = os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai")
                perplexity_client = MCPClient(
                    base_url=perplexity_base_url,
                    api_key=perplexity_api_key,
                    model=os.getenv("PERPLEXITY_MODEL", "sonar")
                )
                logger.info(f"Perplexity client initialized: {perplexity_base_url}")
            else:
                logger.warning("PERPLEXITY_API_KEY not set, research_deep tool will be unavailable")

            # Initialize ResearchMCPServer with Perplexity client
            app.state.research_server = ResearchMCPServer(perplexity_client=perplexity_client)
            logger.info("Research MCP server initialized")

            # Initialize MemoryMCPServer
            memory_service_url = os.getenv("MEM0_MCP_URL", "http://mem0-mcp:8765")
            app.state.memory_server = MemoryMCPServer(memory_service_url=memory_service_url)
            logger.info(f"Memory MCP server initialized: {memory_service_url}")

            # Initialize tool executor
            app.state.tool_executor = ResearchToolExecutor(
                research_server=app.state.research_server,
                memory_server=app.state.memory_server,
                permission_gate=app.state.permission_gate,
                budget_manager=app.state.budget_manager
            )
            logger.info("Research tool executor initialized")

            # Initialize model coordinator
            app.state.model_coordinator = ModelCoordinator(
                permission_gate=app.state.permission_gate
            )
            logger.info("Model coordinator initialized")

            # Register components for dependency injection into research graph
            from brain.research.graph.components import ResearchComponents, set_global_components

            components = ResearchComponents(
                tool_executor=app.state.tool_executor,
                permission_gate=app.state.permission_gate,
                model_coordinator=app.state.model_coordinator,
                budget_manager=app.state.budget_manager,
                research_server=app.state.research_server,
                memory_server=app.state.memory_server,
                io_control=app.state.io_control
            )

            set_global_components(components)
            logger.info(f"Research components registered for dependency injection: {components.get_status()}")

            # Build research graph (Phase 5)
            from brain.research.graph import build_research_graph

            app.state.research_graph = build_research_graph(checkpointer=app.state.checkpointer)
            logger.info("Research graph built and compiled")

            # Initialize session manager with graph
            app.state.session_manager = ResearchSessionManager(
                graph=app.state.research_graph,
                checkpointer=app.state.checkpointer,
                connection_pool=app.state.pg_pool
            )
            logger.info("Research session manager initialized with graph")

        except Exception as e:
            logger.error(f"Failed to initialize research infrastructure: {e}")
            logger.warning("Research endpoints will not be available")
            app.state.pg_pool = None
            app.state.checkpointer = None
            app.state.session_manager = None
            app.state.io_control = None
            app.state.budget_manager = None
            app.state.permission_gate = None
            app.state.research_server = None
            app.state.memory_server = None
            app.state.tool_executor = None
            app.state.model_coordinator = None
    else:
        logger.warning("DATABASE_URL not configured, research infrastructure disabled")
        app.state.pg_pool = None
        app.state.checkpointer = None
        app.state.session_manager = None
        app.state.io_control = None
        app.state.budget_manager = None
        app.state.permission_gate = None
        app.state.research_server = None
        app.state.memory_server = None
        app.state.tool_executor = None
        app.state.model_coordinator = None

    # Start autonomous scheduler if enabled
    autonomous_enabled = getattr(settings, "autonomous_enabled", False)
    if autonomous_enabled:
        logger.info("Autonomous mode enabled, starting scheduler")
        scheduler = get_scheduler()
        scheduler.start()

        # Register autonomous jobs (4am-6am PST = 12pm-2pm UTC)
        # Jobs are persisted to database, so only add if they don't already exist

        existing_job_ids = {job.id for job in scheduler.get_jobs()}
        jobs_registered = 0

        # Daily health check at 4:00 PST (12:00 UTC)
        if "daily_health_check" not in existing_job_ids:
            scheduler.add_cron_job(
                func=daily_health_check,
                hour=12,
                minute=0,
                job_id="daily_health_check",
            )
            jobs_registered += 1

        # Weekly research cycle - Monday at 5:00 PST (13:00 UTC)
        if "weekly_research_cycle" not in existing_job_ids:
            scheduler.add_cron_job(
                func=weekly_research_cycle,
                day_of_week="mon",
                hour=13,
                minute=0,
                job_id="weekly_research_cycle",
            )
            jobs_registered += 1

        # Knowledge base update - Monday at 6:00 PST (14:00 UTC)
        if "knowledge_base_update" not in existing_job_ids:
            scheduler.add_cron_job(
                func=knowledge_base_update,
                day_of_week="mon",
                hour=14,
                minute=0,
                job_id="knowledge_base_update",
            )
            jobs_registered += 1

        # Printer fleet health check - Every 4 hours
        if "printer_fleet_health_check" not in existing_job_ids:
            scheduler.add_interval_job(
                func=printer_fleet_health_check,
                hours=4,
                job_id="printer_fleet_health_check",
            )
            jobs_registered += 1

        # Project generation - Daily at 4:30am PST (12:30 UTC)
        if "project_generation_cycle" not in existing_job_ids:
            scheduler.add_cron_job(
                func=project_generation_cycle,
                hour=12,
                minute=30,
                job_id="project_generation_cycle",
            )
            jobs_registered += 1

        # Task execution - Every 15 minutes (executes ready tasks)
        if "task_execution_cycle" not in existing_job_ids:
            scheduler.add_interval_job(
                func=task_execution_cycle,
                minutes=15,
                job_id="task_execution_cycle",
            )
            jobs_registered += 1

        # Outcome measurement (Phase 3) - Daily at 6:00am PST (14:00 UTC)
        if "outcome_measurement_cycle" not in existing_job_ids:
            scheduler.add_cron_job(
                func=outcome_measurement_cycle,
                hour=14,
                minute=0,
                job_id="outcome_measurement_cycle",
            )
            jobs_registered += 1

        total_jobs = len(scheduler.get_jobs())
        logger.info(
            f"Autonomous scheduler started: {jobs_registered} new jobs registered, "
            f"{total_jobs - jobs_registered} restored from database, "
            f"{total_jobs} total active jobs"
        )
    else:
        logger.info("Autonomous mode disabled (AUTONOMOUS_ENABLED=false)")

    yield

    # Shutdown
    logger.info("Brain service shutting down")

    # Graceful shutdown for research session manager (wait for pending writes)
    if hasattr(app.state, 'session_manager') and app.state.session_manager is not None:
        logger.info("Initiating graceful shutdown for research session manager")
        try:
            shutdown_stats = await app.state.session_manager.graceful_shutdown(timeout_seconds=30)
            logger.info(f"Research session manager shutdown complete: {shutdown_stats}")
        except Exception as e:
            logger.error(f"Error during session manager graceful shutdown: {e}")

    # Cleanup research infrastructure
    if hasattr(app.state, 'pg_pool') and app.state.pg_pool is not None:
        logger.info("Closing PostgreSQL connection pool")
        try:
            await app.state.pg_pool.close()
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connection pool: {e}")

    # Cleanup async Redis client
    if hasattr(app.state, 'async_redis') and app.state.async_redis is not None:
        logger.info("Closing async Redis connection")
        try:
            await app.state.async_redis.close()
            logger.info("Async Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing async Redis: {e}")

    if autonomous_enabled:
        logger.info("Stopping autonomous scheduler")
        scheduler = get_scheduler()
        scheduler.stop(wait=True)
        logger.info("Autonomous scheduler stopped")


app = FastAPI(title="KITTY Brain API", lifespan=lifespan)

# Add CORS middleware to allow web UI access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(conversations_router)
app.include_router(projects_router)
app.include_router(models_router)
app.include_router(autonomy_router)
app.include_router(autonomy_calendar_router)
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
