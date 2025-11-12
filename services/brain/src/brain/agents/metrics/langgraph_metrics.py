"""
Prometheus metrics for LangGraph routing system.

Metrics:
- Node execution duration
- Tier routing counts (Q4/F16)
- Escalation rate
- Confidence scores
- Tool success rate
- Memory retrieval performance
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Generator, Optional

from prometheus_client import Counter, Gauge, Histogram, Summary

from common.db.models import RoutingTier

logger = logging.getLogger(__name__)

# =============================================================================
# Graph Execution Metrics
# =============================================================================

# Node execution duration (histogram for percentiles)
GRAPH_NODE_DURATION = Histogram(
    "brain_graph_node_duration_seconds",
    "Time spent executing each graph node",
    labelnames=["graph", "node"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# Graph execution counts
GRAPH_EXECUTION_COUNT = Counter(
    "brain_graph_execution_total",
    "Total number of graph executions",
    labelnames=["graph", "status"],  # status: completed, failed
)

# Graph total duration
GRAPH_TOTAL_DURATION = Summary(
    "brain_graph_total_duration_seconds",
    "Total time for complete graph execution",
    labelnames=["graph"],
)

# =============================================================================
# Routing Metrics
# =============================================================================

# Tier routing counts
TIER_ROUTING_COUNT = Counter(
    "brain_tier_routing_total",
    "Number of queries routed to each tier",
    labelnames=["tier"],  # tier: local, mcp, frontier
)

# Escalation rate (Q4 → F16)
ESCALATION_COUNT = Counter(
    "brain_escalation_total",
    "Number of Q4 → F16 escalations",
    labelnames=["reason"],  # reason: low_confidence, high_complexity, explicit
)

# Escalation success/failure
ESCALATION_STATUS = Counter(
    "brain_escalation_status_total",
    "Escalation outcomes",
    labelnames=["status"],  # status: success, fallback
)

# =============================================================================
# Quality Metrics
# =============================================================================

# Confidence scores (gauge for latest value)
CONFIDENCE_SCORE = Gauge(
    "brain_confidence_score",
    "Latest confidence score for responses",
    labelnames=["tier"],
)

# Confidence histogram for distribution
CONFIDENCE_DISTRIBUTION = Histogram(
    "brain_confidence_distribution",
    "Distribution of confidence scores",
    labelnames=["tier"],
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

# Complexity scores
COMPLEXITY_SCORE = Histogram(
    "brain_complexity_score",
    "Distribution of query complexity scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# =============================================================================
# Tool Execution Metrics
# =============================================================================

# Tool execution counts
TOOL_EXECUTION_COUNT = Counter(
    "brain_tool_execution_total",
    "Number of tool executions",
    labelnames=["tool", "status"],  # status: completed, failed, skipped, blocked
)

# Tool execution duration
TOOL_EXECUTION_DURATION = Histogram(
    "brain_tool_execution_duration_seconds",
    "Time spent executing tools",
    labelnames=["tool"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)

# Tool retry counts
TOOL_RETRY_COUNT = Counter(
    "brain_tool_retry_total",
    "Number of tool retries",
    labelnames=["tool"],
)

# Tool success rate (derived from TOOL_EXECUTION_COUNT)
# Can be calculated in Grafana: rate(brain_tool_execution_total{status="completed"}) / rate(brain_tool_execution_total)

# =============================================================================
# Memory Metrics
# =============================================================================

# Memory retrieval duration
MEMORY_RETRIEVAL_DURATION = Histogram(
    "brain_memory_retrieval_duration_seconds",
    "Time spent retrieving memories",
    labelnames=["search_type"],  # search_type: initial, deep
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)

# Memory hit count
MEMORY_HIT_COUNT = Counter(
    "brain_memory_hit_total",
    "Number of memories found",
    labelnames=["search_type"],
)

# Memory sufficiency score
MEMORY_SUFFICIENCY_SCORE = Histogram(
    "brain_memory_sufficiency_score",
    "Distribution of memory sufficiency scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# Fact extraction count
FACT_EXTRACTION_COUNT = Counter(
    "brain_fact_extraction_total",
    "Number of facts extracted from conversations",
)

# =============================================================================
# Deep Reasoner Metrics
# =============================================================================

# Reasoning steps count
REASONING_STEPS_COUNT = Histogram(
    "brain_reasoning_steps",
    "Number of reasoning steps in F16 deep reasoner",
    buckets=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10),
)

# Self-evaluation scores
SELF_EVALUATION_SCORE = Histogram(
    "brain_self_evaluation_score",
    "F16 self-evaluation scores",
    buckets=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

# Retry count for deep reasoning
REASONING_RETRY_COUNT = Counter(
    "brain_reasoning_retry_total",
    "Number of reasoning retries in F16",
)

# =============================================================================
# A/B Testing Metrics
# =============================================================================

# LangGraph routing usage
LANGGRAPH_ROUTING_COUNT = Counter(
    "brain_langgraph_routing_total",
    "Number of queries routed via LangGraph",
    labelnames=["enabled"],  # enabled: true, false
)

# Rollout percentage (gauge)
ROLLOUT_PERCENTAGE = Gauge(
    "brain_langgraph_rollout_percent",
    "Current LangGraph rollout percentage",
)

# =============================================================================
# Helper Functions
# =============================================================================


@contextmanager
def track_node_execution(graph_name: str, node_name: str) -> Generator[None, None, None]:
    """
    Context manager to track node execution duration.

    Usage:
        with track_node_execution("router_graph", "complexity_analysis"):
            # Node logic here
            pass
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        GRAPH_NODE_DURATION.labels(graph=graph_name, node=node_name).observe(duration)


