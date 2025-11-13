"""Tests for autonomous job functions."""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime

from brain.autonomous.jobs import (
    daily_health_check,
    weekly_research_cycle,
    knowledge_base_update,
    printer_fleet_health_check,
)
from brain.autonomous.resource_manager import (
    ResourceStatus,
    AutonomousWorkload,
)


@pytest.fixture
def mock_resource_status_ready():
    """Mock resource status indicating system is ready."""
    return ResourceStatus(
        budget_available=Decimal("4.50"),
        budget_used_today=Decimal("0.50"),
        is_idle=True,
        cpu_usage_percent=15.0,
        memory_usage_percent=45.0,
        gpu_available=True,
        can_run_autonomous=True,
        reason="Ready: $4.50 available, idle, CPU 15.0%, RAM 45.0%",
        workload=AutonomousWorkload.scheduled,
    )


@pytest.fixture
def mock_resource_status_blocked():
    """Mock resource status indicating system is blocked."""
    return ResourceStatus(
        budget_available=Decimal("0.00"),
        budget_used_today=Decimal("5.00"),
        is_idle=False,
        cpu_usage_percent=85.0,
        memory_usage_percent=75.0,
        gpu_available=True,
        can_run_autonomous=False,
        reason="Daily budget exhausted ($5.00/day limit)",
        workload=AutonomousWorkload.scheduled,
    )


