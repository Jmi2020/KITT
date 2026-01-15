"""
Configuration models for the Tiered Collective Architecture.

Defines the configuration schema for multi-model orchestration with
differentiated roles: Planner (123B), Executor (24B), Judge (123B shared).
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RoutingConfig:
    """Configuration for task complexity routing."""

    # Confidence threshold for collective vs direct execution
    # < threshold → collective orchestration
    # >= threshold → direct execution
    complexity_threshold: float = 0.7

    # Patterns that always bypass collective (direct execution)
    auto_execute_patterns: List[str] = field(default_factory=lambda: [
        r"fix\s+typo",
        r"add\s+import",
        r"rename\s+variable",
        r"update\s+comment",
        r"format\s+code",
    ])

    # Patterns that always trigger collective orchestration
    always_plan_patterns: List[str] = field(default_factory=lambda: [
        r"refactor",
        r"implement\s+feature",
        r"design\s+system",
        r"migrate",
        r"add\s+tests?\s+for",
    ])


@dataclass
class JudgmentConfig:
    """Configuration for Judge role behavior."""

    # Tools that require Judge approval before execution
    require_approval: List[str] = field(default_factory=lambda: [
        "write_file",
        "bash",
        "search_replace",
    ])

    # Tools that auto-approve (no Judge review needed)
    auto_approve: List[str] = field(default_factory=lambda: [
        "read_file",
        "grep",
        "todo",
    ])

    # Maximum revision cycles before escalation
    max_revision_cycles: int = 3

    # Maximum escalations before error
    max_escalations: int = 2


@dataclass
class PerformanceConfig:
    """Performance tuning for collective orchestration."""

    # Target latency for fast-path executor responses (ms)
    executor_fast_path_target_ms: int = 2000

    # Maximum planner calls per request
    max_planner_calls: int = 3

    # Enable plan caching to reduce redundant planner calls
    enable_plan_cache: bool = True

    # Timeout for individual model calls (seconds)
    model_timeout_s: int = 120

    # Timeout for full collective orchestration (seconds)
    collective_timeout_s: int = 300


@dataclass
class CollectiveConfig:
    """
    Main configuration for the Tiered Collective Architecture.

    Model Differentiation:
    - Planner/Judge: Devstral 2 123B (72.2% SWE-bench, ~5 tok/s)
    - Executor: Devstral Small 2 24B (68% SWE-bench, ~20-25 tok/s)

    The 24B Executor provides ~4-5x speedup with only 4% accuracy trade-off.
    Simple pattern-matched tasks bypass collective entirely.
    """

    # Master switch for collective orchestration
    enabled: bool = False

    # Model assignments (aliases from models list)
    # Planner: Strategic task decomposition - needs highest accuracy
    planner_model: str = "devstral:123b"

    # Executor: Code generation - prioritizes speed
    # Uses Devstral Small 2 24B for ~4-5x faster inference
    # Ollama model name: devstral-small-2:24b
    executor_model: str = "devstral-small-2:24b"

    # Judge: Validation - shares backend with Planner for efficiency
    judge_model: str = "devstral:123b"

    # Sub-configurations
    routing: RoutingConfig = field(default_factory=RoutingConfig)
    judgment: JudgmentConfig = field(default_factory=JudgmentConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    def validate(self) -> List[str]:
        """
        Validate configuration and return list of warnings.

        Returns:
            List of warning messages (empty if valid)
        """
        warnings = []

        # Check confidence threshold bounds
        if not 0.0 <= self.routing.complexity_threshold <= 1.0:
            warnings.append(
                f"complexity_threshold {self.routing.complexity_threshold} "
                "should be between 0.0 and 1.0"
            )

        # Check revision limits
        if self.judgment.max_revision_cycles < 1:
            warnings.append(
                f"max_revision_cycles {self.judgment.max_revision_cycles} "
                "should be at least 1"
            )

        if self.judgment.max_escalations < 1:
            warnings.append(
                f"max_escalations {self.judgment.max_escalations} "
                "should be at least 1"
            )

        # Check timeout sanity
        if self.performance.collective_timeout_s < self.performance.model_timeout_s:
            warnings.append(
                f"collective_timeout_s ({self.performance.collective_timeout_s}) "
                f"should be >= model_timeout_s ({self.performance.model_timeout_s})"
            )

        return warnings

    @classmethod
    def from_dict(cls, data: dict) -> "CollectiveConfig":
        """
        Create CollectiveConfig from a dictionary (e.g., TOML config).

        Args:
            data: Dictionary with collective configuration

        Returns:
            CollectiveConfig instance
        """
        routing_data = data.get("routing", {})
        judgment_data = data.get("judgment", {})
        performance_data = data.get("performance", {})

        return cls(
            enabled=data.get("enabled", False),
            planner_model=data.get("planner_model", "devstral:123b"),
            executor_model=data.get("executor_model", "devstral-small:24b"),
            judge_model=data.get("judge_model", "devstral:123b"),
            routing=RoutingConfig(
                complexity_threshold=routing_data.get("complexity_threshold", 0.7),
                auto_execute_patterns=routing_data.get("auto_execute_patterns", [
                    r"fix\s+typo", r"add\s+import", r"rename\s+variable",
                    r"update\s+comment", r"format\s+code",
                ]),
                always_plan_patterns=routing_data.get("always_plan_patterns", [
                    r"refactor", r"implement\s+feature", r"design\s+system",
                    r"migrate", r"add\s+tests?\s+for",
                ]),
            ),
            judgment=JudgmentConfig(
                require_approval=judgment_data.get("require_approval", [
                    "write_file", "bash", "search_replace",
                ]),
                auto_approve=judgment_data.get("auto_approve", [
                    "read_file", "grep", "todo",
                ]),
                max_revision_cycles=judgment_data.get("max_revision_cycles", 3),
                max_escalations=judgment_data.get("max_escalations", 2),
            ),
            performance=PerformanceConfig(
                executor_fast_path_target_ms=performance_data.get(
                    "executor_fast_path_target_ms", 2000
                ),
                max_planner_calls=performance_data.get("max_planner_calls", 3),
                enable_plan_cache=performance_data.get("enable_plan_cache", True),
                model_timeout_s=performance_data.get("model_timeout_s", 120),
                collective_timeout_s=performance_data.get("collective_timeout_s", 300),
            ),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "planner_model": self.planner_model,
            "executor_model": self.executor_model,
            "judge_model": self.judge_model,
            "routing": {
                "complexity_threshold": self.routing.complexity_threshold,
                "auto_execute_patterns": self.routing.auto_execute_patterns,
                "always_plan_patterns": self.routing.always_plan_patterns,
            },
            "judgment": {
                "require_approval": self.judgment.require_approval,
                "auto_approve": self.judgment.auto_approve,
                "max_revision_cycles": self.judgment.max_revision_cycles,
                "max_escalations": self.judgment.max_escalations,
            },
            "performance": {
                "executor_fast_path_target_ms": self.performance.executor_fast_path_target_ms,
                "max_planner_calls": self.performance.max_planner_calls,
                "enable_plan_cache": self.performance.enable_plan_cache,
                "model_timeout_s": self.performance.model_timeout_s,
                "collective_timeout_s": self.performance.collective_timeout_s,
            },
        }
