#!/usr/bin/env python3
"""KITTY I/O Control Dashboard - TUI.

Interactive terminal interface for managing external device integrations
and feature flags with dependency validation and intelligent restarts.
"""

import sys
from pathlib import Path

# Add common to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services/common/src"))

import redis
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Checkbox, Footer, Header, Label, Static

from common.io_control import FeatureCategory, feature_registry
from common.io_control.state_manager import FeatureStateManager


class FeatureGroup(Static):
    """Widget displaying a group of related features."""

    def __init__(self, category: FeatureCategory, manager: FeatureStateManager):
        super().__init__()
        self.category = category
        self.manager = manager
        self.checkboxes = {}

    def compose(self) -> ComposeResult:
        """Compose the feature group UI."""
        features = feature_registry.list_by_category(self.category)
        current_state = self.manager.get_current_state()

        # Category header
        yield Label(f"[bold]{self.category.value.replace('_', ' ').title()}[/bold]")

        # Features in category
        for feature in features:
            is_enabled = current_state.get(feature.id, feature.default_value)

            with Horizontal(classes="feature-row"):
                checkbox = Checkbox(
                    feature.name,
                    is_enabled if isinstance(is_enabled, bool) else False,
                    id=f"check_{feature.id}",
                )
                self.checkboxes[feature.id] = checkbox
                yield checkbox

                # Status indicators
                if feature.requires:
                    deps_met = all(
                        current_state.get(req, False) for req in feature.requires
                    )
                    status = "✓" if deps_met else "⚠"
                    yield Label(status, classes="status-icon")

                # Restart indicator
                restart_icon = {
                    "none": "",
                    "service": "🔄",
                    "stack": "🔄🔄",
                    "llamacpp": "🧠",
                }
                yield Label(
                    restart_icon.get(feature.restart_scope.value, ""),
                    classes="restart-icon",
                )

        yield Label("")  # Spacer


class IOControlDashboard(App):
    """KITTY I/O Control Dashboard TUI."""

    CSS = """
    Screen {
        background: $surface;
    }

    #info-panel {
        background: $panel;
        height: auto;
        padding: 1 2;
        margin: 1 2;
    }

    #feature-container {
        height: auto;
        margin: 1 2;
    }

    .feature-row {
        height: auto;
        margin: 0 0 1 0;
    }

    .status-icon {
        width: 3;
        content-align: center middle;
    }

    .restart-icon {
        width: 5;
        content-align: center middle;
    }

    #button-bar {
        height: auto;
        dock: bottom;
        padding: 1 2;
        background: $panel;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "save", "Save & Apply"),
        Binding("h", "help", "Help"),
    ]

    def __init__(self):
        super().__init__()
        self.title = "KITTY I/O Control Dashboard"
        self.sub_title = "External Device & Feature Management"

        # Initialize state manager
        try:
            redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)
            redis_client.ping()
        except:
            redis_client = None

        self.manager = FeatureStateManager(redis_client=redis_client)
        self.feature_groups = {}

    def compose(self) -> ComposeResult:
        """Compose the dashboard UI."""
        yield Header()

        # Info panel
        with Container(id="info-panel"):
            yield Label("[bold]KITTY I/O Control Dashboard[/bold]")
            yield Label("Toggle features and manage external devices")
            yield Label("")
            yield Label("Legend: ⚠ = Missing dependencies | 🔄 = Restart required | 🧠 = llama.cpp restart")

        # Feature groups by category
        with ScrollableContainer(id="feature-container"):
            for category in FeatureCategory:
                group = FeatureGroup(category, self.manager)
                self.feature_groups[category] = group
                yield group

        # Button bar
        with Horizontal(id="button-bar"):
            yield Button("Save & Apply", id="save-button", variant="primary")
            yield Button("Refresh", id="refresh-button")
            yield Button("Validate", id="validate-button")
            yield Button("Help", id="help-button")
            yield Button("Quit", id="quit-button", variant="error")

        yield Footer()

    def action_refresh(self):
        """Refresh feature states from current config."""
        self.refresh()
        self.notify("Refreshed feature states")

    def action_save(self):
        """Save and apply changes."""
        self._save_changes()

    def action_help(self):
        """Show help information."""
        help_text = """
[bold]KITTY I/O Control Dashboard Help[/bold]

[bold]Features:[/bold]
- Toggle external device integrations and feature flags
- Automatic dependency validation
- Intelligent service restart handling
- Hot-reload for runtime flags (no restart needed)

[bold]Indicators:[/bold]
- ⚠  Missing dependencies (enable them first)
- 🔄 Service restart required
- 🧠 llama.cpp restart required

[bold]Keyboard Shortcuts:[/bold]
- q: Quit
- r: Refresh state
- s: Save and apply changes
- h: Show this help

[bold]Feature Categories:[/bold]
- Print Monitoring: Outcome tracking, visual evidence
- Camera: Bamboo Labs, Raspberry Pi cameras
- Storage: MinIO snapshot uploads
- Communication: MQTT broker, notifications
- Intelligence: Success prediction, recommendations
- Printer: Physical printer integrations
- Discovery: Network device discovery

[bold]Smart Restart Logic:[/bold]
- Runtime flags: Hot-reload, no restart (camera capture, outcome tracking)
- Service changes: Restart affected Docker services only
- Infrastructure: Full restart for critical changes (MQTT, databases)

Changes are validated before applying. Dependencies must be enabled first.
        """
        self.push_screen("help", lambda: self.notify(help_text))
        self.notify(help_text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-button":
            self._save_changes()
        elif event.button.id == "refresh-button":
            self.action_refresh()
        elif event.button.id == "validate-button":
            self._validate_changes()
        elif event.button.id == "help-button":
            self.action_help()
        elif event.button.id == "quit-button":
            self.exit()

    def _save_changes(self):
        """Save and apply all changes."""
        changes = {}

        # Collect all changes from checkboxes
        for category, group in self.feature_groups.items():
            for feature_id, checkbox in group.checkboxes.items():
                current_value = self.manager.get_feature_value(feature_id)
                new_value = checkbox.value

                # Only track actual changes
                if new_value != current_value:
                    changes[feature_id] = new_value

        if not changes:
            self.notify("No changes to apply", severity="information")
            return

        # Apply changes with validation
        success, errors = self.manager.bulk_set(changes, persist=True)

        if success:
            self.notify(f"✓ Applied {len(changes)} changes successfully", severity="information")
            self.action_refresh()
        else:
            error_msg = "\n".join([f"{fid}: {err}" for fid, err in errors.items()])
            self.notify(f"❌ Failed to apply changes:\n{error_msg}", severity="error")

    def _validate_changes(self):
        """Validate current checkbox states."""
        current_state = {}

        # Get checkbox states
        for category, group in self.feature_groups.items():
            for feature_id, checkbox in group.checkboxes.items():
                current_state[feature_id] = checkbox.value

        # Validate each feature
        issues = []
        for feature_id, enabled in current_state.items():
            if enabled:
                can_enable, reason = feature_registry.can_enable(feature_id, current_state)
                if not can_enable:
                    feature = feature_registry.get(feature_id)
                    issues.append(f"{feature.name}: {reason}")

        if issues:
            self.notify(f"⚠ Validation issues:\n" + "\n".join(issues), severity="warning")
        else:
            self.notify("✓ All features validated successfully", severity="information")


def main():
    """Run the I/O Control Dashboard TUI."""
    app = IOControlDashboard()
    app.run()


if __name__ == "__main__":
    main()
