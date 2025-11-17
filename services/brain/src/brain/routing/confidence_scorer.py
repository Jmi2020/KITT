"""
Confidence Scoring for Routing Decisions

Analyzes model responses to calculate confidence for routing escalation.
Unlike research confidence (which scores research findings), this scores
the model's certainty about its response.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Uncertainty markers that indicate low confidence
UNCERTAINTY_MARKERS = [
    r"\bi don'?t know\b",
    r"\bnot sure\b",
    r"\bunsure\b",
    r"\buncertain\b",
    r"\bprobably\b",
    r"\bmaybe\b",
    r"\bmight be\b",
    r"\bcould be\b",
    r"\bperhaps\b",
    r"\bpossibly\b",
    r"\bi think\b",
    r"\bi believe\b",
    r"\bseems like\b",
    r"\bappears to\b",
    r"\bas far as i (can tell|know)\b",
    r"\bto the best of my knowledge\b",
]

# Hedging phrases that indicate moderate confidence
HEDGING_PHRASES = [
    r"\bgenerally\b",
    r"\btypically\b",
    r"\busually\b",
    r"\boften\b",
    r"\bin most cases\b",
    r"\bfor the most part\b",
]


@dataclass
class RoutingConfidenceFactors:
    """Individual factors contributing to routing confidence score"""

    response_completeness: float = 0.0  # 0.0-1.0: Whether response is complete
    linguistic_certainty: float = 0.0   # 0.0-1.0: Language patterns indicating confidence
    tool_usage: float = 0.0             # 0.0-1.0: Appropriate tool usage
    response_quality: float = 0.0       # 0.0-1.0: Length and coherence
    model_metadata: float = 0.0         # 0.0-1.0: Stop reason, truncation, etc.

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "response_completeness": self.response_completeness,
            "linguistic_certainty": self.linguistic_certainty,
            "tool_usage": self.tool_usage,
            "response_quality": self.response_quality,
            "model_metadata": self.model_metadata,
        }


@dataclass
class RoutingConfidenceScore:
    """Overall confidence score with breakdown and explanation"""

    overall: float = 0.0
    factors: RoutingConfidenceFactors = field(default_factory=RoutingConfidenceFactors)
    explanation: str = ""
    warnings: List[str] = field(default_factory=list)
    should_escalate: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "overall": self.overall,
            "factors": self.factors.to_dict(),
            "explanation": self.explanation,
            "warnings": self.warnings,
            "should_escalate": self.should_escalate,
        }


class RoutingConfidenceScorer:
    """
    Computes confidence scores for routing decisions.

    Weights:
    - Response completeness: 30%
    - Linguistic certainty: 25%
    - Tool usage: 20%
    - Response quality: 15%
    - Model metadata: 10%
    """

    def __init__(
        self,
        min_response_length: int = 10,
        max_response_length: int = 4000,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize routing confidence scorer.

        Args:
            min_response_length: Minimum expected response length
            max_response_length: Maximum expected response length
            weights: Custom weights for factors (must sum to 1.0)
        """
        self.min_response_length = min_response_length
        self.max_response_length = max_response_length

        # Default weights
        self.weights = weights or {
            "response_completeness": 0.30,
            "linguistic_certainty": 0.25,
            "tool_usage": 0.20,
            "response_quality": 0.15,
            "model_metadata": 0.10,
        }

        # Validate weights sum to 1.0
        total_weight = sum(self.weights.values())
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"Confidence weights sum to {total_weight}, normalizing to 1.0"
            )
            self.weights = {k: v / total_weight for k, v in self.weights.items()}

    def score_response(
        self,
        response_text: str,
        tool_calls: Optional[List[Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None,
    ) -> RoutingConfidenceScore:
        """
        Calculate confidence score for a model response.

        Args:
            response_text: The model's response text
            tool_calls: List of tool calls made by the model
            metadata: Additional metadata (stop_reason, truncated, etc.)
            prompt: Original prompt (for context)

        Returns:
            RoutingConfidenceScore with overall score and breakdown
        """
        metadata = metadata or {}
        tool_calls = tool_calls or []

        factors = RoutingConfidenceFactors()
        warnings: List[str] = []

        # 1. Response Completeness (30%)
        factors.response_completeness = self._score_completeness(
            response_text, metadata, warnings
        )

        # 2. Linguistic Certainty (25%)
        factors.linguistic_certainty = self._score_linguistic_certainty(
            response_text, warnings
        )

        # 3. Tool Usage (20%)
        factors.tool_usage = self._score_tool_usage(
            tool_calls, response_text, warnings
        )

        # 4. Response Quality (15%)
        factors.response_quality = self._score_response_quality(
            response_text, prompt, warnings
        )

        # 5. Model Metadata (10%)
        factors.model_metadata = self._score_metadata(metadata, warnings)

        # Calculate weighted overall score
        overall = (
            self.weights["response_completeness"] * factors.response_completeness +
            self.weights["linguistic_certainty"] * factors.linguistic_certainty +
            self.weights["tool_usage"] * factors.tool_usage +
            self.weights["response_quality"] * factors.response_quality +
            self.weights["model_metadata"] * factors.model_metadata
        )

        # Generate explanation
        explanation = self._generate_explanation(factors, overall)

        # Determine if escalation is recommended (overall < 0.7 is typical threshold)
        should_escalate = overall < 0.7

        return RoutingConfidenceScore(
            overall=overall,
            factors=factors,
            explanation=explanation,
            warnings=warnings,
            should_escalate=should_escalate,
        )

    def _score_completeness(
        self, response_text: str, metadata: Dict[str, Any], warnings: List[str]
    ) -> float:
        """Score whether the response is complete"""
        score = 1.0

        # Check if response exists
        if not response_text or len(response_text.strip()) == 0:
            warnings.append("Empty or missing response")
            return 0.0

        # Check if truncated
        if metadata.get("truncated"):
            warnings.append("Response was truncated (hit token limit)")
            score -= 0.5

        # Check for incomplete stop reason
        stop_reason = metadata.get("stop_reason") or metadata.get("stop_type")
        if stop_reason == "length":
            warnings.append("Response stopped due to length limit")
            score -= 0.3
        elif stop_reason and stop_reason not in ["stop", "end_turn", None]:
            warnings.append(f"Unexpected stop reason: {stop_reason}")
            score -= 0.2

        # Check for incomplete sentences
        if response_text and not response_text.rstrip().endswith((".", "!", "?", "```")):
            if len(response_text) > 50:  # Only penalize if response is substantial
                warnings.append("Response may be incomplete (no ending punctuation)")
                score -= 0.15

        return max(0.0, min(1.0, score))

    def _score_linguistic_certainty(
        self, response_text: str, warnings: List[str]
    ) -> float:
        """Score linguistic patterns that indicate certainty/uncertainty"""
        if not response_text:
            return 0.0

        score = 1.0
        text_lower = response_text.lower()

        # Count uncertainty markers
        uncertainty_count = 0
        for pattern in UNCERTAINTY_MARKERS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            uncertainty_count += len(matches)

        # Penalize based on uncertainty markers
        if uncertainty_count > 0:
            penalty = min(0.6, uncertainty_count * 0.15)
            score -= penalty
            warnings.append(
                f"Found {uncertainty_count} uncertainty marker(s) in response"
            )

        # Count hedging phrases (less severe)
        hedging_count = 0
        for pattern in HEDGING_PHRASES:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            hedging_count += len(matches)

        if hedging_count > 2:
            penalty = min(0.3, (hedging_count - 2) * 0.1)
            score -= penalty
            warnings.append(f"Found {hedging_count} hedging phrase(s) in response")

        # Check for explicit refusal/inability
        refusal_patterns = [
            r"i (can'?t|cannot|am unable to)",
            r"(don'?t|do not) have (access|information|data)",
            r"beyond my (knowledge|capabilities|scope)",
        ]
        for pattern in refusal_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                warnings.append("Response indicates inability to answer")
                score -= 0.4
                break

        return max(0.0, min(1.0, score))

    def _score_tool_usage(
        self, tool_calls: List[Any], response_text: str, warnings: List[str]
    ) -> float:
        """Score whether tool usage is appropriate"""
        # Default high score if no tools were expected
        score = 0.85

        # If tools were called, that's generally good (model knows what it needs)
        if tool_calls and len(tool_calls) > 0:
            score = 0.95

            # But too many tool calls might indicate confusion
            if len(tool_calls) > 5:
                warnings.append(f"Many tool calls ({len(tool_calls)}) may indicate uncertainty")
                score = 0.75

        # If response mentions needing to search/look up but didn't call tools
        if response_text:
            needs_lookup = re.search(
                r"(would need to|need to (search|look up|check|verify)|"
                r"requires (searching|checking|verification))",
                response_text.lower()
            )
            if needs_lookup and not tool_calls:
                warnings.append("Response suggests need for lookup but no tools used")
                score = 0.5

        return score

    def _score_response_quality(
        self, response_text: str, prompt: Optional[str], warnings: List[str]
    ) -> float:
        """Score the quality and appropriateness of the response"""
        if not response_text:
            return 0.0

        score = 1.0

        # Check length appropriateness
        length = len(response_text)
        if length < self.min_response_length:
            warnings.append(f"Response very short ({length} chars)")
            score -= 0.3
        elif length > self.max_response_length:
            warnings.append(f"Response very long ({length} chars)")
            score -= 0.1

        # Check for repetition (sign of model confusion)
        words = response_text.lower().split()
        if len(words) > 20:
            # Look for repeated phrases (3+ word sequences)
            phrases = [" ".join(words[i:i+3]) for i in range(len(words) - 2)]
            unique_phrases = set(phrases)
            if len(phrases) > 0:
                repetition_ratio = 1.0 - (len(unique_phrases) / len(phrases))
                if repetition_ratio > 0.3:
                    warnings.append(f"High repetition in response ({repetition_ratio:.0%})")
                    score -= min(0.4, repetition_ratio * 0.5)

        # Check coherence (basic - at least some sentence structure)
        sentences = re.split(r'[.!?]+', response_text)
        valid_sentences = [s for s in sentences if len(s.strip()) > 10]
        if len(valid_sentences) == 0 and length > 50:
            warnings.append("Response lacks clear sentence structure")
            score -= 0.2

        return max(0.0, min(1.0, score))

    def _score_metadata(
        self, metadata: Dict[str, Any], warnings: List[str]
    ) -> float:
        """Score based on model metadata"""
        score = 1.0

        # Check for errors or unusual metadata
        if metadata.get("error"):
            warnings.append(f"Model returned error: {metadata['error']}")
            return 0.0

        # Check token usage if available (from raw response)
        raw = metadata.get("raw", {})
        usage = raw.get("usage", {})

        # If response used very few tokens, might indicate refusal or inability
        completion_tokens = usage.get("completion_tokens", 0)
        if completion_tokens > 0 and completion_tokens < 10:
            warnings.append("Very few completion tokens used")
            score -= 0.3

        # Check for unusual prompt/completion ratio (if available)
        prompt_tokens = usage.get("prompt_tokens", 0)
        if prompt_tokens > 0 and completion_tokens > 0:
            ratio = completion_tokens / prompt_tokens
            if ratio < 0.05:  # Response much shorter than prompt
                warnings.append("Response much shorter than prompt")
                score -= 0.2

        return max(0.0, min(1.0, score))

    def _generate_explanation(
        self, factors: RoutingConfidenceFactors, overall: float
    ) -> str:
        """Generate human-readable explanation of the confidence score"""
        # Determine overall assessment
        if overall >= 0.85:
            assessment = "High confidence"
        elif overall >= 0.70:
            assessment = "Moderate confidence"
        elif overall >= 0.50:
            assessment = "Low confidence"
        else:
            assessment = "Very low confidence"

        # Find weakest factor
        factor_dict = factors.to_dict()
        weakest = min(factor_dict.items(), key=lambda x: x[1])
        weakest_name = weakest[0].replace("_", " ").title()
        weakest_score = weakest[1]

        explanation = f"{assessment} (score: {overall:.2f}). "

        if weakest_score < 0.7:
            explanation += f"Weakest factor: {weakest_name} ({weakest_score:.2f}). "

        if overall < 0.7:
            explanation += "Consider escalating to higher-tier model."
        else:
            explanation += "Response appears reliable."

        return explanation


__all__ = [
    "RoutingConfidenceScorer",
    "RoutingConfidenceScore",
    "RoutingConfidenceFactors",
]
