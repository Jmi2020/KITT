"""I/O Control Dashboard API.

REST endpoints for managing external device integrations and feature flags
with dependency validation and intelligent restart handling.
"""

from typing import Dict, List, Optional

import redis
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from common.io_control import (
    FeatureCategory,
    FeatureDefinition,
    RestartScope,
    feature_registry,
    get_tool_availability,
    get_preset,
    list_presets,
    ALL_PRESETS,
)
from common.io_control.state_manager import FeatureStateManager
from common.io_control.tool_availability import ToolAvailability

router = APIRouter(prefix="/api/io-control", tags=["io-control"])

# Initialize state manager
try:
    redis_client = redis.Redis(host="redis", port=6379, db=0, decode_responses=False)
    redis_client.ping()
except:
    redis_client = None

state_manager = FeatureStateManager(redis_client=redis_client)


# ============================================================================
# Request/Response Models
# ============================================================================


class FeatureResponse(BaseModel):
    """Feature definition for API responses."""

    id: str
    name: str
    description: str
    category: str
    env_var: str
    default_value: bool | str | int | float
    current_value: bool | str | int | float
    restart_scope: str
    requires: List[str]
    enables: List[str]
    conflicts_with: List[str]
    validation_message: Optional[str] = None
    setup_instructions: Optional[str] = None
    docs_url: Optional[str] = None

    # Computed fields
    can_enable: bool = True
    can_disable: bool = True
    dependencies_met: bool = True


class FeatureUpdateRequest(BaseModel):
    """Request to update a feature."""

    feature_id: str
    value: bool | str | int | float
    persist: bool = True
    trigger_restart: bool = True


class BulkUpdateRequest(BaseModel):
    """Request to update multiple features."""

    changes: Dict[str, bool | str | int | float]
    persist: bool = True


class PreviewChangesRequest(BaseModel):
    """Request to preview changes."""

    changes: Dict[str, bool | str | int | float]


class PreviewChangesResponse(BaseModel):
    """Response with change preview."""

    dependencies: Dict[str, List[str]]
    costs: Dict
    restarts: Dict
    conflicts: Dict[str, List[str]]
    health_warnings: Dict[str, str]


class HealthStatusResponse(BaseModel):
    """Health status for enabled features."""

    feature_id: str
    feature_name: str
    is_healthy: bool
    message: str


class ToolAvailabilityResponse(BaseModel):
    """Tool availability status."""

    available_tools: Dict[str, bool]
    enabled_functions: List[str]
    unavailable_message: str


class PresetResponse(BaseModel):
    """Preset configuration."""

    id: str
    name: str
    description: str
    features: Dict[str, bool | str | int | float]
    cost_estimate: Dict


class DashboardStateResponse(BaseModel):
    """Complete dashboard state."""

    features_by_category: Dict[str, List[FeatureResponse]]
    current_state: Dict[str, bool | str | int | float]
    restart_pending: bool = False
    restart_services: List[str] = []
    tool_availability: Dict[str, bool] | None = None
    enabled_functions: List[str] | None = None
    unavailable_message: str | None = None
    health_warnings: List[HealthStatusResponse] | None = None


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/features", response_model=List[FeatureResponse])
async def list_features():
    """List all features with current state."""
    current_state = state_manager.get_current_state()
    features = []

    for feature_id, feature in feature_registry.features.items():
        current_value = current_state.get(feature_id, feature.default_value)

        # Check if can be enabled/disabled
        can_enable, _ = feature_registry.can_enable(feature_id, current_state)
        can_disable, _ = feature_registry.can_disable(feature_id, current_state)

        # Check if dependencies are met
        dependencies_met = True
        if feature.requires:
            dependencies_met = all(current_state.get(req, False) for req in feature.requires)

        features.append(
            FeatureResponse(
                id=feature.id,
                name=feature.name,
                description=feature.description,
                category=feature.category.value,
                env_var=feature.env_var,
                default_value=feature.default_value,
                current_value=current_value,
                restart_scope=feature.restart_scope.value,
                requires=feature.requires,
                enables=feature.enables,
                conflicts_with=feature.conflicts_with,
                validation_message=feature.validation_message,
                setup_instructions=feature.setup_instructions,
                docs_url=feature.docs_url,
                can_enable=can_enable,
                can_disable=can_disable,
                dependencies_met=dependencies_met,
            )
        )

    return features


