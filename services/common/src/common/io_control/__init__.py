"""I/O Control Dashboard module.

Centralized control for external device integrations and feature flags
with TUI and web interfaces.
"""

from common.io_control.feature_registry import (
    FeatureCategory,
    FeatureDefinition,
    FeatureRegistry,
    RestartScope,
    feature_registry,
)

__all__ = [
    "FeatureCategory",
    "FeatureDefinition",
    "FeatureRegistry",
    "RestartScope",
    "feature_registry",
]
