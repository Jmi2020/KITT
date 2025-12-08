"""Feature Registry for I/O Control Dashboard.

Centralized registry of all external device integrations and feature flags
with dependency tracking, restart requirements, and validation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable

from . import health_checks


class FeatureCategory(Enum):
    """Category of feature for grouping in UI."""

    PRINT_MONITORING = "print_monitoring"
    CAMERA = "camera"
    STORAGE = "storage"
    COMMUNICATION = "communication"
    INTELLIGENCE = "intelligence"
    PRINTER = "printer"
    DISCOVERY = "discovery"
    API_SERVICES = "api_services"
    ROUTING = "routing"
    AUTONOMOUS = "autonomous"
    COLLECTIVE_PROVIDERS = "collective_providers"


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

    def restart_impacts(self) -> Dict[str, List[str]]:
        """Map restart scopes to affected services based on registered features."""
        impacts = {
            RestartScope.LLAMACPP.value: ["llama.cpp servers"],
            RestartScope.STACK.value: ["All Docker services"],
        }
        service_scopes = set(
            f.restart_scope for f in self.features.values() if f.restart_scope == RestartScope.SERVICE
        )
        if service_scopes:
            impacts[RestartScope.SERVICE.value] = ["fabrication"]
        return impacts

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

        self.register(
            FeatureDefinition(
                id="parallel_agents",
                name="Parallel Agent Orchestration",
                description="Multi-agent parallel execution for complex queries (3-4x faster)",
                category=FeatureCategory.INTELLIGENCE,
                env_var="ENABLE_PARALLEL_AGENTS",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Enables decompose->parallel execute->synthesize pipeline. Requires multiple LLM slots.",
                docs_url="Research/ParallelAgentExecution.md",
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

        # ====================================================================
        # API Services (External Paid Services)
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="perplexity_api",
                name="Perplexity API (MCP Tier)",
                description="Search-augmented generation for fresh information and research",
                category=FeatureCategory.API_SERVICES,
                env_var="PERPLEXITY_API_KEY",
                default_value="",
                restart_scope=RestartScope.NONE,  # Hot-reload
                health_check=health_checks.check_perplexity_api,
                validation_message="Requires API key from perplexity.ai. Costs ~$0.001-0.005/query",
                setup_instructions="Get API key from https://perplexity.ai → Settings → API",
            )
        )

        self.register(
            FeatureDefinition(
                id="openai_api",
                name="OpenAI API (Frontier Tier)",
                description="GPT-4 and GPT-4 Turbo for complex queries requiring frontier intelligence",
                category=FeatureCategory.API_SERVICES,
                env_var="OPENAI_API_KEY",
                default_value="",
                restart_scope=RestartScope.NONE,  # Hot-reload
                health_check=health_checks.check_openai_api,
                validation_message="Requires API key from OpenAI. Costs ~$0.01-0.06/query depending on model",
                setup_instructions="Get API key from https://platform.openai.com/api-keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="anthropic_api",
                name="Anthropic API (Frontier Tier)",
                description="Claude 3.5 Sonnet for complex reasoning and coding tasks",
                category=FeatureCategory.API_SERVICES,
                env_var="ANTHROPIC_API_KEY",
                default_value="",
                restart_scope=RestartScope.NONE,  # Hot-reload
                health_check=health_checks.check_anthropic_api,
                validation_message="Requires API key from Anthropic. Costs ~$0.01-0.08/query depending on model",
                setup_instructions="Get API key from https://console.anthropic.com/settings/keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="zoo_cad_api",
                name="Zoo CAD API",
                description="Parametric CAD generation (Text-to-CAD with editable parameters)",
                category=FeatureCategory.API_SERVICES,
                env_var="ZOO_API_KEY",
                default_value="",
                restart_scope=RestartScope.NONE,  # Hot-reload
                health_check=health_checks.check_zoo_api,
                validation_message="Requires API key from zoo.dev. First choice for CAD generation",
                setup_instructions="Get API key from https://zoo.dev → Account → API Keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="tripo_cad_api",
                name="Tripo CAD API",
                description="Image-to-3D and Text-to-3D mesh generation",
                category=FeatureCategory.API_SERVICES,
                env_var="TRIPO_API_KEY",
                default_value="",
                restart_scope=RestartScope.NONE,  # Hot-reload
                health_check=health_checks.check_tripo_api,
                validation_message="Requires API key from tripo.ai. Fallback for organic/mesh CAD",
                setup_instructions="Get API key from https://platform.tripo3d.ai/api-keys",
            )
        )

        # ====================================================================
        # Routing Features (Intelligence Tier Selection)
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="cloud_routing",
                name="Cloud Routing",
                description="Enable cloud API escalation (MCP/Frontier) when local confidence is low",
                category=FeatureCategory.ROUTING,
                env_var="OFFLINE_MODE",
                default_value=False,  # False = cloud routing enabled
                restart_scope=RestartScope.NONE,  # Hot-reload
                conflicts_with=["offline_mode"],
                validation_message="Allows using Perplexity/OpenAI/Claude when local model has low confidence",
            )
        )

        self.register(
            FeatureDefinition(
                id="offline_mode",
                name="Offline Mode (Local Only)",
                description="Disable all cloud API calls, use only local llama.cpp models",
                category=FeatureCategory.ROUTING,
                env_var="OFFLINE_MODE",
                default_value=False,  # False = offline mode disabled
                restart_scope=RestartScope.NONE,  # Hot-reload
                conflicts_with=["cloud_routing"],
                validation_message="Disables Perplexity, OpenAI, Claude, Zoo, Tripo. Local-only operation.",
            )
        )

        self.register(
            FeatureDefinition(
                id="function_calling",
                name="Function Calling",
                description="Allow LLMs to call device control functions (printer commands, CAD generation)",
                category=FeatureCategory.ROUTING,
                env_var="ENABLE_FUNCTION_CALLING",
                default_value=True,
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Enables conversational device control via LLM function calls",
            )
        )

        # ====================================================================
        # Autonomous Features
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="autonomous_mode",
                name="Autonomous Mode",
                description="Enable autonomous goal execution and research workflows",
                category=FeatureCategory.AUTONOMOUS,
                env_var="AUTONOMOUS_ENABLED",
                default_value=False,
                restart_scope=RestartScope.SERVICE,  # Restart brain service
                validation_message="KITTY will autonomously pursue goals when system is idle",
                setup_instructions="Set AUTONOMOUS_DAILY_BUDGET_USD to limit costs",
            )
        )

        self.register(
            FeatureDefinition(
                id="autonomous_budget_enforcement",
                name="Autonomous Budget Enforcement",
                description="Enforce daily spending limits for autonomous operations",
                category=FeatureCategory.AUTONOMOUS,
                env_var="AUTONOMOUS_DAILY_BUDGET_USD",
                default_value="5.00",
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["autonomous_mode"],
                validation_message="Daily budget for autonomous API calls and operations",
            )
        )

        self.register(
            FeatureDefinition(
                id="autonomous_full_time",
                name="Autonomous Full-Time Mode",
                description="Run autonomous workflows 24/7 (instead of only when idle)",
                category=FeatureCategory.AUTONOMOUS,
                env_var="AUTONOMOUS_FULL_TIME_MODE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["autonomous_mode"],
                validation_message="⚠️ KITTY will continuously execute goals. May consume budget quickly.",
            )
        )

        # ====================================================================
        # Permission & Budget Controls (Unified Permission System)
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="auto_approve_trivial",
                name="Auto-Approve Trivial API Calls",
                description="Automatically approve external API calls < $0.01 without omega password",
                category=FeatureCategory.AUTONOMOUS,
                env_var="AUTO_APPROVE_TRIVIAL",
                default_value=True,  # Safe default - trivial costs
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Enables seamless UX for very low-cost calls (e.g., Perplexity quick search)",
            )
        )

        self.register(
            FeatureDefinition(
                id="auto_approve_low_cost",
                name="Auto-Approve Low-Cost API Calls",
                description="Automatically approve external API calls < $0.10 without omega password",
                category=FeatureCategory.AUTONOMOUS,
                env_var="AUTO_APPROVE_LOW_COST",
                default_value=False,  # Requires explicit enable
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="⚠️ Budget protection reduced. Only enable if you trust autonomous operations.",
                setup_instructions="Recommended for autonomous research workflows to reduce friction",
            )
        )

        self.register(
            FeatureDefinition(
                id="omega_password",
                name="Omega Password",
                description="Password required for high-cost external API calls (>= $0.10)",
                category=FeatureCategory.AUTONOMOUS,
                env_var="API_OVERRIDE_PASSWORD",
                default_value="omega",
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Change default password for production use",
                setup_instructions="Set strong password in .env: API_OVERRIDE_PASSWORD=your_secret_password",
            )
        )

        self.register(
            FeatureDefinition(
                id="research_budget_per_session",
                name="Research Budget (Per Session)",
                description="Maximum USD spend per autonomous research session",
                category=FeatureCategory.AUTONOMOUS,
                env_var="RESEARCH_BUDGET_USD",
                default_value="2.00",
                restart_scope=RestartScope.NONE,  # Hot-reload
                validation_message="Research sessions auto-stop when budget exhausted",
                setup_instructions="Increase for complex research requiring more external API calls",
            )
        )

        self.register(
            FeatureDefinition(
                id="research_external_call_limit",
                name="Research External Call Limit",
                description="Maximum number of external API calls per research session",
                category=FeatureCategory.AUTONOMOUS,
                env_var="RESEARCH_EXTERNAL_CALL_LIMIT",
                default_value="10",
                restart_scope=RestartScope.NONE,  # Hot-reload
                requires=["research_budget_per_session"],
                validation_message="Hard limit on external calls per session (even if budget remains)",
            )
        )

        # ====================================================================
        # Collective Providers (Multi-Provider Meta-Agent Diversity)
        # ====================================================================

        self.register(
            FeatureDefinition(
                id="enable_openai_collective",
                name="OpenAI Collective",
                description="Enable OpenAI models (GPT-4o-mini) in collective meta-agent for diverse opinions",
                category=FeatureCategory.COLLECTIVE_PROVIDERS,
                env_var="ENABLE_OPENAI_COLLECTIVE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload via ProviderRegistry
                health_check=health_checks.check_openai_api,
                validation_message="💰 Cost: $0.15/1M input tokens, $0.60/1M output tokens. Requires OPENAI_API_KEY.",
                setup_instructions="Get API key from https://platform.openai.com/api-keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="enable_anthropic_collective",
                name="Anthropic Collective",
                description="Enable Anthropic models (Claude Haiku) in collective meta-agent for diverse opinions",
                category=FeatureCategory.COLLECTIVE_PROVIDERS,
                env_var="ENABLE_ANTHROPIC_COLLECTIVE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload via ProviderRegistry
                health_check=health_checks.check_anthropic_api,
                validation_message="💰 Cost: $0.25/1M input tokens, $1.25/1M output tokens. Requires ANTHROPIC_API_KEY.",
                setup_instructions="Get API key from https://console.anthropic.com/settings/keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="enable_mistral_collective",
                name="Mistral Collective",
                description="Enable Mistral models (Mistral-small) in collective meta-agent for diverse opinions",
                category=FeatureCategory.COLLECTIVE_PROVIDERS,
                env_var="ENABLE_MISTRAL_COLLECTIVE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload via ProviderRegistry
                validation_message="💰 Cost: $0.10/1M input tokens, $0.30/1M output tokens. Requires MISTRAL_API_KEY.",
                setup_instructions="Get API key from https://console.mistral.ai/api-keys",
            )
        )

        self.register(
            FeatureDefinition(
                id="enable_perplexity_collective",
                name="Perplexity Collective",
                description="Enable Perplexity models (Sonar) in collective meta-agent for search-augmented opinions",
                category=FeatureCategory.COLLECTIVE_PROVIDERS,
                env_var="ENABLE_PERPLEXITY_COLLECTIVE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload via ProviderRegistry
                health_check=health_checks.check_perplexity_api,
                validation_message="💰 Cost: $0.20/1M tokens (combined). Requires PERPLEXITY_API_KEY.",
                setup_instructions="Get API key from https://perplexity.ai → Settings → API",
            )
        )

        self.register(
            FeatureDefinition(
                id="enable_gemini_collective",
                name="Google Gemini Collective",
                description="Enable Google Gemini models (Flash) in collective meta-agent for diverse opinions",
                category=FeatureCategory.COLLECTIVE_PROVIDERS,
                env_var="ENABLE_GEMINI_COLLECTIVE",
                default_value=False,
                restart_scope=RestartScope.NONE,  # Hot-reload via ProviderRegistry
                validation_message="💰 Cost: $0.075/1M input tokens, $0.30/1M output tokens. Requires GEMINI_API_KEY.",
                setup_instructions="Get API key from https://aistudio.google.com/app/apikey",
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

    def check_health(self, feature_id: str) -> tuple[bool, Optional[str]]:
        """Check health of a feature.

        Args:
            feature_id: Feature to check

        Returns:
            Tuple of (is_healthy, status_message)
        """
        feature = self.get(feature_id)
        if not feature:
            return False, f"Feature not found: {feature_id}"

        if not feature.health_check:
            return True, "No health check defined"

        try:
            is_healthy = feature.health_check()
            if is_healthy:
                return True, "Healthy"
            else:
                return False, "Health check failed (not configured or unreachable)"
        except Exception as e:
            return False, f"Health check error: {str(e)}"

    def get_health_status(self, current_state: Dict[str, bool]) -> Dict[str, tuple[bool, str]]:
        """Get health status for all enabled features.

        Args:
            current_state: Current enabled state of all features

        Returns:
            Dict mapping feature_id to (is_healthy, status_message)
        """
        health_status = {}
        for feature_id, is_enabled in current_state.items():
            if is_enabled:
                health_status[feature_id] = self.check_health(feature_id)
        return health_status

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
