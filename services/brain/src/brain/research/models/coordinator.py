"""
Model Coordination System

Implements tiered consultation strategy for autonomous research.
Dynamically selects models based on task complexity and budget constraints.
Integrates with I/O Control for external API permission checks.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from decimal import Decimal
import asyncio

from .registry import (
    ModelRegistry,
    ModelInfo,
    ModelCapability,
    ModelTier,
    get_model_registry
)

# Import unified permission gate
try:
    from brain.research.permissions import UnifiedPermissionGate
    PERMISSION_GATE_AVAILABLE = True
except ImportError:
    UnifiedPermissionGate = None
    PERMISSION_GATE_AVAILABLE = False

logger = logging.getLogger(__name__)


class ConsultationTier(str, Enum):
    """
    Consultation tiers for decision-making.

    Determines which models to use and how much budget to allocate.
    """
    TRIVIAL = "trivial"        # Simple tasks: local small models only
    LOW = "low"                # Low complexity: local medium models
    MEDIUM = "medium"          # Medium complexity: local large models
    HIGH = "high"              # High complexity: 1 external call allowed
    CRITICAL = "critical"      # Critical decisions: multiple external calls, debate


@dataclass
class ConsultationRequest:
    """A request for model consultation"""
    task_description: str
    required_capabilities: Set[ModelCapability]
    tier: ConsultationTier
    context: Dict[str, Any] = field(default_factory=dict)

    # Constraints
    max_cost: Optional[Decimal] = None
    min_context_window: Optional[int] = None
    timeout_seconds: float = 30.0

    # Options
    allow_external: bool = True
    prefer_local: bool = True
    require_debate: bool = False  # For critical decisions


@dataclass
class ConsultationResponse:
    """Response from model consultation"""
    result: Any
    model_used: str
    cost_usd: Decimal
    latency_ms: float
    success: bool
    error: Optional[str] = None
    confidence: float = 0.0

    # For debate responses
    debate_rounds: int = 0
    models_consulted: List[str] = field(default_factory=list)


@dataclass
class ModelSelection:
    """A selected model for a task"""
    model_info: ModelInfo
    selection_reason: str
    estimated_cost: Decimal
    priority: int = 0  # Higher = higher priority


class ModelCoordinator:
    """
    Coordinates model usage for autonomous research.

    Implements:
    - Tiered consultation strategy
    - Dynamic model selection
    - Cost optimization
    - Fallback handling
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        default_max_cost: Decimal = Decimal("2.0"),
        default_prefer_local: bool = True,
        permission_gate: Optional[Any] = None
    ):
        self.registry = registry or get_model_registry()
        self.default_max_cost = default_max_cost
        self.default_prefer_local = default_prefer_local

        # Unified permission gate for I/O control and API approval
        self.permission_gate = permission_gate

        # Tier configuration
        self._configure_tiers()

    def _is_external_model_allowed(self, model: ModelInfo) -> tuple[bool, str]:
        """
        Check if external model is allowed based on I/O Control.

        Args:
            model: Model to check

        Returns:
            (allowed, reason) tuple
        """
        if model.provider == "llama_cpp":
            return True, ""  # Local models always allowed

        if not self.permission_gate:
            # No permission gate, allow by default (legacy behavior)
            logger.warning("No permission gate configured, allowing external models by default")
            return True, ""

        # Map model provider to I/O control provider name
        provider_map = {
            "openai": "openai",
            "anthropic": "anthropic",
        }

        provider = provider_map.get(model.provider)
        if not provider:
            # Unknown provider, block by default
            return False, f"Unknown provider: {model.provider}"

        # Check I/O Control via unified permission gate
        return self.permission_gate.check_io_control(provider)

    def _configure_tiers(self):
        """Configure consultation tiers"""
        self.tier_config = {
            ConsultationTier.TRIVIAL: {
                "allowed_tiers": [ModelTier.LOCAL_SMALL],
                "max_external_calls": 0,
                "max_cost_per_call": Decimal("0.0"),
                "timeout_seconds": 10.0,
                "require_consensus": False,
            },
            ConsultationTier.LOW: {
                "allowed_tiers": [ModelTier.LOCAL_SMALL, ModelTier.LOCAL_MEDIUM],
                "max_external_calls": 0,
                "max_cost_per_call": Decimal("0.0"),
                "timeout_seconds": 20.0,
                "require_consensus": False,
            },
            ConsultationTier.MEDIUM: {
                "allowed_tiers": [
                    ModelTier.LOCAL_SMALL,
                    ModelTier.LOCAL_MEDIUM,
                    ModelTier.LOCAL_LARGE
                ],
                "max_external_calls": 0,
                "max_cost_per_call": Decimal("0.0"),
                "timeout_seconds": 30.0,
                "require_consensus": False,
            },
            ConsultationTier.HIGH: {
                "allowed_tiers": [
                    ModelTier.LOCAL_MEDIUM,
                    ModelTier.LOCAL_LARGE,
                    ModelTier.EXTERNAL_CHEAP,
                    ModelTier.EXTERNAL_PREMIUM
                ],
                "max_external_calls": 1,
                "max_cost_per_call": Decimal("0.10"),
                "timeout_seconds": 45.0,
                "require_consensus": False,
            },
            ConsultationTier.CRITICAL: {
                "allowed_tiers": [
                    ModelTier.LOCAL_LARGE,
                    ModelTier.EXTERNAL_PREMIUM
                ],
                "max_external_calls": 3,
                "max_cost_per_call": Decimal("0.50"),
                "timeout_seconds": 60.0,
                "require_consensus": True,
            },
        }

    def select_model(
        self,
        request: ConsultationRequest,
        budget_remaining: Decimal,
        external_calls_remaining: int
    ) -> Optional[ModelSelection]:
        """
        Select best model for a consultation request.

        Args:
            request: Consultation request
            budget_remaining: Remaining budget
            external_calls_remaining: Remaining external API calls

        Returns:
            ModelSelection or None if no suitable model
        """
        tier_config = self.tier_config[request.tier]
        allowed_tiers = tier_config["allowed_tiers"]
        max_cost = min(
            request.max_cost or self.default_max_cost,
            tier_config["max_cost_per_call"],
            budget_remaining
        )

        # Get candidate models
        candidates = []

        for model in self.registry.list_models():
            # Check tier
            if model.tier not in allowed_tiers:
                continue

            # Check capabilities
            if not request.required_capabilities.issubset(model.capabilities):
                continue

            # Check context window
            if request.min_context_window and model.context_window < request.min_context_window:
                continue

            # Check if external allowed
            if model.provider != "llama_cpp":
                # Check I/O control first
                is_allowed, block_reason = self._is_external_model_allowed(model)
                if not is_allowed:
                    logger.debug(f"Model {model.model_id} blocked: {block_reason}")
                    continue

                if not request.allow_external:
                    continue
                if external_calls_remaining <= 0:
                    continue

            # Check cost
            estimated_cost = self._estimate_cost(model)
            if estimated_cost > max_cost:
                continue

            candidates.append(
                ModelSelection(
                    model_info=model,
                    selection_reason=self._get_selection_reason(model, request.tier),
                    estimated_cost=estimated_cost,
                    priority=self._calculate_priority(model, request)
                )
            )

        if not candidates:
            logger.warning(
                f"No suitable model found for tier {request.tier} "
                f"with capabilities {request.required_capabilities}"
            )
            return None

        # Sort by priority
        candidates.sort(key=lambda x: x.priority, reverse=True)

        best = candidates[0]
        logger.info(
            f"Selected model {best.model_info.model_id} for {request.tier} tier: "
            f"{best.selection_reason}"
        )

        return best

    def select_models_for_debate(
        self,
        request: ConsultationRequest,
        budget_remaining: Decimal,
        external_calls_remaining: int,
        num_models: int = 3
    ) -> List[ModelSelection]:
        """
        Select multiple models for mixture-of-agents debate.

        Args:
            request: Consultation request
            budget_remaining: Remaining budget
            external_calls_remaining: Remaining external calls
            num_models: Number of models to select

        Returns:
            List of selected models (diverse set)
        """
        tier_config = self.tier_config[request.tier]
        allowed_tiers = tier_config["allowed_tiers"]

        # Select diverse set of models
        selected = []
        providers_used = set()
        tiers_used = set()

        # First pass: get all eligible models
        candidates = []
        for model in self.registry.list_models():
            if model.tier not in allowed_tiers:
                continue
            if not request.required_capabilities.issubset(model.capabilities):
                continue

            # Check I/O control for external models
            if model.provider != "llama_cpp":
                is_allowed, block_reason = self._is_external_model_allowed(model)
                if not is_allowed:
                    continue
                if external_calls_remaining <= len(selected):
                    continue

            estimated_cost = self._estimate_cost(model)
            if estimated_cost > budget_remaining:
                continue

            candidates.append(
                ModelSelection(
                    model_info=model,
                    selection_reason="debate participant",
                    estimated_cost=estimated_cost,
                    priority=self._calculate_priority(model, request)
                )
            )

        # Second pass: select diverse models
        for candidate in sorted(candidates, key=lambda x: x.priority, reverse=True):
            if len(selected) >= num_models:
                break

            # Encourage diversity
            if candidate.model_info.provider in providers_used and len(providers_used) < num_models:
                # Skip if we haven't covered all providers yet
                continue
            if candidate.model_info.tier in tiers_used and len(tiers_used) < num_models:
                # Skip if we haven't covered all tiers yet
                continue

            selected.append(candidate)
            providers_used.add(candidate.model_info.provider)
            tiers_used.add(candidate.model_info.tier)

        # If still not enough, add more regardless of diversity
        if len(selected) < num_models:
            for candidate in sorted(candidates, key=lambda x: x.priority, reverse=True):
                if len(selected) >= num_models:
                    break
                if candidate not in selected:
                    selected.append(candidate)

        logger.info(
            f"Selected {len(selected)} models for debate: "
            f"{[s.model_info.model_id for s in selected]}"
        )

        return selected

    def _estimate_cost(self, model: ModelInfo, tokens: int = 1000) -> Decimal:
        """Estimate cost for a model call"""
        # Estimate input + output tokens
        return (model.cost_input_per_1k + model.cost_output_per_1k) * Decimal(tokens / 1000)

    def _calculate_priority(self, model: ModelInfo, request: ConsultationRequest) -> int:
        """Calculate priority score for model selection"""
        score = 0

        # Local models get boost if preferred
        if model.provider == "llama_cpp" and request.prefer_local:
            score += 100

        # More capabilities = higher score
        score += len(model.capabilities) * 10

        # Higher success rate = higher score
        score += int(model.success_rate * 50)

        # Lower latency = higher score
        if model.avg_latency_ms:
            score += max(0, int(50 - (model.avg_latency_ms / 100)))

        # Lower cost = higher score (for external models)
        if model.provider != "llama_cpp":
            cost = float(model.cost_input_per_1k + model.cost_output_per_1k)
            score += max(0, int(50 - (cost * 1000)))

        # Tier-based adjustments
        if request.tier == ConsultationTier.TRIVIAL:
            if model.tier == ModelTier.LOCAL_SMALL:
                score += 50
        elif request.tier == ConsultationTier.CRITICAL:
            if model.tier in [ModelTier.LOCAL_LARGE, ModelTier.EXTERNAL_PREMIUM]:
                score += 50

        return score

    def _get_selection_reason(self, model: ModelInfo, tier: ConsultationTier) -> str:
        """Get human-readable reason for model selection"""
        reasons = []

        if model.provider == "llama_cpp":
            reasons.append("local (zero cost)")

        if tier == ConsultationTier.TRIVIAL and model.tier == ModelTier.LOCAL_SMALL:
            reasons.append("fast for simple tasks")
        elif tier == ConsultationTier.CRITICAL and model.tier == ModelTier.EXTERNAL_PREMIUM:
            reasons.append("highest capability for critical decision")

        if model.success_rate > 0.95:
            reasons.append("high reliability")

        if not reasons:
            reasons.append("meets requirements")

        return ", ".join(reasons)

    async def consult(
        self,
        request: ConsultationRequest,
        budget_remaining: Decimal,
        external_calls_remaining: int,
        invoke_model_func: Any  # Callable to actually invoke the model
    ) -> ConsultationResponse:
        """
        Perform model consultation.

        Args:
            request: Consultation request
            budget_remaining: Remaining budget
            external_calls_remaining: Remaining external calls
            invoke_model_func: Async function to invoke model
                               Signature: async def(model_id: str, prompt: str) -> dict

        Returns:
            ConsultationResponse with result
        """
        import time

        # Select model
        selection = self.select_model(request, budget_remaining, external_calls_remaining)

        if not selection:
            return ConsultationResponse(
                result=None,
                model_used="none",
                cost_usd=Decimal("0.0"),
                latency_ms=0.0,
                success=False,
                error="No suitable model available"
            )

        # Invoke model
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                invoke_model_func(
                    selection.model_info.model_id,
                    request.task_description,
                    request.context
                ),
                timeout=request.timeout_seconds
            )

            latency_ms = (time.time() - start_time) * 1000

            # Update model stats
            self.registry.update_model_stats(
                selection.model_info.model_id,
                success=True,
                latency_ms=latency_ms
            )

            return ConsultationResponse(
                result=result,
                model_used=selection.model_info.model_id,
                cost_usd=selection.estimated_cost,
                latency_ms=latency_ms,
                success=True,
                models_consulted=[selection.model_info.model_id]
            )

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000

            self.registry.update_model_stats(
                selection.model_info.model_id,
                success=False,
                latency_ms=latency_ms
            )

            return ConsultationResponse(
                result=None,
                model_used=selection.model_info.model_id,
                cost_usd=Decimal("0.0"),
                latency_ms=latency_ms,
                success=False,
                error=f"Timeout after {request.timeout_seconds}s",
                models_consulted=[selection.model_info.model_id]
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000

            self.registry.update_model_stats(
                selection.model_info.model_id,
                success=False,
                latency_ms=latency_ms
            )

            logger.error(f"Model invocation failed: {e}")

            return ConsultationResponse(
                result=None,
                model_used=selection.model_info.model_id,
                cost_usd=Decimal("0.0"),
                latency_ms=latency_ms,
                success=False,
                error=str(e),
                models_consulted=[selection.model_info.model_id]
            )

    def get_tier_for_task(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ConsultationTier:
        """
        Determine consultation tier for a task.

        Uses heuristics to classify task complexity.
        In Phase 4, this will be enhanced with ML-based classification.

        Args:
            task_description: Description of the task
            context: Additional context

        Returns:
            Recommended consultation tier
        """
        # Simple heuristic-based classification
        desc_lower = task_description.lower()

        # Critical indicators
        critical_keywords = ["critical", "important", "final decision", "high stakes", "verify"]
        if any(kw in desc_lower for kw in critical_keywords):
            return ConsultationTier.CRITICAL

        # High complexity indicators
        high_keywords = ["complex", "analyze", "synthesize", "evaluate", "compare"]
        if any(kw in desc_lower for kw in high_keywords):
            # Check length as proxy for complexity
            if len(task_description) > 200:
                return ConsultationTier.HIGH
            return ConsultationTier.MEDIUM

        # Medium complexity indicators
        medium_keywords = ["research", "investigate", "explore", "find"]
        if any(kw in desc_lower for kw in medium_keywords):
            return ConsultationTier.MEDIUM

        # Low complexity indicators
        low_keywords = ["extract", "list", "summarize", "format"]
        if any(kw in desc_lower for kw in low_keywords):
            return ConsultationTier.LOW

        # Default to trivial for very short, simple tasks
        if len(task_description) < 50:
            return ConsultationTier.TRIVIAL

        # Default to low
        return ConsultationTier.LOW
