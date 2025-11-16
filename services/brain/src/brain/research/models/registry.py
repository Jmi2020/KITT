"""
Model Capability Registry

Tracks available models, their capabilities, costs, and performance characteristics.
Supports both local (Ollama) and external (API) models.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from decimal import Decimal

logger = logging.getLogger(__name__)


class ModelCapability(str, Enum):
    """Model capabilities for different research tasks"""
    REASONING = "reasoning"              # Complex reasoning and analysis
    SYNTHESIS = "synthesis"              # Information synthesis across sources
    EXTRACTION = "extraction"            # Information extraction from text
    VALIDATION = "validation"            # Quality validation and verification
    CREATIVITY = "creativity"            # Creative problem-solving
    CODING = "coding"                    # Code analysis and generation
    MULTILINGUAL = "multilingual"        # Multiple language support
    LONG_CONTEXT = "long_context"        # Large context window support
    FAST_INFERENCE = "fast_inference"    # Quick response time


class ModelTier(str, Enum):
    """Model tiers based on cost and capability"""
    LOCAL_SMALL = "local_small"      # Small local models (< 10B params)
    LOCAL_MEDIUM = "local_medium"    # Medium local models (10-30B params)
    LOCAL_LARGE = "local_large"      # Large local models (> 30B params)
    EXTERNAL_CHEAP = "external_cheap"  # Low-cost external APIs
    EXTERNAL_PREMIUM = "external_premium"  # Premium external APIs


@dataclass
class ModelInfo:
    """Information about a model"""
    model_id: str
    model_name: str
    provider: str  # "ollama", "openai", "anthropic"
    tier: ModelTier

    # Capabilities
    capabilities: Set[ModelCapability] = field(default_factory=set)

    # Performance characteristics
    context_window: int = 4096
    max_tokens: int = 2048
    avg_latency_ms: Optional[float] = None

    # Cost (per 1K tokens)
    cost_input_per_1k: Decimal = Decimal("0.0")  # Local models are free
    cost_output_per_1k: Decimal = Decimal("0.0")

    # Reliability
    success_rate: float = 1.0

    # Availability
    is_available: bool = True
    requires_api_key: bool = False

    # Additional metadata
    description: str = ""
    use_cases: List[str] = field(default_factory=list)


class ModelRegistry:
    """
    Registry of available models for research tasks.

    Maintains catalog of local and external models with their
    capabilities, costs, and performance characteristics.
    """

    def __init__(self):
        self.models: Dict[str, ModelInfo] = {}
        self._initialize_default_models()

    def _initialize_default_models(self):
        """Initialize registry with default model set"""

        # ============================================================
        # LOCAL MODELS (via llama.cpp servers)
        # ============================================================

        # Athene V2 Agent Q4_K_M - Fast tool orchestrator (port 8083)
        self.register_model(ModelInfo(
            model_id="kitty-q4",
            model_name="Athene V2 Agent Q4_K_M",
            provider="llama_cpp",
            tier=ModelTier.LOCAL_SMALL,
            capabilities={
                ModelCapability.REASONING,
                ModelCapability.EXTRACTION,
                ModelCapability.FAST_INFERENCE,
                ModelCapability.CODING,
            },
            context_window=32768,
            max_tokens=4096,
            avg_latency_ms=400.0,
            cost_input_per_1k=Decimal("0.0"),
            cost_output_per_1k=Decimal("0.0"),
            description="Fast Q4 quantized agent optimized for tool calling, web search, and orchestration. 32K context window.",
            use_cases=["tool calling", "web search", "CAD generation", "device control", "fast workflows"]
        ))

        # Llama 3.3 70B F16 - Deep reasoning engine (port 8082)
        self.register_model(ModelInfo(
            model_id="kitty-f16",
            model_name="Llama 3.3 70B F16",
            provider="llama_cpp",
            tier=ModelTier.LOCAL_LARGE,
            capabilities={
                ModelCapability.REASONING,
                ModelCapability.SYNTHESIS,
                ModelCapability.EXTRACTION,
                ModelCapability.VALIDATION,
                ModelCapability.CREATIVITY,
                ModelCapability.CODING,
                ModelCapability.LONG_CONTEXT,
            },
            context_window=65536,
            max_tokens=8192,
            avg_latency_ms=3000.0,
            cost_input_per_1k=Decimal("0.0"),
            cost_output_per_1k=Decimal("0.0"),
            description="Full precision 70B parameter model. Comprehensive analysis, nuanced responses, complex reasoning. 65K context window.",
            use_cases=["complex reasoning", "deep synthesis", "validation", "code analysis", "long documents"]
        ))

        # Gemma 3 27B Q4_K_M with mmproj - Vision/multimodal (port 8086)
        self.register_model(ModelInfo(
            model_id="kitty-vision",
            model_name="Gemma 3 27B Q4_K_M Vision",
            provider="llama_cpp",
            tier=ModelTier.LOCAL_MEDIUM,
            capabilities={
                ModelCapability.REASONING,
                ModelCapability.EXTRACTION,
                ModelCapability.VALIDATION,
                ModelCapability.MULTILINGUAL,
            },
            context_window=8192,
            max_tokens=2048,
            avg_latency_ms=1500.0,
            cost_input_per_1k=Decimal("0.0"),
            cost_output_per_1k=Decimal("0.0"),
            description="Multimodal model with vision capabilities. Image understanding for CAD reference analysis.",
            use_cases=["image understanding", "vision queries", "CAD reference analysis", "multimodal tasks"]
        ))

        # Qwen2.5 Coder 32B Q8 - Code generation specialist
        self.register_model(ModelInfo(
            model_id="kitty-coder",
            model_name="Qwen2.5 Coder 32B Q8",
            provider="llama_cpp",
            tier=ModelTier.LOCAL_MEDIUM,
            capabilities={
                ModelCapability.CODING,
                ModelCapability.REASONING,
                ModelCapability.EXTRACTION,
                ModelCapability.FAST_INFERENCE,
            },
            context_window=8192,
            max_tokens=4096,
            avg_latency_ms=1800.0,
            cost_input_per_1k=Decimal("0.0"),
            cost_output_per_1k=Decimal("0.0"),
            description="Specialized code generation model. Q8 quantized for quality/speed balance.",
            use_cases=["code generation", "code analysis", "programming tasks", "technical documentation"]
        ))

        # ============================================================
        # EXTERNAL MODELS (via APIs)
        # ============================================================

        # Claude Sonnet 4.5 - Anthropic's latest model
        self.register_model(ModelInfo(
            model_id="claude-sonnet-4-5-20250929",
            model_name="Claude Sonnet 4.5",
            provider="anthropic",
            tier=ModelTier.EXTERNAL_PREMIUM,
            capabilities={
                ModelCapability.REASONING,
                ModelCapability.SYNTHESIS,
                ModelCapability.EXTRACTION,
                ModelCapability.VALIDATION,
                ModelCapability.CREATIVITY,
                ModelCapability.CODING,
                ModelCapability.LONG_CONTEXT,
            },
            context_window=200000,
            max_tokens=8192,
            avg_latency_ms=2500.0,
            cost_input_per_1k=Decimal("0.003"),   # $3 per 1M input tokens
            cost_output_per_1k=Decimal("0.015"),  # $15 per 1M output tokens
            requires_api_key=True,
            description="Anthropic's Claude Sonnet 4.5. Excellent reasoning and long context.",
            use_cases=["long document analysis", "complex reasoning", "creative synthesis"]
        ))

        # GPT-5 - OpenAI's latest model
        self.register_model(ModelInfo(
            model_id="gpt-5",
            model_name="GPT-5",
            provider="openai",
            tier=ModelTier.EXTERNAL_PREMIUM,
            capabilities={
                ModelCapability.REASONING,
                ModelCapability.SYNTHESIS,
                ModelCapability.EXTRACTION,
                ModelCapability.VALIDATION,
                ModelCapability.CREATIVITY,
                ModelCapability.CODING,
                ModelCapability.MULTILINGUAL,
                ModelCapability.LONG_CONTEXT,
            },
            context_window=200000,
            max_tokens=32768,
            avg_latency_ms=2000.0,
            cost_input_per_1k=Decimal("0.010"),
            cost_output_per_1k=Decimal("0.030"),
            is_available=True,
            requires_api_key=True,
            description="OpenAI's next-generation model with advanced reasoning capabilities.",
            use_cases=["advanced reasoning", "complex multi-step tasks", "critical decisions"]
        ))

        logger.info(f"Initialized model registry with {len(self.models)} models")

    def register_model(self, model: ModelInfo):
        """Register a model in the registry"""
        self.models[model.model_id] = model
        logger.debug(f"Registered model: {model.model_name} ({model.model_id})")

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get model by ID"""
        return self.models.get(model_id)

    def get_models_by_tier(self, tier: ModelTier) -> List[ModelInfo]:
        """Get all models in a specific tier"""
        return [
            model for model in self.models.values()
            if model.tier == tier and model.is_available
        ]

    def get_models_by_capability(self, capability: ModelCapability) -> List[ModelInfo]:
        """Get all models with a specific capability"""
        return [
            model for model in self.models.values()
            if capability in model.capabilities and model.is_available
        ]

    def get_local_models(self) -> List[ModelInfo]:
        """Get all local (llama.cpp) models"""
        return [
            model for model in self.models.values()
            if model.provider == "llama_cpp" and model.is_available
        ]

    def get_external_models(self) -> List[ModelInfo]:
        """Get all external (API) models"""
        return [
            model for model in self.models.values()
            if model.provider in ["openai", "anthropic"] and model.is_available
        ]

    def get_cheapest_model_for_capability(
        self,
        capability: ModelCapability,
        prefer_local: bool = True
    ) -> Optional[ModelInfo]:
        """
        Get cheapest model with a specific capability.

        Args:
            capability: Required capability
            prefer_local: If True, prefer local models (zero cost)

        Returns:
            Cheapest model with capability, or None
        """
        candidates = self.get_models_by_capability(capability)

        if not candidates:
            return None

        # If preferring local, return first local model
        if prefer_local:
            local_candidates = [m for m in candidates if m.provider == "llama_cpp"]
            if local_candidates:
                # Sort by parameter size (smaller = faster)
                local_candidates.sort(key=lambda m: m.context_window)
                return local_candidates[0]

        # Otherwise, sort by cost
        candidates.sort(key=lambda m: m.cost_input_per_1k + m.cost_output_per_1k)
        return candidates[0]

    def get_best_model_for_task(
        self,
        required_capabilities: Set[ModelCapability],
        max_cost_per_call: Optional[Decimal] = None,
        min_context_window: Optional[int] = None,
        prefer_local: bool = True
    ) -> Optional[ModelInfo]:
        """
        Get best model for a task based on requirements.

        Args:
            required_capabilities: Set of required capabilities
            max_cost_per_call: Maximum cost per call (None = unlimited)
            min_context_window: Minimum context window required
            prefer_local: If True, prefer local models

        Returns:
            Best matching model, or None
        """
        candidates = []

        for model in self.models.values():
            if not model.is_available:
                continue

            # Check capabilities
            if not required_capabilities.issubset(model.capabilities):
                continue

            # Check context window
            if min_context_window and model.context_window < min_context_window:
                continue

            # Check cost (estimate 1K tokens each way)
            if max_cost_per_call:
                estimated_cost = (model.cost_input_per_1k + model.cost_output_per_1k)
                if estimated_cost > max_cost_per_call:
                    continue

            candidates.append(model)

        if not candidates:
            return None

        # Score candidates
        def score_model(model: ModelInfo) -> float:
            score = 0.0

            # Local models get big boost
            if model.provider == "llama_cpp" and prefer_local:
                score += 100.0

            # Prefer more capabilities
            score += len(model.capabilities) * 10.0

            # Prefer lower latency
            if model.avg_latency_ms:
                score += max(0, 10.0 - (model.avg_latency_ms / 500.0))

            # Prefer higher success rate
            score += model.success_rate * 20.0

            # Penalize cost
            cost = float(model.cost_input_per_1k + model.cost_output_per_1k)
            score -= cost * 100.0

            return score

        candidates.sort(key=score_model, reverse=True)
        return candidates[0]

    def update_model_stats(
        self,
        model_id: str,
        success: bool,
        latency_ms: Optional[float] = None
    ):
        """
        Update model statistics based on usage.

        Args:
            model_id: Model to update
            success: Whether call was successful
            latency_ms: Observed latency
        """
        model = self.get_model(model_id)
        if not model:
            return

        # Update success rate (exponential moving average)
        alpha = 0.1  # Weight for new observation
        if success:
            model.success_rate = model.success_rate * (1 - alpha) + alpha
        else:
            model.success_rate = model.success_rate * (1 - alpha)

        # Update latency (exponential moving average)
        if latency_ms and model.avg_latency_ms:
            model.avg_latency_ms = model.avg_latency_ms * (1 - alpha) + latency_ms * alpha
        elif latency_ms:
            model.avg_latency_ms = latency_ms

        logger.debug(
            f"Updated stats for {model_id}: "
            f"success_rate={model.success_rate:.2f}, "
            f"avg_latency={model.avg_latency_ms:.0f}ms"
        )

    def mark_unavailable(self, model_id: str, reason: str = ""):
        """Mark a model as unavailable"""
        model = self.get_model(model_id)
        if model:
            model.is_available = False
            logger.warning(f"Marked {model_id} as unavailable: {reason}")

    def mark_available(self, model_id: str):
        """Mark a model as available"""
        model = self.get_model(model_id)
        if model:
            model.is_available = True
            logger.info(f"Marked {model_id} as available")

    def list_models(
        self,
        include_unavailable: bool = False,
        tier: Optional[ModelTier] = None
    ) -> List[ModelInfo]:
        """
        List all models in registry.

        Args:
            include_unavailable: Include unavailable models
            tier: Filter by tier (None = all tiers)

        Returns:
            List of models
        """
        models = list(self.models.values())

        if not include_unavailable:
            models = [m for m in models if m.is_available]

        if tier:
            models = [m for m in models if m.tier == tier]

        return models


# Global registry instance
_model_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get the global model registry instance"""
    global _model_registry

    if _model_registry is None:
        _model_registry = ModelRegistry()
        logger.info("Created global model registry")

    return _model_registry
