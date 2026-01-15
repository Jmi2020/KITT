"""
Complexity-based routing for the Tiered Collective Architecture.

Routes user requests to either direct execution (simple tasks) or
collective orchestration (complex tasks) based on pattern matching
and confidence scoring.

Pattern borrowed from KITTY brain/routing/confidence_scorer.py
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import CollectiveConfig, RoutingConfig


@dataclass
class RoutingDecision:
    """
    Decision from the ComplexityRouter.

    Determines whether a task should be handled directly (single model)
    or through collective orchestration (Planner → Executor → Judge).
    """

    # "direct" for simple tasks, "collective" for complex tasks
    mode: str

    # Confidence in the routing decision (0.0-1.0)
    confidence: float

    # Which pattern matched (if any)
    matched_pattern: Optional[str] = None

    # Factors that influenced the decision
    factors: List[Tuple[str, float]] = None

    def __post_init__(self):
        if self.factors is None:
            self.factors = []

    def is_direct(self) -> bool:
        """Check if this routes to direct execution."""
        return self.mode == "direct"

    def is_collective(self) -> bool:
        """Check if this routes to collective orchestration."""
        return self.mode == "collective"


class ComplexityRouter:
    """
    Routes tasks using pattern matching + confidence scoring.

    Borrowed from KITTY brain/routing/confidence_scorer.py pattern.

    Flow:
    1. Check auto-execute patterns (fast path to direct execution)
    2. Check always-plan patterns (fast path to collective)
    3. Fall back to confidence scoring (linguistic analysis)

    Confidence Thresholds:
    - >= 0.7: Direct execution (high confidence)
    - < 0.7: Collective orchestration (needs planning/review)
    - < 0.3: Low confidence, will likely need re-planning
    """

    # Linguistic markers that reduce confidence (uncertainty)
    UNCERTAINTY_MARKERS = [
        "maybe",
        "probably",
        "i think",
        "might",
        "could",
        "possibly",
        "not sure",
        "unclear",
    ]

    # Multi-step indicators (reduce confidence)
    STEP_INDICATORS = [
        "then",
        "after",
        "next",
        "finally",
        "first",
        "second",
        "third",
        "also",
        "additionally",
    ]

    # Complexity indicators (reduce confidence)
    COMPLEXITY_MARKERS = [
        "refactor",
        "redesign",
        "restructure",
        "migrate",
        "implement",
        "integrate",
        "architecture",
        "system",
    ]

    def __init__(self, config: RoutingConfig):
        """
        Initialize the router with configuration.

        Args:
            config: Routing configuration with patterns and thresholds
        """
        self.config = config

        # Compile patterns for efficiency
        self._auto_execute_patterns = [
            re.compile(p, re.IGNORECASE) for p in config.auto_execute_patterns
        ]
        self._always_plan_patterns = [
            re.compile(p, re.IGNORECASE) for p in config.always_plan_patterns
        ]

    def route(self, user_input: str, context: Optional[dict] = None) -> RoutingDecision:
        """
        Route a user request to direct or collective execution.

        Args:
            user_input: The user's request text
            context: Optional context (conversation history, file state, etc.)

        Returns:
            RoutingDecision with mode, confidence, and factors
        """
        context = context or {}
        factors = []

        # 1. Pattern matching (fast path)
        for pattern in self._auto_execute_patterns:
            if pattern.search(user_input):
                return RoutingDecision(
                    mode="direct",
                    confidence=0.95,
                    matched_pattern=pattern.pattern,
                    factors=[("auto_execute_pattern", 0.95)],
                )

        for pattern in self._always_plan_patterns:
            if pattern.search(user_input):
                return RoutingDecision(
                    mode="collective",
                    confidence=0.95,
                    matched_pattern=pattern.pattern,
                    factors=[("always_plan_pattern", -0.95)],
                )

        # 2. Confidence scoring (detailed analysis)
        score, factors = self._compute_confidence_score(user_input, context)

        # 3. Make decision based on threshold
        mode = "direct" if score >= self.config.complexity_threshold else "collective"

        return RoutingDecision(
            mode=mode,
            confidence=score,
            factors=factors,
        )

    def _compute_confidence_score(
        self, text: str, context: dict
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """
        Compute confidence score using linguistic markers.

        Borrowed from KITTY brain/routing/confidence_scorer.py pattern.
        Uses deterministic scoring based on text analysis.

        Args:
            text: User input text
            context: Additional context

        Returns:
            Tuple of (score, factors) where score is 0.0-1.0
        """
        text_lower = text.lower()
        factors = []
        score = 1.0

        # Factor 1: Uncertainty markers reduce confidence
        uncertainty_count = 0
        for marker in self.UNCERTAINTY_MARKERS:
            if marker in text_lower:
                uncertainty_count += 1

        if uncertainty_count > 0:
            penalty = min(uncertainty_count * 0.1, 0.3)
            score -= penalty
            factors.append(("uncertainty_markers", -penalty))

        # Factor 2: Multi-step indicators reduce confidence
        step_count = 0
        for indicator in self.STEP_INDICATORS:
            step_count += len(re.findall(rf"\b{indicator}\b", text_lower))

        if step_count > 0:
            penalty = min(step_count * 0.1, 0.4)
            score -= penalty
            factors.append(("step_indicators", -penalty))

        # Factor 3: Multiple files mentioned
        file_pattern = r'\b[\w/.-]+\.(py|ts|js|tsx|jsx|rs|go|java|cpp|c|h)\b'
        file_count = len(re.findall(file_pattern, text))

        if file_count > 3:
            penalty = min((file_count - 3) * 0.1, 0.3)
            score -= penalty
            factors.append(("multiple_files", -penalty))

        # Factor 4: Complexity markers
        complexity_count = 0
        for marker in self.COMPLEXITY_MARKERS:
            if marker in text_lower:
                complexity_count += 1

        if complexity_count > 0:
            penalty = min(complexity_count * 0.15, 0.4)
            score -= penalty
            factors.append(("complexity_markers", -penalty))

        # Factor 5: Question length (longer = more complex)
        word_count = len(text.split())
        if word_count > 50:
            penalty = min((word_count - 50) * 0.005, 0.2)
            score -= penalty
            factors.append(("long_request", -penalty))

        # Factor 6: Code blocks present (might be context, less risky)
        if "```" in text:
            bonus = 0.1
            score += bonus
            factors.append(("code_context", bonus))

        # Factor 7: Context from conversation (if available)
        if context.get("has_recent_errors"):
            penalty = 0.15
            score -= penalty
            factors.append(("recent_errors", -penalty))

        if context.get("has_active_plan"):
            bonus = 0.1
            score += bonus
            factors.append(("active_plan", bonus))

        # Clamp to valid range
        score = max(0.0, min(1.0, score))

        return score, factors

    @classmethod
    def from_config(cls, config: CollectiveConfig) -> "ComplexityRouter":
        """Create router from CollectiveConfig."""
        return cls(config.routing)


def should_use_collective(
    user_input: str,
    config: CollectiveConfig,
    context: Optional[dict] = None,
) -> bool:
    """
    Convenience function to check if collective should be used.

    Args:
        user_input: User's request
        config: Collective configuration
        context: Optional context

    Returns:
        True if collective orchestration should be used
    """
    if not config.enabled:
        return False

    router = ComplexityRouter(config.routing)
    decision = router.route(user_input, context)
    return decision.is_collective()
