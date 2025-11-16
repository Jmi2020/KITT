"""
Unit tests for UnifiedPermissionGate

Tests the 3-layer permission hierarchy:
1. I/O Control (hard gate) - Is provider enabled?
2. Budget (hard gate) - Can we afford it?
3. Runtime Approval (soft gate) - Smart cost-based gating
"""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

from brain.research.permissions import UnifiedPermissionGate, PermissionResult, ApprovalTier
from brain.research.models.budget import BudgetManager, BudgetConfig


class MockIOControlStateManager:
    """Mock FeatureStateManager for testing"""

    def __init__(self, state: dict):
        self.state = state

    def get_current_state(self):
        return self.state


class TestUnifiedPermissionGate:
    """Test suite for UnifiedPermissionGate"""

    @pytest.fixture
    def mock_io_control_enabled(self):
        """I/O Control with all providers enabled"""
        return MockIOControlStateManager({
            "perplexity_api": True,
            "openai_api": True,
            "anthropic_api": True,
            "offline_mode": False,
            "cloud_routing": True,
        })

    @pytest.fixture
    def mock_io_control_disabled(self):
        """I/O Control with providers disabled"""
        return MockIOControlStateManager({
            "perplexity_api": False,
            "openai_api": False,
            "anthropic_api": False,
            "offline_mode": True,
            "cloud_routing": False,
        })

    @pytest_asyncio.fixture
    async def mock_budget_manager(self):
        """Budget manager with available budget"""
        config = BudgetConfig(
            max_total_cost_usd=Decimal("2.0"),
            max_external_calls=10
        )
        return BudgetManager(config=config)

    @pytest_asyncio.fixture
    async def mock_budget_manager_depleted(self):
        """Budget manager with depleted budget"""
        config = BudgetConfig(
            max_total_cost_usd=Decimal("0.001"),  # Almost nothing
            max_external_calls=0
        )
        manager = BudgetManager(config=config)
        # Record a call to deplete budget
        await manager.record_call(
            model_id="test",
            cost_usd=Decimal("0.001"),
            success=True
        )
        return manager

    # ===== Layer 1: I/O Control Tests =====

    def test_check_io_control_enabled(self, mock_io_control_enabled):
        """Test I/O Control check when provider is enabled"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_enabled,
            budget_manager=None
        )

        allowed, reason = gate.check_io_control("perplexity")
        assert allowed is True
        assert reason == ""

    def test_check_io_control_disabled(self, mock_io_control_disabled):
        """Test I/O Control check when provider is disabled"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_disabled,
            budget_manager=None
        )

        allowed, reason = gate.check_io_control("perplexity")
        assert allowed is False
        assert "offline mode" in reason.lower()

    def test_check_io_control_specific_provider_disabled(self):
        """Test I/O Control when specific provider is disabled"""
        io_control = MockIOControlStateManager({
            "perplexity_api": False,  # Disabled
            "openai_api": True,
            "anthropic_api": True,
            "offline_mode": False,
            "cloud_routing": True,
        })

        gate = UnifiedPermissionGate(
            io_control_state_manager=io_control,
            budget_manager=None
        )

        # Perplexity should be blocked
        allowed, reason = gate.check_io_control("perplexity")
        assert allowed is False
        assert "perplexity" in reason.lower()

        # OpenAI should be allowed
        allowed, reason = gate.check_io_control("openai")
        assert allowed is True

    def test_check_io_control_no_state_manager(self):
        """Test I/O Control fallback when no state manager"""
        with patch.dict('os.environ', {'PERPLEXITY_API_KEY': 'test_key'}):
            gate = UnifiedPermissionGate(
                io_control_state_manager=None,
                budget_manager=None
            )

            allowed, reason = gate.check_io_control("perplexity")
            assert allowed is True  # Should allow with API key present

    # ===== Layer 2: Budget Tests =====

    @pytest.mark.asyncio
    async def test_check_budget_sufficient(self, mock_budget_manager):
        """Test budget check with sufficient funds"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=None,
            budget_manager=mock_budget_manager
        )

        allowed, reason = await gate._check_budget(Decimal("0.10"))
        assert allowed is True
        assert reason == ""

    @pytest.mark.asyncio
    async def test_check_budget_insufficient(self, mock_budget_manager_depleted):
        """Test budget check with insufficient funds"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=None,
            budget_manager=mock_budget_manager_depleted
        )

        allowed, reason = await gate._check_budget(Decimal("0.10"))
        assert allowed is False
        assert "budget exceeded" in reason.lower()

    @pytest.mark.asyncio
    async def test_check_budget_no_manager(self):
        """Test budget check without budget manager"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=None,
            budget_manager=None
        )

        allowed, reason = await gate._check_budget(Decimal("0.10"))
        assert allowed is True  # Should allow when no budget manager

    # ===== Layer 3: Runtime Approval Tests =====

    def test_determine_approval_tier_trivial(self):
        """Test approval tier determination for trivial cost"""
        gate = UnifiedPermissionGate()

        tier = gate._determine_approval_tier(Decimal("0.005"))  # < $0.01
        assert tier == ApprovalTier.TRIVIAL

    def test_determine_approval_tier_low(self):
        """Test approval tier determination for low cost"""
        gate = UnifiedPermissionGate()

        tier = gate._determine_approval_tier(Decimal("0.05"))  # < $0.10
        assert tier == ApprovalTier.LOW

    def test_determine_approval_tier_high(self):
        """Test approval tier determination for high cost"""
        gate = UnifiedPermissionGate()

        tier = gate._determine_approval_tier(Decimal("0.15"))  # >= $0.10
        assert tier == ApprovalTier.HIGH

    @pytest.mark.asyncio
    async def test_runtime_approval_trivial_auto_approve(self):
        """Test trivial cost auto-approval"""
        gate = UnifiedPermissionGate(
            auto_approve_trivial=True
        )

        result = await gate._check_runtime_approval(
            "perplexity",
            Decimal("0.005"),
            ApprovalTier.TRIVIAL
        )

        assert result.approved is True
        assert "auto-approved" in result.reason.lower()
        assert result.prompt_user is False

    @pytest.mark.asyncio
    async def test_runtime_approval_low_auto_approve(self):
        """Test low cost auto-approval when enabled"""
        gate = UnifiedPermissionGate(
            auto_approve_low_cost=True
        )

        result = await gate._check_runtime_approval(
            "perplexity",
            Decimal("0.05"),
            ApprovalTier.LOW
        )

        assert result.approved is True
        assert "auto-approved" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_runtime_approval_low_prompt(self):
        """Test low cost prompting when auto-approve disabled"""
        gate = UnifiedPermissionGate(
            auto_approve_low_cost=False
        )

        result = await gate._check_runtime_approval(
            "perplexity",
            Decimal("0.05"),
            ApprovalTier.LOW
        )

        assert result.approved is False
        assert result.prompt_user is True
        assert result.prompt_message is not None
        assert "omega" in result.prompt_message.lower()

    @pytest.mark.asyncio
    async def test_runtime_approval_high_always_prompt(self):
        """Test high cost always requires prompt"""
        gate = UnifiedPermissionGate(
            auto_approve_trivial=True,
            auto_approve_low_cost=True
        )

        result = await gate._check_runtime_approval(
            "perplexity",
            Decimal("0.15"),
            ApprovalTier.HIGH
        )

        assert result.approved is False
        assert result.prompt_user is True
        assert "high-cost" in result.reason.lower()

    # ===== Full Permission Check Tests =====

    @pytest.mark.asyncio
    async def test_check_permission_full_flow_approved(
        self,
        mock_io_control_enabled,
        mock_budget_manager
    ):
        """Test complete permission check - approved"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_enabled,
            budget_manager=mock_budget_manager,
            auto_approve_trivial=True
        )

        result = await gate.check_permission(
            provider="perplexity",
            estimated_cost=Decimal("0.005"),  # Trivial
            context={"session_id": "test"}
        )

        assert result.approved is True
        assert result.provider == "perplexity"
        assert result.approval_tier == ApprovalTier.TRIVIAL

    @pytest.mark.asyncio
    async def test_check_permission_io_control_blocked(
        self,
        mock_io_control_disabled,
        mock_budget_manager
    ):
        """Test permission check - blocked by I/O Control"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_disabled,
            budget_manager=mock_budget_manager
        )

        result = await gate.check_permission(
            provider="perplexity",
            estimated_cost=Decimal("0.005"),
            context={}
        )

        assert result.approved is False
        assert result.prompt_user is False  # Hard block
        assert "offline mode" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_permission_budget_blocked(
        self,
        mock_io_control_enabled,
        mock_budget_manager_depleted
    ):
        """Test permission check - blocked by budget"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_enabled,
            budget_manager=mock_budget_manager_depleted
        )

        result = await gate.check_permission(
            provider="perplexity",
            estimated_cost=Decimal("0.10"),
            context={}
        )

        assert result.approved is False
        assert result.prompt_user is False  # Hard block
        assert "budget" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_check_permission_prompt_required(
        self,
        mock_io_control_enabled,
        mock_budget_manager
    ):
        """Test permission check - prompt required for low cost"""
        gate = UnifiedPermissionGate(
            io_control_state_manager=mock_io_control_enabled,
            budget_manager=mock_budget_manager,
            auto_approve_low_cost=False
        )

        result = await gate.check_permission(
            provider="perplexity",
            estimated_cost=Decimal("0.05"),  # Low cost
            context={}
        )

        assert result.approved is False
        assert result.prompt_user is True  # Soft block - can prompt
        assert result.approval_tier == ApprovalTier.LOW

    # ===== User Prompting Tests =====

    @pytest.mark.asyncio
    async def test_prompt_user_for_approval_correct_password(self, mock_budget_manager):
        """Test user prompt with correct omega password"""
        gate = UnifiedPermissionGate(
            budget_manager=mock_budget_manager,
            omega_password="test_omega"
        )

        permission_result = PermissionResult(
            approved=False,
            reason="Test",
            prompt_user=True,
            prompt_message="Enter password: ",
            provider="perplexity",
            estimated_cost=Decimal("0.05")
        )

        with patch('builtins.input', return_value="test_omega"):
            approved = await gate.prompt_user_for_approval(permission_result)

        assert approved is True

    @pytest.mark.asyncio
    async def test_prompt_user_for_approval_wrong_password(self, mock_budget_manager):
        """Test user prompt with wrong password"""
        gate = UnifiedPermissionGate(
            budget_manager=mock_budget_manager,
            omega_password="test_omega"
        )

        permission_result = PermissionResult(
            approved=False,
            reason="Test",
            prompt_user=True,
            prompt_message="Enter password: ",
            provider="perplexity",
            estimated_cost=Decimal("0.05")
        )

        with patch('builtins.input', return_value="wrong_password"):
            approved = await gate.prompt_user_for_approval(permission_result)

        assert approved is False

    # ===== Cost Recording Tests =====

    def test_record_actual_cost_with_budget_manager(self, mock_budget_manager):
        """Test cost recording with budget manager"""
        gate = UnifiedPermissionGate(
            budget_manager=mock_budget_manager
        )

        # Should not raise exception
        gate.record_actual_cost(Decimal("0.005"), "perplexity")

    def test_record_actual_cost_without_budget_manager(self):
        """Test cost recording without budget manager"""
        gate = UnifiedPermissionGate(
            budget_manager=None
        )

        # Should not raise exception, just log warning
        gate.record_actual_cost(Decimal("0.005"), "perplexity")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
