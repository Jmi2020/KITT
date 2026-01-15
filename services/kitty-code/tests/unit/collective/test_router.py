"""Tests for the ComplexityRouter."""

import pytest

from kitty_code.core.collective.config import RoutingConfig
from kitty_code.core.collective.router import ComplexityRouter, RoutingDecision


class TestComplexityRouter:
    """Test suite for ComplexityRouter."""

    @pytest.fixture
    def router(self) -> ComplexityRouter:
        """Create a router with default config."""
        return ComplexityRouter(RoutingConfig())

    @pytest.fixture
    def custom_router(self) -> ComplexityRouter:
        """Create a router with custom patterns."""
        config = RoutingConfig(
            complexity_threshold=0.6,
            auto_execute_patterns=[r"fix\s+typo", r"add\s+import"],
            always_plan_patterns=[r"refactor", r"implement\s+feature"],
        )
        return ComplexityRouter(config)

    # =========================================================================
    # Pattern Matching Tests
    # =========================================================================

    def test_auto_execute_pattern_fix_typo(self, router: ComplexityRouter):
        """Simple typo fix should bypass collective."""
        decision = router.route("fix typo in README")
        assert decision.is_direct()
        assert decision.confidence == 0.95
        assert decision.matched_pattern is not None

    def test_auto_execute_pattern_add_import(self, router: ComplexityRouter):
        """Adding import should bypass collective."""
        decision = router.route("add import for os module")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_auto_execute_pattern_rename_variable(self, router: ComplexityRouter):
        """Renaming variable should bypass collective."""
        decision = router.route("rename variable foo to bar")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_auto_execute_pattern_format_code(self, router: ComplexityRouter):
        """Formatting code should bypass collective."""
        decision = router.route("format code in utils.py")
        assert decision.is_direct()
        assert decision.confidence == 0.95

    def test_always_plan_pattern_refactor(self, router: ComplexityRouter):
        """Refactoring should use collective."""
        decision = router.route("refactor the authentication module")
        assert decision.is_collective()
        assert decision.confidence == 0.95
        assert decision.matched_pattern is not None

    def test_always_plan_pattern_implement_feature(self, router: ComplexityRouter):
        """Implementing a feature should use collective."""
        decision = router.route("implement feature for user notifications")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    def test_always_plan_pattern_design_system(self, router: ComplexityRouter):
        """Designing a system should use collective."""
        decision = router.route("design system for caching")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    def test_always_plan_pattern_add_tests(self, router: ComplexityRouter):
        """Adding tests should use collective."""
        decision = router.route("add tests for the API endpoints")
        assert decision.is_collective()
        assert decision.confidence == 0.95

    # =========================================================================
    # Confidence Scoring Tests
    # =========================================================================

    def test_simple_request_high_confidence(self, router: ComplexityRouter):
        """Simple request without complexity markers."""
        decision = router.route("read the file config.py")
        assert decision.confidence >= 0.7
        assert decision.is_direct()

    def test_uncertainty_markers_reduce_confidence(self, router: ComplexityRouter):
        """Uncertainty markers should reduce confidence."""
        decision = router.route("maybe we should update the config, I think")
        # Should have reduced confidence due to "maybe" and "I think"
        assert decision.confidence < 1.0
        assert ("uncertainty_markers", pytest.approx(-0.2, abs=0.05)) in [
            (f, pytest.approx(v, abs=0.05)) for f, v in decision.factors
        ] or any("uncertainty" in f for f, _ in decision.factors)

    def test_multi_step_indicators_reduce_confidence(self, router: ComplexityRouter):
        """Multi-step indicators should reduce confidence."""
        decision = router.route("first read the file, then update it, next run tests")
        # "first", "then", "next" are step indicators
        assert any("step" in f for f, _ in decision.factors)

    def test_multiple_files_reduce_confidence(self, router: ComplexityRouter):
        """Multiple files mentioned should reduce confidence."""
        decision = router.route(
            "update config.py, utils.py, main.py, app.py, and test_app.py"
        )
        assert any("files" in f for f, _ in decision.factors)

    def test_complexity_markers_reduce_confidence(self, router: ComplexityRouter):
        """Complexity markers should reduce confidence."""
        # Note: "refactor" would match always_plan pattern, so use different markers
        decision = router.route("need to integrate this with the architecture")
        # "integrate" and "architecture" are complexity markers
        assert any("complexity" in f for f, _ in decision.factors)

    def test_code_context_adds_confidence(self, router: ComplexityRouter):
        """Code blocks in request should add confidence."""
        decision = router.route("what does this code do?\n```python\nprint('hello')\n```")
        assert any("code" in f for f, _ in decision.factors)

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

    def test_empty_input(self, router: ComplexityRouter):
        """Empty input should default to direct."""
        decision = router.route("")
        assert decision.is_direct()
        assert decision.confidence == 1.0

    def test_very_long_request(self, router: ComplexityRouter):
        """Very long request should reduce confidence."""
        long_request = "please " * 100  # 100 words
        decision = router.route(long_request)
        assert any("long" in f for f, _ in decision.factors)

    def test_case_insensitive_patterns(self, router: ComplexityRouter):
        """Patterns should match case-insensitively."""
        decision = router.route("FIX TYPO IN README")
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
