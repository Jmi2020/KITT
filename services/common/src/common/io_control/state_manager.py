"""Feature State Manager.

Manages feature flag state with Redis hot-reload and .env persistence.
Handles intelligent restart logic for Docker services.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import redis

from common.config import Settings
from common.io_control.feature_registry import RestartScope, feature_registry
from common.io_control.presets import estimate_cost_impact, Preset
from common.logging import get_logger

LOGGER = get_logger(__name__)


class FeatureStateManager:
    """Manages feature state with hot-reload and persistence."""

    def __init__(self, redis_client: Optional[redis.Redis] = None, env_file: Optional[Path] = None):
        """Initialize state manager.

        Args:
            redis_client: Redis client for hot-reload state (optional)
            env_file: Path to .env file for persistence (defaults to project root)
        """
        self.redis = redis_client
        self.env_file = env_file or Path("/home/user/KITT/.env")
        self.settings = Settings()

    # ========================================================================
    # Preview and Validation
    # ========================================================================

    def preview_changes(
        self, changes: Dict[str, bool | str]
    ) -> Dict[str, any]:
        """Preview the impact of applying changes.

        Args:
            changes: Dict of feature_id -> new_value

        Returns:
            Dict with:
                - dependencies: Missing dependencies that need to be enabled
                - costs: Cost impact estimate
                - restarts: Services that will restart
                - conflicts: Features that would break
                - health_warnings: Features with known health issues
        """
        current_state = self.get_current_state()
        preview = {
            "dependencies": {},
            "costs": {"enabled_paid_services": [], "estimated_cost_per_query": {}},
            "restarts": {"scopes": set(), "services": []},
            "conflicts": {},
            "health_warnings": {},
        }

        # Check dependencies for features being enabled
        for feature_id, new_value in changes.items():
            if new_value and isinstance(new_value, bool):
                missing_deps = self._check_missing_dependencies(feature_id, current_state, changes)
                if missing_deps:
                    preview["dependencies"][feature_id] = missing_deps

        # Check conflicts for features being disabled
        for feature_id, new_value in changes.items():
            if not new_value and isinstance(new_value, bool):
                conflicts = self._check_dependents(feature_id, current_state, changes)
                if conflicts:
                    preview["conflicts"][feature_id] = conflicts

        # Calculate cost impact (for enabled API services)
        cost_features = {}
        for feature_id, new_value in changes.items():
            feature = feature_registry.get(feature_id)
            if feature and new_value:
                cost_features[feature_id] = new_value

        if cost_features:
            # Build a temporary preset to estimate costs
            temp_preset = Preset(
                id="preview",
                name="Preview",
                description="Temporary preset for cost estimation",
                features=cost_features,
            )
            preview["costs"] = estimate_cost_impact(temp_preset)

        # Determine restart scopes
        restart_scopes = set()
        for feature_id in changes.keys():
            feature = feature_registry.get(feature_id)
            if feature and feature.restart_scope != RestartScope.NONE:
                restart_scopes.add(feature.restart_scope)
                preview["restarts"]["scopes"].add(feature.restart_scope.value)

        # Map scopes to services
        if RestartScope.SERVICE in restart_scopes:
            preview["restarts"]["services"].append("fabrication")
        if RestartScope.LLAMACPP in restart_scopes:
            preview["restarts"]["services"].append("llama.cpp servers")
        if RestartScope.STACK in restart_scopes:
            preview["restarts"]["services"] = ["All Docker services"]

        # Convert set to list for JSON serialization
        preview["restarts"]["scopes"] = list(preview["restarts"]["scopes"])

        # Check health for features being enabled
        for feature_id, new_value in changes.items():
            if new_value and isinstance(new_value, bool):
                feature = feature_registry.get(feature_id)
                if feature and feature.health_check:
                    is_healthy, message = feature_registry.check_health(feature_id)
                    if not is_healthy:
                        preview["health_warnings"][feature_id] = message

        return preview

    def get_missing_dependencies(self, feature_id: str) -> list[str]:
        """Get list of missing dependencies for a feature.

        Args:
            feature_id: Feature to check

        Returns:
            List of feature IDs that are dependencies but not enabled
        """
        current_state = self.get_current_state()
        return self._check_missing_dependencies(feature_id, current_state, {})

    def _check_missing_dependencies(
        self,
        feature_id: str,
        current_state: Dict[str, bool | str],
        pending_changes: Dict[str, bool | str],
    ) -> list[str]:
        """Check for missing dependencies considering pending changes.

        Args:
            feature_id: Feature to check
            current_state: Current feature state
            pending_changes: Changes being applied

        Returns:
            List of missing dependency feature IDs
        """
        feature = feature_registry.get(feature_id)
        if not feature or not feature.requires:
            return []

        missing = []
        for dep_id in feature.requires:
            # Check if dependency will be enabled in pending changes
            if dep_id in pending_changes:
                if not pending_changes[dep_id]:
                    missing.append(dep_id)
            # Otherwise check current state
            elif not current_state.get(dep_id):
                missing.append(dep_id)

        return missing

    def _check_dependents(
        self,
        feature_id: str,
        current_state: Dict[str, bool | str],
        pending_changes: Dict[str, bool | str],
    ) -> list[str]:
        """Check which enabled features depend on this one.

        Args:
            feature_id: Feature being disabled
            current_state: Current feature state
            pending_changes: Changes being applied

        Returns:
            List of feature IDs that would break
        """
        dependents = []

        for other_id, other_feature in feature_registry.features.items():
            # Skip if this feature doesn't depend on the one we're disabling
            if not other_feature.requires or feature_id not in other_feature.requires:
                continue

            # Check if this dependent is currently enabled
            if other_id in pending_changes:
                is_enabled = pending_changes[other_id]
            else:
                is_enabled = current_state.get(other_id)

            if is_enabled:
                dependents.append(other_id)

        return dependents

    def resolve_dependencies(
        self, feature_id: str, current_state: Optional[Dict[str, bool | str]] = None
    ) -> Dict[str, bool]:
        """Auto-resolve dependencies for a feature.

        Args:
            feature_id: Feature to enable
            current_state: Optional current state (fetched if not provided)

        Returns:
            Dict of additional features to enable (feature_id -> True)
        """
        if current_state is None:
            current_state = self.get_current_state()

        feature = feature_registry.get(feature_id)
        if not feature or not feature.requires:
            return {}

        to_enable = {}
        for dep_id in feature.requires:
            if not current_state.get(dep_id):
                to_enable[dep_id] = True

                # Recursively resolve dependencies of dependencies
                nested_deps = self.resolve_dependencies(dep_id, current_state)
                to_enable.update(nested_deps)

        return to_enable

    # ========================================================================
    # State Reading
    # ========================================================================

    def get_current_state(self) -> Dict[str, bool | str]:
        """Get current state of all features.

        Checks Redis first (hot-reload), falls back to Settings.

        Returns:
            Dict mapping feature_id to current value
        """
        state = {}

        for feature_id, feature in feature_registry.features.items():
            # Check Redis first for hot-reloaded values
            if self.redis:
                redis_key = f"feature_flag:{feature.env_var}"
                redis_value = self.redis.get(redis_key)
                if redis_value is not None:
                    state[feature_id] = self._parse_value(redis_value.decode())
                    continue

            # Fall back to Settings (from .env)
            env_value = getattr(self.settings, feature.env_var.lower(), feature.default_value)
            state[feature_id] = env_value

        return state

    def get_feature_value(self, feature_id: str) -> Optional[bool | str]:
        """Get current value of a specific feature.

        Args:
            feature_id: Feature identifier

        Returns:
            Current value or None if feature not found
        """
        feature = feature_registry.get(feature_id)
        if not feature:
            return None

        # Check Redis first
        if self.redis:
            redis_key = f"feature_flag:{feature.env_var}"
            redis_value = self.redis.get(redis_key)
            if redis_value is not None:
                return self._parse_value(redis_value.decode())

        # Fall back to Settings
        return getattr(self.settings, feature.env_var.lower(), feature.default_value)

    # ========================================================================
    # State Writing
    # ========================================================================

    def set_feature_with_deps(
        self,
        feature_id: str,
        value: bool | str,
        persist: bool = True,
        trigger_restart: bool = True,
    ) -> tuple[bool, Optional[str], Dict[str, bool]]:
        """Set feature value with automatic dependency resolution.

        Args:
            feature_id: Feature identifier
            value: New value
            persist: Whether to write to .env file
            trigger_restart: Whether to trigger service restart if needed

        Returns:
            Tuple of (success, error_message, enabled_dependencies)
        """
        # If enabling, check for missing dependencies
        if value and isinstance(value, bool):
            missing_deps = self.get_missing_dependencies(feature_id)
            if missing_deps:
                # Auto-resolve dependencies
                auto_enabled = self.resolve_dependencies(feature_id)

                # Build changes dict
                changes = auto_enabled.copy()
                changes[feature_id] = value

                # Apply all changes
                success, errors = self.bulk_set(changes, persist=persist)
                if success:
                    return True, None, auto_enabled
                else:
                    error_msg = "; ".join(f"{k}: {v}" for k, v in errors.items())
                    return False, error_msg, {}

        # No dependencies, use regular set
        success, error = self.set_feature(feature_id, value, persist, trigger_restart)
        return success, error, {}

    def set_feature(
        self,
        feature_id: str,
        value: bool | str,
        persist: bool = True,
        trigger_restart: bool = True,
    ) -> tuple[bool, Optional[str]]:
        """Set feature value with validation and optional restart.

        Args:
            feature_id: Feature identifier
            value: New value
            persist: Whether to write to .env file
            trigger_restart: Whether to trigger service restart if needed

        Returns:
            Tuple of (success, error_message)
        """
        feature = feature_registry.get(feature_id)
        if not feature:
            return False, f"Feature not found: {feature_id}"

        # Validate change
        current_state = self.get_current_state()

        if value and isinstance(value, bool):  # Enabling
            can_enable, reason = feature_registry.can_enable(feature_id, current_state)
            if not can_enable:
                return False, reason
        elif not value and isinstance(value, bool):  # Disabling
            can_disable, reason = feature_registry.can_disable(feature_id, current_state)
            if not can_disable:
                return False, reason

        # Update Redis for hot-reload
        if self.redis:
            redis_key = f"feature_flag:{feature.env_var}"
            self.redis.set(redis_key, str(value))
            self.redis.set(f"{redis_key}:updated_at", datetime.utcnow().isoformat())
            LOGGER.info(f"Updated feature in Redis: {feature_id} = {value}")

        # Persist to .env if requested
        if persist:
            success = self._update_env_file(feature.env_var, value)
            if not success:
                return False, "Failed to update .env file"

        # Trigger restart if needed
        if trigger_restart and feature.restart_scope != RestartScope.NONE:
            restart_success = self._trigger_restart(feature.restart_scope, feature.id)
            if not restart_success:
                LOGGER.warning(f"Failed to restart services for {feature_id}")
                # Don't fail the operation, just warn
                return True, f"Feature updated but restart failed (restart manually)"

        return True, None

    def bulk_set(
        self, changes: Dict[str, bool | str], persist: bool = True
    ) -> tuple[bool, Dict[str, Optional[str]]]:
        """Set multiple features at once with validation.

        Args:
            changes: Dict of feature_id -> new_value
            persist: Whether to persist to .env

        Returns:
            Tuple of (all_succeeded, errors_by_feature_id)
        """
        errors = {}
        restart_scopes_needed = set()

        # Validate all changes first
        current_state = self.get_current_state()
        for feature_id, value in changes.items():
            feature = feature_registry.get(feature_id)
            if not feature:
                errors[feature_id] = f"Feature not found: {feature_id}"
                continue

            if value and isinstance(value, bool):
                can_enable, reason = feature_registry.can_enable(feature_id, current_state)
                if not can_enable:
                    errors[feature_id] = reason
            elif not value and isinstance(value, bool):
                can_disable, reason = feature_registry.can_disable(feature_id, current_state)
                if not can_disable:
                    errors[feature_id] = reason

        # If any validation failed, abort
        if errors:
            return False, errors

        # Apply all changes
        for feature_id, value in changes.items():
            feature = feature_registry.get(feature_id)
            if not feature:
                continue

            # Update Redis
            if self.redis:
                redis_key = f"feature_flag:{feature.env_var}"
                self.redis.set(redis_key, str(value))

            # Track restart scopes
            if feature.restart_scope != RestartScope.NONE:
                restart_scopes_needed.add(feature.restart_scope)

        # Persist all changes to .env
        if persist:
            for feature_id, value in changes.items():
                feature = feature_registry.get(feature_id)
                if feature:
                    self._update_env_file(feature.env_var, value)

        # Trigger restarts (most disruptive last)
        restart_order = [RestartScope.SERVICE, RestartScope.LLAMACPP, RestartScope.STACK]
        for scope in restart_order:
            if scope in restart_scopes_needed:
                self._trigger_restart(scope, "bulk_update")

        return True, {}

    # ========================================================================
    # File Operations
    # ========================================================================

    def _update_env_file(self, env_var: str, value: bool | str) -> bool:
        """Update .env file with new value.

        Args:
            env_var: Environment variable name
            value: New value

        Returns:
            Success boolean
        """
        if not self.env_file.exists():
            LOGGER.error(f".env file not found: {self.env_file}")
            return False

        try:
            # Read current content
            content = self.env_file.read_text()
            lines = content.split("\n")

            # Find and update the line
            updated = False
            value_str = str(value).lower() if isinstance(value, bool) else str(value)

            for i, line in enumerate(lines):
                # Skip comments and empty lines
                if line.strip().startswith("#") or not line.strip():
                    continue

                # Check if this line sets our variable
                if "=" in line:
                    var_name = line.split("=")[0].strip()
                    if var_name == env_var:
                        lines[i] = f"{env_var}={value_str}"
                        updated = True
                        break

            # If variable not found, append it
            if not updated:
                lines.append(f"{env_var}={value_str}")

            # Write back
            self.env_file.write_text("\n".join(lines))
            LOGGER.info(f"Updated .env: {env_var} = {value_str}")
            return True

        except Exception as e:
            LOGGER.error(f"Failed to update .env file: {e}", exc_info=True)
            return False

    # ========================================================================
    # Restart Logic
    # ========================================================================

    def _trigger_restart(self, scope: RestartScope, feature_id: str) -> bool:
        """Trigger restart based on scope.

        Args:
            scope: Restart scope
            feature_id: Feature that triggered restart (for logging)

        Returns:
            Success boolean
        """
        LOGGER.info(f"Triggering restart for {feature_id}: {scope.value}")

        try:
            if scope == RestartScope.SERVICE:
                # Restart fabrication service (most common)
                return self._restart_docker_service("fabrication")

            elif scope == RestartScope.LLAMACPP:
                # Restart llama.cpp servers
                return self._restart_llamacpp()

            elif scope == RestartScope.STACK:
                # Full docker-compose restart
                return self._restart_docker_stack()

            return True

        except Exception as e:
            LOGGER.error(f"Restart failed: {e}", exc_info=True)
            return False

    def _restart_docker_service(self, service_name: str) -> bool:
        """Restart a single Docker service.

        Args:
            service_name: Docker service name

        Returns:
            Success boolean
        """
        try:
            cmd = [
                "docker",
                "compose",
                "-f",
                "/home/user/KITT/infra/compose/docker-compose.yml",
                "restart",
                service_name,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                LOGGER.info(f"Restarted Docker service: {service_name}")
                return True
            else:
                LOGGER.error(f"Failed to restart {service_name}: {result.stderr}")
                return False

        except Exception as e:
            LOGGER.error(f"Failed to restart Docker service: {e}", exc_info=True)
            return False

    def _restart_llamacpp(self) -> bool:
        """Restart llama.cpp servers.

        Returns:
            Success boolean
        """
        try:
            # Use the dual-model restart script
            script = Path("/home/user/KITT/ops/scripts/restart-llamacpp-dual.sh")
            if not script.exists():
                LOGGER.warning("llama.cpp restart script not found, skipping")
                return False

            result = subprocess.run([str(script)], capture_output=True, text=True, timeout=120)

            if result.returncode == 0:
                LOGGER.info("Restarted llama.cpp servers")
                return True
            else:
                LOGGER.error(f"Failed to restart llama.cpp: {result.stderr}")
                return False

        except Exception as e:
            LOGGER.error(f"Failed to restart llama.cpp: {e}", exc_info=True)
            return False

    def _restart_docker_stack(self) -> bool:
        """Restart entire Docker Compose stack.

        Returns:
            Success boolean
        """
        try:
            compose_file = Path("/home/user/KITT/infra/compose/docker-compose.yml")

            # Restart all services
            cmd = ["docker", "compose", "-f", str(compose_file), "restart"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)

            if result.returncode == 0:
                LOGGER.info("Restarted Docker Compose stack")
                return True
            else:
                LOGGER.error(f"Failed to restart stack: {result.stderr}")
                return False

        except Exception as e:
            LOGGER.error(f"Failed to restart Docker stack: {e}", exc_info=True)
            return False

    # ========================================================================
    # Utilities
    # ========================================================================

    def _parse_value(self, value_str: str) -> bool | str:
        """Parse string value to appropriate type.

        Args:
            value_str: String value from Redis or .env

        Returns:
            Parsed value (bool or str)
        """
        lower = value_str.lower().strip()
        if lower in ("true", "1", "yes", "on"):
            return True
        elif lower in ("false", "0", "no", "off"):
            return False
        else:
            return value_str
