"""
Autonomous Research LangGraph

The main orchestration graph that ties together all research components:
- State management and checkpointing (Phase 1)
- Tool orchestration and validation (Phase 2)
- Model coordination and debate (Phase 3)
- Quality metrics and stopping criteria (Phase 4)
"""

__version__ = "0.1.0"

from .state import (
    ResearchState,
    ResearchConfig,
    ResearchStatus,
)

from .graph import (
    build_research_graph,
    ResearchGraph,
)

from .nodes import (
    initialize_research,
    select_strategy,
    execute_iteration,
    validate_findings,
    score_quality,
    check_stopping,
    synthesize_results,
    handle_error,
)

__all__ = [
    # State
    "ResearchState",
    "ResearchConfig",
    "ResearchStatus",
    # Graph
    "build_research_graph",
    "ResearchGraph",
    # Nodes
    "initialize_research",
    "select_strategy",
    "execute_iteration",
    "validate_findings",
    "score_quality",
    "check_stopping",
    "synthesize_results",
    "handle_error",
]
