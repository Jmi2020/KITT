"""
Research State Definition

Defines the state that flows through the autonomous research graph.
"""

import logging
from typing import Dict, List, Optional, Any, TypedDict, Annotated
from enum import Enum
from decimal import Decimal
from datetime import datetime

# Import structured claim types
from ..types import Claim

logger = logging.getLogger(__name__)


class ResearchStatus(str, Enum):
    """Research session status"""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchConfig(TypedDict, total=False):
    """Configuration for research session"""
    # Strategy
    strategy: str  # "breadth_first", "depth_first", "task_decomposition", "hybrid"

    # Iteration limits
    max_iterations: int
    max_depth: int
    max_breadth: int

    # Quality thresholds
    min_quality_score: float
    min_confidence: float
    min_ragas_score: float

    # Saturation
    saturation_threshold: float
    min_novelty_rate: float

    # Budget
    max_total_cost_usd: float
    max_external_calls: int

    # Time limits
    max_time_seconds: Optional[float]

    # Model selection
    prefer_local: bool
    allow_external: bool
    enable_debate: bool

    # Local/offline mode
    force_local_only: bool

    # Analysis options
    enable_source_summaries: bool        # Summarize each fetched source
    enable_opinion_tagging: bool         # Tag claims as fact/opinion/recommendation

    # Stopping criteria
    require_critical_gaps_resolved: bool

    # Hierarchical decomposition
    enable_hierarchical: bool
    min_sub_questions: int
    max_sub_questions: int
    sub_question_min_iterations: int
    sub_question_max_iterations: int


class ResearchState(TypedDict):
    """
    Complete state for autonomous research.

    This state flows through the LangGraph and is checkpointed after each node.
    """
    # Session metadata
    session_id: str
    user_id: str
    query: str
    status: ResearchStatus
    config: ResearchConfig

    # Iteration tracking
    current_iteration: int
    start_time: float
    last_update_time: float

    # Research strategy
    strategy: str
    strategy_context: Dict[str, Any]

    # Findings and sources
    findings: List[Dict[str, Any]]  # List of research findings
    sources: List[Dict[str, Any]]   # List of sources used
    claims: List[Claim]              # Structured claims with evidence attribution

    # Tool execution
    tool_executions: List[Dict[str, Any]]  # History of tool calls
    tool_results: Dict[str, Any]           # Latest tool results

    # Quality metrics
    quality_scores: List[float]
    confidence_scores: List[Dict[str, Any]]
    ragas_results: List[Dict[str, Any]]

    # Saturation tracking
    saturation_status: Optional[Dict[str, Any]]
    novelty_history: List[float]

    # Knowledge gaps
    knowledge_gaps: List[Dict[str, Any]]

    # Reflection / progress tracking
    iteration_summaries: List[Dict[str, Any]]
    reflection: Optional[Dict[str, Any]]
    next_queries: List[str]

    # Stopping criteria
    stopping_decision: Optional[Dict[str, Any]]

    # Budget tracking
    total_cost_usd: Decimal
    external_calls_used: int
    budget_remaining: Decimal
    external_calls_remaining: int

    # Model usage
    models_used: List[str]
    model_call_history: List[Dict[str, Any]]

    # Final synthesis
    final_answer: Optional[str]
    synthesis: Optional[Dict[str, Any]]

    # Hierarchical decomposition
    sub_questions: List[Dict[str, Any]]
    sub_question_findings: Dict[str, List[Dict[str, Any]]]
    sub_question_syntheses: Dict[str, str]
    current_sub_question_id: Optional[str]
    hierarchical_synthesis: Optional[str]
    decomposition_tree: Optional[Dict[str, Any]]

    # Error handling
    errors: List[Dict[str, Any]]
    last_error: Optional[str]
    retry_count: int

    # Metadata
    metadata: Dict[str, Any]


# Default configuration
DEFAULT_RESEARCH_CONFIG: ResearchConfig = {
    "strategy": "hybrid",
    "max_iterations": 15,
    "max_depth": 3,
    "max_breadth": 10,
    "min_quality_score": 0.7,
    "min_confidence": 0.7,
    "min_ragas_score": 0.75,
    "saturation_threshold": 0.75,
    "min_novelty_rate": 0.15,
    "max_total_cost_usd": 2.0,
    "max_external_calls": 10,
    "max_time_seconds": None,
    "prefer_local": True,
    "allow_external": True,
    "enable_debate": True,
    "force_local_only": False,
    "require_critical_gaps_resolved": True,
    "enable_hierarchical": False,  # Opt-in feature
    "min_sub_questions": 2,
    "max_sub_questions": 5,
    "sub_question_min_iterations": 2,
    "sub_question_max_iterations": 5,

    # Analysis options
    "enable_source_summaries": True,
    "enable_opinion_tagging": True,
}


