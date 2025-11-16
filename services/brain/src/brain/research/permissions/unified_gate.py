"""
Unified Permission Gate

Single entry point for all external API permission checks.
Replaces the tangled web of PermissionManager, ResearchPermissionManager, and ToolSafetyChecker.

Three-layer hierarchy:
1. I/O Control (hard gate): Is provider enabled?
2. Budget (hard gate): Can we afford it?
3. Runtime Approval (soft gate): Smart cost-based approval
"""

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class ApprovalTier(str, Enum):
    """Approval tier based on estimated cost"""
    TRIVIAL = "trivial"      # < $0.01 - Auto-approve always
    LOW = "low"              # < $0.10 - Auto-approve if enabled
    HIGH = "high"            # >= $0.10 - Require omega password


@dataclass
class PermissionResult:
    """Result of permission check"""
    approved: bool
    reason: str

    # For user prompting
    prompt_user: bool = False
    prompt_message: Optional[str] = None

    # Metadata
    approval_tier: Optional[ApprovalTier] = None
    estimated_cost: Decimal = Decimal("0.0")
    provider: Optional[str] = None


class UnifiedPermissionGate:
    """
    Unified permission gate for external API calls.

    Consolidates all permission logic into a single, clear flow:
    1. Check I/O Control feature state
    2. Check budget availability
    3. Smart approval based on cost threshold

    Replaces:
    - PermissionManager (routing/permission.py)
    - ResearchPermissionManager (research/tools/safety.py)
    - ToolSafetyChecker (research/tools/safety.py)
    """

    def __init__(
        self,
        io_control_state_manager: Optional[Any] = None,
        budget_manager: Optional[Any] = None,
        omega_password: Optional[str] = None,
        auto_approve_trivial: bool = True,
        auto_approve_low_cost: bool = False,
    ):
        """
        Initialize unified permission gate.

        Args:
            io_control_state_manager: FeatureStateManager for I/O Control
            budget_manager: BudgetManager for cost tracking
            omega_password: Override password for high-cost calls
            auto_approve_trivial: Auto-approve calls < $0.01
            auto_approve_low_cost: Auto-approve calls < $0.10
        """
        self.io_control = io_control_state_manager
        self.budget = budget_manager
        self.omega_password = omega_password or os.getenv("API_OVERRIDE_PASSWORD", "omega")
        self.auto_approve_trivial = auto_approve_trivial
        self.auto_approve_low_cost = auto_approve_low_cost

        # Cost thresholds
        self.TRIVIAL_THRESHOLD = Decimal("0.01")
        self.LOW_COST_THRESHOLD = Decimal("0.10")

    def _get_io_control_state(self) -> Dict[str, Any]:
        """
        Get current I/O Control feature state.

        Returns:
            Dict with provider enable flags:
            - perplexity_enabled: bool
            - openai_enabled: bool
            - anthropic_enabled: bool
            - offline_mode: bool
            - cloud_routing_enabled: bool
        """
        if not self.io_control:
            # No I/O Control, check env vars as fallback
            logger.warning("I/O Control not available, using env var fallback")
            return {
                "perplexity_enabled": bool(os.getenv("PERPLEXITY_API_KEY")),
                "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
                "anthropic_enabled": bool(os.getenv("ANTHROPIC_API_KEY")),
                "offline_mode": os.getenv("OFFLINE_MODE", "false").lower() == "true",
                "cloud_routing_enabled": os.getenv("OFFLINE_MODE", "false").lower() != "true",
            }

        try:
            current_state = self.io_control.get_current_state()

            return {
                "perplexity_enabled": bool(current_state.get("perplexity_api")),
                "openai_enabled": bool(current_state.get("openai_api")),
                "anthropic_enabled": bool(current_state.get("anthropic_api")),
                "offline_mode": current_state.get("offline_mode", False),
                "cloud_routing_enabled": current_state.get("cloud_routing", True),
            }
        except Exception as exc:
            logger.error(f"Error getting I/O Control state: {exc}")
            # Fail closed - restrictive defaults
            return {
                "perplexity_enabled": False,
                "openai_enabled": False,
                "anthropic_enabled": False,
                "offline_mode": True,
                "cloud_routing_enabled": False,
            }

    def check_io_control(self, provider: str) -> tuple[bool, str]:
        """
        Layer 1: Check I/O Control (hard gate).

        This is a public method for components that need to check I/O Control
        without going through the full permission flow (e.g., model filtering
        in ModelCoordinator).

        Args:
            provider: API provider (perplexity, openai, anthropic)

        Returns:
            (allowed, reason) tuple
        """
        state = self._get_io_control_state()

        # Check offline mode
        if state["offline_mode"]:
            return False, "System in offline mode (I/O Control). All external APIs disabled."

        # Check cloud routing
        if not state["cloud_routing_enabled"]:
            return False, "Cloud routing disabled (I/O Control). External APIs not available."

        # Check provider-specific flag
        provider_key = f"{provider}_enabled"
        if provider_key in state and not state[provider_key]:
            return False, f"{provider.title()} API disabled in I/O Control. Enable in dashboard to use."

        return True, ""

    async def _check_budget(self, estimated_cost: Decimal) -> tuple[bool, str]:
        """
        Layer 2: Check budget (hard gate).

        Args:
            estimated_cost: Estimated cost of API call

        Returns:
            (allowed, reason) tuple
        """
        if not self.budget:
            # No budget manager, allow (legacy behavior)
            return True, ""

        status = await self.budget.get_status()
        budget_remaining = status.budget_remaining

        if budget_remaining < estimated_cost:
            return False, (
                f"Budget exceeded. Remaining: ${budget_remaining:.2f}, "
                f"Required: ${estimated_cost:.2f}"
            )

        return True, ""

    def _determine_approval_tier(self, estimated_cost: Decimal) -> ApprovalTier:
        """
        Determine approval tier based on cost.

        Args:
            estimated_cost: Estimated cost

        Returns:
            ApprovalTier
        """
        if estimated_cost < self.TRIVIAL_THRESHOLD:
            return ApprovalTier.TRIVIAL
        elif estimated_cost < self.LOW_COST_THRESHOLD:
            return ApprovalTier.LOW
        else:
            return ApprovalTier.HIGH

    async def _check_runtime_approval(
        self,
        provider: str,
        estimated_cost: Decimal,
        approval_tier: ApprovalTier
    ) -> PermissionResult:
        """
        Layer 3: Runtime approval (soft gate).

        Smart cost-based approval:
        - Trivial (< $0.01): Auto-approve
        - Low (< $0.10): Auto-approve if enabled, otherwise prompt
        - High (>= $0.10): Always prompt for omega password

        Args:
            provider: API provider name
            estimated_cost: Estimated cost
            approval_tier: Approval tier

        Returns:
            PermissionResult
        """
        # Get budget info for prompts
        budget_remaining_str = "N/A"
        if self.budget:
            status = await self.budget.get_status()
            budget_remaining_str = f"${status.budget_remaining:.2f}"

        if approval_tier == ApprovalTier.TRIVIAL:
            # Always auto-approve trivial costs
            if self.auto_approve_trivial:
                return PermissionResult(
                    approved=True,
                    reason=f"Auto-approved (trivial cost: ${estimated_cost:.4f})",
                    approval_tier=approval_tier,
                    estimated_cost=estimated_cost,
                    provider=provider
                )

        elif approval_tier == ApprovalTier.LOW:
            # Auto-approve if enabled
            if self.auto_approve_low_cost:
                return PermissionResult(
                    approved=True,
                    reason=f"Auto-approved (low cost: ${estimated_cost:.2f})",
                    approval_tier=approval_tier,
                    estimated_cost=estimated_cost,
                    provider=provider
                )
            else:
                # Prompt user
                return PermissionResult(
                    approved=False,
                    reason="Requires approval (low-cost call)",
                    prompt_user=True,
                    prompt_message=(
                        f"\n{'─' * 50}\n"
                        f"API Permission Required\n"
                        f"Provider: {provider.title()}\n"
                        f"Estimated cost: ${estimated_cost:.2f}\n"
                        f"Budget remaining: {budget_remaining_str}\n"
                        f"\nEnter '{self.omega_password}' to approve, or press Enter to deny: "
                    ),
                    approval_tier=approval_tier,
                    estimated_cost=estimated_cost,
                    provider=provider
                )

        else:  # HIGH
            # Always prompt for high-cost calls
            return PermissionResult(
                approved=False,
                reason="High-cost call requires approval",
                prompt_user=True,
                prompt_message=(
                    f"\n{'═' * 50}\n"
                    f"⚠️  HIGH-COST API CALL\n"
                    f"{'═' * 50}\n"
                    f"Provider: {provider.title()}\n"
                    f"Estimated cost: ${estimated_cost:.2f}\n"
                    f"Budget remaining: {budget_remaining_str}\n"
                    f"\n⚠️  This call requires explicit approval.\n"
                    f"Enter '{self.omega_password}' to approve, or press Enter to deny: "
                ),
                approval_tier=approval_tier,
                estimated_cost=estimated_cost,
                provider=provider
            )

    async def check_permission(
        self,
        provider: str,
        estimated_cost: Decimal,
        context: Optional[Dict[str, Any]] = None
    ) -> PermissionResult:
        """
        Check if external API call is permitted.

        Three-layer check:
        1. I/O Control: Is provider enabled?
        2. Budget: Can we afford it?
        3. Runtime Approval: Smart cost-based gating

        Args:
            provider: API provider (perplexity, openai, anthropic)
            estimated_cost: Estimated cost in USD
            context: Optional context dict

        Returns:
            PermissionResult with approval decision
        """
        context = context or {}

        logger.info(
            f"Permission check: {provider}, ${estimated_cost:.4f}, "
            f"context={list(context.keys())}"
        )

        # Layer 1: I/O Control (hard gate)
        io_allowed, io_reason = self.check_io_control(provider)
        if not io_allowed:
            logger.warning(f"I/O Control blocked {provider}: {io_reason}")
            return PermissionResult(
                approved=False,
                reason=io_reason,
                prompt_user=False,  # Hard block, don't prompt
                estimated_cost=estimated_cost,
                provider=provider
            )

        # Layer 2: Budget (hard gate)
        budget_allowed, budget_reason = await self._check_budget(estimated_cost)
        if not budget_allowed:
            logger.warning(f"Budget check blocked {provider}: {budget_reason}")
            return PermissionResult(
                approved=False,
                reason=budget_reason,
                prompt_user=False,  # Hard block, don't prompt
                estimated_cost=estimated_cost,
                provider=provider
            )

        # Layer 3: Runtime Approval (soft gate)
        approval_tier = self._determine_approval_tier(estimated_cost)
        result = await self._check_runtime_approval(provider, estimated_cost, approval_tier)

        logger.info(
            f"Permission result for {provider}: approved={result.approved}, "
            f"tier={approval_tier}, reason={result.reason}"
        )

        return result

    async def prompt_user_for_approval(self, permission_result: PermissionResult) -> bool:
        """
        Prompt user for omega password approval.

        Args:
            permission_result: Result from check_permission() with prompt_user=True

        Returns:
            True if user provided correct password, False otherwise
        """
        if not permission_result.prompt_user or not permission_result.prompt_message:
            return False

        try:
            print(permission_result.prompt_message, end="", flush=True)
            user_input = input().strip()

            approved = user_input.lower() == self.omega_password.lower()

            if approved:
                logger.info(
                    f"User approved {permission_result.provider} call "
                    f"(${permission_result.estimated_cost:.2f})"
                )
                print(f"✅ API call approved\n")
            else:
                logger.info(
                    f"User denied {permission_result.provider} call "
                    f"(${permission_result.estimated_cost:.2f})"
                )
                print(f"❌ API call denied. Using local models only.\n")

            return approved

        except (EOFError, KeyboardInterrupt):
            logger.info("User interrupted permission prompt")
            print("\n❌ Permission denied (interrupted)\n")
            return False

    def record_actual_cost(self, actual_cost: Decimal, provider: str):
        """
        Record actual cost after API call completes.

        Args:
            actual_cost: Actual cost from API response
            provider: Provider that was called
        """
        if self.budget:
            # Budget manager will handle recording
            logger.info(f"Recorded {provider} cost: ${actual_cost:.4f}")
        else:
            logger.warning("No budget manager available to record cost")
