"""Unit tests for autonomous resource manager.

Tests budget tracking, idle detection, and resource availability constraints.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from common.db.models import Base, RoutingDecision
from services.brain.src.brain.autonomous.resource_manager import (
    ResourceManager,
    ResourceStatus,
)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def resource_manager(db_session):
    """Create a ResourceManager instance for testing."""
    return ResourceManager(
        db_session=db_session,
        daily_budget=Decimal("5.00"),
        idle_threshold_minutes=30,
        cpu_threshold_percent=20.0,
        memory_threshold_percent=70.0,
    )


class TestBudgetTracking:
    """Test budget tracking functionality."""

    def test_get_budget_used_today_no_records(self, resource_manager):
        """Test budget calculation with no routing decisions today."""
        budget_used = resource_manager._get_budget_used_today()
        assert budget_used == Decimal("0.00")

    def test_get_budget_used_today_with_records(self, resource_manager, db_session):
        """Test budget calculation with routing decisions today."""
        # Add routing decisions from today
        today = datetime.utcnow()
        db_session.add(
            RoutingDecision(
                id="decision1",
                user_id="user1",
                query="Test query 1",
                tier_used="local",
                cost_usd=0.05,
                timestamp=today,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.add(
            RoutingDecision(
                id="decision2",
                user_id="user2",
                query="Test query 2",
                tier_used="mcp",
                cost_usd=0.15,
                timestamp=today,
                latency_ms=200,
                confidence=0.85,
            )
        )
        db_session.commit()

        budget_used = resource_manager._get_budget_used_today()
        assert budget_used == Decimal("0.20")

    def test_get_budget_used_today_excludes_yesterday(self, resource_manager, db_session):
        """Test that budget calculation excludes yesterday's records."""
        # Add routing decision from yesterday
        yesterday = datetime.utcnow() - timedelta(days=1)
        db_session.add(
            RoutingDecision(
                id="decision_old",
                user_id="user1",
                query="Old query",
                tier_used="local",
                cost_usd=1.00,
                timestamp=yesterday,
                latency_ms=100,
                confidence=0.95,
            )
        )

        # Add routing decision from today
        today = datetime.utcnow()
        db_session.add(
            RoutingDecision(
                id="decision_new",
                user_id="user1",
                query="New query",
                tier_used="local",
                cost_usd=0.25,
                timestamp=today,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        budget_used = resource_manager._get_budget_used_today()
        assert budget_used == Decimal("0.25")

    def test_get_budget_used_today_filters_by_user(self, resource_manager, db_session):
        """Test budget calculation filtered by user ID."""
        today = datetime.utcnow()
        db_session.add(
            RoutingDecision(
                id="decision1",
                user_id="system-autonomous",
                query="Autonomous query",
                tier_used="local",
                cost_usd=0.50,
                timestamp=today,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.add(
            RoutingDecision(
                id="decision2",
                user_id="user1",
                query="User query",
                tier_used="mcp",
                cost_usd=0.30,
                timestamp=today,
                latency_ms=200,
                confidence=0.85,
            )
        )
        db_session.commit()

        # Get budget for autonomous user only
        budget_used = resource_manager._get_budget_used_today(user_id="system-autonomous")
        assert budget_used == Decimal("0.50")


class TestIdleDetection:
    """Test idle system detection functionality."""

    def test_is_system_idle_no_recent_activity(self, resource_manager):
        """Test system is idle with no recent activity."""
        is_idle = resource_manager._is_system_idle()
        assert is_idle is True

    def test_is_system_idle_with_recent_activity(self, resource_manager, db_session):
        """Test system is not idle with recent activity."""
        # Add routing decision from 10 minutes ago
        recent = datetime.utcnow() - timedelta(minutes=10)
        db_session.add(
            RoutingDecision(
                id="decision_recent",
                user_id="user1",
                query="Recent query",
                tier_used="local",
                cost_usd=0.05,
                timestamp=recent,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        is_idle = resource_manager._is_system_idle()
        assert is_idle is False

    def test_is_system_idle_excludes_autonomous_user(self, resource_manager, db_session):
        """Test system idle detection excludes autonomous user activity."""
        # Add autonomous user activity from 10 minutes ago
        recent = datetime.utcnow() - timedelta(minutes=10)
        db_session.add(
            RoutingDecision(
                id="decision_autonomous",
                user_id="system-autonomous",
                query="Autonomous query",
                tier_used="local",
                cost_usd=0.05,
                timestamp=recent,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        # System should be idle (autonomous activity is excluded)
        is_idle = resource_manager._is_system_idle(user_id="system-autonomous")
        assert is_idle is True

    def test_is_system_idle_old_activity(self, resource_manager, db_session):
        """Test system is idle with only old activity."""
        # Add routing decision from 2 hours ago
        old = datetime.utcnow() - timedelta(hours=2)
        db_session.add(
            RoutingDecision(
                id="decision_old",
                user_id="user1",
                query="Old query",
                tier_used="local",
                cost_usd=0.05,
                timestamp=old,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        is_idle = resource_manager._is_system_idle()
        assert is_idle is True


class TestGPUAvailability:
    """Test GPU availability detection."""

    @patch("services.brain.src.brain.autonomous.resource_manager.platform")
    def test_check_gpu_available_on_mac(self, mock_platform, resource_manager):
        """Test GPU availability check on macOS."""
        mock_platform.system.return_value = "Darwin"
        is_available = resource_manager._check_gpu_available()
        assert is_available is True

    @patch("services.brain.src.brain.autonomous.resource_manager.platform")
    def test_check_gpu_available_on_linux(self, mock_platform, resource_manager):
        """Test GPU availability check on Linux."""
        mock_platform.system.return_value = "Linux"
        is_available = resource_manager._check_gpu_available()
        # Default implementation assumes available
        assert is_available is True

    @patch("services.brain.src.brain.autonomous.resource_manager.platform")
    def test_check_gpu_available_exception(self, mock_platform, resource_manager):
        """Test GPU availability check handles exceptions."""
        mock_platform.system.side_effect = Exception("Platform error")
        is_available = resource_manager._check_gpu_available()
        assert is_available is False


class TestCanRunAutonomous:
    """Test autonomous work execution constraints."""

    def test_can_run_autonomous_all_constraints_met(self, resource_manager):
        """Test can run autonomous when all constraints are met."""
        can_run, reason = resource_manager._can_run_autonomous(
            budget_available=Decimal("5.00"),
            is_idle=True,
            cpu_usage=15.0,
            memory_usage=60.0,
            gpu_available=True,
        )
        assert can_run is True
        assert "Ready" in reason
        assert "5.00" in reason

    def test_can_run_autonomous_budget_exhausted(self, resource_manager):
        """Test cannot run autonomous when budget is exhausted."""
        can_run, reason = resource_manager._can_run_autonomous(
            budget_available=Decimal("0.00"),
            is_idle=True,
            cpu_usage=15.0,
            memory_usage=60.0,
            gpu_available=True,
        )
        assert can_run is False
        assert "budget exhausted" in reason.lower()

    def test_can_run_autonomous_not_idle(self, resource_manager):
        """Test cannot run autonomous when system is not idle."""
        can_run, reason = resource_manager._can_run_autonomous(
            budget_available=Decimal("5.00"),
            is_idle=False,
            cpu_usage=15.0,
            memory_usage=60.0,
            gpu_available=True,
        )
        assert can_run is False
        assert "not idle" in reason.lower()

    def test_can_run_autonomous_cpu_too_high(self, resource_manager):
        """Test cannot run autonomous when CPU usage is too high."""
        can_run, reason = resource_manager._can_run_autonomous(
            budget_available=Decimal("5.00"),
            is_idle=True,
            cpu_usage=75.0,
            memory_usage=60.0,
            gpu_available=True,
        )
        assert can_run is False
        assert "CPU usage too high" in reason

    def test_can_run_autonomous_memory_too_high(self, resource_manager):
        """Test cannot run autonomous when memory usage is too high."""
        can_run, reason = resource_manager._can_run_autonomous(
            budget_available=Decimal("5.00"),
            is_idle=True,
            cpu_usage=15.0,
            memory_usage=85.0,
            gpu_available=True,
        )
        assert can_run is False
        assert "Memory usage too high" in reason


class TestResourceStatus:
    """Test comprehensive resource status reporting."""

    @patch("services.brain.src.brain.autonomous.resource_manager.psutil")
    def test_get_status_all_good(self, mock_psutil, resource_manager, db_session):
        """Test resource status when all constraints are met."""
        # Mock psutil responses
        mock_psutil.cpu_percent.return_value = 15.0
        mock_memory = MagicMock()
        mock_memory.percent = 60.0
        mock_psutil.virtual_memory.return_value = mock_memory

        # Add some budget usage
        today = datetime.utcnow()
        db_session.add(
            RoutingDecision(
                id="decision1",
                user_id="system-autonomous",
                query="Test query",
                tier_used="local",
                cost_usd=1.50,
                timestamp=today,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        status = resource_manager.get_status()

        assert isinstance(status, ResourceStatus)
        assert status.budget_used_today == Decimal("1.50")
        assert status.budget_available == Decimal("3.50")
        assert status.is_idle is True
        assert status.cpu_usage_percent == 15.0
        assert status.memory_usage_percent == 60.0
        assert status.gpu_available is True
        assert status.can_run_autonomous is True
        assert "Ready" in status.reason

    @patch("services.brain.src.brain.autonomous.resource_manager.psutil")
    def test_get_status_budget_exhausted(self, mock_psutil, resource_manager, db_session):
        """Test resource status when budget is exhausted."""
        # Mock psutil responses
        mock_psutil.cpu_percent.return_value = 15.0
        mock_memory = MagicMock()
        mock_memory.percent = 60.0
        mock_psutil.virtual_memory.return_value = mock_memory

        # Exhaust budget
        today = datetime.utcnow()
        db_session.add(
            RoutingDecision(
                id="decision1",
                user_id="system-autonomous",
                query="Expensive query",
                tier_used="frontier",
                cost_usd=5.00,
                timestamp=today,
                latency_ms=100,
                confidence=0.95,
            )
        )
        db_session.commit()

        status = resource_manager.get_status()

        assert status.budget_used_today == Decimal("5.00")
        assert status.budget_available == Decimal("0.00")
        assert status.can_run_autonomous is False
        assert "budget exhausted" in status.reason.lower()


class TestBudgetSummary:
    """Test budget usage summary functionality."""

    def test_get_autonomous_budget_summary_empty(self, resource_manager):
        """Test budget summary with no data."""
        summary = resource_manager.get_autonomous_budget_summary(days=7)

        assert summary["days"] == 7
        assert summary["total_cost_usd"] == 0.0
        assert summary["total_requests"] == 0
        assert summary["average_cost_per_day"] == 0.0
        assert summary["budget_limit_per_day"] == 5.00

    def test_get_autonomous_budget_summary_with_data(self, resource_manager, db_session):
        """Test budget summary with multiple days of data."""
        # Add routing decisions from different days
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        two_days_ago = today - timedelta(days=2)

        db_session.add_all(
            [
                RoutingDecision(
                    id="decision1",
                    user_id="system-autonomous",
                    query="Query 1",
                    tier_used="local",
                    cost_usd=1.00,
                    timestamp=today,
                    latency_ms=100,
                    confidence=0.95,
                ),
                RoutingDecision(
                    id="decision2",
                    user_id="system-autonomous",
                    query="Query 2",
                    tier_used="mcp",
                    cost_usd=0.50,
                    timestamp=today,
                    latency_ms=150,
                    confidence=0.90,
                ),
                RoutingDecision(
                    id="decision3",
                    user_id="system-autonomous",
                    query="Query 3",
                    tier_used="local",
                    cost_usd=0.75,
                    timestamp=yesterday,
                    latency_ms=120,
                    confidence=0.92,
                ),
                RoutingDecision(
                    id="decision4",
                    user_id="system-autonomous",
                    query="Query 4",
                    tier_used="frontier",
                    cost_usd=2.00,
                    timestamp=two_days_ago,
                    latency_ms=300,
                    confidence=0.88,
                ),
            ]
        )
        db_session.commit()

        summary = resource_manager.get_autonomous_budget_summary(days=7)

        assert summary["days"] == 7
        assert summary["total_cost_usd"] == 4.25
        assert summary["total_requests"] == 4
        assert summary["average_cost_per_day"] == pytest.approx(4.25 / 7)
        assert len(summary["daily_breakdown"]) == 3  # 3 distinct days

    def test_record_autonomous_cost_logging(self, resource_manager, caplog):
        """Test autonomous cost recording logs correctly."""
        import logging

        caplog.set_level(logging.INFO)

        resource_manager.record_autonomous_cost(
            cost_usd=Decimal("0.50"),
            user_id="system-autonomous",
            description="Test autonomous operation",
        )

        assert "Autonomous work cost recorded" in caplog.text
        assert "$0.5000" in caplog.text
        assert "Test autonomous operation" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
