"""Prometheus metrics for KITTY brain service."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from common.logging import get_logger

LOGGER = get_logger(__name__)

router = APIRouter(tags=["metrics"])

ROUTING_REQUESTS = Counter(
    "kitty_routing_requests_total",
    "Total routing decisions by tier",
    labelnames=("tier",),
)

ROUTING_LATENCY = Histogram(
    "kitty_routing_latency_ms",
    "Routing latency in milliseconds",
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)

ROUTING_COST = Counter(
    "kitty_routing_cost_total",
    "Accumulated routing cost by tier",
    labelnames=("tier",),
)

LOCAL_HANDLED_RATIO = Gauge(
    "kitty_routing_local_ratio",
    "Rolling ratio of requests handled locally",
)


def record_decision(
    *, tier: str, latency_ms: int, cost: float, local_ratio: Optional[float] = None
) -> None:
    ROUTING_REQUESTS.labels(tier=tier).inc()
    ROUTING_LATENCY.observe(latency_ms)
    ROUTING_COST.labels(tier=tier).inc(cost)
    if local_ratio is not None:
        LOCAL_HANDLED_RATIO.set(local_ratio)


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
