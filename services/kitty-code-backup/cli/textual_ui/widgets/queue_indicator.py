"""Queue indicator widget for showing pending input messages."""

from __future__ import annotations

from textual.widgets import Static


class QueueIndicator(Static):
    """Shows count of queued messages in status bar.

    Displays when user submits input while the agent is processing,
    indicating how many messages are waiting to be sent.
    """

    DEFAULT_CSS = """
    QueueIndicator {
        background: $warning-muted;
        color: $text;
        padding: 0 1;
        display: none;
        text-style: italic;
    }
    QueueIndicator.visible {
        display: block;
    }
    """

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes)

    def update_count(self, count: int) -> None:
        """Update the indicator with the current queue count.

        Args:
            count: Number of messages in the queue. Hides indicator if 0.
        """
        if count > 0:
            msg = "message" if count == 1 else "messages"
            self.update(f"Queued: {count} {msg}")
            self.add_class("visible")
        else:
            self.remove_class("visible")
            self.update("")
