"""Prometheus metrics for KITTY brain service."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from common.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..autonomous.resource_manager import ResourceStatus

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

AUTONOMY_BUDGET_AVAILABLE = Gauge(
    "kitty_autonomy_budget_available_usd",
    "Daily budget remaining for autonomous work",
)

AUTONOMY_BUDGET_USED = Gauge(
    "kitty_autonomy_budget_used_today_usd",
    "Budget spent today on autonomous work",
)

AUTONOMY_IDLE_STATE = Gauge(
    "kitty_autonomy_idle_state",
    "Whether KITTY is idle enough to run autonomy (1 idle, 0 busy)",
)

AUTONOMY_CPU_USAGE = Gauge(
    "kitty_autonomy_cpu_percent",
    "CPU usage observed when evaluating autonomy eligibility",
)

AUTONOMY_MEMORY_USAGE = Gauge(
    "kitty_autonomy_memory_percent",
    "Memory usage observed when evaluating autonomy eligibility",
)

AUTONOMY_GPU_AVAILABLE = Gauge(
    "kitty_autonomy_gpu_available",
    "GPU availability for autonomous workloads (1 available, 0 unavailable)",
)

AUTONOMY_CAN_RUN = Gauge(
    "kitty_autonomy_ready_state",
    "Whether KITTY can run autonomous work (1 ready, 0 blocked)",
    labelnames=("workload",),
)


def record_decision(
    *, tier: str, latency_ms: int, cost: float, local_ratio: Optional[float] = None
) -> None:
    ROUTING_REQUESTS.labels(tier=tier).inc()
    ROUTING_LATENCY.observe(latency_ms)
    ROUTING_COST.labels(tier=tier).inc(cost)
    if local_ratio is not None:
        LOCAL_HANDLED_RATIO.set(local_ratio)


def record_autonomy_status(status: "ResourceStatus") -> None:
    """Push resource manager status into Prometheus gauges."""
    AUTONOMY_BUDGET_AVAILABLE.set(float(status.budget_available))
    AUTONOMY_BUDGET_USED.set(float(status.budget_used_today))
    AUTONOMY_IDLE_STATE.set(1 if status.is_idle else 0)
    AUTONOMY_CPU_USAGE.set(status.cpu_usage_percent)
    AUTONOMY_MEMORY_USAGE.set(status.memory_usage_percent)
    AUTONOMY_GPU_AVAILABLE.set(1 if status.gpu_available else 0)
    AUTONOMY_CAN_RUN.labels(workload=status.workload.value).set(
        1 if status.can_run_autonomous else 0
    )


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
