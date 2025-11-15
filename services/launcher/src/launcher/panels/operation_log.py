"""Log viewer for Access-All console actions."""

from __future__ import annotations

import textwrap
from typing import Iterable

from textual.app import ComposeResult
from textual.widgets import Static

try:  # Textual < 0.50
    from textual.widgets import TextLog as _LogWidget
except ImportError:  # Textual >= 0.50 renamed the widget to Log
    from textual.widgets import Log as _LogWidget


class OperationLogPanel(Static):
    """Scrollable log that records control center actions."""

    DEFAULT_CSS = """
    OperationLogPanel {
        border: round $secondary;
        margin: 1 2;
        padding: 1;
        height: 12;
    }

    OperationLogPanel TextLog,
    OperationLogPanel Log {
        background: transparent;
        width: 100%;
        overflow-x: hidden;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._log: _LogWidget | None = None

    def compose(self) -> ComposeResult:
        """Create the text log widget."""
        kwargs = {"id": "operation-log", "highlight": True}
        if _LogWidget.__name__ == "TextLog":
            kwargs.update({"markup": True, "wrap": True})
        log = _LogWidget(**kwargs)
        if hasattr(log, "wrap"):
            log.wrap = True
        log.write("[dim]Access-All console ready.[/dim]")
        self._log = log
        yield log

    def write(self, message: str, style: str = "text") -> None:
        """Append a message to the log with basic wrapping."""
        if not self._log:
            return

        width = 100
        for segment in self._wrap_message(message, width):
            chunk = f"[{style}]{segment}[/]" if style else segment
            self._log.write(chunk + "\n")

    def clear(self) -> None:
        """Reset the log contents."""
        if self._log:
            self._log.clear()

    def _wrap_message(self, message: str, width: int) -> Iterable[str]:
        """Wrap a message into chunks that fit the panel width."""
        if width <= 0:
            yield message
            return

        for raw_line in message.splitlines() or [""]:
            clean = raw_line.rstrip()
            if len(clean) <= width:
                yield clean
                continue

            for chunk in textwrap.wrap(clean, width=width, drop_whitespace=False):
                yield chunk
