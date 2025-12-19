"""
Research Event System

Typed events for real-time streaming of research progress,
following the pattern from Collective Intelligence system.

Events are emitted by ResearchSessionManager and streamed to
WebSocket clients for live progress updates.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class ResearchEventType(str, Enum):
    """Research event types for streaming progress."""

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_COMPLETE = "session_complete"
    SESSION_ERROR = "session_error"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"

    # Iteration lifecycle
    ITERATION_START = "iteration_start"
    ITERATION_COMPLETE = "iteration_complete"

    # Search events (fine-grained)
    SEARCH_PHASE_START = "search_phase_start"
    SEARCH_QUERY_START = "search_query_start"
    SEARCH_QUERY_COMPLETE = "search_query_complete"
    SEARCH_CACHE_HIT = "search_cache_hit"
    SEARCH_PHASE_COMPLETE = "search_phase_complete"

    # Finding extraction events
    EXTRACTION_START = "extraction_start"
    FINDING_EXTRACTED = "finding_extracted"
    EXTRACTION_COMPLETE = "extraction_complete"

    # Validation events
    VALIDATION_START = "validation_start"
    VALIDATION_COMPLETE = "validation_complete"

    # Quality/stopping events
    QUALITY_CHECK = "quality_check"
    SATURATION_CHECK = "saturation_check"
    STOPPING_DECISION = "stopping_decision"

    # Synthesis events
    SYNTHESIS_START = "synthesis_start"
    SYNTHESIS_CHUNK = "synthesis_chunk"
    SYNTHESIS_COMPLETE = "synthesis_complete"

    # Connection events
    CONNECTION = "connection"
    HEARTBEAT = "heartbeat"


@dataclass
class ResearchEvent:
    """Base research event with common fields."""

    type: ResearchEventType = field(default=ResearchEventType.HEARTBEAT)  # Override in subclasses
    session_id: str = ""  # Required, set by caller
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class SessionStartedEvent(ResearchEvent):
    """Emitted when research session begins."""

    type: ResearchEventType = field(default=ResearchEventType.SESSION_STARTED)
    query: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 15
    max_cost_usd: float = 2.0


@dataclass
class SessionCompleteEvent(ResearchEvent):
    """Emitted when research session completes successfully."""

    type: ResearchEventType = field(default=ResearchEventType.SESSION_COMPLETE)
    total_iterations: int = 0
    total_findings: int = 0
    total_sources: int = 0
    total_cost_usd: float = 0.0
    completeness_score: Optional[float] = None
    confidence_score: Optional[float] = None
    has_synthesis: bool = False


@dataclass
class SessionErrorEvent(ResearchEvent):
    """Emitted when research session fails."""

    type: ResearchEventType = field(default=ResearchEventType.SESSION_ERROR)
    error: str = ""
    error_type: str = ""
    iteration: int = 0
    recoverable: bool = False


@dataclass
class IterationStartEvent(ResearchEvent):
    """Emitted at the start of each research iteration."""

    type: ResearchEventType = field(default=ResearchEventType.ITERATION_START)
    iteration: int = 0
    max_iterations: int = 15
    strategy: str = "hybrid"
    pending_queries: List[str] = field(default_factory=list)


@dataclass
class IterationCompleteEvent(ResearchEvent):
    """Emitted at the end of each research iteration."""

    type: ResearchEventType = field(default=ResearchEventType.ITERATION_COMPLETE)
    iteration: int = 0
    new_findings: int = 0
    new_sources: int = 0
    cost_this_iteration: float = 0.0
    cumulative_findings: int = 0
    cumulative_sources: int = 0
    cumulative_cost: float = 0.0


@dataclass
class SearchPhaseStartEvent(ResearchEvent):
    """Emitted when search phase begins for an iteration."""

    type: ResearchEventType = field(default=ResearchEventType.SEARCH_PHASE_START)
    iteration: int = 0
    query_count: int = 0
    providers: List[str] = field(default_factory=list)


@dataclass
class SearchQueryStartEvent(ResearchEvent):
    """Emitted when a search query is about to execute."""

    type: ResearchEventType = field(default=ResearchEventType.SEARCH_QUERY_START)
    iteration: int = 0
    query_index: int = 0
    total_queries: int = 0
    query: str = ""
    provider: str = "duckduckgo"


@dataclass
class SearchQueryCompleteEvent(ResearchEvent):
    """Emitted when a search query completes."""

    type: ResearchEventType = field(default=ResearchEventType.SEARCH_QUERY_COMPLETE)
    iteration: int = 0
    query_index: int = 0
    query: str = ""
    provider: str = "duckduckgo"
    results_count: int = 0
    success: bool = True
    cached: bool = False
    latency_ms: float = 0.0


@dataclass
class SearchCacheHitEvent(ResearchEvent):
    """Emitted when a search result is served from cache."""

    type: ResearchEventType = field(default=ResearchEventType.SEARCH_CACHE_HIT)
    query: str = ""
    provider: str = "duckduckgo"
    results_count: int = 0
    cache_age_seconds: float = 0.0


@dataclass
class SearchPhaseCompleteEvent(ResearchEvent):
    """Emitted when all searches for an iteration complete."""

    type: ResearchEventType = field(default=ResearchEventType.SEARCH_PHASE_COMPLETE)
    iteration: int = 0
    total_queries: int = 0
    successful_queries: int = 0
    cached_queries: int = 0
    total_results: int = 0
    dedup_saved: int = 0  # Queries saved by deduplication


@dataclass
class ExtractionStartEvent(ResearchEvent):
    """Emitted when finding extraction begins."""

    type: ResearchEventType = field(default=ResearchEventType.EXTRACTION_START)
    iteration: int = 0
    sources_to_process: int = 0


@dataclass
class FindingExtractedEvent(ResearchEvent):
    """Emitted when a single finding is extracted."""

    type: ResearchEventType = field(default=ResearchEventType.FINDING_EXTRACTED)
    iteration: int = 0
    finding_index: int = 0
    finding_type: str = "fact"
    content_preview: str = ""  # First ~100 chars
    confidence: float = 0.0
    source_url: str = ""
    source_title: str = ""


@dataclass
class ExtractionCompleteEvent(ResearchEvent):
    """Emitted when finding extraction completes."""

    type: ResearchEventType = field(default=ResearchEventType.EXTRACTION_COMPLETE)
    iteration: int = 0
    findings_extracted: int = 0
    sources_processed: int = 0


@dataclass
class ValidationStartEvent(ResearchEvent):
    """Emitted when validation phase begins."""

    type: ResearchEventType = field(default=ResearchEventType.VALIDATION_START)
    iteration: int = 0
    claims_to_validate: int = 0


@dataclass
class ValidationCompleteEvent(ResearchEvent):
    """Emitted when validation phase completes."""

    type: ResearchEventType = field(default=ResearchEventType.VALIDATION_COMPLETE)
    iteration: int = 0
    claims_validated: int = 0
    claims_rejected: int = 0
    avg_confidence: float = 0.0


@dataclass
class QualityCheckEvent(ResearchEvent):
    """Emitted when quality metrics are computed."""

    type: ResearchEventType = field(default=ResearchEventType.QUALITY_CHECK)
    iteration: int = 0
    completeness_score: float = 0.0
    confidence_score: float = 0.0
    ragas_score: Optional[float] = None
    meets_threshold: bool = False


@dataclass
class SaturationCheckEvent(ResearchEvent):
    """Emitted when saturation is checked."""

    type: ResearchEventType = field(default=ResearchEventType.SATURATION_CHECK)
    iteration: int = 0
    novel_findings_last_n: int = 0
    saturation_threshold: float = 0.75
    threshold_met: bool = False
    novelty_rate: float = 0.0


@dataclass
class StoppingDecisionEvent(ResearchEvent):
    """Emitted when stopping criteria are evaluated."""

    type: ResearchEventType = field(default=ResearchEventType.STOPPING_DECISION)
    iteration: int = 0
    should_stop: bool = False
    reason: str = ""
    criteria_met: List[str] = field(default_factory=list)
    criteria_not_met: List[str] = field(default_factory=list)


@dataclass
class SynthesisStartEvent(ResearchEvent):
    """Emitted when synthesis generation begins."""

    type: ResearchEventType = field(default=ResearchEventType.SYNTHESIS_START)
    findings_count: int = 0
    sources_count: int = 0
    model: str = "DEEP"


@dataclass
class SynthesisChunkEvent(ResearchEvent):
    """Emitted for streaming synthesis chunks."""

    type: ResearchEventType = field(default=ResearchEventType.SYNTHESIS_CHUNK)
    chunk: str = ""
    chunk_index: int = 0


@dataclass
class SynthesisCompleteEvent(ResearchEvent):
    """Emitted when synthesis generation completes."""

    type: ResearchEventType = field(default=ResearchEventType.SYNTHESIS_COMPLETE)
    synthesis_length: int = 0
    model_used: str = ""
    cost_usd: float = 0.0


@dataclass
class ConnectionEvent(ResearchEvent):
    """Emitted on WebSocket connection."""

    type: ResearchEventType = field(default=ResearchEventType.CONNECTION)
    message: str = "Connected to research session stream"


@dataclass
class HeartbeatEvent(ResearchEvent):
    """Emitted periodically to keep connection alive."""

    type: ResearchEventType = field(default=ResearchEventType.HEARTBEAT)
    iteration: int = 0
    status: str = "active"
    uptime_seconds: float = 0.0


# Type alias for all event types
ResearchEventUnion = Union[
    SessionStartedEvent,
    SessionCompleteEvent,
    SessionErrorEvent,
    IterationStartEvent,
    IterationCompleteEvent,
    SearchPhaseStartEvent,
    SearchQueryStartEvent,
    SearchQueryCompleteEvent,
    SearchCacheHitEvent,
    SearchPhaseCompleteEvent,
    ExtractionStartEvent,
    FindingExtractedEvent,
    ExtractionCompleteEvent,
    ValidationStartEvent,
    ValidationCompleteEvent,
    QualityCheckEvent,
    SaturationCheckEvent,
    StoppingDecisionEvent,
    SynthesisStartEvent,
    SynthesisChunkEvent,
    SynthesisCompleteEvent,
    ConnectionEvent,
    HeartbeatEvent,
]


def create_event(event_type: ResearchEventType, session_id: str, **kwargs) -> Dict[str, Any]:
    """
    Factory function to create event dictionaries.

    Args:
        event_type: Type of event
        session_id: Session ID
        **kwargs: Event-specific fields

    Returns:
        Dictionary ready for JSON serialization
    """
    base = {
        "type": event_type.value,
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    base.update(kwargs)
    return base
