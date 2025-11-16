"""
Quality metrics for autonomous research.

Provides:
- RAGAS integration (faithfulness, relevancy, precision, recall)
- Confidence scoring
- Saturation detection
- Knowledge gap identification
- Stopping criteria
"""

__version__ = "0.1.0"

from .ragas_metrics import (
    RAGASEvaluator,
    RAGASMetrics,
    RAGASResult,
)

from .confidence import (
    ConfidenceScorer,
    ConfidenceScore,
    ConfidenceFactors,
)

from .saturation import (
    SaturationDetector,
    SaturationStatus,
    NoveltyTracker,
)

from .knowledge_gaps import (
    GapDetector,
    KnowledgeGap,
    GapType,
    GapPriority,
)

from .stopping_criteria import (
    StoppingCriteria,
    StoppingReason,
    StoppingDecision,
)

__all__ = [
    # RAGAS
    "RAGASEvaluator",
    "RAGASMetrics",
    "RAGASResult",
    # Confidence
    "ConfidenceScorer",
    "ConfidenceScore",
    "ConfidenceFactors",
    # Saturation
    "SaturationDetector",
    "SaturationStatus",
    "NoveltyTracker",
    # Knowledge Gaps
    "GapDetector",
    "KnowledgeGap",
    "GapType",
    "GapPriority",
    # Stopping Criteria
    "StoppingCriteria",
    "StoppingReason",
    "StoppingDecision",
]
