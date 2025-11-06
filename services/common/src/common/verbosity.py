# noqa: D401
"""Utilities for handling KITTY verbosity levels."""

from __future__ import annotations

from enum import IntEnum
from typing import Dict

from .config import settings


class VerbosityLevel(IntEnum):
    """Verbosity scale shared across services."""

    EXTREMELY_TERSE = 1
    CONCISE = 2
    DETAILED = 3
    COMPREHENSIVE = 4
    EXHAUSTIVE = 5


VERBOSITY_DESCRIPTIONS: Dict[VerbosityLevel, str] = {
    VerbosityLevel.EXTREMELY_TERSE: "extremely terse",
    VerbosityLevel.CONCISE: "concise",
    VerbosityLevel.DETAILED: "detailed",
    VerbosityLevel.COMPREHENSIVE: "comprehensive",
    VerbosityLevel.EXHAUSTIVE: "exhaustive and nuanced detail",
}


def clamp_level(value: int) -> VerbosityLevel:
    """Clamp raw integer into the supported verbosity range."""

    try:
        return VerbosityLevel(
            max(VerbosityLevel.EXTREMELY_TERSE, min(value, VerbosityLevel.EXHAUSTIVE))
        )
    except ValueError:
        return VerbosityLevel.DETAILED


def get_verbosity_level() -> VerbosityLevel:
    """Return configured verbosity level."""

    return clamp_level(getattr(settings, "verbosity", VerbosityLevel.DETAILED))


def describe_level(level: VerbosityLevel | int) -> str:
    """Human-friendly description for a verbosity level."""

    if not isinstance(level, VerbosityLevel):
        level = clamp_level(int(level))
    return VERBOSITY_DESCRIPTIONS.get(level, "detailed")


__all__ = [
    "VerbosityLevel",
    "VERBOSITY_DESCRIPTIONS",
    "get_verbosity_level",
    "describe_level",
    "clamp_level",
]
