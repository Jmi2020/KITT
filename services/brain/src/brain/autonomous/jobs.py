"""Autonomous job functions executed by the scheduler.

These functions are called by APScheduler on defined schedules (cron, interval).
Each job should be idempotent and handle errors gracefully.
"""

import logging
from datetime import datetime
from typing import Optional

import structlog

from common.config import settings
from common.db import SessionLocal

from .resource_manager import ResourceManager, AutonomousWorkload

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger()


async def daily_health_check() -> None:
    """Daily health check for autonomous system.

    Performs:
    - Resource availability check
    - Budget status verification
    - System idle detection
    - Logs status to reasoning.jsonl

    Scheduled: Daily at 4:00 PST (12:00 UTC)
    """
    try:
        struct_logger.info("autonomous_health_check_started", timestamp=datetime.utcnow().isoformat())

        # Get resource manager
        resource_manager = ResourceManager.from_settings()

        # Check status for both workload types
        scheduled_status = resource_manager.get_status(
            workload=AutonomousWorkload.scheduled,
            update_metrics=True
        )

        exploration_status = resource_manager.get_status(
            workload=AutonomousWorkload.exploration,
            update_metrics=True
        )

        # Get budget summary for last 7 days
        budget_summary = resource_manager.get_autonomous_budget_summary(days=7)

        # Log comprehensive health status
        struct_logger.info(
            "autonomous_health_check_completed",
            scheduled_ready=scheduled_status.can_run_autonomous,
            scheduled_reason=scheduled_status.reason,
            exploration_ready=exploration_status.can_run_autonomous,
            exploration_reason=exploration_status.reason,
            budget_available=float(scheduled_status.budget_available),
            budget_used_today=float(scheduled_status.budget_used_today),
            budget_limit=float(resource_manager.daily_budget),
            cpu_percent=scheduled_status.cpu_usage_percent,
            memory_percent=scheduled_status.memory_usage_percent,
            is_idle=scheduled_status.is_idle,
            weekly_budget_summary=budget_summary,
            timestamp=datetime.utcnow().isoformat()
        )

        logger.info("✅ Daily health check completed successfully")

    except Exception as exc:
        logger.error(f"❌ Daily health check failed: {exc}", exc_info=True)
        struct_logger.error("autonomous_health_check_failed", error=str(exc))


async def weekly_research_cycle() -> None:
    """Weekly autonomous research cycle (Monday morning).

    Performs:
    - Opportunity detection from print failures and knowledge gaps
    - Goal generation with impact scoring (OpportunityScore 0-100)
    - Goal persistence to database (status=identified, awaiting approval)

    Scheduled: Monday at 5:00 PST (13:00 UTC)

    Generated goals are saved with status=identified and require user approval
    before KITTY proceeds with research or fabrication projects.
    """
    try:
        struct_logger.info("weekly_research_cycle_started", timestamp=datetime.utcnow().isoformat())

        # Check resource availability before running
        resource_manager = ResourceManager.from_settings()
        status = resource_manager.get_status(workload=AutonomousWorkload.scheduled)

        if not status.can_run_autonomous:
            logger.warning(f"⚠️ Weekly research cycle skipped: {status.reason}")
            struct_logger.warning(
                "weekly_research_cycle_skipped",
                reason=status.reason,
                budget_available=float(status.budget_available)
            )
            return

        logger.info("🔍 Weekly research cycle starting")

        # Import goal generator
        from .goal_generator import GoalGenerator

        # Initialize goal generator
        goal_gen = GoalGenerator(
            lookback_days=30,
            min_failure_count=3,
            min_impact_score=50.0,
        )

        # Generate high-impact goals
        logger.info("🎯 Analyzing opportunities and generating goals...")
        goals = goal_gen.generate_goals(max_goals=5)

        if not goals:
            logger.info("📋 No high-impact goals identified this cycle")
            struct_logger.info(
                "weekly_research_cycle_no_goals",
                message="No opportunities meeting minimum impact threshold",
                budget_available=float(status.budget_available)
            )
            return

        # Persist goals to database
        saved_count = goal_gen.persist_goals(goals)

        logger.info(
            f"✅ Weekly research cycle completed: "
            f"{saved_count} goals created, "
            f"awaiting approval"
        )

        struct_logger.info(
            "weekly_research_cycle_completed",
            goals_generated=len(goals),
            goals_persisted=saved_count,
            goal_types=[g.goal_type.value for g in goals],
            top_descriptions=[g.description[:80] for g in goals[:3]],
            budget_available=float(status.budget_available)
        )

    except Exception as exc:
        logger.error(f"❌ Weekly research cycle failed: {exc}", exc_info=True)
        struct_logger.error("weekly_research_cycle_failed", error=str(exc))


