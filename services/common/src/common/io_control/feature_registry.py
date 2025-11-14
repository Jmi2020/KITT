"""Feature Registry for I/O Control Dashboard.

Centralized registry of all external device integrations and feature flags
with dependency tracking, restart requirements, and validation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable


class FeatureCategory(Enum):
    """Category of feature for grouping in UI."""

    PRINT_MONITORING = "print_monitoring"
    CAMERA = "camera"
    STORAGE = "storage"
    COMMUNICATION = "communication"
    INTELLIGENCE = "intelligence"
    PRINTER = "printer"
    DISCOVERY = "discovery"


class RestartScope(Enum):
    """What needs to restart when feature is toggled."""

    NONE = "none"  # Hot-reload, no restart needed
    SERVICE = "service"  # Single Docker service restart
    STACK = "stack"  # Full docker-compose restart
    LLAMACPP = "llamacpp"  # llama.cpp server restart


@dataclass
class FeatureDefinition:
    """Definition of a feature flag or device integration."""

    # Identity
    id: str  # Unique identifier (e.g., "camera_capture")
    name: str  # Display name
    description: str  # User-facing description
    category: FeatureCategory

    # Configuration
    env_var: str  # Environment variable name
    default_value: bool | str  # Default value

    # Behavior
    restart_scope: RestartScope  # What restarts when toggled
    requires: List[str] = field(default_factory=list)  # Feature IDs this depends on
    enables: List[str] = field(default_factory=list)  # Features this unlocks
    conflicts_with: List[str] = field(default_factory=list)  # Mutually exclusive features

    # Validation
    health_check: Optional[Callable[[], bool]] = None  # Function to check if feature is working
    validation_message: Optional[str] = None  # Message shown when enabling

    # Documentation
    docs_url: Optional[str] = None  # Link to documentation
    setup_instructions: Optional[str] = None  # Brief setup guide


class FeatureRegistry:
    """Registry of all I/O features and external devices."""

    def __init__(self):
        """Initialize feature registry."""
        self.features: Dict[str, FeatureDefinition] = {}
        self._register_all_features()

    def _register_all_features(self):
        """Register all features in the system."""

        # ====================================================================
        # Print Monitoring Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="print_outcome_tracking",
                name="Print Outcome Tracking",
                description="Store print results in database with visual evidence",
                category=FeatureCategory.PRINT_MONITORING,
                env_var="ENABLE_PRINT_OUTCOME_TRACKING",
                default_value=True,
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Requires PostgreSQL database",
            )
        )

        # ====================================================================
        # Camera Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="camera_capture",
                name="Camera Capture (Master)",
                description="Enable all camera snapshot features",
                category=FeatureCategory.CAMERA,
                env_var="ENABLE_CAMERA_CAPTURE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                enables=["bamboo_camera", "raspberry_pi_cameras"],
                validation_message="Master switch for all camera features. Enable specific cameras separately.",
            )
        )

        self.register(
            FeatureDefinition(
                id="bamboo_camera",
                name="Bamboo Labs Camera",
                description="Capture snapshots from Bamboo Labs H2D built-in camera via MQTT",
                category=FeatureCategory.CAMERA,
                env_var="ENABLE_BAMBOO_CAMERA",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["camera_capture", "mqtt_broker"],
                validation_message="Requires BAMBOO_ACCESS_CODE in .env",
                setup_instructions="Get access code from: Printer Settings → Network → WiFi Settings",
            )
        )

        self.register(
            FeatureDefinition(
                id="raspberry_pi_cameras",
                name="Raspberry Pi Cameras",
                description="Capture snapshots from Raspberry Pi cameras via HTTP (Snapmaker, Elegoo)",
                category=FeatureCategory.CAMERA,
                env_var="ENABLE_RASPBERRY_PI_CAMERAS",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["camera_capture"],
                validation_message="Requires SNAPMAKER_CAMERA_URL and ELEGOO_CAMERA_URL in .env",
                setup_instructions="Install mjpg-streamer or picamera2 on Raspberry Pi",
            )
        )

        # ====================================================================
        # Storage Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="minio_snapshot_upload",
                name="MinIO Snapshot Upload",
                description="Upload camera snapshots to MinIO S3-compatible storage",
                category=FeatureCategory.STORAGE,
                env_var="ENABLE_MINIO_SNAPSHOT_UPLOAD",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["camera_capture"],
                validation_message="Requires MinIO server running and credentials configured",
                setup_instructions="Ensure MINIO_ACCESS_KEY and MINIO_SECRET_KEY are set",
            )
        )

        # ====================================================================
        # Communication Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="mqtt_broker",
                name="MQTT Broker",
                description="Message broker for device communication and notifications",
                category=FeatureCategory.COMMUNICATION,
                env_var="MQTT_HOST",
                default_value="mosquitto",
                restart_scope=RestartScope.SERVICE,  # Restart services that use MQTT
                validation_message="Required for printer control and feedback notifications",
            )
        )

        self.register(
            FeatureDefinition(
                id="human_feedback_requests",
                name="Human Feedback Requests",
                description="Send MQTT notifications requesting print review",
                category=FeatureCategory.COMMUNICATION,
                env_var="ENABLE_HUMAN_FEEDBACK_REQUESTS",
                default_value=True,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["mqtt_broker"],
            )
        )

        # ====================================================================
        # Intelligence Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="print_intelligence",
                name="Print Intelligence",
                description="Success prediction and setting recommendations based on historical data",
                category=FeatureCategory.INTELLIGENCE,
                env_var="ENABLE_PRINT_INTELLIGENCE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["print_outcome_tracking"],
                validation_message="Requires minimum 30 historical print outcomes per material/printer combo",
            )
        )

        # ====================================================================
        # Printer Devices
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="bamboo_h2d",
                name="Bamboo Labs H2D",
                description="High-quality FDM printer (325×320×325mm)",
                category=FeatureCategory.PRINTER,
                env_var="BAMBOO_IP",
                default_value="192.168.1.100",
                restart_scope=RestartScope.SERVICE,  # Restart fabrication service
                validation_message="Requires BAMBOO_ACCESS_CODE and BAMBOO_SERIAL",
            )
        )

        self.register(
            FeatureDefinition(
                id="snapmaker_artisan",
                name="Snapmaker Artisan",
                description="3-in-1 platform: 3D/CNC/Laser (400×400×400mm)",
                category=FeatureCategory.PRINTER,
                env_var="SNAPMAKER_IP",
                default_value="192.168.1.150",
                restart_scope=RestartScope.SERVICE,  # Restart fabrication service
            )
        )

        self.register(
            FeatureDefinition(
                id="elegoo_giga",
                name="Elegoo OrangeStorm Giga",
                description="Large format FDM printer (800×800×1000mm)",
                category=FeatureCategory.PRINTER,
                env_var="ELEGOO_IP",
                default_value="192.168.1.200",
                restart_scope=RestartScope.SERVICE,  # Restart fabrication service
            )
        )

        # ====================================================================
        # Discovery Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="network_discovery",
                name="Network Discovery",
                description="Auto-discover printers and devices on local network",
                category=FeatureCategory.DISCOVERY,
                env_var="DISCOVERY_ENABLE_PERIODIC_SCANS",
                default_value=True,
                restart_scope=RestartScope.SERVICE,  # Restart discovery service
            )
        )

    def register(self, feature: FeatureDefinition):
        """Register a feature in the registry.

        Args:
            feature: Feature definition to register
        """
        self.features[feature.id] = feature

    def get(self, feature_id: str) -> Optional[FeatureDefinition]:
        """Get feature by ID.

        Args:
            feature_id: Feature identifier

        Returns:
            Feature definition or None if not found
        """
        return self.features.get(feature_id)

    def list_by_category(self, category: FeatureCategory) -> List[FeatureDefinition]:
        """List all features in a category.

        Args:
            category: Feature category

        Returns:
            List of features in category
        """
        return [f for f in self.features.values() if f.category == category]

    def get_dependencies(self, feature_id: str) -> List[FeatureDefinition]:
        """Get all dependencies of a feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of required features
        """
        feature = self.get(feature_id)
        if not feature:
            return []

        return [self.features[req_id] for req_id in feature.requires if req_id in self.features]

    def get_dependents(self, feature_id: str) -> List[FeatureDefinition]:
        """Get all features that depend on this feature.

        Args:
            feature_id: Feature identifier

        Returns:
            List of dependent features
        """
        dependents = []
        for feat in self.features.values():
            if feature_id in feat.requires:
                dependents.append(feat)
        return dependents

    def can_enable(self, feature_id: str, current_state: Dict[str, bool]) -> tuple[bool, Optional[str]]:
        """Check if a feature can be enabled.

        Args:
            feature_id: Feature to check
            current_state: Current enabled state of all features

        Returns:
            Tuple of (can_enable, reason_if_not)
        """
        feature = self.get(feature_id)
        if not feature:
            return False, f"Feature not found: {feature_id}"

        # Check dependencies
        for req_id in feature.requires:
            if not current_state.get(req_id, False):
                req_feature = self.get(req_id)
                req_name = req_feature.name if req_feature else req_id
                return False, f"Requires '{req_name}' to be enabled first"

        # Check conflicts
        for conflict_id in feature.conflicts_with:
            if current_state.get(conflict_id, False):
                conflict_feature = self.get(conflict_id)
                conflict_name = conflict_feature.name if conflict_feature else conflict_id
                return False, f"Conflicts with '{conflict_name}' (disable it first)"

        return True, None

    def can_disable(self, feature_id: str, current_state: Dict[str, bool]) -> tuple[bool, Optional[str]]:
        """Check if a feature can be disabled.

        Args:
            feature_id: Feature to check
            current_state: Current enabled state of all features

        Returns:
            Tuple of (can_disable, reason_if_not)
        """
        # Check if other enabled features depend on this one
        dependents = self.get_dependents(feature_id)
        enabled_dependents = [d for d in dependents if current_state.get(d.id, False)]

        if enabled_dependents:
            dependent_names = [d.name for d in enabled_dependents]
            return False, f"Required by: {', '.join(dependent_names)} (disable them first)"

        return True, None


# Global registry instance
feature_registry = FeatureRegistry()
