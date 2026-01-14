"""Interactive directory browser widget for /cd command."""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.message import Message
from textual.widgets import Static


class DirectoryBrowserApp(Container):
    """Interactive directory browser for the /cd command.

    Displays current directory contents and allows keyboard navigation
    to select a new working directory.
    """

    can_focus = True
    can_focus_children = False

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("backspace", "go_up", "Parent", show=False),
        Binding("tab", "confirm", "Confirm", show=False),
        Binding("home", "go_home", "Home", show=False),
    ]

    class DirectorySelected(Message):
        """Posted when user confirms a directory selection."""

        def __init__(self, path: Path) -> None:
            super().__init__()
            self.path = path

    class BrowserCancelled(Message):
        """Posted when user cancels the directory browser."""

        pass

    def __init__(self, initial_path: Path | None = None) -> None:
        super().__init__(id="directory-browser-app")
        self._current_path = (initial_path or Path.cwd()).resolve()
        self._directories: list[Path] = []
        self._selected_index = 0
        self._max_visible = 8

        self._title_widget: Static | None = None
        self._path_widget: Static | None = None
        self._list_container: Vertical | None = None
        self._item_widgets: list[Static] = []
        self._help_widget: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="directory-browser-content"):
            self._title_widget = Static(
                "Select Directory", classes="directory-browser-title"
            )
            yield self._title_widget

            self._path_widget = Static(
                str(self._current_path), classes="directory-browser-path"
            )
            yield self._path_widget

            self._list_container = Vertical(id="directory-browser-list")
            with self._list_container:
                # Create placeholder items
                for _ in range(self._max_visible + 1):  # +1 for ".."
                    widget = Static("", classes="directory-option")
                    self._item_widgets.append(widget)
                    yield widget

            self._help_widget = Static(
                "↑↓ navigate  Enter select  ⌫ parent  Tab confirm  ESC cancel",
                classes="directory-browser-help",
            )
            yield self._help_widget

    def on_mount(self) -> None:
        self._load_directories()
        self._update_display()
        self.focus()

    def _load_directories(self) -> None:
        """Load directories from current path."""
        self._directories = []
        try:
            for item in sorted(self._current_path.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    self._directories.append(item)
        except PermissionError:
            pass
        except OSError:
            pass

    def _update_display(self) -> None:
        """Update the display to show current state."""
        if self._path_widget:
            self._path_widget.update(str(self._current_path))

        # Build list: ".." first, then directories
        items: list[str] = [".."]
        items.extend(f"{d.name}/" for d in self._directories)

        # Update item widgets
        for i, widget in enumerate(self._item_widgets):
            if i < len(items):
                is_selected = i == self._selected_index
                cursor = "› " if is_selected else "  "
                widget.update(f"{cursor}{items[i]}")
                widget.display = True

                widget.remove_class("directory-option-selected")
                if is_selected:
                    widget.add_class("directory-option-selected")
            else:
                widget.update("")
                widget.display = False
                widget.remove_class("directory-option-selected")

    def _navigate_to(self, path: Path) -> None:
        """Navigate to a new directory."""
        try:
            resolved = path.resolve()
            if resolved.is_dir():
                self._current_path = resolved
                self._selected_index = 0
                self._load_directories()
                self._update_display()
        except (PermissionError, OSError):
            pass

    def action_move_up(self) -> None:
        """Move selection up."""
        total_items = 1 + len(self._directories)  # ".." + directories
        self._selected_index = (self._selected_index - 1) % total_items
        self._update_display()

    def action_move_down(self) -> None:
        """Move selection down."""
        total_items = 1 + len(self._directories)  # ".." + directories
        self._selected_index = (self._selected_index + 1) % total_items
        self._update_display()

    def action_select(self) -> None:
        """Enter selected directory."""
        if self._selected_index == 0:
            # ".." selected - go to parent
            self._navigate_to(self._current_path.parent)
        elif self._selected_index <= len(self._directories):
            # Directory selected
            selected_dir = self._directories[self._selected_index - 1]
            self._navigate_to(selected_dir)

    def action_go_up(self) -> None:
        """Go to parent directory (shortcut for ..)."""
        self._navigate_to(self._current_path.parent)

    def action_go_home(self) -> None:
        """Go to home directory."""
        self._navigate_to(Path.home())

    def action_confirm(self) -> None:
        """Confirm current directory selection."""
        self.post_message(self.DirectorySelected(path=self._current_path))

    def action_cancel(self) -> None:
        """Cancel and close the browser."""
        self.post_message(self.BrowserCancelled())

    def on_blur(self, event: events.Blur) -> None:
        """Maintain focus while active."""
        self.call_after_refresh(self.focus)
