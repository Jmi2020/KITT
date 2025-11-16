"""
Safety Layer for Research Tools

Integrates I/O Control and Permission Manager to ensure safe external API usage.
Prevents unauthorized/expensive API calls in autonomous research.
"""

import logging
import os
from typing import Optional, Dict, Any
from decimal import Decimal

try:
    from common.io_control import get_tool_availability, feature_registry
    from common.io_control.state_manager import FeatureStateManager
    IO_CONTROL_AVAILABLE = True
except ImportError:
    IO_CONTROL_AVAILABLE = False
    feature_registry = None
    FeatureStateManager = None

try:
    from brain.routing.permission import PermissionManager
    PERMISSION_MANAGER_AVAILABLE = True
except ImportError:
    PERMISSION_MANAGER_AVAILABLE = False
    PermissionManager = None

logger = logging.getLogger(__name__)


class ToolSafetyChecker:
    """
    Checks if research tools are safe to use based on I/O Control settings.

    Prevents:
    - Using external APIs when offline mode enabled
    - Using Perplexity when API key not configured or feature disabled
    - Using paid APIs when cloud routing disabled
    - Budget overruns
    """

    def __init__(self, state_manager: Optional[Any] = None):
        """
        Initialize safety checker.

        Args:
            state_manager: Optional FeatureStateManager instance
        """
        if state_manager is None and IO_CONTROL_AVAILABLE and FeatureStateManager:
            # Try to create state manager with Redis
            try:
                import redis
                redis_client = redis.Redis(
                    host=os.getenv("REDIS_HOST", "redis"),
                    port=int(os.getenv("REDIS_PORT", "6379")),
                    db=0,
                    decode_responses=False
                )
                redis_client.ping()
                state_manager = FeatureStateManager(redis_client=redis_client)
            except Exception as exc:
                logger.warning(f"Could not connect to Redis for I/O control: {exc}")
                state_manager = None

        self.state_manager = state_manager

    def get_feature_state(self) -> Dict[str, Any]:
        """
        Get current feature state from I/O Control.

        Returns:
            Dict with feature flags:
            - perplexity_enabled: bool
            - offline_mode: bool
            - cloud_routing_enabled: bool
            - openai_enabled: bool
            - anthropic_enabled: bool
        """
        if not self.state_manager or not IO_CONTROL_AVAILABLE:
            # Fallback to env vars if I/O control not available
            return {
                "perplexity_enabled": bool(os.getenv("PERPLEXITY_API_KEY")),
                "offline_mode": os.getenv("OFFLINE_MODE", "false").lower() == "true",
                "cloud_routing_enabled": os.getenv("OFFLINE_MODE", "false").lower() != "true",
                "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
                "anthropic_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
            }

        try:
            current_state = self.state_manager.get_current_state()

            return {
                "perplexity_enabled": bool(current_state.get("perplexity_api")),
                "offline_mode": current_state.get("offline_mode", False),
                "cloud_routing_enabled": current_state.get("cloud_routing", True),
                "openai_enabled": bool(current_state.get("openai_api")),
                "anthropic_enabled": bool(current_state.get("anthropic_api")),
            }
        except Exception as exc:
            logger.error(f"Error getting feature state: {exc}")
            # Fallback to restrictive defaults
            return {
                "perplexity_enabled": False,
                "offline_mode": True,
                "cloud_routing_enabled": False,
                "openai_enabled": False,
                "anthropic_enabled": False,
            }

    def can_use_external_api(self, provider: str) -> tuple[bool, str]:
        """
        Check if external API can be used.

        Args:
            provider: API provider (perplexity, openai, anthropic)

        Returns:
            (allowed, reason) tuple
        """
        state = self.get_feature_state()

        # Check offline mode
        if state["offline_mode"]:
            return False, "Offline mode enabled (I/O Control)"

        # Check cloud routing
        if not state["cloud_routing_enabled"]:
            return False, "Cloud routing disabled (I/O Control)"

        # Check provider-specific flags
        if provider == "perplexity":
            if not state["perplexity_enabled"]:
                return False, "Perplexity API disabled or not configured (I/O Control)"
        elif provider == "openai":
            if not state["openai_enabled"]:
                return False, "OpenAI API disabled or not configured (I/O Control)"
        elif provider == "anthropic":
            if not state["anthropic_enabled"]:
                return False, "Anthropic API disabled or not configured (I/O Control)"

        return True, ""