async def knowledge_base_update() -> None:
    """Update knowledge base with latest information (Monday).

    Performs:
    - Material cost updates from supplier APIs
    - Sustainability score refreshes
    - Technique guide updates based on recent successes

    Scheduled: Monday at 6:00 PST (14:00 UTC)

    Note: This is a basic implementation. Full supplier integration in Sprint 2.
    """
    try:
        struct_logger.info("kb_update_started", timestamp=datetime.utcnow().isoformat())

        # Check resource availability
        resource_manager = ResourceManager.from_settings()
        status = resource_manager.get_status(workload=AutonomousWorkload.scheduled)

        if not status.can_run_autonomous:
            logger.warning(f"⚠️ Knowledge base update skipped: {status.reason}")
            struct_logger.warning("kb_update_skipped", reason=status.reason)
            return

        logger.info("📚 Knowledge base update starting")

        # Import KnowledgeUpdater
        from ..knowledge.updater import KnowledgeUpdater

        kb_updater = KnowledgeUpdater()

        # List current knowledge base content
        materials = kb_updater.list_materials()
        techniques = kb_updater.list_techniques()
        research = kb_updater.list_research()

        logger.info(
            f"📊 Knowledge base status: "
            f"{len(materials)} materials, "
            f"{len(techniques)} techniques, "
            f"{len(research)} research articles"
        )

        # TODO: Sprint 2 - Implement supplier API integration
        # - Query Farnell/ELEGOO/Ultimaker APIs for current PLA/PETG/ABS prices
        # - Update frontmatter with new cost_per_kg values
        # - Recalculate sustainability scores

        struct_logger.info(
            "kb_update_placeholder",
            materials_count=len(materials),
            techniques_count=len(techniques),
            research_count=len(research),
            message="Supplier integration pending Sprint 2"
        )

        logger.info("✅ Knowledge base update completed (placeholder)")

    except Exception as exc:
        logger.error(f"❌ Knowledge base update failed: {exc}", exc_info=True)
        struct_logger.error("kb_update_failed", error=str(exc))


async def printer_fleet_health_check() -> None:
    """Check printer fleet health and log status (every 4 hours).

    Performs:
    - Query all printers via fabrication service
    - Log online/offline status
    - Detect printers needing maintenance
    - Update Prometheus metrics

    Scheduled: Every 4 hours
    """
    try:
        struct_logger.info("printer_fleet_check_started", timestamp=datetime.utcnow().isoformat())

        # TODO: Sprint 2 - Integrate with fabrication service API
        # GET /api/fabrication/printer_status for all printers
        # Log failures, maintenance needs, filament levels

        logger.info("🖨️ Printer fleet health check (placeholder)")
        struct_logger.info(
            "printer_fleet_check_placeholder",
            message="Fabrication service integration pending Sprint 2"
        )

        logger.info("✅ Printer fleet check completed (placeholder)")

    except Exception as exc:
        logger.error(f"❌ Printer fleet check failed: {exc}", exc_info=True)
        struct_logger.error("printer_fleet_check_failed", error=str(exc))


async def project_generation_cycle() -> None:
    """Generate projects from approved goals (every 4 hours).

    Performs:
    - Query for approved goals without projects
    - Create Project records with task breakdowns
    - Set task dependencies and priorities
    - Log project creation for user visibility

    Scheduled: Every 4 hours

    Projects are created with status=proposed and require no additional approval.
    Tasks inherit the goal's budget allocation and are ready for execution.
    """
    try:
        struct_logger.info("project_generation_cycle_started", timestamp=datetime.utcnow().isoformat())

        # Import project generator
        from .project_generator import ProjectGenerator

        # Initialize generator
        project_gen = ProjectGenerator(created_by="system-autonomous")

        # Generate projects from approved goals
        logger.info("📋 Checking for approved goals...")
        projects = project_gen.generate_projects_from_approved_goals(limit=10)

        if not projects:
            logger.info("No approved goals pending project generation")
            struct_logger.info("project_generation_no_goals")
            return

        logger.info(
            f"✅ Project generation completed: "
            f"{len(projects)} projects created"
        )

        struct_logger.info(
            "project_generation_completed",
            projects_created=len(projects),
            project_titles=[p.title[:60] for p in projects],
            project_ids=[p.id for p in projects],
        )

    except Exception as exc:
        logger.error(f"❌ Project generation cycle failed: {exc}", exc_info=True)
        struct_logger.error("project_generation_cycle_failed", error=str(exc))


__all__ = [
    "daily_health_check",
    "weekly_research_cycle",
    "knowledge_base_update",
    "printer_fleet_health_check",
    "project_generation_cycle",
]