@contextmanager
def track_graph_execution(graph_name: str) -> Generator[None, None, None]:
    """
    Context manager to track complete graph execution.

    Usage:
        with track_graph_execution("router_graph"):
            # Graph execution
            pass
    """
    start_time = time.time()
    status = "completed"
    try:
        yield
    except Exception:
        status = "failed"
        raise
    finally:
        duration = time.time() - start_time
        GRAPH_EXECUTION_COUNT.labels(graph=graph_name, status=status).inc()
        GRAPH_TOTAL_DURATION.labels(graph=graph_name).observe(duration)


def record_tier_routing(tier: RoutingTier) -> None:
    """Record a tier routing decision."""
    tier_label = tier.value if isinstance(tier, RoutingTier) else str(tier)
    TIER_ROUTING_COUNT.labels(tier=tier_label).inc()


def record_escalation(reason: str, success: bool = True) -> None:
    """
    Record a Q4 → F16 escalation.

    Args:
        reason: Escalation reason (low_confidence, high_complexity, explicit)
        success: Whether escalation succeeded or fell back to Q4
    """
    ESCALATION_COUNT.labels(reason=reason).inc()
    status = "success" if success else "fallback"
    ESCALATION_STATUS.labels(status=status).inc()


def record_confidence(confidence: float, tier: RoutingTier) -> None:
    """
    Record confidence score.

    Args:
        confidence: Confidence score 0.0-1.0
        tier: Routing tier used
    """
    tier_label = tier.value if isinstance(tier, RoutingTier) else str(tier)
    CONFIDENCE_SCORE.labels(tier=tier_label).set(confidence)
    CONFIDENCE_DISTRIBUTION.labels(tier=tier_label).observe(confidence)


def record_complexity(complexity: float) -> None:
    """
    Record query complexity score.

    Args:
        complexity: Complexity score 0.0-1.0
    """
    COMPLEXITY_SCORE.observe(complexity)


def record_tool_execution(
    tool_name: str,
    status: str,
    duration_seconds: Optional[float] = None,
    retry_count: int = 0,
) -> None:
    """
    Record tool execution metrics.

    Args:
        tool_name: Name of the tool
        status: Execution status (completed, failed, skipped, blocked)
        duration_seconds: Execution duration
        retry_count: Number of retries attempted
    """
    TOOL_EXECUTION_COUNT.labels(tool=tool_name, status=status).inc()

    if duration_seconds is not None:
        TOOL_EXECUTION_DURATION.labels(tool=tool_name).observe(duration_seconds)

    if retry_count > 0:
        TOOL_RETRY_COUNT.labels(tool=tool_name).inc(retry_count)


def record_memory_retrieval(
    search_type: str,
    duration_seconds: float,
    hit_count: int,
    sufficiency_score: Optional[float] = None,
) -> None:
    """
    Record memory retrieval metrics.

    Args:
        search_type: Type of search (initial, deep)
        duration_seconds: Search duration
        hit_count: Number of memories found
        sufficiency_score: Memory sufficiency score 0.0-1.0
    """
    MEMORY_RETRIEVAL_DURATION.labels(search_type=search_type).observe(duration_seconds)
    MEMORY_HIT_COUNT.labels(search_type=search_type).inc(hit_count)

    if sufficiency_score is not None:
        MEMORY_SUFFICIENCY_SCORE.observe(sufficiency_score)


def record_fact_extraction(fact_count: int) -> None:
    """
    Record fact extraction.

    Args:
        fact_count: Number of facts extracted
    """
    FACT_EXTRACTION_COUNT.inc(fact_count)


def record_deep_reasoning(
    reasoning_steps: int,
    self_eval_score: float,
    retry_count: int = 0,
) -> None:
    """
    Record F16 deep reasoning metrics.

    Args:
        reasoning_steps: Number of reasoning steps executed
        self_eval_score: Self-evaluation score 0.0-1.0
        retry_count: Number of reasoning retries
    """
    REASONING_STEPS_COUNT.observe(reasoning_steps)
    SELF_EVALUATION_SCORE.observe(self_eval_score)

    if retry_count > 0:
        REASONING_RETRY_COUNT.inc(retry_count)


def record_langgraph_routing(enabled: bool) -> None:
    """
    Record LangGraph routing decision.

    Args:
        enabled: Whether LangGraph routing was used
    """
    LANGGRAPH_ROUTING_COUNT.labels(enabled=str(enabled).lower()).inc()


def update_rollout_percentage(percentage: int) -> None:
    """
    Update LangGraph rollout percentage gauge.

    Args:
        percentage: Rollout percentage 0-100
    """
    ROLLOUT_PERCENTAGE.set(percentage)


# =============================================================================
# Initialization
# =============================================================================


def initialize_metrics(rollout_percent: int = 0) -> None:
    """
    Initialize metrics with default values.

    Args:
        rollout_percent: Initial rollout percentage
    """
    logger.info("Initializing LangGraph Prometheus metrics")

    # Set initial rollout percentage
    update_rollout_percentage(rollout_percent)

    logger.info("LangGraph metrics initialized")


__all__ = [
    "track_node_execution",
    "track_graph_execution",
    "record_tier_routing",
    "record_escalation",
    "record_confidence",
    "record_complexity",
    "record_tool_execution",
    "record_memory_retrieval",
    "record_fact_extraction",
    "record_deep_reasoning",
    "record_langgraph_routing",
    "update_rollout_percentage",
    "initialize_metrics",
]
