"""
APScheduler integration for KITTY autonomous operations.

Provides a wrapper around APScheduler's BackgroundScheduler for managing
periodic tasks, cron jobs, and scheduled autonomous workflows.

Features:
- Persistent job storage via PostgreSQL (SQLAlchemyJobStore)
- Jobs survive service restarts
- Automatic job state persistence (next_run_time, run_count, etc.)
"""

import logging
from datetime import datetime
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent

from common.config import settings

logger = logging.getLogger(__name__)


class AutonomousScheduler:
    """
    Manages scheduled autonomous tasks using APScheduler.

    Provides methods to add periodic jobs, cron-style jobs, and manage
    the scheduler lifecycle integrated with the brain service.
    """

    def __init__(self, database_url: Optional[str] = None):
        """Initialize the scheduler (not started).

        Args:
            database_url: PostgreSQL connection URL for job persistence.
                         If None, uses settings.database_url.
        """
        self._scheduler: Optional[BackgroundScheduler] = None
        self._is_running = False
        self._database_url = database_url or settings.database_url

    def start(self) -> None:
        """
        Start the background scheduler with persistent job storage.

        Jobs are persisted to PostgreSQL and survive service restarts.
        Should be called during brain service startup.
        """
        if self._is_running:
            logger.warning("Scheduler already running, ignoring start request")
            return

        logger.info("Starting autonomous scheduler with persistent job store")

        # Configure persistent job store (PostgreSQL)
        jobstores = {
            'default': SQLAlchemyJobStore(
                url=self._database_url,
                tablename='apscheduler_jobs'
            )
        }

        # Create scheduler with persistent job store
        self._scheduler = BackgroundScheduler(
            jobstores=jobstores,
            timezone="UTC"
        )

        # Add event listeners for job execution tracking
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )

        self._scheduler.start()
        self._is_running = True

        # Log existing jobs (from previous runs)
        existing_jobs = self._scheduler.get_jobs()
        if existing_jobs:
            logger.info(
                f"Autonomous scheduler started - {len(existing_jobs)} existing jobs "
                f"restored from database"
            )
        else:
            logger.info("Autonomous scheduler started - no existing jobs in database")

    def stop(self, wait: bool = True) -> None:
        """
        Stop the background scheduler.

        Should be called during brain service shutdown.

        Args:
            wait: If True, wait for running jobs to complete before shutting down
        """
        if not self._is_running or self._scheduler is None:
            logger.warning("Scheduler not running, ignoring stop request")
            return

        logger.info("Stopping autonomous scheduler")
        self._scheduler.shutdown(wait=wait)
        self._is_running = False
        self._scheduler = None
        logger.info("Autonomous scheduler stopped")

    def add_interval_job(
        self,
        func: Callable,
        seconds: Optional[int] = None,
        minutes: Optional[int] = None,
        hours: Optional[int] = None,
        job_id: Optional[str] = None,
        replace_existing: bool = True,
        **kwargs
    ) -> str:
        """
        Add a job that runs at fixed intervals.

        Args:
            func: The function to execute
            seconds: Interval in seconds
            minutes: Interval in minutes
            hours: Interval in hours
            job_id: Unique identifier for the job (auto-generated if None)
            replace_existing: If True, replace job with same ID
            **kwargs: Additional arguments passed to the job function

        Returns:
            Job ID

        Example:
            scheduler.add_interval_job(
                health_check,
                minutes=30,
                job_id="health_check_periodic"
            )
        """
        if not self._is_running or self._scheduler is None:
            raise RuntimeError("Scheduler not started. Call start() first.")

        trigger = IntervalTrigger(
            seconds=seconds or 0,
            minutes=minutes or 0,
            hours=hours or 0,
            timezone="UTC"
        )

        job = self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            replace_existing=replace_existing,
            kwargs=kwargs,
            name=job_id or func.__name__
        )

        logger.info(
            f"Added interval job '{job.id}' (every "
            f"{hours or 0}h {minutes or 0}m {seconds or 0}s)"
        )
        return job.id

    def add_cron_job(
        self,
        func: Callable,
        day_of_week: Optional[str] = None,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        job_id: Optional[str] = None,
        replace_existing: bool = True,
        **kwargs
    ) -> str:
        """
        Add a cron-style job that runs at specific times.

        Args:
            func: The function to execute
            day_of_week: Day(s) of week (0-6 or mon,tue,wed,thu,fri,sat,sun)
            hour: Hour (0-23)
            minute: Minute (0-59)
            job_id: Unique identifier for the job (auto-generated if None)
            replace_existing: If True, replace job with same ID
            **kwargs: Additional arguments passed to the job function

        Returns:
            Job ID

        Example:
            scheduler.add_cron_job(
                weekly_research_cycle,
                day_of_week='mon',
                hour=9,
                minute=0,
                job_id="weekly_autonomous_cycle"
            )
        """
        if not self._is_running or self._scheduler is None:
            raise RuntimeError("Scheduler not started. Call start() first.")

        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            timezone="UTC"
        )

        job = self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            replace_existing=replace_existing,
            kwargs=kwargs,
            name=job_id or func.__name__
        )

        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if job.next_run_time else "N/A"
        logger.info(
            f"Added cron job '{job.id}' "
            f"(day_of_week={day_of_week}, hour={hour}, minute={minute}). "
            f"Next run: {next_run}"
        )
        return job.id

    def add_job(
        self,
        func: Callable,
        trigger: str = "interval",
        job_id: Optional[str] = None,
        **trigger_args
    ) -> str:
        """
        Generic method to add any type of job.

        Args:
            func: The function to execute
            trigger: Type of trigger ('interval', 'cron', 'date')
            job_id: Unique identifier for the job
            **trigger_args: Arguments for the trigger

        Returns:
            Job ID
        """
        if not self._is_running or self._scheduler is None:
            raise RuntimeError("Scheduler not started. Call start() first.")

        job = self._scheduler.add_job(
            func=func,
            trigger=trigger,
            id=job_id,
            **trigger_args
        )

        logger.info(f"Added job '{job.id}' with trigger '{trigger}'")
        return job.id

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job.

        Args:
            job_id: The ID of the job to remove
        """
        if not self._is_running or self._scheduler is None:
            raise RuntimeError("Scheduler not started")

        self._scheduler.remove_job(job_id)
        logger.info(f"Removed job '{job_id}'")

    def get_jobs(self) -> list:
        """
        Get all scheduled jobs.

        Returns:
            List of job objects
        """
        if not self._is_running or self._scheduler is None:
            return []

        return self._scheduler.get_jobs()

    def get_job_info(self) -> dict:
        """
        Get information about all scheduled jobs.

        Returns:
            Dictionary with job details
        """
        jobs = self.get_jobs()
        return {
            "scheduler_running": self._is_running,
            "job_count": len(jobs),
            "jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
                for job in jobs
            ]
        }

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """
        Event listener for job execution.

        Logs job execution and errors for monitoring.
        """
        if event.exception:
            logger.error(
                f"Job '{event.job_id}' failed with exception: {event.exception}",
                exc_info=event.exception
            )
        else:
            logger.info(
                f"Job '{event.job_id}' executed successfully "
                f"(scheduled: {event.scheduled_run_time})"
            )

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running


# Singleton instance for brain service
_scheduler_instance: Optional[AutonomousScheduler] = None


def get_scheduler() -> AutonomousScheduler:
    """
    Get the singleton scheduler instance.

    Returns:
        AutonomousScheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutonomousScheduler()
    return _scheduler_instance
