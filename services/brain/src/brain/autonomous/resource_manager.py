"""Resource manager for autonomous operations.

Tracks budget usage, detects idle periods, and enforces constraints to enable
bounded autonomy for KITTY's self-directed work.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import psutil
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from common.db.models import RoutingDecision

logger = logging.getLogger(__name__)


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
    - idle_threshold_minutes: Minutes without user activity to consider idle (default: 30)
    - cpu_threshold_percent: Max CPU usage to consider idle (default: 20%)
    - memory_threshold_percent: Max memory usage to consider idle (default: 70%)
    """

    def __init__(
        self,
        db_session: Session,
        daily_budget: Decimal = Decimal("5.00"),
        idle_threshold_minutes: int = 30,
        cpu_threshold_percent: float = 20.0,
        memory_threshold_percent: float = 70.0,
    ):
        """Initialize the resource manager.

        Args:
            db_session: SQLAlchemy database session for querying routing decisions
            daily_budget: Maximum USD spend per day for autonomous work
            idle_threshold_minutes: Minutes without user activity to consider idle
            cpu_threshold_percent: Maximum CPU usage % to consider idle
            memory_threshold_percent: Maximum memory usage % to consider idle
        """
        self.db_session = db_session
        self.daily_budget = daily_budget
        self.idle_threshold_minutes = idle_threshold_minutes
        self.cpu_threshold_percent = cpu_threshold_percent
        self.memory_threshold_percent = memory_threshold_percent

    def get_status(self, user_id: Optional[str] = None) -> ResourceStatus:
        """Get current resource availability status.

        Args:
            user_id: Optional user ID to filter budget usage (default: all users)

        Returns:
            ResourceStatus with availability details and reason
        """
        # Calculate budget usage for today
        budget_used_today = self._get_budget_used_today(user_id)
        budget_available = self.daily_budget - budget_used_today

        # Check if system is idle
        is_idle = self._is_system_idle(user_id)

        # Get current resource usage
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        memory_usage = memory.percent

        # Check GPU availability (Metal on Mac)
        gpu_available = self._check_gpu_available()

        # Determine if autonomous work can run
        can_run, reason = self._can_run_autonomous(
            budget_available, is_idle, cpu_usage, memory_usage, gpu_available
        )

        return ResourceStatus(
            budget_available=budget_available,
            budget_used_today=budget_used_today,
            is_idle=is_idle,
            cpu_usage_percent=cpu_usage,
            memory_usage_percent=memory_usage,
            gpu_available=gpu_available,
            can_run_autonomous=can_run,
            reason=reason,
        )

    def _get_budget_used_today(self, user_id: Optional[str] = None) -> Decimal:
        """Calculate total budget used today across all routing tiers.

        Args:
            user_id: Optional user ID to filter (autonomous work uses system user)

        Returns:
            Total USD spent today as Decimal
        """
        # Get start of today (midnight UTC)
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # Query routing decisions from today
        query = select(func.sum(RoutingDecision.cost_usd)).where(
            RoutingDecision.timestamp >= today_start
        )

        # Filter by user if provided (for autonomous work tracking)
        if user_id:
            query = query.where(RoutingDecision.user_id == user_id)

        result = self.db_session.execute(query).scalar()

        # Handle None (no records today)
        if result is None:
            return Decimal("0.00")

        return Decimal(str(result))

    def _is_system_idle(self, user_id: Optional[str] = None) -> bool:
        """Determine if the system is idle (no recent user activity).

        Checks for user-initiated requests in the recent time window.

        Args:
            user_id: Optional user ID to exclude autonomous work from idle detection

        Returns:
            True if system has been idle for idle_threshold_minutes
        """
        # Calculate idle threshold timestamp
        idle_threshold = datetime.utcnow() - timedelta(minutes=self.idle_threshold_minutes)

        # Query for recent user requests
        query = select(func.count(RoutingDecision.id)).where(
            RoutingDecision.timestamp >= idle_threshold
        )

        # Exclude autonomous work from idle detection
        if user_id:
            query = query.where(RoutingDecision.user_id != user_id)

        recent_requests = self.db_session.execute(query).scalar()

        # System is idle if no recent user requests
        return recent_requests == 0

    def _check_gpu_available(self) -> bool:
        """Check if GPU is available for autonomous work.

        On Mac, this checks if Metal GPU is available. On Linux/Windows,
        this would check CUDA/ROCm availability.

        Returns:
            True if GPU is available and not heavily utilized
        """
        # On Mac M3 Ultra, Metal GPU is always available
        # Future: Check GPU utilization via Metal Performance Shaders (MPS)
        # For now, assume GPU is available if system is running
        try:
            # Check if we're on macOS
            import platform

            if platform.system() == "Darwin":
                return True

            # On other platforms, could check nvidia-smi or rocm-smi
            # For now, assume available
            return True
        except Exception as e:
            logger.warning(f"Failed to check GPU availability: {e}")
            return False

    def _can_run_autonomous(
        self,
        budget_available: Decimal,
        is_idle: bool,
        cpu_usage: float,
        memory_usage: float,
        gpu_available: bool,
    ) -> tuple[bool, str]:
        """Determine if autonomous work can run based on all constraints.

        Args:
            budget_available: Remaining budget for today
            is_idle: Whether system is idle
            cpu_usage: Current CPU usage percentage
            memory_usage: Current memory usage percentage
            gpu_available: Whether GPU is available

        Returns:
            Tuple of (can_run: bool, reason: str)
        """
        # Check budget constraint
        if budget_available <= Decimal("0.00"):
            return False, f"Daily budget exhausted (${self.daily_budget}/day limit)"

        # Check idle constraint
        if not is_idle:
            return False, f"System not idle (recent user activity within {self.idle_threshold_minutes}m)"

        # Check CPU constraint
        if cpu_usage > self.cpu_threshold_percent:
            return (
                False,
                f"CPU usage too high ({cpu_usage:.1f}% > {self.cpu_threshold_percent}% threshold)",
            )

        # Check memory constraint
        if memory_usage > self.memory_threshold_percent:
            return (
                False,
                f"Memory usage too high ({memory_usage:.1f}% > {self.memory_threshold_percent}% threshold)",
            )

        # All constraints satisfied
        return (
            True,
            f"Ready: ${budget_available:.2f} available, idle, CPU {cpu_usage:.1f}%, RAM {memory_usage:.1f}%",
        )

    def record_autonomous_cost(
        self, cost_usd: Decimal, user_id: str, description: str
    ) -> None:
        """Record cost of autonomous work for budget tracking.

        This is a convenience method to ensure autonomous work costs are
        properly tracked in the routing_decisions table.

        Args:
            cost_usd: Cost in USD
            user_id: System user ID for autonomous work
            description: Description of the autonomous operation
        """
        # Autonomous work is tracked through normal routing decisions
        # This is handled by the BrainRouter when autonomous work calls LLM
        logger.info(f"Autonomous work cost recorded: ${cost_usd:.4f} - {description}")

    def get_autonomous_budget_summary(self, days: int = 7) -> dict:
        """Get budget usage summary for autonomous work over recent days.

        Args:
            days: Number of days to include in summary

        Returns:
            Dict with daily breakdown and totals
        """
        # Calculate start date
        start_date = datetime.utcnow() - timedelta(days=days)
        start_of_day = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Query routing decisions grouped by day
        query = (
            select(
                func.date(RoutingDecision.timestamp).label("date"),
                func.sum(RoutingDecision.cost_usd).label("cost"),
                func.count(RoutingDecision.id).label("requests"),
            )
            .where(RoutingDecision.timestamp >= start_of_day)
            .group_by(func.date(RoutingDecision.timestamp))
            .order_by(func.date(RoutingDecision.timestamp))
        )

        results = self.db_session.execute(query).all()

        # Format results
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
