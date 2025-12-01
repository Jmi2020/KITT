"""Configuration management for fabrication service."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import yaml

from common.logging import get_logger

LOGGER = get_logger(__name__)

# Default config paths to search
_CONFIG_PATHS = [
    Path(__file__).parent.parent.parent.parent / "printer_config.yaml",
    Path(__file__).parent.parent.parent.parent / "printer_config.example.yaml",
    Path("/etc/kitt/printer_config.yaml"),
]

_printer_config: Optional[Dict[str, Any]] = None


def get_printer_config() -> Dict[str, Any]:
    """
    Load printer configuration from YAML file.

    Searches for printer_config.yaml in common locations.
    Falls back to default configuration if no file found.
    """
    global _printer_config

    if _printer_config is not None:
        return _printer_config

    # Try to load from file
    for config_path in _CONFIG_PATHS:
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    _printer_config = yaml.safe_load(f)
                    LOGGER.info(f"Loaded printer config from {config_path}")
                    return _printer_config
            except Exception as e:
                LOGGER.warning(f"Failed to load config from {config_path}: {e}")

    # Return default configuration
    LOGGER.warning("No printer config found, using defaults")
    _printer_config = _get_default_config()
    return _printer_config


def _get_default_config() -> Dict[str, Any]:
    """Return default printer configuration."""
    return {
        "printers": {
            "bamboo_h2d": {
                "name": "Bambu Lab H2D",
                "model": "H2D",
                "build_volume": [256, 256, 256],
                "materials": ["PLA", "PETG", "ABS", "TPU"],
            },
            "elegoo_giga": {
                "name": "Elegoo OrangeStorm Giga",
                "model": "OrangeStorm Giga",
                "build_volume": [800, 800, 1000],
                "materials": ["PLA", "PETG", "ABS"],
            },
            "snapmaker_artisan": {
                "name": "Snapmaker Artisan",
                "model": "Artisan",
                "build_volume": [400, 400, 400],
                "materials": ["PLA", "PETG", "ABS"],
            },
        },
        "features": {
            "auto_start_prints": False,
            "monitor_temperature": True,
        },
    }


def get_build_volume(printer_id: str) -> tuple[float, float, float]:
    """
    Get build volume for a specific printer.

    Args:
        printer_id: Printer identifier

    Returns:
        Build volume as (x, y, z) in mm
    """
    config = get_printer_config()
    printers = config.get("printers", {})

    if printer_id in printers:
        printer_info = printers[printer_id]
        # Check for capabilities.build_volume or direct build_volume
        if "capabilities" in printer_info and "build_volume" in printer_info["capabilities"]:
            vol = printer_info["capabilities"]["build_volume"]
        elif "build_volume" in printer_info:
            vol = printer_info["build_volume"]
        else:
            vol = [250, 250, 250]
        return (float(vol[0]), float(vol[1]), float(vol[2]))

    # Default
    return (250.0, 250.0, 250.0)


def list_printers() -> list[Dict[str, Any]]:
    """List all configured printers with their capabilities."""
    config = get_printer_config()
    printers = []

    for printer_id, printer_info in config.get("printers", {}).items():
        build_volume = get_build_volume(printer_id)
        printers.append({
            "printer_id": printer_id,
            "name": printer_info.get("name", printer_id),
            "model": printer_info.get("model", "Unknown"),
            "build_volume_mm": build_volume,
            "enabled": printer_info.get("enabled", True),
        })

    return printers
