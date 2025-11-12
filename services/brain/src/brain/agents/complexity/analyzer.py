"""
Complexity analyzer for intelligent query routing.

Analyzes incoming queries to determine complexity score and recommended
model tier (Q4 fast vs F16 deep reasoning).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Set

from common.db.models import RoutingTier

from ..graphs.states import ComplexityScore

logger = logging.getLogger(__name__)


class ComplexityAnalyzer:
    """
    Analyze query complexity for optimal model routing.

    Scoring factors:
    - Token count: Longer queries tend to be more complex
    - Technical density: Presence of technical terms, parameters
    - Multi-step indicators: Words like "then", "after", "also"
    - Ambiguity: Vague language like "something", "maybe"
    - Tool requirements: Number of tools likely needed
    """

    # Technical terms that indicate complexity
    TECHNICAL_TERMS: Set[str] = {
        "cad",
        "parametric",
        "mesh",
        "stl",
        "gcode",
        "slice",
        "slicer",
        "printer",
        "fabrication",
        "cnc",
        "laser",
        "tolerance",
        "dimension",
        "coordinate",
        "vector",
        "algorithm",
        "function",
        "class",
        "module",
        "import",
        "library",
        "framework",
        "api",
        "endpoint",
        "database",
        "query",
        "schema",
    }

    # Multi-step indicators
    MULTI_STEP_INDICATORS: Set[str] = {
        "then",
        "after",
        "next",
        "also",
        "and then",
        "followed by",
        "once",
        "when",
        "if",
        "afterwards",
        "subsequently",
    }

    # Ambiguous language
    AMBIGUOUS_TERMS: Set[str] = {
        "something",
        "somehow",
        "maybe",
        "perhaps",
        "possibly",
        "kind of",
        "sort of",
        "approximately",
        "roughly",
        "about",
        "around",
    }

    # Tool-indicating keywords
    TOOL_KEYWORDS: Dict[str, Set[str]] = {
        "cad": {"design", "model", "cad", "generate", "create", "mesh"},
        "fabrication": {"print", "slice", "slicer", "bamboo", "elegoo", "printer"},
        "search": {"search", "find", "look up", "research", "google"},
        "vision": {"image", "picture", "photo", "visual", "screenshot"},
        "coding": {"code", "function", "script", "program", "implement"},
        "memory": {"remember", "recall", "memory", "previous", "last time"},
    }

    def analyze(
        self,
        query: str,
        context: Dict[str, Any] | None = None,
    ) -> ComplexityScore:
        """
        Analyze query complexity and recommend routing tier.

        Args:
            query: User query string
            context: Optional context (memories, conversation state, etc.)

        Returns:
            ComplexityScore with overall score, factors, and routing recommendation
        """
        context = context or {}

        # Calculate individual factors
        token_score = self._score_token_count(query)
        technical_score = self._score_technical_density(query)
        multi_step = self._detect_multi_step(query)
        ambiguity_score = self._score_ambiguity(query)
        tool_count = self._estimate_tool_count(query)

        # Weighted combination
        factors = {
            "token_count": token_score,
            "technical_density": technical_score,
            "multi_step": multi_step,
            "ambiguity": ambiguity_score,
            "tool_count": min(tool_count / 3.0, 1.0),  # Normalize to 0-1
        }

        # Calculate overall score (weighted average)
        overall = (
            token_score * 0.15
            + technical_score * 0.30
            + (1.0 if multi_step else 0.0) * 0.25
            + ambiguity_score * 0.15
            + factors["tool_count"] * 0.15
        )

        # Determine recommended tier
        recommended_tier = self._determine_tier(overall, factors, context)

        # Generate reasoning
        reasoning = self._generate_reasoning(overall, factors, recommended_tier)

        return ComplexityScore(
            overall=round(overall, 2),
            factors=factors,
            recommended_tier=recommended_tier,
            reasoning=reasoning,
        )

    def _score_token_count(self, query: str) -> float:
        """Score based on query length (approximate tokens)."""
        # Rough estimate: 1 token ≈ 4 characters
        approx_tokens = len(query) / 4

        if approx_tokens < 20:
            return 0.0  # Very short
        elif approx_tokens < 50:
            return 0.3  # Short
        elif approx_tokens < 100:
            return 0.6  # Medium
        else:
            return 1.0  # Long

    def _score_technical_density(self, query: str) -> float:
        """Score based on technical term density."""
        words = set(re.findall(r"\b\w+\b", query.lower()))
        technical_matches = words & self.TECHNICAL_TERMS

        if not words:
            return 0.0

        density = len(technical_matches) / len(words)

        # Scale to 0-1
        return min(density * 5.0, 1.0)  # 20% technical = 1.0

    def _detect_multi_step(self, query: str) -> bool:
        """Detect if query requires multiple steps."""
        query_lower = query.lower()

        for indicator in self.MULTI_STEP_INDICATORS:
            if indicator in query_lower:
                return True

        return False

    def _score_ambiguity(self, query: str) -> float:
        """Score ambiguity level (higher = more ambiguous)."""
        query_lower = query.lower()
        ambiguous_count = sum(
            1 for term in self.AMBIGUOUS_TERMS if term in query_lower
        )

        # Normalize
        return min(ambiguous_count / 3.0, 1.0)

    def _estimate_tool_count(self, query: str) -> int:
        """Estimate number of tools needed."""
        query_lower = query.lower()
        tools_detected = set()

        for tool_name, keywords in self.TOOL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    tools_detected.add(tool_name)
                    break

        return len(tools_detected)

    def _determine_tier(
        self,
        overall_score: float,
        factors: Dict[str, Any],
        context: Dict[str, Any],
    ) -> RoutingTier:
        """
        Determine recommended routing tier.

        Args:
            overall_score: Overall complexity score
            factors: Individual factor scores
            context: Additional context

        Returns:
            Recommended RoutingTier
        """
        # Check for explicit search requirements
        if context.get("requires_search"):
            return RoutingTier.mcp

        # Simple queries → Q4
        if overall_score < 0.3:
            return RoutingTier.local

        # Complex queries → F16
        if overall_score > 0.7:
            return RoutingTier.local  # F16 via LOCAL tier

        # Medium queries → Q4 with F16 fallback
        return RoutingTier.local

    def _generate_reasoning(
        self,
        overall: float,
        factors: Dict[str, Any],
        tier: RoutingTier,
    ) -> str:
        """Generate human-readable reasoning for the score."""
        reasons = []

        if factors["token_count"] > 0.5:
            reasons.append("long query")

        if factors["technical_density"] > 0.4:
            reasons.append("high technical density")

        if factors["multi_step"]:
            reasons.append("multi-step workflow")

        if factors["ambiguity"] > 0.4:
            reasons.append("ambiguous language")

        if factors["tool_count"] > 0.5:
            reasons.append(f"requires {int(factors['tool_count'] * 3)} tools")

        if not reasons:
            reasons.append("simple query")

        reasoning = f"Complexity: {overall:.2f} ({', '.join(reasons)}) → {tier.value} tier"

        return reasoning
