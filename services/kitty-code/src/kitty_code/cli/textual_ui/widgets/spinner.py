from __future__ import annotations

from abc import ABC
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from textual.timer import Timer
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class Spinner(ABC):
    FRAMES: ClassVar[tuple[str, ...]]

    def __init__(self) -> None:
        self._position = 0

    def next_frame(self) -> str:
        frame = self.FRAMES[self._position]
        self._position = (self._position + 1) % len(self.FRAMES)
        return frame

    def current_frame(self) -> str:
        return self.FRAMES[self._position]

    def reset(self) -> None:
        self._position = 0


class BrailleSpinner(Spinner):
    FRAMES: ClassVar[tuple[str, ...]] = (
        "⠋",
        "⠙",
        "⠹",
        "⠸",
        "⠼",
        "⠴",
        "⠦",
        "⠧",
        "⠇",
        "⠏",
    )


class LineSpinner(Spinner):
    FRAMES: ClassVar[tuple[str, ...]] = ("|", "/", "-", "\\")


class CircleSpinner(Spinner):
    FRAMES: ClassVar[tuple[str, ...]] = ("◴", "◷", "◶", "◵")


class BowtieSpinner(Spinner):
    FRAMES: ClassVar[tuple[str, ...]] = (
        "⠋",
        "⠙",
        "⠚",
        "⠞",
        "⠖",
        "⠦",
        "⠴",
        "⠲",
        "⠳",
        "⠓",
    )


class DotWaveSpinner(Spinner):
    FRAMES: ClassVar[tuple[str, ...]] = ("⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷")


class SpinnerType(Enum):
    BRAILLE = "braille"
    LINE = "line"
    CIRCLE = "circle"
    BOWTIE = "bowtie"
    DOT_WAVE = "dot_wave"


_SPINNER_CLASSES: dict[SpinnerType, type[Spinner]] = {
    SpinnerType.BRAILLE: BrailleSpinner,
    SpinnerType.LINE: LineSpinner,
    SpinnerType.CIRCLE: CircleSpinner,
    SpinnerType.BOWTIE: BowtieSpinner,
    SpinnerType.DOT_WAVE: DotWaveSpinner,
}


def create_spinner(spinner_type: SpinnerType = SpinnerType.BRAILLE) -> Spinner:
    spinner_class = _SPINNER_CLASSES.get(spinner_type, BrailleSpinner)
    return spinner_class()


class SpinnerMixin:
    """Mixin class providing spinner animation for widgets.

    Classes using this mixin should:
    1. Override SPINNER_TYPE, SPINNING_TEXT, COMPLETED_TEXT class variables
    2. Call init_spinner() in compose() to get the indicator and status widgets
    3. Call start_spinner_timer() to begin animation
    4. Call stop_spinning() when done
    """

    SPINNER_TYPE: ClassVar[SpinnerType] = SpinnerType.LINE
    SPINNING_TEXT: ClassVar[str] = ""
    COMPLETED_TEXT: ClassVar[str] = ""

    _spinner: Spinner
    _spinner_timer: Timer | None
    _is_spinning: bool
    _indicator_widget: Static
    _status_text_widget: Static

    def init_spinner(self) -> ComposeResult:
        """Initialize spinner widgets. Call this in compose()."""
        self._spinner = create_spinner(self.SPINNER_TYPE)
        self._spinner_timer = None
        self._is_spinning = False
        self._indicator_widget = Static(self._spinner.current_frame(), classes="indicator")
        self._status_text_widget = Static(self.SPINNING_TEXT, classes="status-text")
        yield self._indicator_widget
        yield self._status_text_widget

    def start_spinner_timer(self, interval: float = 0.1) -> None:
        """Start the spinner animation timer."""
        if self._spinner_timer is None and hasattr(self, "set_timer"):
            self._is_spinning = True
            self._spinner_timer = self.set_timer(  # type: ignore[attr-defined]
                interval, self._update_spinner_frame, pause=False
            )

    def _update_spinner_frame(self) -> None:
        """Update spinner to next frame and reschedule."""
        if self._is_spinning:
            self._indicator_widget.update(self._spinner.next_frame())
            if hasattr(self, "set_timer"):
                self._spinner_timer = self.set_timer(  # type: ignore[attr-defined]
                    0.1, self._update_spinner_frame, pause=False
                )

    def refresh_spinner(self) -> None:
        """Refresh the spinner to current frame without advancing."""
        self._indicator_widget.update(self._spinner.current_frame())

    def stop_spinning(self) -> None:
        """Stop spinner animation and update to completed state."""
        self._is_spinning = False
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        self._indicator_widget.update("▼")
        self._status_text_widget.update(self.COMPLETED_TEXT)

    def on_unmount(self) -> None:
        """Clean up timer on unmount."""
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