@router.get("/features/category/{category}", response_model=List[FeatureResponse])
async def list_features_by_category(category: str):
    """List features in a specific category."""
    try:
        cat_enum = FeatureCategory(category)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

    current_state = state_manager.get_current_state()
    category_features = feature_registry.list_by_category(cat_enum)
    features = []

    for feature in category_features:
        current_value = current_state.get(feature.id, feature.default_value)
        can_enable, _ = feature_registry.can_enable(feature.id, current_state)
        can_disable, _ = feature_registry.can_disable(feature.id, current_state)
        dependencies_met = all(current_state.get(req, False) for req in feature.requires)

        features.append(
            FeatureResponse(
                id=feature.id,
                name=feature.name,
                description=feature.description,
                category=feature.category.value,
                env_var=feature.env_var,
                default_value=feature.default_value,
                current_value=current_value,
                restart_scope=feature.restart_scope.value,
                requires=feature.requires,
                enables=feature.enables,
                conflicts_with=feature.conflicts_with,
                validation_message=feature.validation_message,
                setup_instructions=feature.setup_instructions,
                docs_url=feature.docs_url,
                can_enable=can_enable,
                can_disable=can_disable,
                dependencies_met=dependencies_met,
            )
        )

    return features


@router.get("/features/{feature_id}", response_model=FeatureResponse)
async def get_feature(feature_id: str):
    """Get a specific feature with current state."""
    feature = feature_registry.get(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

    current_state = state_manager.get_current_state()
    current_value = current_state.get(feature_id, feature.default_value)
    can_enable, _ = feature_registry.can_enable(feature_id, current_state)
    can_disable, _ = feature_registry.can_disable(feature_id, current_state)
    dependencies_met = all(current_state.get(req, False) for req in feature.requires)

    return FeatureResponse(
        id=feature.id,
        name=feature.name,
        description=feature.description,
        category=feature.category.value,
        env_var=feature.env_var,
        default_value=feature.default_value,
        current_value=current_value,
        restart_scope=feature.restart_scope.value,
        requires=feature.requires,
        enables=feature.enables,
        conflicts_with=feature.conflicts_with,
        validation_message=feature.validation_message,
        setup_instructions=feature.setup_instructions,
        docs_url=feature.docs_url,
        can_enable=can_enable,
        can_disable=can_disable,
        dependencies_met=dependencies_met,
    )


@router.post("/features/{feature_id}")
async def update_feature(feature_id: str, request: FeatureUpdateRequest):
    """Update a single feature."""
    success, error = state_manager.set_feature(
        feature_id=request.feature_id,
        value=request.value,
        persist=request.persist,
        trigger_restart=request.trigger_restart,
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {"success": True, "feature_id": feature_id, "value": request.value}


@router.post("/features/bulk-update")
async def bulk_update_features(request: BulkUpdateRequest):
    """Update multiple features at once."""
    success, errors = state_manager.bulk_set(request.changes, persist=request.persist)

    if not success:
        raise HTTPException(status_code=400, detail={"errors": errors})

    return {"success": True, "updated_count": len(request.changes)}


@router.get("/state", response_model=DashboardStateResponse)
async def get_dashboard_state():
    """Get complete dashboard state grouped by category."""
    current_state = state_manager.get_current_state()
    tool_checker = ToolAvailability(redis_client=redis_client)
    tool_availability = tool_checker.get_available_tools()
    enabled_functions = tool_checker.get_enabled_function_names()
    unavailable_message = tool_checker.get_unavailable_tools_message()
    health_status = feature_registry.get_health_status(current_state)
    health_warnings = []
    for feature_id, (is_healthy, message) in health_status.items():
        feature = feature_registry.get(feature_id)
        if feature and not is_healthy:
            health_warnings.append(
                HealthStatusResponse(
                    feature_id=feature_id,
                    feature_name=feature.name,
                    is_healthy=is_healthy,
                    message=message,
                )
            )

    # Group features by category
    features_by_category = {}
    for category in FeatureCategory:
        category_features = feature_registry.list_by_category(category)
        features = []

        for feature in category_features:
            current_value = current_state.get(feature.id, feature.default_value)
            can_enable, _ = feature_registry.can_enable(feature.id, current_state)
            can_disable, _ = feature_registry.can_disable(feature.id, current_state)
            dependencies_met = all(current_state.get(req, False) for req in feature.requires)

            features.append(
                FeatureResponse(
                    id=feature.id,
                    name=feature.name,
                    description=feature.description,
                    category=feature.category.value,
                    env_var=feature.env_var,
                    default_value=feature.default_value,
                    current_value=current_value,
                    restart_scope=feature.restart_scope.value,
                    requires=feature.requires,
                    enables=feature.enables,
                    conflicts_with=feature.conflicts_with,
                    validation_message=feature.validation_message,
                    setup_instructions=feature.setup_instructions,
                    docs_url=feature.docs_url,
                    can_enable=can_enable,
                    can_disable=can_disable,
                    dependencies_met=dependencies_met,
                )
            )

        if features:
            features_by_category[category.value] = features

    return DashboardStateResponse(
        features_by_category=features_by_category,
        current_state=current_state,
        tool_availability=tool_availability,
        enabled_functions=enabled_functions,
        unavailable_message=unavailable_message,
        health_warnings=health_warnings or None,
    )


@router.get("/validate")
async def validate_current_state():
    """Validate current feature state for issues."""
    current_state = state_manager.get_current_state()
    issues = []

    for feature_id, enabled in current_state.items():
        if enabled and isinstance(enabled, bool):
            can_enable, reason = feature_registry.can_enable(feature_id, current_state)
            if not can_enable:
                feature = feature_registry.get(feature_id)
                if feature:
                    issues.append({"feature_id": feature_id, "feature_name": feature.name, "issue": reason})

    return {"valid": len(issues) == 0, "issues": issues}


# ============================================================================
# New Enhancement Endpoints
# ============================================================================


@router.get("/health", response_model=List[HealthStatusResponse])
async def get_health_status():
    """Get health status for all enabled features."""
    current_state = state_manager.get_current_state()
    health_status = feature_registry.get_health_status(current_state)

    results = []
    for feature_id, (is_healthy, message) in health_status.items():
        feature = feature_registry.get(feature_id)
        if feature:
            results.append(
                HealthStatusResponse(
                    feature_id=feature_id,
                    feature_name=feature.name,
                    is_healthy=is_healthy,
                    message=message,
                )
            )

    return results


@router.get("/features/{feature_id}/dependencies")
async def get_feature_dependencies(feature_id: str):
    """Get missing dependencies for a feature."""
    feature = feature_registry.get(feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail=f"Feature not found: {feature_id}")

    missing = state_manager.get_missing_dependencies(feature_id)
    resolved = state_manager.resolve_dependencies(feature_id)

    return {
        "feature_id": feature_id,
        "missing_dependencies": missing,
        "auto_resolved": resolved,
    }


@router.post("/preview", response_model=PreviewChangesResponse)
async def preview_changes(request: PreviewChangesRequest):
    """Preview the impact of applying changes."""
    preview = state_manager.preview_changes(request.changes)

    return PreviewChangesResponse(
        dependencies=preview["dependencies"],
        costs=preview["costs"],
        restarts=preview["restarts"],
        conflicts=preview["conflicts"],
        health_warnings=preview["health_warnings"],
    )


@router.get("/tool-availability", response_model=ToolAvailabilityResponse)
async def get_tool_availability_status():
    """Get tool availability status based on current I/O control settings."""
    tool_checker = get_tool_availability(redis_client)
    available_tools = tool_checker.get_available_tools()
    enabled_functions = tool_checker.get_enabled_function_names()
    unavailable_message = tool_checker.get_unavailable_tools_message()

    return ToolAvailabilityResponse(
        available_tools=available_tools,
        enabled_functions=enabled_functions,
        unavailable_message=unavailable_message,
    )


@router.get("/presets", response_model=List[PresetResponse])
async def get_presets():
    """List all available presets."""
    from common.io_control.presets import estimate_cost_impact

    presets = list_presets()
    results = []

    for preset in presets:
        cost_estimate = estimate_cost_impact(preset)
        results.append(
            PresetResponse(
                id=preset.id,
                name=preset.name,
                description=preset.description,
                features=preset.features,
                cost_estimate=cost_estimate,
            )
        )

    return results


@router.get("/presets/{preset_id}", response_model=PresetResponse)
async def get_preset_details(preset_id: str):
    """Get details for a specific preset."""
    from common.io_control.presets import estimate_cost_impact

    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")

    cost_estimate = estimate_cost_impact(preset)

    return PresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        features=preset.features,
        cost_estimate=cost_estimate,
    )


@router.post("/presets/{preset_id}/apply")
async def apply_preset(preset_id: str, persist: bool = True):
    """Apply a preset configuration."""
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset not found: {preset_id}")

    # Apply all preset features
    success, errors = state_manager.bulk_set(preset.features, persist=persist)

    if not success:
        raise HTTPException(status_code=400, detail={"errors": errors})

    return {
        "success": True,
        "preset_id": preset_id,
        "preset_name": preset.name,
        "updated_count": len(preset.features),
    }
