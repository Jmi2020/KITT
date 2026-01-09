from __future__ import annotations

from typing import Any

from textual.widgets import Static
from textual.widgets.static import VisualType


class NoMarkupStatic(Static):
    """Static widget with markup disabled by default."""

    def __init__(self, content: VisualType = "", **kwargs: Any) -> None:
        super().__init__(content, markup=False, **kwargs)
