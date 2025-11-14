"""I/O Control Presets for quick mode switching.

Provides pre-configured sets of features for common scenarios:
- Development Mode: All features mocked, no external dependencies
- Production Mode: All real hardware/APIs enabled
- Cost-Saving Mode: Offline mode + local-only
- Testing Mode: Enable specific hardware for testing
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class Preset:
    """A preset configuration of features."""

    id: str
    name: str
    description: str
    features: Dict[str, bool | str]  # feature_id -> enabled state or value


# ============================================================================
# Preset Definitions
# ============================================================================

DEVELOPMENT_MODE = Preset(
    id="development",
    name="Development Mode",
    description="All features mocked, no external dependencies required",
    features={
        # Disable all external services
        "perplexity_api": False,
        "openai_api": False,
        "anthropic_api": False,
        "zoo_cad_api": False,
        "tripo_cad_api": False,

        # Enable offline mode
        "offline_mode": True,
        "cloud_routing": False,

        # Enable function calling for testing
        "function_calling": True,

        # Disable cameras (use mocks)
        "camera_capture": False,
        "bamboo_camera": False,
        "raspberry_pi_cameras": False,

        # Disable MinIO (use local storage)
        "minio_snapshot_upload": False,

        # Enable print tracking (database usually works)
        "print_outcome_tracking": True,
        "print_intelligence": False,

        # Disable autonomous
        "autonomous_mode": False,
        "autonomous_full_time": False,

        # Enable feedback requests (via MQTT mock)
        "human_feedback_requests": True,
    }
)

PRODUCTION_MODE = Preset(
    id="production",
    name="Production Mode",
    description="All real hardware and APIs enabled (requires configuration)",
    features={
        # Enable cloud services (if keys configured)
        "perplexity_api": True,
        "openai_api": True,
        "anthropic_api": True,
        "zoo_cad_api": True,
        "tripo_cad_api": True,

        # Enable cloud routing
        "cloud_routing": True,
        "offline_mode": False,
        "function_calling": True,

        # Enable cameras
        "camera_capture": True,
        "bamboo_camera": True,
        "raspberry_pi_cameras": True,

        # Enable MinIO uploads
        "minio_snapshot_upload": True,

        # Enable all monitoring
        "print_outcome_tracking": True,
        "print_intelligence": True,
        "human_feedback_requests": True,

        # Enable autonomous (with budget limits)
        "autonomous_mode": True,
        "autonomous_budget_enforcement": "5.00",
        "autonomous_full_time": False,

        # Enable network discovery
        "network_discovery": True,
    }
)

COST_SAVING_MODE = Preset(
    id="cost_saving",
    name="Cost-Saving Mode",
    description="Local-only operation, no paid API services",
    features={
        # Disable all paid services
        "perplexity_api": False,
        "openai_api": False,
        "anthropic_api": False,
        "zoo_cad_api": False,
        "tripo_cad_api": False,

        # Force offline mode
        "offline_mode": True,
        "cloud_routing": False,
        "function_calling": True,

        # Keep cameras enabled (no cost)
        "camera_capture": True,
        "bamboo_camera": True,
        "raspberry_pi_cameras": True,

        # Keep MinIO enabled (local, no cost)
        "minio_snapshot_upload": True,

        # Keep monitoring enabled
        "print_outcome_tracking": True,
        "print_intelligence": False,  # Requires historical data
        "human_feedback_requests": True,

        # Disable autonomous (no API costs)
        "autonomous_mode": False,
        "autonomous_full_time": False,

        # Keep discovery enabled
        "network_discovery": True,
    }
)

TESTING_MODE = Preset(
    id="testing",
    name="Testing Mode",
    description="Enable specific hardware for testing (cameras + one printer)",
    features={
        # Disable cloud services
        "perplexity_api": False,
        "openai_api": False,
        "anthropic_api": False,
        "zoo_cad_api": False,
        "tripo_cad_api": False,

        # Local only
        "offline_mode": True,
        "cloud_routing": False,
        "function_calling": True,

        # Enable cameras for testing
        "camera_capture": True,
        "bamboo_camera": False,  # Pick one to test
        "raspberry_pi_cameras": True,  # Test Pi cameras

        # Enable MinIO for snapshot testing
        "minio_snapshot_upload": True,

        # Enable monitoring for testing
        "print_outcome_tracking": True,
        "print_intelligence": False,
        "human_feedback_requests": True,

        # Disable autonomous
        "autonomous_mode": False,
        "autonomous_full_time": False,

        # Enable discovery for finding devices
        "network_discovery": True,
    }
)

MINIMAL_MODE = Preset(
    id="minimal",
    name="Minimal Mode",
    description="Only core features enabled, everything else off",
    features={
        # Disable all external services
        "perplexity_api": False,
        "openai_api": False,
        "anthropic_api": False,
        "zoo_cad_api": False,
        "tripo_cad_api": False,

        # Offline only
        "offline_mode": True,
        "cloud_routing": False,
        "function_calling": False,  # No device control

        # Disable all cameras
        "camera_capture": False,
        "bamboo_camera": False,
        "raspberry_pi_cameras": False,

        # Disable MinIO
        "minio_snapshot_upload": False,

        # Minimal monitoring
        "print_outcome_tracking": False,
        "print_intelligence": False,
        "human_feedback_requests": False,

        # No autonomous
        "autonomous_mode": False,
        "autonomous_full_time": False,

        # No discovery
        "network_discovery": False,
    }
)


# ============================================================================
# Preset Registry
# ============================================================================

ALL_PRESETS = {
    "development": DEVELOPMENT_MODE,
    "production": PRODUCTION_MODE,
    "cost_saving": COST_SAVING_MODE,
    "testing": TESTING_MODE,
    "minimal": MINIMAL_MODE,
}


def get_preset(preset_id: str) -> Preset | None:
    """Get preset by ID.

    Args:
        preset_id: Preset identifier

    Returns:
        Preset or None if not found
    """
    return ALL_PRESETS.get(preset_id)


def list_presets() -> list[Preset]:
    """Get all available presets.

    Returns:
        List of all presets
    """
    return list(ALL_PRESETS.values())


def estimate_cost_impact(preset: Preset) -> dict:
    """Estimate cost impact of applying a preset.

    Args:
        preset: Preset to analyze

    Returns:
        Dict with cost estimates
    """
    costs = {
        "perplexity_api": {"min": 0.001, "max": 0.005, "unit": "per query"},
        "openai_api": {"min": 0.01, "max": 0.06, "unit": "per query"},
        "anthropic_api": {"min": 0.01, "max": 0.08, "unit": "per query"},
        "zoo_cad_api": {"min": 0.05, "max": 0.20, "unit": "per generation"},
        "tripo_cad_api": {"min": 0.10, "max": 0.30, "unit": "per generation"},
    }

    enabled_services = []
    total_min_per_query = 0.0
    total_max_per_query = 0.0

    for feature_id, enabled in preset.features.items():
        if enabled and feature_id in costs:
            enabled_services.append(feature_id)
            total_min_per_query += costs[feature_id]["min"]
            total_max_per_query += costs[feature_id]["max"]

    return {
        "enabled_paid_services": enabled_services,
        "estimated_cost_per_query": {
            "min": round(total_min_per_query, 3),
            "max": round(total_max_per_query, 3),
            "unit": "USD"
        },
        "estimated_daily_cost_100_queries": {
            "min": round(total_min_per_query * 100, 2),
            "max": round(total_max_per_query * 100, 2),
            "unit": "USD"
        }
    }
