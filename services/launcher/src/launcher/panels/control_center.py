"""Interactive control center for the KITTY Access-All console."""

from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.message import Message
from textual.widgets import Button, Static


class ControlActionRequested(Message):
    """Message emitted when a quick action button is pressed."""

    def __init__(self, sender: Static, action: str) -> None:
        super().__init__()
        self.action = action
        self.sender = sender


@dataclass(frozen=True)
class QuickAction:
    """Metadata describing a control center action."""

    id: str
    label: str
    description: str
    variant: str = "neutral"


QUICK_ACTIONS: tuple[QuickAction, ...] = (
    QuickAction("start_stack", "🚀 Start KITTY", "Run Ollama + Docker + llama.cpp", "success"),
    QuickAction("stop_stack", "⏹ Stop KITTY", "Graceful shutdown (Docker + local servers)", "warning"),
    QuickAction("start_ollama", "🧠 Start Ollama (GPT-OSS)", "Main reasoning/judge stack", "accent"),
    QuickAction("stop_ollama", "🧠 Stop Ollama", "Stop Ollama server", "warning"),
    QuickAction("restart_ollama", "🧠 Restart Ollama", "Restart Ollama server", "neutral"),
    QuickAction("start_llama", "🔥 Start llama.cpp", "Legacy/local fallback instances", "accent"),
    QuickAction("stop_llama", "🔥 Stop llama.cpp", "Stop llama.cpp instances", "warning"),
    QuickAction("restart_llama", "🔥 Restart llama.cpp", "Restart llama.cpp instances", "neutral"),
    QuickAction("start_docker", "🐳 Start Docker Stack", "Bring up docker compose services", "accent"),
    QuickAction("stop_docker", "🐳 Stop Docker Stack", "docker compose down", "warning"),
    QuickAction("restart_docker", "🐳 Restart Docker Stack", "Stop + start docker compose", "neutral"),
    QuickAction("launch_cli", "💬 Launch CLI", "Open kitty-cli shell with health checks"),
    QuickAction("launch_model_manager", "🎛 Model Manager", "Swap llama.cpp models (TUI)"),
    QuickAction("open_web_console", "🖥 Web Console", "Launch the React/Vision UI in browser"),
    QuickAction("launch_io_dashboard", "⚙️ I/O Dashboard", "I/O feature switches + presets"),
)


class ControlCenterPanel(Static):
    """Hero panel that exposes quick controls."""

    DEFAULT_CSS = """
    ControlCenterPanel {
        border: round $primary;
        padding: 1 2;
        margin: 1 2 0 2;
        width: 100%;
    }

    ControlCenterPanel > .title {
        text-style: bold;
        color: $primary-lighten-1;
    }

    ControlCenterPanel > .subtitle {
        color: $text-muted;
        margin-bottom: 1;
    }

    ControlCenterPanel .actions-grid {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 1fr;
        grid-gutter: 1 1;
    }

    ControlCenterPanel Button.action-button {
        height: 5;
        text-align: left;
        padding: 0 1;
        border: none;
        background: $background 25%;
    }

    ControlCenterPanel Button.action-button:focus {
        background: $boost;
    }

    ControlCenterPanel Button.action-success {
        background: $success 20%;
    }

    ControlCenterPanel Button.action-warning {
        background: $warning 20%;
    }

    ControlCenterPanel Button.action-accent {
        background: $accent 20%;
    }

    ControlCenterPanel .action-label {
        text-style: bold;
    }

    ControlCenterPanel .action-desc {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the hero panel."""
        yield Static("KITTY Access-All Console", classes="title")
        yield Static(
            "Control center for stacks, tools, and dashboards. "
            "Use shortcuts on the footer or activate any quick action below.",
            classes="subtitle",
        )

        with Static(classes="actions-grid"):
            for action in QUICK_ACTIONS:
                label = f"{action.label}\n[dim]{action.description}[/dim]"
                classes = f"action-button action-{action.variant}"
                yield Button(label, id=action.id, classes=classes)

    @on(Button.Pressed)
    def handle_button_pressed(self, event: Button.Pressed) -> None:
        """Emit a message when a quick action is selected."""
        if event.button.id:
            self.post_message(ControlActionRequested(self, event.button.id))
