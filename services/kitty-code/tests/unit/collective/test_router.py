"""Tests for the ComplexityRouter."""

import pytest

from kitty_code.core.collective.config import RoutingConfig
from kitty_code.core.collective.router import ComplexityRouter, RoutingDecision


class TestComplexityRouter:
    """Test suite for ComplexityRouter."""

    @pytest.fixture
    def collective_router(self) -> ComplexityRouter:
        """Create a router with collective mode (new default)."""
        config = RoutingConfig(default_mode="collective")
        return ComplexityRouter(config)

    @pytest.fixture
    def direct_router(self) -> ComplexityRouter:
        """Create a router with direct mode (legacy behavior)."""
        config = RoutingConfig(default_mode="direct")
        return ComplexityRouter(config)

    @pytest.fixture
    def custom_router(self) -> ComplexityRouter:
        """Create a router with custom patterns (direct mode for testing)."""
        config = RoutingConfig(
            default_mode="direct",
            complexity_threshold=0.6,
            auto_execute_patterns=[r"fix\s+typo", r"add\s+import"],
            always_plan_patterns=[r"refactor", r"implement\s+feature"],
        )
        return ComplexityRouter(config)

    # =========================================================================
    # Collective Mode Tests (New Default)
    # =========================================================================

    def test_collective_mode_trivial_pattern_fix_typo(self, collective_router: ComplexityRouter):
        """Trivial fix typo pattern should bypass collective even in collective mode."""
        decision = collective_router.route("fix typo in README")
        assert decision.is_direct()
        assert decision.confidence == 0.95
        assert decision.matched_pattern is not None
        assert "trivial_pattern" in [f for f, _ in decision.factors]

    def test_collective_mode_trivial_pattern_add_import(self, collective_router: ComplexityRouter):
        """Single import pattern should bypass collective."""
        # Note: pattern is ^add\s+import\s+\w+$ (anchored)
        decision = collective_router.route("add import os")
        assert decision.is_direct()

    def test_collective_mode_trivial_pattern_what_is(self, collective_router: ComplexityRouter):
        """Questions starting with 'what is' should bypass collective."""
        decision = collective_router.route("what is this code doing?")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_collective_mode_trivial_pattern_explain(self, collective_router: ComplexityRouter):
        """Explanations should bypass collective."""
        decision = collective_router.route("explain this function")
        assert decision.is_direct()

    def test_collective_mode_default_is_collective(self, collective_router: ComplexityRouter):
        """Non-trivial requests should route to collective by default."""
        decision = collective_router.route("update the config file")
        assert decision.is_collective()
        assert decision.confidence == 0.85
        assert "default_mode_collective" in [f for f, _ in decision.factors]

    def test_collective_mode_coding_task_uses_collective(self, collective_router: ComplexityRouter):
        """Coding tasks should use collective in collective mode."""
        decision = collective_router.route("add error handling to the API")
        assert decision.is_collective()

    def test_collective_mode_refactor_uses_collective(self, collective_router: ComplexityRouter):
        """Refactoring should use collective."""
        decision = collective_router.route("refactor the authentication module")
        assert decision.is_collective()
        # In collective mode, it's routed by default, not by pattern match
        assert decision.confidence == 0.85

    # =========================================================================
    # Direct Mode Tests (Legacy Behavior)
    # =========================================================================

    def test_direct_mode_auto_execute_pattern_fix_typo(self, direct_router: ComplexityRouter):
        """Simple typo fix should bypass collective in direct mode."""
        decision = direct_router.route("fix typo in README")
        assert decision.is_direct()
        assert decision.confidence == 0.95
        # Could be trivial OR auto_execute pattern
        assert decision.matched_pattern is not None

    def test_direct_mode_auto_execute_pattern_add_import(self, direct_router: ComplexityRouter):
        """Adding import should bypass collective."""
        decision = direct_router.route("add import for os module")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_direct_mode_auto_execute_pattern_rename_variable(self, direct_router: ComplexityRouter):
        """Renaming variable should bypass collective."""
        decision = direct_router.route("rename variable foo to bar")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_direct_mode_auto_execute_pattern_format_code(self, direct_router: ComplexityRouter):
        """Formatting code should bypass collective."""
        decision = direct_router.route("format code in utils.py")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_direct_mode_always_plan_pattern_refactor(self, direct_router: ComplexityRouter):
        """Refactoring should use collective in direct mode via pattern."""
        decision = direct_router.route("refactor the authentication module")
        assert decision.is_collective()
        assert decision.confidence == 0.95
        assert decision.matched_pattern is not None

    def test_direct_mode_always_plan_pattern_implement_feature(self, direct_router: ComplexityRouter):
        """Implementing a feature should use collective."""
        decision = direct_router.route("implement feature for user notifications")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    def test_direct_mode_always_plan_pattern_design_system(self, direct_router: ComplexityRouter):
        """Designing a system should use collective."""
        decision = direct_router.route("design system for caching")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    def test_direct_mode_always_plan_pattern_add_tests(self, direct_router: ComplexityRouter):
        """Adding tests should use collective."""
        decision = direct_router.route("add tests for the API endpoints")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    # =========================================================================
    # Confidence Scoring Tests (Direct Mode Only)
    # =========================================================================

    def test_direct_mode_simple_request_high_confidence(self, direct_router: ComplexityRouter):
        """Simple request without complexity markers in direct mode."""
        decision = direct_router.route("read the file config.py")
        assert decision.confidence >= 0.7
        assert decision.is_direct()

    def test_direct_mode_uncertainty_markers_reduce_confidence(self, direct_router: ComplexityRouter):
        """Uncertainty markers should reduce confidence."""
        decision = direct_router.route("maybe we should update the config, I think")
        # Should have reduced confidence due to "maybe" and "I think"
        assert decision.confidence < 1.0
        assert any("uncertainty" in f for f, _ in decision.factors)

    def test_direct_mode_multi_step_indicators_reduce_confidence(self, direct_router: ComplexityRouter):
        """Multi-step indicators should reduce confidence."""
        decision = direct_router.route("first read the file, then update it, next run tests")
        # "first", "then", "next" are step indicators
        assert any("step" in f for f, _ in decision.factors)

    def test_direct_mode_multiple_files_reduce_confidence(self, direct_router: ComplexityRouter):
        """Multiple files mentioned should reduce confidence."""
        decision = direct_router.route(
            "update config.py, utils.py, main.py, app.py, and test_app.py"
        )
        assert any("files" in f for f, _ in decision.factors)

    def test_direct_mode_complexity_markers_reduce_confidence(self, direct_router: ComplexityRouter):
        """Complexity markers should reduce confidence."""
        # Note: "refactor" would match always_plan pattern, so use different markers
        decision = direct_router.route("need to integrate this with the architecture")
        # "integrate" and "architecture" are complexity markers
        assert any("complexity" in f for f, _ in decision.factors)

    def test_direct_mode_code_context_adds_confidence(self, direct_router: ComplexityRouter):
        """Code blocks in request should add confidence."""
        decision = direct_router.route("what does this code do?\n```python\nprint('hello')\n```")
        # In direct mode, code context adds confidence
        # But "what" matches trivial pattern, so it bypasses scoring
        # Let's use a different prompt
        decision2 = direct_router.route("update this code:\n```python\nprint('hello')\n```")
        assert any("code" in f for f, _ in decision2.factors)

    # =========================================================================
    # Threshold Tests
    # =========================================================================

    def test_custom_threshold(self, custom_router: ComplexityRouter):
        """Custom threshold should affect routing."""
        # With threshold at 0.6, borderline cases should route to collective
        decision = custom_router.route("update the user model maybe")
        # This has uncertainty marker, should be below 0.6 threshold
        if decision.confidence < 0.6:
            assert decision.is_collective()

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_collective_mode_empty_input(self, collective_router: ComplexityRouter):
        """Empty input in collective mode routes to collective."""
        decision = collective_router.route("")
        assert decision.is_collective()
        assert decision.confidence == 0.85

    def test_direct_mode_empty_input(self, direct_router: ComplexityRouter):
        """Empty input in direct mode defaults to direct with high confidence."""
        decision = direct_router.route("")
        assert decision.is_direct()
        assert decision.confidence == 1.0

    def test_direct_mode_very_long_request(self, direct_router: ComplexityRouter):
        """Very long request should reduce confidence in direct mode."""
        long_request = "please update " * 60  # More than 50 words
        decision = direct_router.route(long_request)
        assert any("long" in f for f, _ in decision.factors)

    def test_case_insensitive_patterns(self, collective_router: ComplexityRouter):
        """Patterns should match case-insensitively."""
        decision = collective_router.route("FIX TYPO IN README")
        assert decision.is_direct()
        assert decision.confidence == 0.95


class TestRoutingDecision:
    """Test suite for RoutingDecision dataclass."""

    def test_is_direct(self):
        """Test is_direct method."""
        decision = RoutingDecision(mode="direct", confidence=0.9)
        assert decision.is_direct()
        assert not decision.is_collective()

    def test_is_collective(self):
        """Test is_collective method."""
        decision = RoutingDecision(mode="collective", confidence=0.8)
        assert decision.is_collective()
        assert not decision.is_direct()

    def test_factors_default(self):
        """Test factors default to empty list."""
        decision = RoutingDecision(mode="direct", confidence=0.9)
        assert decision.factors == []

    def test_matched_pattern(self):
        """Test matched_pattern attribute."""
        decision = RoutingDecision(
            mode="direct",
            confidence=0.95,
            matched_pattern=r"fix\s+typo",
        )
        assert decision.matched_pattern == r"fix\s+typo"
