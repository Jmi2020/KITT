"""
Model coordination for autonomous research.

Provides:
- Model capability registry
- Tiered consultation strategy
- Cost optimization
- Mixture-of-agents debate
- Dynamic model selection
"""

__version__ = "0.1.0"

from .registry import (
    ModelCapability,
    ModelTier,
    ModelInfo,
    ModelRegistry,
    get_model_registry,
)

from .coordinator import (
    ModelCoordinator,
    ConsultationTier,
    ConsultationRequest,
    ConsultationResponse,
    ModelSelection,
)

from .debate import (
    DebateCoordinator,
    DebateRound,
    DebateResult,
    ConsensusStrategy,
)

from .budget import (
    BudgetManager,
    BudgetConfig,
    BudgetStatus,
    CostTracker,
)

__all__ = [
    # Registry
    "ModelCapability",
    "ModelTier",
    "ModelInfo",
    "ModelRegistry",
    "get_model_registry",
    # Coordinator
    "ModelCoordinator",
    "ConsultationTier",
    "ConsultationRequest",
    "ConsultationResponse",
    "ModelSelection",
    # Debate
    "DebateCoordinator",
    "DebateRound",
    "DebateResult",
    "ConsensusStrategy",
    # Budget
    "BudgetManager",
    "BudgetConfig",
    "BudgetStatus",
    "CostTracker",
]
