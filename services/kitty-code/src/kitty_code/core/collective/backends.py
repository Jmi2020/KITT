"""
Backend pool for multi-model management in the Tiered Collective Architecture.

Manages multiple LLM backends for different roles:
- Planner backend: Devstral 2 123B (shared with Judge)
- Executor backend: Devstral Small 2 24B (fast code generation)
- Judge backend: Shares instance with Planner (efficiency)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from typing import TYPE_CHECKING

from ..config import ModelConfig

if TYPE_CHECKING:
    from ..config import VibeConfig
    from ..llm.types import BackendLike

logger = logging.getLogger("kitty-code")


@dataclass
class BackendStats:
    """Statistics for a backend instance."""

    # Request counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    # Token usage
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0

    # Timing
    total_duration_ms: int = 0

    @property
    def avg_duration_ms(self) -> float:
        """Average request duration in milliseconds."""
        if self.total_requests == 0:
            return 0.0
        return self.total_duration_ms / self.total_requests

    @property
    def success_rate(self) -> float:
        """Success rate (0.0-1.0)."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def total_tokens(self) -> int:
        """Total tokens used."""
        return self.total_prompt_tokens + self.total_completion_tokens


@dataclass
class BackendInstance:
    """
    Wrapper for a backend instance with metadata.

    Tracks role assignment, health, and usage statistics.
    """

    # Role this backend serves (planner, executor, judge)
    role: str

    # Model configuration
    model_config: ModelConfig

    # The actual backend instance (LLM client)
    backend: Any = None

    # Whether this backend is healthy
    healthy: bool = True

    # Error message if unhealthy
    error: Optional[str] = None

    # Usage statistics
    stats: BackendStats = field(default_factory=BackendStats)

    def record_request(
        self,
        success: bool,
        duration_ms: int,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record a request to this backend."""
        self.stats.total_requests += 1
        self.stats.total_duration_ms += duration_ms
        self.stats.total_prompt_tokens += prompt_tokens
        self.stats.total_completion_tokens += completion_tokens

        if success:
            self.stats.successful_requests += 1
        else:
            self.stats.failed_requests += 1
            self.error = error

    def mark_healthy(self) -> None:
        """Mark this backend as healthy."""
        self.healthy = True
        self.error = None

    def mark_unhealthy(self, error: str) -> None:
        """Mark this backend as unhealthy."""
        self.healthy = False
        self.error = error


class BackendPool:
    """
    Manages multiple backend instances for collective orchestration.

    Handles:
    - Lazy initialization of backends
    - Backend sharing (Judge shares with Planner)
    - Health monitoring and fallback
    - Statistics aggregation
    """

    def __init__(
        self,
        planner_model: str,
        executor_model: str,
        judge_model: str,
        backend_factory: Callable[[ModelConfig], Any],
        model_configs: Dict[str, ModelConfig],
    ):
        """
        Initialize the backend pool.

        Args:
            planner_model: Model alias for Planner (e.g., "devstral:123b")
            executor_model: Model alias for Executor (e.g., "devstral-small:24b")
            judge_model: Model alias for Judge (typically same as planner)
            backend_factory: Factory function to create backend instances
            model_configs: Dictionary mapping model aliases to configs
        """
        self.planner_model = planner_model
        self.executor_model = executor_model
        self.judge_model = judge_model
        self.backend_factory = backend_factory
        self.model_configs = model_configs

        # Backend instances (lazy initialized)
        self._backends: Dict[str, BackendInstance] = {}

        # Track which backends share instances
        self._shared_backends: Dict[str, str] = {}

        # Initialize sharing map
        if judge_model == planner_model:
            self._shared_backends["judge"] = "planner"

    def get_planner_backend(self) -> BackendInstance:
        """Get the backend for Planner role."""
        return self._get_or_create_backend("planner", self.planner_model)

    def get_executor_backend(self) -> BackendInstance:
        """Get the backend for Executor role."""
        return self._get_or_create_backend("executor", self.executor_model)

    def get_judge_backend(self) -> BackendInstance:
        """
        Get the backend for Judge role.

        May return shared backend with Planner if configured.
        """
        # Check for shared backend
        if "judge" in self._shared_backends:
            shared_role = self._shared_backends["judge"]
            logger.debug(f"Judge sharing backend with {shared_role}")
            return self._get_or_create_backend(shared_role, self.planner_model)

        return self._get_or_create_backend("judge", self.judge_model)

    def _get_or_create_backend(self, role: str, model_alias: str) -> BackendInstance:
        """Get existing backend or create new one."""
        if role in self._backends:
            return self._backends[role]

        # Get model config
        model_config = self.model_configs.get(model_alias)
        if model_config is None:
            logger.warning(f"Model config not found for {model_alias}, using defaults")
            model_config = ModelConfig(
                name=model_alias,
                provider="ollama",
                alias=model_alias,
            )

        # Create backend
        try:
            backend = self.backend_factory(model_config)
            instance = BackendInstance(
                role=role,
                model_config=model_config,
                backend=backend,
                healthy=True,
            )
            self._backends[role] = instance
            logger.info(f"Created backend for {role}: {model_alias}")

        except Exception as e:
            logger.error(f"Failed to create backend for {role}: {e}")
            instance = BackendInstance(
                role=role,
                model_config=model_config,
                backend=None,
                healthy=False,
                error=str(e),
            )
            self._backends[role] = instance

        return instance

    def get_healthy_backends(self) -> List[BackendInstance]:
        """Get all healthy backend instances."""
        return [b for b in self._backends.values() if b.healthy]

    def get_fallback_backend(self, role: str) -> Optional[BackendInstance]:
        """
        Get a fallback backend for a failed role.

        Fallback order:
        1. Planner failure → Use Executor
        2. Executor failure → Use Planner
        3. Judge failure → Use Planner (shared anyway)
        """
        fallback_map = {
            "planner": "executor",
            "executor": "planner",
            "judge": "executor",  # If judge somehow separate and fails
        }

        fallback_role = fallback_map.get(role)
        if fallback_role and fallback_role in self._backends:
            fallback = self._backends[fallback_role]
            if fallback.healthy:
                logger.warning(f"Using {fallback_role} as fallback for {role}")
                return fallback

        return None

    def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics across all backends."""
        total_requests = 0
        total_tokens = 0
        total_duration_ms = 0
        role_stats = {}

        for role, instance in self._backends.items():
            stats = instance.stats
            total_requests += stats.total_requests
            total_tokens += stats.total_tokens
            total_duration_ms += stats.total_duration_ms

            role_stats[role] = {
                "requests": stats.total_requests,
                "tokens": stats.total_tokens,
                "avg_duration_ms": stats.avg_duration_ms,
                "success_rate": stats.success_rate,
                "healthy": instance.healthy,
            }

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_duration_ms": total_duration_ms,
            "by_role": role_stats,
            "shared_backends": self._shared_backends,
        }

    def reset_stats(self) -> None:
        """Reset all statistics."""
        for instance in self._backends.values():
            instance.stats = BackendStats()

    def shutdown(self) -> None:
        """Shutdown all backends."""
        for role, instance in self._backends.items():
            if instance.backend is not None:
                logger.info(f"Shutting down backend for {role}")
                # Most backends don't need explicit shutdown,
                # but some might have cleanup methods
                if hasattr(instance.backend, "shutdown"):
                    try:
                        instance.backend.shutdown()
                    except Exception as e:
                        logger.warning(f"Error shutting down {role} backend: {e}")

        self._backends.clear()


def create_backend_from_config(
    model_config: ModelConfig,
    config: "VibeConfig",
) -> "BackendLike":
    """Create an LLM backend from model config using VibeConfig.

    Uses the same pattern as Agent._select_backend() to create
    the appropriate backend based on provider configuration.

    Args:
        model_config: Model configuration with name, provider, etc.
        config: Full application config with provider settings

    Returns:
        BackendLike instance ready for LLM calls
    """
    from kitty_code.core.llm.backend.factory import BACKEND_FACTORY

    provider = config.get_provider_for_model(model_config)
    timeout = config.api_timeout
    return BACKEND_FACTORY[provider.backend](provider=provider, timeout=timeout)
