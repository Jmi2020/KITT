"""Helpers for locating the KITTY project root and scripts."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Best-effort detection of the KITTY repository root.

    Returns:
        Path to the repo root (directory containing .git). Falls back to cwd.
    """
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()


def find_first_existing(rel_paths: Iterable[str]) -> Optional[Path]:
    """Return the first existing path under the project root.

    Args:
        rel_paths: Relative paths to probe in order of preference.

    Returns:
        Path to the first existing file or None if none exist.
    """
    root = get_project_root()
    for rel in rel_paths:
        candidate = root / rel
        if candidate.exists():
            return candidate
    return None