def create_initial_state(
    session_id: str,
    user_id: str,
    query: str,
    config: Optional[ResearchConfig] = None
) -> ResearchState:
    """
    Create initial research state.

    Args:
        session_id: Unique session ID
        user_id: User ID
        query: Research query
        config: Optional configuration override

    Returns:
        Initial ResearchState
    """
    import time

    # Merge with defaults
    final_config = DEFAULT_RESEARCH_CONFIG.copy()
    if config:
        final_config.update(config)

    # If force_local_only is enabled, harden configuration to local tools/models
    if final_config.get("force_local_only"):
        final_config["allow_external"] = False
        final_config["enable_debate"] = False
        final_config["prefer_local"] = True
        final_config["max_external_calls"] = 0

    return ResearchState(
        # Session metadata
        session_id=session_id,
        user_id=user_id,
        query=query,
        status=ResearchStatus.INITIALIZING,
        config=final_config,

        # Iteration tracking
        current_iteration=0,
        start_time=time.time(),
        last_update_time=time.time(),

        # Research strategy
        strategy=final_config["strategy"],
        strategy_context={},

        # Findings and sources
        findings=[],
        sources=[],
        claims=[],

        # Tool execution
        tool_executions=[],
        tool_results={},

        # Quality metrics
        quality_scores=[],
        confidence_scores=[],
        ragas_results=[],

        # Saturation tracking
        saturation_status=None,
        novelty_history=[],

        # Knowledge gaps
        knowledge_gaps=[],

        # Reflection / progress tracking
        iteration_summaries=[],
        reflection=None,
        next_queries=[],

        # Stopping criteria
        stopping_decision=None,

        # Budget tracking
        total_cost_usd=Decimal("0.0"),
        external_calls_used=0,
        budget_remaining=Decimal(str(final_config["max_total_cost_usd"])),
        external_calls_remaining=final_config["max_external_calls"],

        # Model usage
        models_used=[],
        model_call_history=[],

        # Final synthesis
        final_answer=None,
        synthesis=None,

        # Hierarchical decomposition
        sub_questions=[],
        sub_question_findings={},
        sub_question_syntheses={},
        current_sub_question_id=None,
        hierarchical_synthesis=None,
        decomposition_tree=None,

        # Error handling
        errors=[],
        last_error=None,
        retry_count=0,

        # Metadata
        metadata={
            "created_at": datetime.now().isoformat(),
            "query_length": len(query),
        }
    )


def update_state_timestamp(state: ResearchState) -> ResearchState:
    """Update the last_update_time in state"""
    import time
    state["last_update_time"] = time.time()
    return state


def add_finding(
    state: ResearchState,
    finding: Dict[str, Any]
) -> ResearchState:
    """Add a finding to state"""
    state["findings"].append(finding)
    return update_state_timestamp(state)


def add_source(
    state: ResearchState,
    source: Dict[str, Any]
) -> ResearchState:
    """Add a source to state"""
    state["sources"].append(source)
    return update_state_timestamp(state)


def add_claim(
    state: ResearchState,
    claim: Claim
) -> ResearchState:
    """Add a structured claim to state"""
    state["claims"].append(claim)
    return update_state_timestamp(state)


def record_tool_execution(
    state: ResearchState,
    tool_name: str,
    result: Any,
    cost: Decimal = Decimal("0.0"),
    success: bool = True
) -> ResearchState:
    """Record a tool execution"""
    execution = {
        "tool": tool_name,
        "iteration": state["current_iteration"],
        "timestamp": datetime.now().isoformat(),
        "success": success,
        "cost_usd": float(cost)
    }

    state["tool_executions"].append(execution)
    state["total_cost_usd"] += cost
    state["budget_remaining"] -= cost

    if cost > 0:  # External call
        state["external_calls_used"] += 1
        state["external_calls_remaining"] -= 1

    return update_state_timestamp(state)


def record_model_call(
    state: ResearchState,
    model_id: str,
    cost: Decimal,
    latency_ms: float,
    success: bool = True
) -> ResearchState:
    """Record a model call"""
    call = {
        "model_id": model_id,
        "iteration": state["current_iteration"],
        "timestamp": datetime.now().isoformat(),
        "cost_usd": float(cost),
        "latency_ms": latency_ms,
        "success": success
    }

    state["model_call_history"].append(call)

    if model_id not in state["models_used"]:
        state["models_used"].append(model_id)

    state["total_cost_usd"] += cost
    state["budget_remaining"] -= cost

    if cost > 0:  # External model
        state["external_calls_used"] += 1
        state["external_calls_remaining"] -= 1

    return update_state_timestamp(state)


def record_error(
    state: ResearchState,
    error: str,
    context: Optional[Dict[str, Any]] = None
) -> ResearchState:
    """Record an error"""
    error_record = {
        "error": error,
        "iteration": state["current_iteration"],
        "timestamp": datetime.now().isoformat(),
        "context": context or {}
    }

    state["errors"].append(error_record)
    state["last_error"] = error
    state["retry_count"] += 1

    return update_state_timestamp(state)


def increment_iteration(state: ResearchState) -> ResearchState:
    """Increment iteration counter"""
    state["current_iteration"] += 1
    return update_state_timestamp(state)


def set_status(state: ResearchState, status: ResearchStatus) -> ResearchState:
    """Update research status"""
    state["status"] = status
    return update_state_timestamp(state)
