# noqa: D401
"""API permission manager with 'omega' override."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from common.db.models import RoutingTier


@dataclass
class PermissionRequest:
    """Request for permission to use online API."""

    tier: RoutingTier
    provider: str
    estimated_cost: float
    reason: str
    conversation_id: str


@dataclass
class PermissionResponse:
    """Response to permission request."""

    approved: bool
    password_provided: Optional[str] = None


# Type for permission callback
# Returns True if approved, False if denied
PermissionCallback = Callable[[PermissionRequest], PermissionResponse]


class PermissionManager:
    """Manages permission requests for online API usage.

    Requires 'omega' override password to approve API calls.
    Supports both CLI and voice approval workflows.
    """

    def __init__(
        self,
        override_password: Optional[str] = None,
        permission_callback: Optional[PermissionCallback] = None,
        auto_approve: bool = False,
    ) -> None:
        """Initialize permission manager.

        Args:
            override_password: Override password (default from env: API_OVERRIDE_PASSWORD)
            permission_callback: Async callback to request user permission
            auto_approve: If True, auto-approve all requests (for testing)
        """
        self._override_password = override_password or os.getenv("API_OVERRIDE_PASSWORD", "omega")
        self._callback = permission_callback
        self._auto_approve = auto_approve
        self._budget_used = 0.0
        self._budget_limit = float(os.getenv("BUDGET_PER_TASK_USD", "0.50"))

    def _format_permission_request(self, request: PermissionRequest) -> str:
        """Format permission request message.

        Args:
            request: Permission request

        Returns:
            Formatted message for user
        """
        return (
            f"\nAPI Permission Required\n"
            f"Provider: {request.provider} ({request.tier.value})\n"
            f"Estimated cost: ${request.estimated_cost:.4f}\n"
            f"Budget remaining: ${self._budget_limit - self._budget_used:.4f}\n"
            f"Reason: {request.reason}\n"
            f"\nEnter '{self._override_password}' to approve, or 'deny' to cancel: "
        )

    async def request_permission(
        self,
        tier: RoutingTier,
        provider: str,
        estimated_cost: float,
        reason: str,
        conversation_id: str,
    ) -> bool:
        """Request permission to use online API.

        Args:
            tier: Routing tier (mcp or frontier)
            provider: Provider name (perplexity, openai, etc.)
            estimated_cost: Estimated cost in USD
            reason: Reason for escalation (e.g., "low local confidence")
            conversation_id: Conversation ID for tracking

        Returns:
            True if approved, False if denied
        """
        # Auto-approve if enabled (for testing)
        if self._auto_approve:
            return True

        # Check budget
        if self._budget_used + estimated_cost > self._budget_limit:
            print(
                f"\n⚠️  Budget exceeded: ${self._budget_used:.4f} + ${estimated_cost:.4f} "
                f"> ${self._budget_limit:.4f}\n"
            )
            return False

        # Create request
        request = PermissionRequest(
            tier=tier,
            provider=provider,
            estimated_cost=estimated_cost,
            reason=reason,
            conversation_id=conversation_id,
        )

        # Use callback if provided
        if self._callback:
            response = self._callback(request)
            approved = response.approved and response.password_provided == self._override_password
        else:
            # Default: CLI prompt (blocking)
            message = self._format_permission_request(request)
            print(message, end="", flush=True)

            try:
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                print("\nPermission denied (interrupted)")
                return False

            approved = user_input.lower() == self._override_password.lower()

        if approved:
            self._budget_used += estimated_cost
            print(f"\n✅ API call approved. Budget used: ${self._budget_used:.4f}\n")
        else:
            print("\n❌ API call denied. Falling back to local model.\n")

        return approved

    def record_actual_cost(self, actual_cost: float) -> None:
        """Record actual cost after API call completes.

        Adjusts budget tracking based on actual vs estimated cost.

        Args:
            actual_cost: Actual cost from API response
        """
        # Adjust budget (actual cost may differ from estimate)
        self._budget_used = actual_cost

    def get_budget_status(self) -> dict[str, float]:
        """Get current budget status.

        Returns:
            Dict with 'used', 'limit', and 'remaining' amounts
        """
        return {
            "used": self._budget_used,
            "limit": self._budget_limit,
            "remaining": max(0, self._budget_limit - self._budget_used),
        }

    def reset_budget(self) -> None:
        """Reset budget tracking (e.g., new conversation)."""
        self._budget_used = 0.0


__all__ = [
    "PermissionRequest",
    "PermissionResponse",
    "PermissionCallback",
    "PermissionManager",
]
