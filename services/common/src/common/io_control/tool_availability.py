"""Tool Availability Checker for I/O Control.

Provides functions to check which tools/functions are available based on
current I/O control feature flags. Used by LLM routing to filter function
definitions before queries.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from common.config import settings
from common.logging import get_logger

LOGGER = get_logger(__name__)


class ToolAvailability:
    """Check which tools are available based on I/O control settings."""

    def __init__(self, redis_client=None):
        """Initialize tool availability checker.

        Args:
            redis_client: Optional Redis client for hot-reload state
        """
        self.redis = redis_client

    def get_available_tools(self) -> Dict[str, bool]:
        """Get availability status for all tool categories.

        Returns:
            Dict mapping tool category to availability (True/False)
        """
        availability = {
            # API Services
            "perplexity_search": self._check_perplexity(),
            "openai_completion": self._check_openai(),
            "anthropic_completion": self._check_anthropic(),
            "zoo_cad_generation": self._check_zoo_cad(),
            "tripo_cad_generation": self._check_tripo_cad(),

            # Device Control
            "printer_control": self._check_function_calling() and self._check_printers(),
            "camera_capture": self._check_camera(),

            # Storage
            "minio_upload": self._check_minio(),

            # Routing
            "cloud_routing": not self._check_offline_mode(),
            "function_calling": self._check_function_calling(),

            # Autonomous
            "autonomous_execution": self._check_autonomous(),
        }

        # Derived application-level tools
        availability["research_deep"] = availability["perplexity_search"] and availability["cloud_routing"]
        availability["web_search"] = True  # free, local
        availability["openai_chat"] = availability["openai_completion"] and availability["cloud_routing"]
        availability["anthropic_chat"] = availability["anthropic_completion"] and availability["cloud_routing"]

        return availability

    def get_enabled_function_names(self) -> List[str]:
        """Get list of function names that should be exposed to LLM.

        Returns:
            List of function names (e.g., ["control_printer", "generate_cad"])
        """
        available = self.get_available_tools()
        enabled_functions = []

        # Map tool availability to function names
        if available["printer_control"]:
            enabled_functions.extend([
                "control_printer",
                "get_printer_status",
                "queue_print_job",
            ])

        if available["zoo_cad_generation"]:
            enabled_functions.append("generate_cad_zoo")

        if available["tripo_cad_generation"]:
            enabled_functions.append("generate_cad_tripo")

        if available["camera_capture"]:
            enabled_functions.extend([
                "capture_snapshot",
                "list_snapshots",
            ])

        if available["perplexity_search"]:
            enabled_functions.append("search_web")

        return enabled_functions

    def should_allow_cloud_routing(self) -> bool:
        """Check if cloud routing is allowed.

        Returns:
            True if cloud APIs can be used for escalation
        """
        # Check OFFLINE_MODE from Redis (hot-reload) or Settings
        offline = self._get_feature_value("OFFLINE_MODE", False)
        return not offline

    def get_unavailable_tools_message(self) -> str:
        """Get human-readable message about unavailable tools.

        Returns:
            Message listing disabled tools and how to enable them
        """
        available = self.get_available_tools()
        unavailable = [name for name, is_available in available.items() if not is_available]

        if not unavailable:
            return "All tools are available."

        lines = ["The following tools are currently disabled:"]
        for tool_name in unavailable:
            hint = self._get_enable_hint(tool_name)
            lines.append(f"  - {tool_name}: {hint}")

        lines.append("\nEnable tools via: kitty-io-control or Web UI at /api/io-control")
        return "\n".join(lines)

    # ========================================================================
    # Feature Checkers
    # ========================================================================

    def _check_perplexity(self) -> bool:
        """Check if Perplexity API is available."""
        api_key = self._get_feature_value("PERPLEXITY_API_KEY", "")
        return bool(api_key and api_key != "***")

    def _check_openai(self) -> bool:
        """Check if OpenAI API is available."""
        api_key = self._get_feature_value("OPENAI_API_KEY", "")
        return bool(api_key and api_key != "***")

    def _check_anthropic(self) -> bool:
        """Check if Anthropic API is available."""
        api_key = self._get_feature_value("ANTHROPIC_API_KEY", "")
        return bool(api_key and api_key != "***")

    def _check_zoo_cad(self) -> bool:
        """Check if Zoo CAD API is available."""
        api_key = self._get_feature_value("ZOO_API_KEY", "")
        offline = self._check_offline_mode()
        return bool(api_key and api_key != "***" and not offline)

    def _check_tripo_cad(self) -> bool:
        """Check if Tripo CAD API is available."""
        api_key = self._get_feature_value("TRIPO_API_KEY", "")
        offline = self._check_offline_mode()
        return bool(api_key and api_key != "***" and not offline)

    def _check_function_calling(self) -> bool:
        """Check if function calling is enabled."""
        return self._get_feature_value("ENABLE_FUNCTION_CALLING", True)

    def _check_printers(self) -> bool:
        """Check if any printers are configured."""
        # At least one printer IP should be set
        bamboo = self._get_feature_value("BAMBOO_IP", "")
        snapmaker = self._get_feature_value("SNAPMAKER_IP", "")
        elegoo = self._get_feature_value("ELEGOO_IP", "")
        return bool(bamboo or snapmaker or elegoo)

    def _check_camera(self) -> bool:
        """Check if camera capture is enabled."""
        return self._get_feature_value("ENABLE_CAMERA_CAPTURE", False)

    def _check_minio(self) -> bool:
        """Check if MinIO uploads are enabled."""
        return self._get_feature_value("ENABLE_MINIO_SNAPSHOT_UPLOAD", False)

    def _check_offline_mode(self) -> bool:
        """Check if offline mode is enabled."""
        return self._get_feature_value("OFFLINE_MODE", False)

    def _check_autonomous(self) -> bool:
        """Check if autonomous mode is enabled."""
        return self._get_feature_value("AUTONOMOUS_ENABLED", False)

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_feature_value(self, env_var: str, default: any) -> any:
        """Get feature value from Redis (hot-reload) or Settings.

        Args:
            env_var: Environment variable name
            default: Default value if not found

        Returns:
            Feature value
        """
        # Check Redis first (hot-reload)
        if self.redis:
            redis_key = f"feature_flag:{env_var}"
            redis_value = self.redis.get(redis_key)
            if redis_value is not None:
                return self._parse_value(redis_value.decode())

        # Fall back to Settings (.env)
        return getattr(settings, env_var.lower(), default)

    def _parse_value(self, value: str) -> bool | str:
        """Parse string value to bool or str.

        Args:
            value: String value

        Returns:
            Parsed value
        """
        if value.lower() in ("true", "1", "yes"):
            return True
        elif value.lower() in ("false", "0", "no"):
            return False
        else:
            return value

    def _get_enable_hint(self, tool_name: str) -> str:
        """Get hint for how to enable a tool.

        Args:
            tool_name: Tool name

        Returns:
            Hint message
        """
        hints = {
            "perplexity_search": "Add PERPLEXITY_API_KEY to .env",
            "openai_completion": "Add OPENAI_API_KEY to .env",
            "anthropic_completion": "Add ANTHROPIC_API_KEY to .env",
            "openai_chat": "Add OPENAI_API_KEY to .env",
            "anthropic_chat": "Add ANTHROPIC_API_KEY to .env",
            "research_deep": "Add PERPLEXITY_API_KEY and enable cloud routing (disable OFFLINE_MODE)",
            "zoo_cad_generation": "Add ZOO_API_KEY to .env and disable offline mode",
            "tripo_cad_generation": "Add TRIPO_API_KEY to .env and disable offline mode",
            "printer_control": "Enable ENABLE_FUNCTION_CALLING and configure printer IPs",
            "camera_capture": "Enable ENABLE_CAMERA_CAPTURE in I/O Control",
            "minio_upload": "Enable ENABLE_MINIO_SNAPSHOT_UPLOAD in I/O Control",
            "cloud_routing": "Disable OFFLINE_MODE in I/O Control",
            "function_calling": "Enable ENABLE_FUNCTION_CALLING in I/O Control",
            "autonomous_execution": "Enable AUTONOMOUS_ENABLED in I/O Control",
        }
        return hints.get(tool_name, "Check I/O Control Dashboard")


# Singleton instance for easy access
_tool_availability: Optional[ToolAvailability] = None


def get_tool_availability(redis_client=None) -> ToolAvailability:
    """Get or create tool availability checker singleton.

    Args:
        redis_client: Optional Redis client

    Returns:
        ToolAvailability instance
    """
    global _tool_availability
    if _tool_availability is None:
        _tool_availability = ToolAvailability(redis_client)
    return _tool_availability
