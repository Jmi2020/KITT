"""Configuration loader and JSON Schema validator for command allow-list."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jsonschema import Draft7Validator
from pydantic import Field
from pydantic_settings import BaseSettings


class BrokerSettings(BaseSettings):
    """Broker service configuration."""

    host: str = Field(default="0.0.0.0", alias="BROKER_HOST")
    port: int = Field(default=8777, alias="BROKER_PORT")
    allow_list_path: str = Field(
        default="/etc/kitty/commands.yaml", alias="BROKER_ALLOW_LIST"
    )
    audit_log_path: str = Field(
        default="/var/log/kitty/broker-audit.jsonl", alias="BROKER_AUDIT_LOG"
    )
    service_user: str = Field(default="kitty-runner", alias="BROKER_SERVICE_USER")
    enable_privilege_drop: bool = Field(
        default=True, alias="BROKER_ENABLE_PRIVILEGE_DROP"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


class CommandDefinition:
    """Represents a single command from the allow-list."""

    def __init__(
        self,
        name: str,
        executable: str,
        args_schema: Optional[Dict[str, Any]] = None,
        launch_type: str = "daemon",
        timeout: int = 30,
        description: str = "",
    ):
        self.name = name
        self.executable = executable
        self.args_schema = args_schema or {"type": "object", "properties": {}}
        self.launch_type = launch_type  # "daemon" or "agent"
        self.timeout = timeout
        self.description = description
        self._validator = Draft7Validator(self.args_schema)

    def validate_args(self, args: Dict[str, Any]) -> None:
        """Validate arguments against JSON Schema.

        Args:
            args: Arguments to validate

        Raises:
            ValidationError: If arguments don't match schema
        """
        self._validator.validate(args)

    def build_command(self, args: Dict[str, Any]) -> List[str]:
        """Build command list from validated arguments.

        Args:
            args: Validated arguments

        Returns:
            Command as list of strings for subprocess.run()
        """
        # Start with executable
        cmd = [self.executable]

        # Add arguments based on schema
        for key, value in args.items():
            if isinstance(value, bool):
                if value:
                    cmd.append(f"--{key}")
            elif isinstance(value, list):
                for item in value:
                    cmd.append(f"--{key}")
                    cmd.append(str(item))
            else:
                cmd.append(f"--{key}")
                cmd.append(str(value))

        return cmd


class CommandRegistry:
    """Registry of allowed commands loaded from YAML allow-list."""

    def __init__(self, allow_list_path: str):
        self.allow_list_path = Path(allow_list_path)
        self.commands: Dict[str, CommandDefinition] = {}
        self._load_allow_list()

    def _load_allow_list(self) -> None:
        """Load and parse YAML allow-list."""
        if not self.allow_list_path.exists():
            raise FileNotFoundError(
                f"Allow-list not found at {self.allow_list_path}. "
                "Broker will not start without valid allow-list."
            )

        with self.allow_list_path.open("r") as f:
            data = yaml.safe_load(f)

        if not data or "commands" not in data:
            raise ValueError("Invalid allow-list: missing 'commands' key")

        for cmd_data in data["commands"]:
            name = cmd_data.get("name")
            if not name:
                raise ValueError("Command missing 'name' field")

            executable = cmd_data.get("executable")
            if not executable:
                raise ValueError(f"Command '{name}' missing 'executable' field")

            cmd_def = CommandDefinition(
                name=name,
                executable=executable,
                args_schema=cmd_data.get("args_schema"),
                launch_type=cmd_data.get("launch_type", "daemon"),
                timeout=cmd_data.get("timeout", 30),
                description=cmd_data.get("description", ""),
            )
            self.commands[name] = cmd_def

    def get_command(self, name: str) -> Optional[CommandDefinition]:
        """Get command definition by name.

        Args:
            name: Command name

        Returns:
            CommandDefinition if found, None otherwise
        """
        return self.commands.get(name)

    def list_commands(self) -> List[Dict[str, Any]]:
        """List all available commands.

        Returns:
            List of command metadata
        """
        return [
            {
                "name": cmd.name,
                "description": cmd.description,
                "launch_type": cmd.launch_type,
                "timeout": cmd.timeout,
            }
            for cmd in self.commands.values()
        ]


def load_settings() -> BrokerSettings:
    """Load broker settings from environment."""
    return BrokerSettings()


__all__ = [
    "BrokerSettings",
    "CommandDefinition",
    "CommandRegistry",
    "load_settings",
]
