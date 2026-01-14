"""Plan approval widget for selecting execution mode after plan presentation."""

from __future__ import annotations

from enum import StrEnum, auto
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.message import Message
from textual.widgets import Static

from kitty_code.cli.textual_ui.widgets.no_markup_static import NoMarkupStatic


class PlanApprovalChoice(StrEnum):
    """Choices for plan approval dialogue."""

    AUTO_ITERATE = auto()
    ACCEPT_WITH_APPROVALS = auto()
    CONTINUE_EDITING = auto()


class PlanApprovalApp(Container):
    """Widget for approving a plan and selecting execution mode."""

    can_focus = True
    can_focus_children = False

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
        Binding("1", "select_1", "Auto-iterate", show=False),
        Binding("a", "select_1", "Auto-iterate", show=False),
        Binding("2", "select_2", "With approvals", show=False),
        Binding("w", "select_2", "With approvals", show=False),
        Binding("3", "select_3", "Continue editing", show=False),
        Binding("c", "select_3", "Continue editing", show=False),
        Binding("escape", "select_3", "Continue editing", show=False),
    ]

    class PlanApproved(Message):
        """Message sent when a plan approval choice is made."""

        def __init__(self, choice: PlanApprovalChoice) -> None:
            super().__init__()
            self.choice = choice

    OPTIONS = [
        ("1", "Auto-iterate", "Execute autonomously until all tasks complete"),
        ("2", "With approvals", "Execute with tool approval prompts (DEFAULT mode)"),
        ("3", "Continue editing", "Stay in plan mode to refine the plan"),
    ]

    def __init__(self) -> None:
        super().__init__(id="plan-approval-app")
        self.selected_option = 0
        self.option_widgets: list[Static] = []
        self.help_widget: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="plan-approval-content"):
            yield NoMarkupStatic(
                "Plan ready. How would you like to proceed?",
                classes="plan-approval-title",
            )

            yield NoMarkupStatic("")

            for _ in range(len(self.OPTIONS)):
                widget = NoMarkupStatic("", classes="plan-approval-option")
                self.option_widgets.append(widget)
                yield widget

            yield NoMarkupStatic("")

            self.help_widget = NoMarkupStatic(
                "↑↓ navigate  Enter select  1/2/3 quick select  ESC cancel",
                classes="plan-approval-help",
            )
            yield self.help_widget

    def on_mount(self) -> None:
        self._update_options()
        self.focus()

    def _update_options(self) -> None:
        for i, (key, label, desc) in enumerate(self.OPTIONS):
            prefix = "▶ " if i == self.selected_option else "  "
            style = "bold" if i == self.selected_option else ""
            text = f"{prefix}[{key}] {label} - {desc}"
            if style:
                text = f"[{style}]{text}[/{style}]"
            self.option_widgets[i].update(text)

    def action_move_up(self) -> None:
        if self.selected_option > 0:
            self.selected_option -= 1
            self._update_options()

    def action_move_down(self) -> None:
        if self.selected_option < len(self.OPTIONS) - 1:
            self.selected_option += 1
            self._update_options()

    def action_select(self) -> None:
        self._submit_choice(self.selected_option)

    def action_select_1(self) -> None:
        self._submit_choice(0)

    def action_select_2(self) -> None:
        self._submit_choice(1)

    def action_select_3(self) -> None:
        self._submit_choice(2)

    def _submit_choice(self, index: int) -> None:
        choices = [
            PlanApprovalChoice.AUTO_ITERATE,
            PlanApprovalChoice.ACCEPT_WITH_APPROVALS,
            PlanApprovalChoice.CONTINUE_EDITING,
        ]
        self.post_message(self.PlanApproved(choices[index]))
