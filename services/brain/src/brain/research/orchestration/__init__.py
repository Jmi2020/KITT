"""
Tool orchestration for autonomous research.

Provides:
- Tool dependency graph modeling
- Wave-based parallel execution
- Multi-strategy orchestration
- Validation pipelines
"""

__version__ = "0.1.0"

from .tool_graph import (
    ToolDependencyGraph,
    WaveExecutor,
    ToolNode,
    ToolResult,
    ToolStatus,
    CyclicDependencyError,
)

from .strategies import (
    ResearchStrategy,
    BaseResearchStrategy,
    BreadthFirstStrategy,
    DepthFirstStrategy,
    TaskDecompositionStrategy,
    HybridStrategy,
    ResearchTask,
    ResearchNode,
    StrategyContext,
    create_strategy,
)

__all__ = [
    # Tool graph
    "ToolDependencyGraph",
    "WaveExecutor",
    "ToolNode",
    "ToolResult",
    "ToolStatus",
    "CyclicDependencyError",
    # Strategies
    "ResearchStrategy",
    "BaseResearchStrategy",
    "BreadthFirstStrategy",
    "DepthFirstStrategy",
    "TaskDecompositionStrategy",
    "HybridStrategy",
    "ResearchTask",
    "ResearchNode",
    "StrategyContext",
    "create_strategy",
]
