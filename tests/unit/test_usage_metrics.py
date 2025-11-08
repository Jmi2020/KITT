"""Tests for provider usage tracking metrics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from brain.app import app
from brain.usage_stats import UsageStats


@pytest.fixture(autouse=True)
def _reset_usage_stats():
    UsageStats.reset()
    yield
    UsageStats.reset()


def test_usage_stats_record_tracks_calls_and_cost():
    UsageStats.record(provider="perplexity", tier="frontier", cost=0.02)

    snapshot = UsageStats.snapshot()
    assert "perplexity" in snapshot
    entry = snapshot["perplexity"]
    assert entry["tier"] == "frontier"
    assert entry["calls"] == 1
    assert entry["total_cost"] == pytest.approx(0.02)
    assert entry["last_used"]


def test_usage_metrics_endpoint_returns_snapshot():
    UsageStats.record(provider="react_agent", tier="local", cost=0.0)

    client = TestClient(app)
    response = client.get("/api/usage/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert "react_agent" in payload
    assert payload["react_agent"]["calls"] == 1
    assert payload["react_agent"]["tier"] == "local"
