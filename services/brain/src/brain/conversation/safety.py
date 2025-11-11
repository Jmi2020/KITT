# noqa: D401
"""Safety checks and confirmation logic for tool execution."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ToolSafetyMetadata:
    """Safety metadata for a tool from the tool registry."""

    tool_name: str
    server: str
    hazard_class: str  # none, low, medium, high
    requires_confirmation: bool
    confirmation_phrase: Optional[str] = None
    requires_signature: bool = False
    requires_override: bool = False
    budget_tier: str = "free"  # free, paid, premium
    enabled: bool = True
    note: Optional[str] = None


@dataclass
class SafetyResult:
    """Result of a safety check."""

    approved: bool
    requires_confirmation: bool = False
    requires_override: bool = False
    confirmation_phrase: Optional[str] = None
    reason: str = ""
    hazard_class: str = "none"


class SafetyChecker:
    """Check tool execution against safety policies from tool registry."""

    def __init__(self, registry_path: Optional[str] = None) -> None:
        """Initialize safety checker with tool registry.

        Args:
            registry_path: Path to tool_registry.yaml
        """
        if not registry_path:
            registry_path = os.getenv("TOOL_REGISTRY_PATH", "config/tool_registry.yaml")

        self._registry_path = Path(registry_path)
        self._tools: Dict[str, ToolSafetyMetadata] = {}
        self._safety_config: Dict[str, Any] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load tool registry from YAML file."""
        if not self._registry_path.exists():
            logger.warning(f"Tool registry not found at {self._registry_path}, using defaults")
            return

        try:
            with open(self._registry_path) as f:
                data = yaml.safe_load(f)

            # Load tools
            for tool_name, tool_config in data.get("tools", {}).items():
                self._tools[tool_name] = ToolSafetyMetadata(
                    tool_name=tool_name,
                    server=tool_config.get("server", "unknown"),
                    hazard_class=tool_config.get("hazard_class", "none"),
                    requires_confirmation=tool_config.get("requires_confirmation", False),
                    confirmation_phrase=tool_config.get("confirmation_phrase"),
                    requires_signature=tool_config.get("requires_signature", False),
                    requires_override=tool_config.get("requires_override", False),
                    budget_tier=tool_config.get("budget_tier", "free"),
                    enabled=tool_config.get("enabled", True),
                    note=tool_config.get("note"),
                )

            # Load safety policies
            self._safety_config = data.get("safety", {})

            logger.info(f"Loaded {len(self._tools)} tools from registry")

        except Exception as e:
            logger.error(f"Failed to load tool registry: {e}")

    def get_tool_metadata(self, tool_name: str) -> Optional[ToolSafetyMetadata]:
        """Get safety metadata for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            ToolSafetyMetadata if tool exists, None otherwise
        """
        return self._tools.get(tool_name)

    def check_tool_execution(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        override_provided: bool = False,
    ) -> SafetyResult:
        """Check if tool execution is safe and allowed.

        Args:
            tool_name: Name of the tool to execute
            tool_args: Tool arguments
            override_provided: Whether API_OVERRIDE_PASSWORD was provided

        Returns:
            SafetyResult with approval status and requirements
        """
        # Get tool metadata
        metadata = self.get_tool_metadata(tool_name)

        if not metadata:
            # Unknown tool - use conservative defaults
            logger.warning(f"Unknown tool '{tool_name}', applying conservative safety policy")
            return SafetyResult(
                approved=False,
                requires_confirmation=True,
                confirmation_phrase=self._get_default_confirmation_phrase(),
                reason=f"Unknown tool '{tool_name}' - confirmation required",
                hazard_class="medium",
            )

        # Check if tool is enabled
        if not metadata.enabled:
            return SafetyResult(
                approved=False,
                reason=f"Tool '{tool_name}' is disabled in registry",
                hazard_class=metadata.hazard_class,
            )

        # Check if tool requires override (paid/premium services)
        if metadata.requires_override and not override_provided:
            return SafetyResult(
                approved=False,
                requires_override=True,
                reason=f"Tool '{tool_name}' requires API override password (budget_tier: {metadata.budget_tier})",
                hazard_class=metadata.hazard_class,
            )

        # Check if tool requires confirmation
        if metadata.requires_confirmation:
            return SafetyResult(
                approved=False,
                requires_confirmation=True,
                confirmation_phrase=metadata.confirmation_phrase
                or self._get_default_confirmation_phrase(),
                reason=f"Confirmation required for {metadata.hazard_class} hazard tool",
                hazard_class=metadata.hazard_class,
            )

        # Check if high hazard class tools require confirmation (global policy)
        if (
            metadata.hazard_class == "high"
            and self._safety_config.get("enforce_high_hazard_confirmation", True)
        ):
            return SafetyResult(
                approved=False,
                requires_confirmation=True,
                confirmation_phrase=metadata.confirmation_phrase
                or self._get_default_confirmation_phrase(),
                reason="High hazard tool requires confirmation (global policy)",
                hazard_class="high",
            )

        # All checks passed
        return SafetyResult(
            approved=True,
            reason="No safety concerns",
            hazard_class=metadata.hazard_class,
        )

    def _get_default_confirmation_phrase(self) -> str:
        """Get default confirmation phrase from env or config."""
        # First try env variable
        phrase = os.getenv("HAZARD_CONFIRMATION_PHRASE")
        if phrase:
            return phrase

        # Then try safety config
        phrase = self._safety_config.get("default_confirmation_phrase")
        if phrase:
            return phrase

        # Fallback
        return "Confirm: proceed"

    def verify_confirmation(self, user_message: str, required_phrase: str) -> bool:
        """Check if user message contains the required confirmation phrase.

        Args:
            user_message: User's message
            required_phrase: Required confirmation phrase

        Returns:
            True if confirmation phrase found, False otherwise
        """
        # Case-insensitive exact match or contained within message
        user_message_lower = user_message.lower().strip()
        required_phrase_lower = required_phrase.lower().strip()

        return required_phrase_lower in user_message_lower

    def get_confirmation_message(
        self, tool_name: str, tool_args: Dict[str, Any], confirmation_phrase: str, reason: str
    ) -> str:
        """Generate user-facing confirmation request message.

        Args:
            tool_name: Tool name
            tool_args: Tool arguments
            confirmation_phrase: Required phrase
            reason: Reason for confirmation

        Returns:
            Formatted confirmation message
        """
        metadata = self.get_tool_metadata(tool_name)

        # Build the message
        lines = [
            f"⚠️  Confirmation required for '{tool_name}'",
            f"Reason: {reason}",
        ]

        if metadata and metadata.note:
            lines.append(f"Note: {metadata.note}")

        lines.extend(
            [
                "",
                f"To proceed, reply with: {confirmation_phrase}",
                "To cancel, reply with: cancel",
            ]
        )

        return "\n".join(lines)


__all__ = ["SafetyChecker", "SafetyResult", "ToolSafetyMetadata"]
