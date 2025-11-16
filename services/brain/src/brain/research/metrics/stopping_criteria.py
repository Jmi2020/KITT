"""
Stopping Criteria for Autonomous Research

Determines when to stop research based on multiple signals:
- Saturation detection
- Quality thresholds
- Budget constraints
- Time limits
- Knowledge gap resolution
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from decimal import Decimal

from .saturation import SaturationStatus
from .confidence import ConfidenceScore
from .knowledge_gaps import KnowledgeGap, GapPriority
from .ragas_metrics import RAGASMetrics

logger = logging.getLogger(__name__)


class StoppingReason(str, Enum):
    """Reasons for stopping research"""
    SATURATION = "saturation"              # Research saturated, diminishing returns
    QUALITY_ACHIEVED = "quality_achieved"  # Quality goals met
    BUDGET_EXHAUSTED = "budget_exhausted"  # Budget limit reached
    TIME_LIMIT = "time_limit"              # Time limit reached
    MAX_ITERATIONS = "max_iterations"      # Max iterations reached
    GAPS_RESOLVED = "gaps_resolved"        # All critical gaps resolved
    USER_REQUESTED = "user_requested"      # User manually stopped
    ERROR = "error"                        # Error occurred, cannot continue


@dataclass
class StoppingDecision:
    """Decision on whether to stop research"""
    should_stop: bool
    reasons: List[StoppingReason] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0: Confidence in stopping decision

    # Current status
    current_iteration: int = 0
    current_quality: float = 0.0
    current_saturation: float = 0.0
    budget_remaining: Decimal = Decimal("0.0")

    # Explanation
    explanation: str = ""
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "should_stop": self.should_stop,
            "reasons": [r.value for r in self.reasons],
            "confidence": self.confidence,
            "current_iteration": self.current_iteration,
            "current_quality": self.current_quality,
            "current_saturation": self.current_saturation,
            "budget_remaining": float(self.budget_remaining),
            "explanation": self.explanation,
            "recommendations": self.recommendations
        }


class StoppingCriteria:
    """
    Determines when autonomous research should stop.

    Considers multiple signals:
    - Saturation (novelty rate)
    - Quality metrics (RAGAS, confidence)
    - Resource constraints (budget, time)
    - Knowledge gaps
    - Iteration limits
    """

    def __init__(
        self,
        # Quality thresholds
        min_quality_score: float = 0.7,
        min_confidence: float = 0.7,
        min_ragas_score: float = 0.75,

        # Saturation thresholds
        max_saturation: float = 0.75,
        min_novelty_rate: float = 0.15,

        # Resource limits
        max_iterations: int = 15,
        max_time_seconds: Optional[float] = None,
        min_budget_reserve: Decimal = Decimal("0.10"),

        # Gap resolution
        require_critical_gaps_resolved: bool = True
    ):
        """
        Initialize stopping criteria.

        Args:
            min_quality_score: Minimum overall quality score to achieve
            min_confidence: Minimum confidence score needed
            min_ragas_score: Minimum RAGAS average score
            max_saturation: Maximum acceptable saturation score
            min_novelty_rate: Minimum acceptable novelty rate
            max_iterations: Maximum research iterations
            max_time_seconds: Maximum time allowed (None = unlimited)
            min_budget_reserve: Minimum budget to keep in reserve
            require_critical_gaps_resolved: Stop only if critical gaps resolved
        """
        self.min_quality_score = min_quality_score
        self.min_confidence = min_confidence
        self.min_ragas_score = min_ragas_score
        self.max_saturation = max_saturation
        self.min_novelty_rate = min_novelty_rate
        self.max_iterations = max_iterations
        self.max_time_seconds = max_time_seconds
        self.min_budget_reserve = min_budget_reserve
        self.require_critical_gaps_resolved = require_critical_gaps_resolved

        logger.info(
            f"Stopping criteria initialized: "
            f"max_iterations={max_iterations}, "
            f"min_quality={min_quality_score}, "
            f"max_saturation={max_saturation}"
        )

    async def should_stop(
        self,
        # Iteration tracking
        current_iteration: int,
        start_time: float,

        # Quality metrics
        quality_scores: List[float],
        confidence_scores: List[ConfidenceScore],
        ragas_results: List[RAGASMetrics],

        # Saturation
        saturation_status: SaturationStatus,

        # Knowledge gaps
        knowledge_gaps: List[KnowledgeGap],

        # Resources
        budget_remaining: Decimal,
        external_calls_remaining: int,

        # Manual override
        user_requested_stop: bool = False
    ) -> StoppingDecision:
        """
        Determine if research should stop.

        Args:
            current_iteration: Current iteration number
            start_time: Research start time (unix timestamp)
            quality_scores: List of quality scores from iterations
            confidence_scores: List of confidence scores
            ragas_results: List of RAGAS evaluation results
            saturation_status: Current saturation status
            knowledge_gaps: Detected knowledge gaps
            budget_remaining: Remaining budget
            external_calls_remaining: Remaining external API calls
            user_requested_stop: User manually requested stop

        Returns:
            StoppingDecision with recommendation
        """
        import time

        reasons = []
        confidence = 0.0

        # Check 1: User requested stop
        if user_requested_stop:
            return StoppingDecision(
                should_stop=True,
                reasons=[StoppingReason.USER_REQUESTED],
                confidence=1.0,
                current_iteration=current_iteration,
                explanation="User manually stopped research"
            )

        # Check 2: Max iterations
        if current_iteration >= self.max_iterations:
            reasons.append(StoppingReason.MAX_ITERATIONS)
            confidence += 0.3

        # Check 3: Time limit
        if self.max_time_seconds:
            elapsed = time.time() - start_time
            if elapsed >= self.max_time_seconds:
                reasons.append(StoppingReason.TIME_LIMIT)
                confidence += 0.3

        # Check 4: Budget exhausted
        if budget_remaining <= self.min_budget_reserve:
            reasons.append(StoppingReason.BUDGET_EXHAUSTED)
            confidence += 0.4

        # Check 5: Saturation
        if saturation_status.is_saturated:
            if saturation_status.saturation_score >= self.max_saturation:
                reasons.append(StoppingReason.SATURATION)
                confidence += 0.5

        # Check 6: Quality achieved
        quality_met = self._check_quality_met(
            quality_scores,
            confidence_scores,
            ragas_results
        )

        if quality_met:
            confidence += 0.4

            # Check knowledge gaps
            critical_gaps_resolved = self._check_critical_gaps_resolved(knowledge_gaps)

            if critical_gaps_resolved or not self.require_critical_gaps_resolved:
                reasons.append(StoppingReason.QUALITY_ACHIEVED)

                if critical_gaps_resolved:
                    reasons.append(StoppingReason.GAPS_RESOLVED)
                    confidence += 0.3

        # Determine if should stop
        should_stop = self._determine_should_stop(reasons, confidence, saturation_status)

        # Calculate current metrics
        current_quality = quality_scores[-1] if quality_scores else 0.0
        current_saturation = saturation_status.saturation_score

        # Generate explanation
        explanation = self._generate_explanation(
            should_stop,
            reasons,
            current_iteration,
            saturation_status,
            quality_met,
            knowledge_gaps
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            should_stop,
            reasons,
            saturation_status,
            quality_met,
            knowledge_gaps,
            budget_remaining
        )

        logger.info(
            f"Stopping decision: should_stop={should_stop}, "
            f"confidence={confidence:.2f}, "
            f"reasons={[r.value for r in reasons]}"
        )

        return StoppingDecision(
            should_stop=should_stop,
            reasons=reasons,
            confidence=min(1.0, confidence),
            current_iteration=current_iteration,
            current_quality=current_quality,
            current_saturation=current_saturation,
            budget_remaining=budget_remaining,
            explanation=explanation,
            recommendations=recommendations
        )

    def _check_quality_met(
        self,
        quality_scores: List[float],
        confidence_scores: List[ConfidenceScore],
        ragas_results: List[RAGASMetrics]
    ) -> bool:
        """Check if quality thresholds are met"""
        # Need at least some results
        if not quality_scores or not confidence_scores:
            return False

        # Check overall quality
        avg_quality = sum(quality_scores) / len(quality_scores)
        if avg_quality < self.min_quality_score:
            return False

        # Check confidence
        avg_confidence = sum(c.overall for c in confidence_scores) / len(confidence_scores)
        if avg_confidence < self.min_confidence:
            return False

        # Check RAGAS if available
        if ragas_results:
            avg_ragas = sum(r.average() for r in ragas_results) / len(ragas_results)
            if avg_ragas < self.min_ragas_score:
                return False

        return True

    def _check_critical_gaps_resolved(self, knowledge_gaps: List[KnowledgeGap]) -> bool:
        """Check if all critical knowledge gaps are resolved"""
        critical_gaps = [
            g for g in knowledge_gaps
            if g.priority == GapPriority.CRITICAL and not g.resolved
        ]
        return len(critical_gaps) == 0

    def _determine_should_stop(
        self,
        reasons: List[StoppingReason],
        confidence: float,
        saturation_status: SaturationStatus
    ) -> bool:
        """Determine if should stop based on reasons and confidence"""
        # Hard stops (must stop)
        hard_stops = {
            StoppingReason.BUDGET_EXHAUSTED,
            StoppingReason.TIME_LIMIT,
            StoppingReason.MAX_ITERATIONS,
            StoppingReason.ERROR
        }

        if any(r in hard_stops for r in reasons):
            return True

        # Quality achieved + gaps resolved = stop
        if (StoppingReason.QUALITY_ACHIEVED in reasons and
            StoppingReason.GAPS_RESOLVED in reasons):
            return True

        # Saturation alone with high confidence
        if (StoppingReason.SATURATION in reasons and
            confidence >= 0.8 and
            saturation_status.novelty_rate < self.min_novelty_rate):
            return True

        # Otherwise, continue
        return False

    def _generate_explanation(
        self,
        should_stop: bool,
        reasons: List[StoppingReason],
        current_iteration: int,
        saturation_status: SaturationStatus,
        quality_met: bool,
        knowledge_gaps: List[KnowledgeGap]
    ) -> str:
        """Generate human-readable explanation"""
        if should_stop:
            explanation = f"Research should stop after {current_iteration} iterations. "

            if StoppingReason.BUDGET_EXHAUSTED in reasons:
                explanation += "Budget exhausted. "
            if StoppingReason.MAX_ITERATIONS in reasons:
                explanation += "Maximum iterations reached. "
            if StoppingReason.TIME_LIMIT in reasons:
                explanation += "Time limit reached. "
            if StoppingReason.QUALITY_ACHIEVED in reasons:
                explanation += "Quality goals achieved. "
            if StoppingReason.SATURATION in reasons:
                explanation += f"Research saturated (novelty rate: {saturation_status.novelty_rate:.1%}). "
            if StoppingReason.GAPS_RESOLVED in reasons:
                explanation += "All critical knowledge gaps resolved. "

        else:
            explanation = f"Research should continue (iteration {current_iteration}). "

            if not quality_met:
                explanation += "Quality goals not yet met. "

            unresolved_gaps = [g for g in knowledge_gaps if not g.resolved]
            if unresolved_gaps:
                explanation += f"{len(unresolved_gaps)} knowledge gaps remaining. "

            if saturation_status.novelty_rate > self.min_novelty_rate:
                explanation += f"Still finding novel information (novelty: {saturation_status.novelty_rate:.1%}). "

        return explanation

    def _generate_recommendations(
        self,
        should_stop: bool,
        reasons: List[StoppingReason],
        saturation_status: SaturationStatus,
        quality_met: bool,
        knowledge_gaps: List[KnowledgeGap],
        budget_remaining: Decimal
    ) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        if should_stop:
            if StoppingReason.QUALITY_ACHIEVED in reasons:
                recommendations.append("Quality goals met - safe to finalize results")
            if StoppingReason.SATURATION in reasons:
                recommendations.append("Diminishing returns detected - consider stopping or changing approach")
            if StoppingReason.BUDGET_EXHAUSTED in reasons:
                recommendations.append("Budget exhausted - synthesize available findings")
        else:
            # Recommend addressing high-priority gaps
            high_priority_gaps = [
                g for g in knowledge_gaps
                if g.priority in [GapPriority.CRITICAL, GapPriority.HIGH] and not g.resolved
            ]

            if high_priority_gaps:
                recommendations.append(
                    f"Address {len(high_priority_gaps)} high-priority knowledge gaps"
                )

            # Recommend focus areas
            if saturation_status.novelty_rate < 0.3:
                recommendations.append("Novelty rate declining - consider new search strategies")

            if not quality_met:
                recommendations.append("Continue research to meet quality thresholds")

            # Budget warnings
            if budget_remaining < Decimal("0.25"):
                recommendations.append("Budget running low - prioritize critical gaps only")

        return recommendations

    def get_progress_summary(
        self,
        current_iteration: int,
        saturation_status: SaturationStatus,
        quality_scores: List[float],
        confidence_scores: List[ConfidenceScore],
        knowledge_gaps: List[KnowledgeGap],
        budget_remaining: Decimal
    ) -> Dict[str, Any]:
        """
        Get progress summary for monitoring.

        Args:
            current_iteration: Current iteration
            saturation_status: Saturation status
            quality_scores: Quality scores
            confidence_scores: Confidence scores
            knowledge_gaps: Knowledge gaps
            budget_remaining: Budget remaining

        Returns:
            Progress summary dict
        """
        return {
            "iteration": current_iteration,
            "max_iterations": self.max_iterations,
            "progress_percentage": (current_iteration / self.max_iterations) * 100,
            "saturation": {
                "is_saturated": saturation_status.is_saturated,
                "score": saturation_status.saturation_score,
                "novelty_rate": saturation_status.novelty_rate
            },
            "quality": {
                "current": quality_scores[-1] if quality_scores else 0.0,
                "average": sum(quality_scores) / len(quality_scores) if quality_scores else 0.0,
                "target": self.min_quality_score
            },
            "confidence": {
                "current": confidence_scores[-1].overall if confidence_scores else 0.0,
                "average": sum(c.overall for c in confidence_scores) / len(confidence_scores) if confidence_scores else 0.0,
                "target": self.min_confidence
            },
            "gaps": {
                "total": len(knowledge_gaps),
                "unresolved": len([g for g in knowledge_gaps if not g.resolved]),
                "critical": len([g for g in knowledge_gaps if g.priority == GapPriority.CRITICAL and not g.resolved])
            },
            "budget": {
                "remaining": float(budget_remaining),
                "reserve_threshold": float(self.min_budget_reserve)
            }
        }
