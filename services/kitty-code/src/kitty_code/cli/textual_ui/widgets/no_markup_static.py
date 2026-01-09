from __future__ import annotations

from typing import Any

from textual.widgets import Static


class NoMarkupStatic(Static):
    """Static widget with markup disabled by default."""

    def __init__(self, content: str = "", **kwargs: Any) -> None:
        super().__init__(content, markup=False, **kwargs)
