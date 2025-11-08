"""Tests for /api/autonomy endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from brain.app import app
from brain.autonomous.resource_manager import (
    AutonomousWorkload,
    ResourceStatus,
)
from brain.routes import autonomy as autonomy_routes


class StubResourceManager:
    def __init__(self):
        self.last_workload = None
        self.budget_days = None

    def get_status(self, *, workload=AutonomousWorkload.scheduled, **_) -> ResourceStatus:
        self.last_workload = workload
        return ResourceStatus(
            budget_available=Decimal("4.50"),
            budget_used_today=Decimal("0.50"),
            is_idle=True,
            cpu_usage_percent=15.0,
            memory_usage_percent=55.0,
            gpu_available=True,
            can_run_autonomous=True,
            reason="Ready: $4.50 available",
            workload=workload,
        )

    def get_autonomous_budget_summary(self, days: int = 7, **_) -> dict:
        self.budget_days = days
        return {
            "days": days,
            "daily_breakdown": [
                {"date": "2025-11-06", "cost_usd": 0.5, "requests": 1},
            ],
            "total_cost_usd": 0.5,
            "total_requests": 1,
            "average_cost_per_day": 0.5 / days,
            "budget_limit_per_day": 5.0,
        }


@pytest.fixture
def client():
    return TestClient(app)


def test_autonomy_status_endpoint_supports_workloads(client):
    stub = StubResourceManager()
    app.dependency_overrides[autonomy_routes.get_resource_manager] = lambda: stub
    try:
        response = client.get("/api/autonomy/status?workload=exploration")
    finally:
        app.dependency_overrides.pop(autonomy_routes.get_resource_manager, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["workload"] == "exploration"
    assert payload["budget_available"] == pytest.approx(4.5)
    assert stub.last_workload == AutonomousWorkload.exploration


def test_autonomy_budget_endpoint_respects_days(client):
    stub = StubResourceManager()
    app.dependency_overrides[autonomy_routes.get_resource_manager] = lambda: stub
    try:
        response = client.get("/api/autonomy/budget?days=3")
    finally:
        app.dependency_overrides.pop(autonomy_routes.get_resource_manager, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["days"] == 3
    assert stub.budget_days == 3
    assert payload["daily_breakdown"][0]["cost_usd"] == 0.5
