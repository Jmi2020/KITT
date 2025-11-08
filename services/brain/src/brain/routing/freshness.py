"""Heuristics for detecting time-sensitive queries that require fresh data."""

from __future__ import annotations

import re
from datetime import datetime, timezone

RELATIVE_KEYWORDS = {
    "today",
    "tonight",
    "tomorrow",
    "yesterday",
    "currently",
    "right now",
    "as of",
    "latest",
    "recent",
    "breaking",
    "live",
    "upcoming",
    "this morning",
    "this evening",
}

RELATIVE_REGEX = re.compile(
    r"\b(this|next|last)\s+(week|month|quarter|year|weekend|season)\b", re.IGNORECASE
)

MONTH_NAMES = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

TIME_TERMS = {"today", "now", "current", "right now", "as of", "latest"}
PRICE_TERMS = {"price", "stock", "rate", "yield", "btc", "eth", "gas", "usd", "inflation"}
EVENT_TERMS = {"schedule", "fixtures", "standings", "rankings", "earnings", "forecast", "release"}


def is_time_sensitive_query(prompt: str) -> bool:
    """Return True if the prompt likely requires real-time information."""
    text = prompt.lower()

    if any(keyword in text for keyword in RELATIVE_KEYWORDS):
        return True

    if RELATIVE_REGEX.search(text):
        return True

    if "as of" in text:
        return True

    if any(time_word in text for time_word in TIME_TERMS) and "news" in text:
        return True

    if any(month in text for month in MONTH_NAMES) and any(term in text for term in EVENT_TERMS):
        return True

    if any(term in text for term in PRICE_TERMS) and any(word in text for word in TIME_TERMS):
        return True

    if "latest" in text and any(term in text for term in EVENT_TERMS):
        return True

    current_year = datetime.now(timezone.utc).year
    year_tokens = {str(current_year), str(current_year + 1)}
    if any(year in text for year in year_tokens) and any(term in text for term in EVENT_TERMS):
        return True

    return False


__all__ = ["is_time_sensitive_query"]
