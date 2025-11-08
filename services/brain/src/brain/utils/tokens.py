"""Lightweight token counting helpers (approximate)."""

from __future__ import annotations

import re
from typing import Any

_whitespace_re = re.compile(r"\s+")


def _normalize_text(text: str) -> str:
    return _whitespace_re.sub(" ", text).strip()


def count_tokens(content: Any) -> int:
    """Approximate token count by splitting on whitespace.

    Args:
        content: String, list, or dict to measure

    Returns:
        Approximate token count (integer)
    """
    if content is None:
        return 0
    if isinstance(content, str):
        normalized = _normalize_text(content)
        return len(normalized.split()) if normalized else 0
    if isinstance(content, list):
        return sum(count_tokens(item) for item in content)
    if isinstance(content, dict):
        return count_tokens(" ".join(f"{key}: {value}" for key, value in content.items()))
    return count_tokens(str(content))