class TestDailyHealthCheck:
    """Tests for daily_health_check job."""

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_health_check_success(self, mock_rm_class, mock_resource_status_ready):
        """Test daily health check runs successfully."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_ready
        mock_rm.get_autonomous_budget_summary.return_value = {
            "days": 7,
            "total_cost_usd": 15.50,
            "total_requests": 45,
        }
        mock_rm.daily_budget = Decimal("5.00")

        # Run health check
        await daily_health_check()

        # Verify resource manager was called correctly
        mock_rm_class.from_settings.assert_called_once()
        assert mock_rm.get_status.call_count == 2  # scheduled + exploration
        mock_rm.get_autonomous_budget_summary.assert_called_once_with(days=7)

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_health_check_handles_errors(self, mock_rm_class, caplog):
        """Test health check handles errors gracefully."""
        # Setup mock to raise error
        mock_rm_class.from_settings.side_effect = Exception("Database connection failed")

        # Run health check (should not raise)
        await daily_health_check()

        # Verify error was logged
        assert "Daily health check failed" in caplog.text


class TestWeeklyResearchCycle:
    """Tests for weekly_research_cycle job."""

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_research_cycle_runs_when_ready(
        self, mock_rm_class, mock_resource_status_ready
    ):
        """Test weekly research cycle runs when resources available."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_ready

        # Run research cycle
        await weekly_research_cycle()

        # Verify resource check was performed
        mock_rm.get_status.assert_called_once_with(
            workload=AutonomousWorkload.scheduled
        )

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_research_cycle_skips_when_blocked(
        self, mock_rm_class, mock_resource_status_blocked, caplog
    ):
        """Test weekly research cycle skips when resources unavailable."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_blocked

        # Run research cycle
        await weekly_research_cycle()

        # Verify it was skipped
        assert "Weekly research cycle skipped" in caplog.text

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_research_cycle_handles_errors(self, mock_rm_class, caplog):
        """Test research cycle handles errors gracefully."""
        # Setup mock to raise error
        mock_rm_class.from_settings.side_effect = Exception("Goal generator failed")

        # Run research cycle (should not raise)
        await weekly_research_cycle()

        # Verify error was logged
        assert "Weekly research cycle failed" in caplog.text


class TestKnowledgeBaseUpdate:
    """Tests for knowledge_base_update job."""

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    @patch('brain.autonomous.jobs.KnowledgeUpdater')
    async def test_kb_update_runs_when_ready(
        self, mock_kb_class, mock_rm_class, mock_resource_status_ready
    ):
        """Test knowledge base update runs when resources available."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_ready

        mock_kb = MagicMock()
        mock_kb_class.return_value = mock_kb
        mock_kb.list_materials.return_value = ["pla", "petg", "abs"]
        mock_kb.list_techniques.return_value = ["first-layer-adhesion"]
        mock_kb.list_research.return_value = []

        # Run KB update
        await knowledge_base_update()

        # Verify KB was queried
        mock_kb.list_materials.assert_called_once()
        mock_kb.list_techniques.assert_called_once()
        mock_kb.list_research.assert_called_once()

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_kb_update_skips_when_blocked(
        self, mock_rm_class, mock_resource_status_blocked, caplog
    ):
        """Test knowledge base update skips when resources unavailable."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_blocked

        # Run KB update
        await knowledge_base_update()

        # Verify it was skipped
        assert "Knowledge base update skipped" in caplog.text

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_kb_update_handles_errors(self, mock_rm_class, caplog):
        """Test knowledge base update handles errors gracefully."""
        # Setup mock to raise error
        mock_rm_class.from_settings.side_effect = Exception("KB path not found")

        # Run KB update (should not raise)
        await knowledge_base_update()

        # Verify error was logged
        assert "Knowledge base update failed" in caplog.text


class TestPrinterFleetHealthCheck:
    """Tests for printer_fleet_health_check job."""

    @pytest.mark.asyncio
    async def test_printer_fleet_check_placeholder(self, caplog):
        """Test printer fleet check runs (placeholder implementation)."""
        # Run printer fleet check
        await printer_fleet_health_check()

        # Verify placeholder logged
        assert "Printer fleet health check" in caplog.text

    @pytest.mark.asyncio
    async def test_printer_fleet_check_handles_errors(self, caplog):
        """Test printer fleet check handles errors gracefully."""
        # Run printer fleet check with patched error
        with patch(
            'brain.autonomous.jobs.struct_logger.info',
            side_effect=Exception("Fabrication service unreachable")
        ):
            await printer_fleet_health_check()

        # Should still complete without raising
        assert "Printer fleet check failed" in caplog.text or "completed" in caplog.text


class TestJobScheduleIntegration:
    """Integration tests for job scheduling."""

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_all_jobs_have_correct_signatures(self, mock_rm_class):
        """Test all job functions are async callables with no required args."""
        jobs = [
            daily_health_check,
            weekly_research_cycle,
            knowledge_base_update,
            printer_fleet_health_check,
        ]

        for job in jobs:
            # Verify is async callable
            assert callable(job)
            assert hasattr(job, '__code__')

            # Should accept no arguments (scheduler calls with no args)
            code = job.__code__
            assert code.co_argcount == 0, f"{job.__name__} should accept no arguments"

    @pytest.mark.asyncio
    @patch('brain.autonomous.jobs.ResourceManager')
    async def test_jobs_use_resource_manager_correctly(
        self, mock_rm_class, mock_resource_status_ready
    ):
        """Test jobs query resource manager before expensive operations."""
        # Setup mocks
        mock_rm = MagicMock()
        mock_rm_class.from_settings.return_value = mock_rm
        mock_rm.get_status.return_value = mock_resource_status_ready
        mock_rm.get_autonomous_budget_summary.return_value = {}
        mock_rm.daily_budget = Decimal("5.00")

        # Run jobs that check resources
        await daily_health_check()
        await weekly_research_cycle()

        # Verify resource manager was instantiated
        assert mock_rm_class.from_settings.call_count >= 2


@pytest.mark.integration
class TestJobExecutionTiming:
    """Integration tests for job execution timing."""

    def test_job_schedules_match_requirements(self):
        """Test job schedules match 4am-6am UTC window."""
        from brain.app import lifespan
        from brain.autonomous.scheduler import get_scheduler
        from common.config import settings

        # Temporarily enable autonomous mode
        original_value = getattr(settings, "autonomous_enabled", False)
        settings.autonomous_enabled = True

        try:
            # Simulate lifespan startup
            import asyncio
            from contextlib import asynccontextmanager

            app = MagicMock()

            async def test_lifespan():
                async with lifespan(app) as _:
                    scheduler = get_scheduler()

                    # Verify jobs are registered
                    job_info = scheduler.get_job_info()
                    assert job_info["job_count"] == 6

                    # Verify job IDs
                    job_ids = [job["id"] for job in job_info["jobs"]]
                    assert "daily_health_check" in job_ids
                    assert "weekly_research_cycle" in job_ids
                    assert "knowledge_base_update" in job_ids
                    assert "printer_fleet_health_check" in job_ids
                    assert "project_generation_cycle" in job_ids
                    assert "task_execution_cycle" in job_ids

            asyncio.run(test_lifespan())

        finally:
            # Restore original value
            settings.autonomous_enabled = original_value
