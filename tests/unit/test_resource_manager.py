"""Unit tests for the autonomous ResourceManager."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Callable
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import Session, sessionmaker

from common.db.models import (
    Base,
    ConversationSession,
    RoutingDecision,
    RoutingTier,
    User,
)
from brain.autonomous.resource_manager import (
    AutonomousWorkload,
    ResourceManager,
)

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    def visit_JSONB(self, type_, **_):
        return "TEXT"

    SQLiteTypeCompiler.visit_JSONB = visit_JSONB  # type: ignore[attr-defined]

AUTONOMY_USER_ID = "system-autonomous"
HUMAN_USER_ID = "00000000-1111-2222-3333-444444444444"
CONVERSATION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture(scope="function")
def session_factory() -> Callable[[], Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal


@pytest.fixture(autouse=True)
def seed_base(session_factory: Callable[[], Session]) -> None:
    session = session_factory()
    session.add_all(
        [
            User(
                id=HUMAN_USER_ID,
                display_name="Operator",
                email="operator@example.com",
                roles=["operator"],
            ),
            User(
                id=AUTONOMY_USER_ID,
                display_name="KITTY Autonomy",
                email="autonomy@example.com",
                roles=["autonomy"],
            ),
            ConversationSession(
                id=CONVERSATION_ID,
                context_key="autonomy-test",
                state={},
                active_participants=[],
            ),
        ]
    )
    session.commit()
    session.close()


@pytest.fixture(autouse=True)
def patch_psutil(monkeypatch):
    monkeypatch.setattr(
        "brain.autonomous.resource_manager.psutil.cpu_percent",
        lambda interval=1: 12.5,
    )
    monkeypatch.setattr(
        "brain.autonomous.resource_manager.psutil.virtual_memory",
        lambda: SimpleNamespace(percent=48.0),
    )


@pytest.fixture
def metrics_spy():
    calls = []

    def _spy(status):
        calls.append(status)

    return calls, _spy


@pytest.fixture
def resource_manager(session_factory, metrics_spy):
    _, spy = metrics_spy
    return ResourceManager(
        session_factory=session_factory,
        daily_budget=Decimal("5.00"),
        idle_threshold_minutes=60,
        cpu_threshold_percent=30.0,
        memory_threshold_percent=80.0,
        autonomous_user_id=AUTONOMY_USER_ID,
        metrics_callback=spy,
    )


def insert_decision(
    session_factory: Callable[[], Session],
    *,
    user_id: str,
    cost: float,
    minutes_ago: int = 0,
) -> None:
    session = session_factory()
    session.add(
        RoutingDecision(
            id=str(uuid4()),
            conversation_id=CONVERSATION_ID,
            request_id=str(uuid4()),
            selected_tier=RoutingTier.local,
            confidence=0.95,
            latency_ms=150,
            cost_estimate=Decimal(str(cost)),
            created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
            user_id=user_id,
        )
    )
    session.commit()
    session.close()


class TestBudgetTracking:
    def test_budget_used_today_filters_autonomy(self, session_factory, resource_manager):
        insert_decision(session_factory, user_id=AUTONOMY_USER_ID, cost=0.50)
        insert_decision(session_factory, user_id=HUMAN_USER_ID, cost=1.00)

        session = session_factory()
        try:
            spent = resource_manager._get_budget_used_today(session, AUTONOMY_USER_ID)
        finally:
            session.close()

        assert spent == Decimal("0.50")


class TestIdleDetection:
    def test_idle_excludes_autonomy_activity(self, session_factory, resource_manager):
        insert_decision(session_factory, user_id=AUTONOMY_USER_ID, cost=0.05, minutes_ago=5)

        session = session_factory()
        try:
            is_idle = resource_manager._is_system_idle(
                session, AUTONOMY_USER_ID, AutonomousWorkload.scheduled
            )
        finally:
            session.close()

        assert is_idle is True

    def test_idle_respects_recent_user_activity(self, session_factory, resource_manager):
        insert_decision(session_factory, user_id=HUMAN_USER_ID, cost=0.05, minutes_ago=5)

        status = resource_manager.get_status()

        assert status.is_idle is False
        assert status.can_run_autonomous is False
        assert "not idle" in status.reason.lower()


class TestStatusEvaluation:
    def test_status_ready_updates_metrics(self, resource_manager, metrics_spy):
        calls, _ = metrics_spy

        status = resource_manager.get_status()

        assert status.can_run_autonomous is True
        assert calls, "metrics callback should be invoked"

    def test_budget_exhausted_blocks_autonomy(self, session_factory, resource_manager):
        insert_decision(session_factory, user_id=AUTONOMY_USER_ID, cost=5.00)

        status = resource_manager.get_status()

        assert status.can_run_autonomous is False
        assert "budget" in status.reason.lower()

    def test_exploration_requires_longer_idle_window(self, session_factory):
        manager = ResourceManager(
            session_factory=session_factory,
            daily_budget=Decimal("5.00"),
            idle_threshold_minutes=60,
            cpu_threshold_percent=30.0,
            memory_threshold_percent=80.0,
            autonomous_user_id=AUTONOMY_USER_ID,
        )

        insert_decision(session_factory, user_id=HUMAN_USER_ID, cost=0.05, minutes_ago=90)

        scheduled_status = manager.get_status(workload=AutonomousWorkload.scheduled)
        exploration_status = manager.get_status(workload=AutonomousWorkload.exploration)

        assert scheduled_status.is_idle is True
        assert exploration_status.is_idle is False
        assert "not idle" in exploration_status.reason.lower()

    def test_gpu_unavailable_blocks_autonomy(self, monkeypatch, resource_manager):
        monkeypatch.setattr(
            "brain.autonomous.resource_manager.ResourceManager._check_gpu_available",
            lambda self: False,
        )

        status = resource_manager.get_status()

        assert status.can_run_autonomous is False
        assert "gpu" in status.reason.lower()


class TestBudgetSummary:
    def test_budget_summary_groups_days(self, session_factory, resource_manager):
        insert_decision(session_factory, user_id=AUTONOMY_USER_ID, cost=1.00, minutes_ago=10)
        insert_decision(
            session_factory,
            user_id=AUTONOMY_USER_ID,
            cost=2.00,
            minutes_ago=60 * 24 + 10,
        )

        summary = resource_manager.get_autonomous_budget_summary(days=3)

        assert summary["days"] == 3
        assert summary["total_cost_usd"] == pytest.approx(3.0)
        assert summary["total_requests"] == 2
        assert len(summary["daily_breakdown"]) == 2