class ResearchPermissionManager:
    """
    Wrapper around PermissionManager for research-specific permission handling.

    Extends base PermissionManager with:
    - Research session budget tracking
    - I/O Control integration
    - Configurable auto-approve for autonomous research
    """

    def __init__(
        self,
        session_id: str,
        max_budget: Decimal = Decimal("2.0"),
        max_external_calls: int = 10,
        auto_approve: bool = False,
        base_permission_manager: Optional[Any] = None
    ):
        """
        Initialize research permission manager.

        Args:
            session_id: Research session ID
            max_budget: Maximum budget for this session
            max_external_calls: Maximum external API calls allowed
            auto_approve: Auto-approve external calls (for autonomous mode)
            base_permission_manager: Optional base PermissionManager instance
        """
        self.session_id = session_id
        self.max_budget = max_budget
        self.max_external_calls = max_external_calls
        self.auto_approve = auto_approve

        # Budget tracking
        self.total_cost = Decimal("0.0")
        self.external_calls_used = 0

        # Safety checker
        self.safety_checker = ToolSafetyChecker()

        # Base permission manager (for omega password if not auto-approve)
        if base_permission_manager is None and PERMISSION_MANAGER_AVAILABLE:
            self.base_manager = PermissionManager(auto_approve=auto_approve)
        else:
            self.base_manager = base_permission_manager

    async def request_permission(
        self,
        tier: str,
        provider: str,
        estimated_cost: float,
        reason: str,
        conversation_id: str
    ) -> bool:
        """
        Request permission for external API call.

        Checks:
        1. I/O Control feature flags
        2. Budget limits
        3. External call limits
        4. Omega password (if not auto-approve)

        Args:
            tier: Routing tier (mcp, frontier)
            provider: Provider name (perplexity, openai, anthropic)
            estimated_cost: Estimated cost in USD
            reason: Reason for API call
            conversation_id: Conversation ID

        Returns:
            True if approved, False otherwise
        """
        # Check I/O Control
        can_use, block_reason = self.safety_checker.can_use_external_api(provider)
        if not can_use:
            logger.warning(f"API call blocked: {block_reason}")
            return False

        # Check budget
        if self.total_cost + Decimal(str(estimated_cost)) > self.max_budget:
            logger.warning(
                f"Budget exceeded: ${self.total_cost} + ${estimated_cost} > ${self.max_budget}"
            )
            return False

        # Check external call limit
        if self.external_calls_used >= self.max_external_calls:
            logger.warning(
                f"External call limit reached: {self.external_calls_used}/{self.max_external_calls}"
            )
            return False

        # If auto-approve enabled, approve immediately
        if self.auto_approve:
            logger.info(
                f"Auto-approving {provider} API call (${estimated_cost}) - "
                f"Budget: ${self.total_cost + Decimal(str(estimated_cost))}/{self.max_budget}"
            )
            return True

        # Otherwise, use base permission manager (omega password)
        if self.base_manager:
            return await self.base_manager.request_permission(
                tier=tier,
                provider=provider,
                estimated_cost=estimated_cost,
                reason=reason,
                conversation_id=conversation_id
            )

        # No permission manager available, deny by default
        logger.warning("No permission manager available, denying by default")
        return False

    def record_actual_cost(self, actual_cost: float):
        """Record actual cost after API call"""
        self.total_cost += Decimal(str(actual_cost))
        self.external_calls_used += 1

        logger.info(
            f"Recorded API cost: ${actual_cost} "
            f"(Total: ${self.total_cost}/{self.max_budget}, "
            f"Calls: {self.external_calls_used}/{self.max_external_calls})"
        )

    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        return {
            "total_cost": float(self.total_cost),
            "budget_limit": float(self.max_budget),
            "budget_remaining": float(self.max_budget - self.total_cost),
            "external_calls_used": self.external_calls_used,
            "external_calls_remaining": self.max_external_calls - self.external_calls_used,
        }
