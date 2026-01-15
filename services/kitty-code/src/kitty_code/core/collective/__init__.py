"""
Tiered Collective Architecture for kitty-code.

Multi-model orchestration system with specialized roles:
- Planner: Strategic task decomposition (Devstral 2 123B)
- Executor: Fast code generation (Devstral Small 2 24B)
- Judge: Validation and approval (shares backend with Planner)
"""

from .config import CollectiveConfig, RoutingConfig, JudgmentConfig, PerformanceConfig
from .state import CollectiveState, CollectiveContext
from .router import ComplexityRouter, RoutingDecision
from .models import TaskPlan, TaskStep, ExecutionResult, Judgment, JudgmentVerdict

__all__ = [
    # Config
    "CollectiveConfig",
    "RoutingConfig",
    "JudgmentConfig",
    "PerformanceConfig",
    # State
    "CollectiveState",
    "CollectiveContext",
    # Router
    "ComplexityRouter",
    "RoutingDecision",
    # Models
    "TaskPlan",
    "TaskStep",
    "ExecutionResult",
    "Judgment",
    "JudgmentVerdict",
]
