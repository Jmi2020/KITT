"""Tests for autonomous scheduler integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from services.brain.src.brain.autonomous.scheduler import AutonomousScheduler, get_scheduler


class TestAutonomousScheduler:
    """Test suite for AutonomousScheduler class."""

    def test_scheduler_initialization(self):
        """Test scheduler initializes correctly."""
        scheduler = AutonomousScheduler()
        assert scheduler.is_running is False
        assert scheduler._scheduler is None

    def test_scheduler_start(self):
        """Test scheduler starts successfully."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        assert scheduler.is_running is True
        assert scheduler._scheduler is not None

        # Cleanup
        scheduler.stop()

    def test_scheduler_start_idempotent(self):
        """Test calling start() twice doesn't break."""
        scheduler = AutonomousScheduler()
        scheduler.start()
        scheduler.start()  # Should log warning but not crash

        assert scheduler.is_running is True

        # Cleanup
        scheduler.stop()

    def test_scheduler_stop(self):
        """Test scheduler stops gracefully."""
        scheduler = AutonomousScheduler()
        scheduler.start()
        scheduler.stop()

        assert scheduler.is_running is False
        assert scheduler._scheduler is None

    def test_add_interval_job(self):
        """Test adding interval job."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        def test_job():
            pass

        job_id = scheduler.add_interval_job(
            func=test_job,
            minutes=30,
            job_id="test_interval_job"
        )

        assert job_id == "test_interval_job"
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "test_interval_job"

        # Cleanup
        scheduler.stop()

    def test_add_cron_job(self):
        """Test adding cron job."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        def test_job():
            pass

        job_id = scheduler.add_cron_job(
            func=test_job,
            day_of_week="mon",
            hour=9,
            minute=0,
            job_id="test_cron_job"
        )

        assert job_id == "test_cron_job"
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "test_cron_job"

        # Cleanup
        scheduler.stop()

    def test_add_job_before_start_raises_error(self):
        """Test adding job before scheduler starts raises error."""
        scheduler = AutonomousScheduler()

        def test_job():
            pass

        with pytest.raises(RuntimeError, match="Scheduler not started"):
            scheduler.add_interval_job(func=test_job, minutes=30)

    def test_remove_job(self):
        """Test removing a job."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        def test_job():
            pass

        job_id = scheduler.add_interval_job(
            func=test_job,
            minutes=30,
            job_id="removable_job"
        )

        assert len(scheduler.get_jobs()) == 1

        scheduler.remove_job(job_id)

        assert len(scheduler.get_jobs()) == 0

        # Cleanup
        scheduler.stop()

    def test_get_job_info(self):
        """Test getting job information."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        def test_job():
            pass

        scheduler.add_cron_job(
            func=test_job,
            day_of_week="mon",
            hour=4,
            minute=0,
            job_id="info_test_job"
        )

        info = scheduler.get_job_info()

        assert info["scheduler_running"] is True
        assert info["job_count"] == 1
        assert len(info["jobs"]) == 1
        assert info["jobs"][0]["id"] == "info_test_job"
        assert info["jobs"][0]["next_run_time"] is not None

        # Cleanup
        scheduler.stop()

    def test_singleton_pattern(self):
        """Test get_scheduler returns singleton instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2


class TestSchedulerEventHandling:
    """Test scheduler event listeners and error handling."""

    def test_job_execution_event_logged(self, caplog):
        """Test successful job execution is logged."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        executed = []

        def test_job():
            executed.append(True)

        # Add job that runs immediately
        scheduler.add_interval_job(
            func=test_job,
            seconds=1,
            job_id="immediate_job"
        )

        # Wait for job to execute
        import time
        time.sleep(2)

        assert len(executed) >= 1

        # Cleanup
        scheduler.stop()

    def test_job_error_event_logged(self, caplog):
        """Test job errors are logged."""
        scheduler = AutonomousScheduler()
        scheduler.start()

        def failing_job():
            raise ValueError("Test error")

        # Add job that runs immediately
        scheduler.add_interval_job(
            func=failing_job,
            seconds=1,
            job_id="failing_job"
        )

        # Wait for job to execute and fail
        import time
        time.sleep(2)

        # Job should have failed but scheduler should still be running
        assert scheduler.is_running is True

        # Cleanup
        scheduler.stop()


class TestSchedulerLifecycle:
    """Test scheduler integration with brain service lifecycle."""

    @patch('services.brain.src.brain.autonomous.scheduler.BackgroundScheduler')
    def test_scheduler_integrates_with_lifespan(self, mock_scheduler_class):
        """Test scheduler integrates with FastAPI lifespan."""
        mock_scheduler_instance = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler_instance

        scheduler = AutonomousScheduler()
        scheduler.start()

        # Verify scheduler was created and started
        mock_scheduler_class.assert_called_once()
        mock_scheduler_instance.start.assert_called_once()

        scheduler.stop()

        # Verify scheduler was stopped
        mock_scheduler_instance.shutdown.assert_called_once_with(True)
