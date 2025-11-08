"""Resource manager for autonomous operations.

Tracks budget usage, detects idle periods, and enforces constraints to enable
bounded autonomy for KITTY's self-directed work.
"""

from __future__ import annotations

import logging
import platform
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Callable, Iterator, Optional, Tuple

import psutil
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.db.models import RoutingDecision

logger = logging.getLogger(__name__)


class AutonomousWorkload(str, Enum):
    """Types of autonomous work KITTY can run."""

    scheduled = "scheduled"
    exploration = "exploration"


WORKLOAD_IDLE_MULTIPLIERS = {
    AutonomousWorkload.scheduled: 1,
    AutonomousWorkload.exploration: 2,
}


@dataclass
class ResourceStatus:
    """Current resource availability status for autonomous work."""

    budget_available: Decimal
    budget_used_today: Decimal
    is_idle: bool
    cpu_usage_percent: float
    memory_usage_percent: float
    gpu_available: bool
    can_run_autonomous: bool
    reason: str
    workload: AutonomousWorkload


class ResourceManager:
    """Manages resources for autonomous operations.

    Responsibilities:
    - Track daily budget usage across all routing tiers
    - Detect idle system periods (low CPU/memory, no recent user requests)
    - Monitor resource availability (CPU, memory, GPU)
    - Enforce budget constraints before allowing autonomous work
    - Provide resource status for scheduling decisions

    Configuration:
    - daily_budget: Maximum USD spend per day (default: $5.00)
    - idle_threshold_minutes: Minutes without user activity to consider idle (default: 120)
    - cpu_threshold_percent: Max CPU usage to consider idle (default: 20%)
    - memory_threshold_percent: Max memory usage to consider idle (default: 70%)
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        daily_budget: Decimal = Decimal("5.00"),
        idle_threshold_minutes: int = 120,
        cpu_threshold_percent: float = 20.0,
        memory_threshold_percent: float = 70.0,
        autonomous_user_id: str = "system-autonomous",
        metrics_callback: Optional[Callable[[ResourceStatus], None]] = None,
    ):
        """Initialize the resource manager.

        Args:
            session_factory: Callable that returns a SQLAlchemy session
            daily_budget: Maximum USD spend per day for autonomous work
            idle_threshold_minutes: Minutes without user activity to consider idle
            cpu_threshold_percent: Maximum CPU usage % to consider idle
            memory_threshold_percent: Maximum memory usage % to consider idle
            autonomous_user_id: User ID recorded for autonomous routing decisions
            metrics_callback: Optional callback for Prometheus/Grafana metrics
        """
        self._session_factory = session_factory
        self.daily_budget = daily_budget
        self.idle_threshold_minutes = idle_threshold_minutes
        self.cpu_threshold_percent = cpu_threshold_percent
        self.memory_threshold_percent = memory_threshold_percent
        self.autonomous_user_id = autonomous_user_id
        self.metrics_callback = metrics_callback

    @classmethod
    def from_settings(
        cls, metrics_callback: Optional[Callable[[ResourceStatus], None]] = None
    ) -> ResourceManager:
        """Factory that loads values from `.env` via common.settings`."""
        from common.config import settings
        from common.db import SessionLocal
        from ..metrics import record_autonomy_status

        callback = metrics_callback or record_autonomy_status

        return cls(
            session_factory=SessionLocal,
            daily_budget=Decimal(str(settings.autonomous_daily_budget_usd)),
            idle_threshold_minutes=settings.autonomous_idle_threshold_minutes,
            cpu_threshold_percent=settings.autonomous_cpu_threshold_percent,
            memory_threshold_percent=settings.autonomous_memory_threshold_percent,
            autonomous_user_id=settings.autonomous_user_id,
            metrics_callback=callback,
        )

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        """Provide a transactional scope for DB operations."""
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def get_status(
        self,
        *,
        workload: AutonomousWorkload = AutonomousWorkload.scheduled,
        user_id: Optional[str] = None,
        update_metrics: bool = True,
    ) -> ResourceStatus:
        """Get current resource availability status."""
        user_filter = user_id or self.autonomous_user_id

        with self._session_scope() as session:
            budget_used_today = self._get_budget_used_today(session, user_filter)
            budget_available = self.daily_budget - budget_used_today
            if budget_available < Decimal("0.00"):
                budget_available = Decimal("0.00")

            is_idle = self._is_system_idle(session, user_filter, workload)

        cpu_usage = psutil.cpu_percent(interval=1)
        memory_usage = psutil.virtual_memory().percent
        gpu_available = self._check_gpu_available()

        can_run, reason = self._can_run_autonomous(
            budget_available, is_idle, cpu_usage, memory_usage, gpu_available, workload
        )

        status = ResourceStatus(
            budget_available=budget_available,
            budget_used_today=budget_used_today,
            is_idle=is_idle,
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage,
            gpu_available=gpu_available,
            can_run_autonomous=can_run,
            reason=reason,
            workload=workload,
        )

        if update_metrics and self.metrics_callback:
            try:
                self.metrics_callback(status)
            except Exception as exc:  # pragma: no cover - metrics shouldn't break autonomy
                logger.warning("Failed to record autonomy metrics: %s", exc)

        return status

    def _get_budget_used_today(self, session: Session, user_id: Optional[str]) -> Decimal:
        """Calculate total budget used today across all routing tiers."""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        query = select(func.sum(RoutingDecision.cost_estimate)).where(
            RoutingDecision.created_at >= today_start
        )

        if user_id:
            query = query.where(RoutingDecision.user_id == user_id)

        result = session.execute(query).scalar()
        if result is None:
            return Decimal("0.00")

        return Decimal(str(result))

    def _is_system_idle(
        self,
        session: Session,
        user_id: Optional[str],
        workload: AutonomousWorkload,
    ) -> bool:
        """Determine if the system is idle (no recent user activity)."""
        idle_minutes = self._idle_threshold_for(workload)
        idle_threshold = datetime.utcnow() - timedelta(minutes=idle_minutes)

        query = select(func.count(RoutingDecision.id)).where(
            RoutingDecision.created_at >= idle_threshold
        )

        if user_id:
            query = query.where(RoutingDecision.user_id != user_id)

        recent_requests = session.execute(query).scalar()
        return recent_requests == 0

    def _idle_threshold_for(self, workload: AutonomousWorkload) -> int:
        """Adjust idle requirement by workload priority."""
        multiplier = WORKLOAD_IDLE_MULTIPLIERS.get(workload, 1)
        return int(self.idle_threshold_minutes * multiplier)

    def _check_gpu_available(self) -> bool:
        """Check if GPU is available for autonomous work."""
        try:
            if platform.system() == "Darwin":
                return True
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to check GPU availability: %s", exc)
            return False

    def _can_run_autonomous(
        self,
        budget_available: Decimal,
        is_idle: bool,
        cpu_usage: float,
        memory_usage: float,
        gpu_available: bool,
        workload: AutonomousWorkload,
    ) -> Tuple[bool, str]:
        """Determine if autonomous work can run based on all constraints."""
        if budget_available <= Decimal("0.00"):
            return False, f"Daily budget exhausted (${self.daily_budget}/day limit)"

        if not is_idle:
            idle_minutes = self._idle_threshold_for(workload)
            return False, f"System not idle (recent user activity within {idle_minutes}m)"

        if cpu_usage > self.cpu_threshold_percent:
            return (
                False,
                f"CPU usage too high ({cpu_usage:.1f}% > {self.cpu_threshold_percent}% threshold)",
            )

        if memory_usage > self.memory_threshold_percent:
            return (
                False,
                f"Memory usage too high ({memory_usage:.1f}% > {self.memory_threshold_percent}% threshold)",
            )

        if not gpu_available:
            return False, "GPU unavailable for autonomous workloads"

        return (
            True,
            f"Ready: ${budget_available:.2f} available, idle, CPU {cpu_usage:.1f}%, RAM {memory_usage:.1f}%",
        )

    def record_autonomous_cost(
        self, cost_usd: Decimal, user_id: str, description: str
    ) -> None:
        """Record cost of autonomous work for budget tracking (logging helper)."""
        logger.info("Autonomous work cost recorded: $%s - %s", cost_usd, description)

    def get_autonomous_budget_summary(
        self, days: int = 7, user_id: Optional[str] = None
    ) -> dict:
        """Get budget usage summary for recent days."""
        if days <= 0:
            raise ValueError("days must be positive")

        user_filter = user_id or self.autonomous_user_id
        start_date = datetime.utcnow() - timedelta(days=days)
        start_of_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        with self._session_scope() as session:
            query = (
                select(
                    func.date(RoutingDecision.created_at).label("date"),
                    func.sum(RoutingDecision.cost_estimate).label("cost"),
                    func.count(RoutingDecision.id).label("requests"),
                )
                .where(RoutingDecision.created_at >= start_of_day)
                .group_by(func.date(RoutingDecision.created_at))
                .order_by(func.date(RoutingDecision.created_at))
            )

            if user_filter:
                query = query.where(RoutingDecision.user_id == user_filter)

            results = session.execute(query).all()

        daily_breakdown = [
            {
                "date": str(row.date),
                "cost_usd": float(row.cost or 0.0),
                "requests": row.requests,
            }
            for row in results
        ]

        total_cost = sum(day["cost_usd"] for day in daily_breakdown)
        total_requests = sum(day["requests"] for day in daily_breakdown)

        return {
            "days": days,
            "daily_breakdown": daily_breakdown,
            "total_cost_usd": total_cost,
            "total_requests": total_requests,
            "average_cost_per_day": total_cost / days if days > 0 else 0.0,
            "budget_limit_per_day": float(self.daily_budget),
        }


__all__ = ["ResourceManager", "ResourceStatus", "AutonomousWorkload"]
