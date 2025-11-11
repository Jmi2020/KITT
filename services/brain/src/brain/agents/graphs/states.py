"""
Shared state types for LangGraph-based agent workflows.

These TypedDict classes define the state that flows through graph nodes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from common.db.models import RoutingTier


class Memory(TypedDict, total=False):
    """Memory item from Qdrant."""

    content: str
    score: float
    metadata: Dict[str, Any]


class ToolResult(TypedDict, total=False):
    """Result from tool execution."""

    success: bool
    output: Any
    error: Optional[str]
    latency_ms: float


class RouterState(TypedDict, total=False):
    """
    State for router agent workflow.

    This state flows through all nodes in the Q4 routing graph.
    """

    # Input
    query: str
    user_id: str
    conversation_id: str
    request_id: str

    # Original prompt before any processing
    original_query: str

    # Memory context
    memories: List[Memory]
    memory_context: str  # Formatted memory text for prompt
    memory_search_attempted: bool

    # Complexity analysis
    complexity_score: float  # 0.0-1.0
    complexity_factors: Dict[str, Any]  # Detailed breakdown
    requires_tools: bool
    requires_search: bool
    requires_vision: bool
    requires_deep_reasoning: bool

    # Tool orchestration
    selected_tools: List[str]  # Tool names from registry
    tool_plan: str  # Step-by-step execution plan
    tool_results: Dict[str, ToolResult]
    tool_execution_errors: List[str]

    # Refinement tracking
    refinement_count: int
    max_refinements: int

    # Model routing
    recommended_tier: RoutingTier
    tier_used: RoutingTier

    # Response generation
    response: str
    confidence: float  # 0.0-1.0
    reasoning: str  # LLM's reasoning process

    # Escalation tracking
    escalated_to_f16: bool
    escalation_reason: str

    # Metadata
    total_tokens: int
    cost_usd: float
    latency_ms: int
    nodes_executed: List[str]  # Track which nodes ran


class DeepReasonerState(TypedDict, total=False):
    """
    State for F16 deep reasoner workflow.

    Extends RouterState with additional fields for deep reasoning.
    """

    # Inherited from RouterState (all fields)
    query: str
    user_id: str
    conversation_id: str
    request_id: str
    original_query: str
    memories: List[Memory]
    memory_context: str
    complexity_score: float
    requires_tools: bool
    tool_results: Dict[str, ToolResult]
    response: str
    confidence: float
    tier_used: RoutingTier
    total_tokens: int
    cost_usd: float
    latency_ms: int
    nodes_executed: List[str]

    # Deep reasoning specific
    q4_attempt: str  # Previous Q4 response (if escalated)
    q4_confidence: float  # Q4's confidence score
    previous_tool_results: Dict[str, ToolResult]  # Tool results from Q4
    synthesized_context: str  # Combined context from all sources

    # Problem decomposition
    sub_problems: List[str]  # Decomposed sub-questions
    decomposition_text: str  # Raw decomposition output

    # Chain-of-thought reasoning
    reasoning_steps: List[Dict[str, Any]]  # Structured reasoning steps
    reasoning_step_count: int  # Current step number
    max_reasoning_steps: int  # Maximum allowed steps

    # Tool refinement
    refined_tool_results: Dict[str, ToolResult]  # Re-executed tool results

    # Evidence synthesis
    evidence: List[Dict[str, Any]]  # Collected evidence pieces

    # Self-evaluation
    self_evaluation_score: float  # 0.0-1.0 quality assessment

    # Retry management
    retry_count: int  # Number of reasoning retries
    max_retries: int  # Maximum retry attempts


class ComplexityScore(TypedDict):
    """Detailed complexity scoring for query analysis."""

    overall: float  # 0.0-1.0 overall complexity
    factors: Dict[str, float]  # Individual factor scores
    recommended_tier: RoutingTier
    reasoning: str  # Why this score was assigned
