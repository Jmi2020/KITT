"""Tests for time-sensitive query detection heuristics."""

from __future__ import annotations

from brain.routing.freshness import is_time_sensitive_query


def test_detects_relative_time_keywords():
    assert is_time_sensitive_query("What is the weather today?")


def test_detects_price_with_time_word():
    assert is_time_sensitive_query("BTC price right now")


def test_detects_month_with_event_term():
    assert is_time_sensitive_query("November 2025 earnings schedule")


def test_non_time_sensitive_query_returns_false():
    assert not is_time_sensitive_query("Explain how to level a 3D printer bed")
