# noqa: D401
"""Configuration management for KITTY Model Manager."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import dotenv_values, set_key, unset_key

from .models import ServerConfig

logger = logging.getLogger(__name__)

# Default .env path (KITTY root)
DEFAULT_ENV_PATH = Path("/Users/Shared/Coding/KITT/.env")


class ConfigManager:
    """Manages llama.cpp server configuration via .env file."""

    def __init__(self, env_path: Optional[Path] = None) -> None:
        """Initialize configuration manager.

        Args:
            env_path: Path to .env file (defaults to KITTY root)
        """
        self.env_path = Path(env_path) if env_path else DEFAULT_ENV_PATH

        if not self.env_path.exists():
            logger.warning(f".env file not found at {self.env_path}")

    def load(self) -> ServerConfig:
        """Load server configuration from .env file.

        Returns:
            ServerConfig instance with current settings
        """
        # Load .env file
        config = dotenv_values(self.env_path)

        # Extract LLAMACPP_* variables
        return ServerConfig(
            primary_model=config.get("LLAMACPP_PRIMARY_MODEL", ""),
            models_dir=Path(config.get("LLAMACPP_MODELS_DIR", "/Users/Shared/Coding/models")),
            model_alias=config.get("LLAMACPP_PRIMARY_ALIAS", "kitty-primary"),
            host=config.get("LLAMACPP_HOST", "localhost"),
            port=int(config.get("LLAMACPP_PORT", "8080")),
            binary=config.get("LLAMACPP_BIN", "llama-server"),
            context_size=int(config.get("LLAMACPP_CTX", "8192")),
            n_predict=int(config.get("LLAMACPP_N_PREDICT", "512")),
            temperature=float(config.get("LLAMACPP_TEMPERATURE", "0.7")),
            top_p=float(config.get("LLAMACPP_TOP_P", "0.95")),
            repeat_penalty=float(config.get("LLAMACPP_REPEAT_PENALTY", "1.1")),
            n_gpu_layers=int(config.get("LLAMACPP_N_GPU_LAYERS", "999")),
            threads=int(config.get("LLAMACPP_THREADS", "20")),
            batch_size=int(config.get("LLAMACPP_BATCH_SIZE", "4096")),
            ubatch_size=int(config.get("LLAMACPP_UBATCH_SIZE", "1024")),
            parallel=int(config.get("LLAMACPP_PARALLEL", "6")),
            flash_attention=config.get("LLAMACPP_FLASH_ATTN", "1") in ("1", "true", "True"),
            tool_calling=config.get("LLAMACPP_TOOL_CALLING", "0") in ("1", "true", "True"),
            stop_tokens=self._parse_list(config.get("LLAMACPP_STOP", "")),
            extra_args=self._parse_list(config.get("LLAMACPP_EXTRA_ARGS", "")),
        )

    def save(self, config: ServerConfig, backup: bool = True) -> None:
        """Save server configuration to .env file.

        Args:
            config: ServerConfig to save
            backup: Whether to create backup before writing
        """
        if backup and self.env_path.exists():
            backup_path = self.env_path.with_suffix(".env.backup")
            shutil.copy2(self.env_path, backup_path)
            logger.info(f"Created backup at {backup_path}")

        # Update .env file with new values
        self._set_env("LLAMACPP_PRIMARY_MODEL", config.primary_model)
        self._set_env("LLAMACPP_MODELS_DIR", str(config.models_dir))
        self._set_env("LLAMACPP_PRIMARY_ALIAS", config.model_alias)
        self._set_env("LLAMACPP_HOST", config.host)
        self._set_env("LLAMACPP_PORT", str(config.port))
        self._set_env("LLAMACPP_BIN", config.binary)

        self._set_env("LLAMACPP_CTX", str(config.context_size))
        self._set_env("LLAMACPP_N_PREDICT", str(config.n_predict))
        self._set_env("LLAMACPP_TEMPERATURE", str(config.temperature))
        self._set_env("LLAMACPP_TOP_P", str(config.top_p))
        self._set_env("LLAMACPP_REPEAT_PENALTY", str(config.repeat_penalty))

        self._set_env("LLAMACPP_N_GPU_LAYERS", str(config.n_gpu_layers))
        self._set_env("LLAMACPP_THREADS", str(config.threads))
        self._set_env("LLAMACPP_BATCH_SIZE", str(config.batch_size))
        self._set_env("LLAMACPP_UBATCH_SIZE", str(config.ubatch_size))
        self._set_env("LLAMACPP_PARALLEL", str(config.parallel))
        self._set_env("LLAMACPP_FLASH_ATTN", "1" if config.flash_attention else "0")
        self._set_env("LLAMACPP_TOOL_CALLING", "1" if config.tool_calling else "0")

        if config.stop_tokens:
            self._set_env("LLAMACPP_STOP", ",".join(config.stop_tokens))
        else:
            self._unset_env("LLAMACPP_STOP")

        if config.extra_args:
            self._set_env("LLAMACPP_EXTRA_ARGS", " ".join(config.extra_args))
        else:
            self._unset_env("LLAMACPP_EXTRA_ARGS")

        logger.info(f"Configuration saved to {self.env_path}")

    def update_model(self, model_path: str, alias: Optional[str] = None) -> None:
        """Update only the model configuration.

        Args:
            model_path: Relative path to model from models_dir
            alias: Optional model alias (defaults to filename stem)
        """
        if alias is None:
            alias = Path(model_path).stem

        self._set_env("LLAMACPP_PRIMARY_MODEL", model_path)
        self._set_env("LLAMACPP_PRIMARY_ALIAS", alias)
        logger.info(f"Updated model to {model_path} with alias {alias}")

    def get_env_vars(self) -> Dict[str, str]:
        """Get all current environment variables from .env.

        Returns:
            Dictionary of all environment variables
        """
        return dict(dotenv_values(self.env_path))

    def _set_env(self, key: str, value: str) -> None:
        """Set environment variable in .env file.

        Args:
            key: Variable name
            value: Variable value
        """
        set_key(self.env_path, key, value, quote_mode="never")

    def _unset_env(self, key: str) -> None:
        """Remove environment variable from .env file.

        Args:
            key: Variable name
        """
        unset_key(self.env_path, key)

    @staticmethod
    def _parse_list(value: str) -> List[str]:
        """Parse comma or space-separated string to list.

        Args:
            value: String to parse

        Returns:
            List of strings
        """
        if not value:
            return []

        # Try comma-separated first
        if "," in value:
            return [item.strip() for item in value.split(",") if item.strip()]

        # Fall back to space-separated
        return [item.strip() for item in value.split() if item.strip()]


def get_config_manager(env_path: Optional[Path] = None) -> ConfigManager:
    """Get configuration manager instance.

    Args:
        env_path: Optional path to .env file

    Returns:
        ConfigManager instance
    """
    return ConfigManager(env_path)


def load_config(env_path: Optional[Path] = None) -> ServerConfig:
    """Load configuration from .env file.

    Args:
        env_path: Optional path to .env file

    Returns:
        ServerConfig instance
    """
    manager = ConfigManager(env_path)
    return manager.load()


def save_config(config: ServerConfig, env_path: Optional[Path] = None, backup: bool = True) -> None:
    """Save configuration to .env file.

    Args:
        config: ServerConfig to save
        env_path: Optional path to .env file
        backup: Whether to create backup
    """
    manager = ConfigManager(env_path)
    manager.save(config, backup=backup)


__all__ = [
    "ConfigManager",
    "get_config_manager",
    "load_config",
    "save_config",
    "DEFAULT_ENV_PATH",
]
