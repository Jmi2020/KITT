"""KITTY Unified Launcher TUI - Main Application

Enhanced with real-time system health monitoring and Docker service management.
"""

import subprocess

import typer
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Static

from launcher.panels.system_status import DetailedStatusPanel, SystemStatusPanel


class WelcomePanel(Static):
    """Welcome message and instructions."""

    DEFAULT_CSS = """
    WelcomePanel {
        border: solid $primary;
        padding: 2 4;
        margin: 1 2;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold cyan]🐱 KITTY Unified Launcher[/bold cyan]\n\n"
                    "[yellow]Version 0.2.0[/yellow]\n\n"
                    "Unified interface for managing the entire KITTY system.\n\n"
                    "[green]Quick Actions:[/green]\n"
                    "  [bold]h[/bold] - Toggle system health status\n"
                    "  [bold]d[/bold] - Toggle detailed service list\n"
                    "  [bold]s[/bold] - Show startup instructions\n"
                    "  [bold]m[/bold] - Launch Model Manager TUI\n"
                    "  [bold]c[/bold] - Launch CLI (external terminal)\n"
                    "  [bold]q[/bold] - Quit\n\n"
                    "[dim]Full features coming:[/dim]\n"
                    "  • Embedded CLI interface\n"
                    "  • Voice capture and transcripts\n"
                    "  • Aggregated log viewing\n"
                    "  • Web UI shortcuts")


class StartupPanel(Static):
    """Startup instructions placeholder."""

    DEFAULT_CSS = """
    StartupPanel {
        border: solid $accent;
        padding: 2 4;
        margin: 1 2;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("[bold]Startup Instructions:[/bold]\n\n"
                    "1. Start llama.cpp model:\n"
                    "   [cyan]kitty-model-manager tui[/cyan]\n\n"
                    "2. Start KITTY services:\n"
                    "   [cyan]./ops/scripts/start-kitty-validated.sh[/cyan]\n\n"
                    "3. Launch CLI interface:\n"
                    "   [cyan]kitty-cli shell[/cyan]\n\n"
                    "[dim]Automated startup coming in next iteration![/dim]")


class KittyLauncherApp(App):
    """KITTY Unified Launcher TUI Application."""

    TITLE = "KITTY Unified Launcher"
    CSS = """
    Screen {
        align: center middle;
    }

    #main-container {
        width: 100;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "toggle_health", "Health Status"),
        Binding("d", "toggle_details", "Service Details"),
        Binding("s", "toggle_startup", "Startup Info"),
        Binding("m", "launch_model_manager", "Model Manager"),
        Binding("c", "launch_cli", "CLI"),
    ]

    def __init__(self):
        super().__init__()
        self.show_startup = False
        self.show_health = False
        self.show_details = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main-container"):
            yield WelcomePanel()
            if self.show_health:
                yield SystemStatusPanel()
            if self.show_details:
                yield DetailedStatusPanel()
            if self.show_startup:
                yield StartupPanel()
        yield Footer()

    def action_toggle_health(self) -> None:
        """Toggle system health status panel."""
        self.show_health = not self.show_health
        self.refresh(recompose=True)
        status = "shown" if self.show_health else "hidden"
        self.notify(f"Health status {status}")

    def action_toggle_details(self) -> None:
        """Toggle detailed service list panel."""
        self.show_details = not self.show_details
        self.refresh(recompose=True)
        status = "shown" if self.show_details else "hidden"
        self.notify(f"Service details {status}")

    def action_toggle_startup(self) -> None:
        """Toggle startup instructions panel."""
        self.show_startup = not self.show_startup
        self.refresh(recompose=True)

    def action_launch_model_manager(self) -> None:
        """Launch Model Manager TUI in external terminal."""
        self.notify("Launching Model Manager TUI...")
        try:
            # Try to launch in new terminal window
            subprocess.Popen([
                "osascript", "-e",
                'tell application "Terminal" to do script "kitty-model-manager tui"'
            ])
            self.notify("Model Manager TUI launched in new terminal")
        except Exception as e:
            self.notify(f"Error launching Model Manager: {e}", severity="error")

    def action_launch_cli(self) -> None:
        """Launch CLI in external terminal."""
        self.notify("Launching KITTY CLI...")
        try:
            subprocess.Popen([
                "osascript", "-e",
                'tell application "Terminal" to do script "kitty-cli shell"'
            ])
            self.notify("KITTY CLI launched in new terminal")
        except Exception as e:
            self.notify(f"Error launching CLI: {e}", severity="error")


cli_app = typer.Typer(help="KITTY Unified Launcher TUI")


@cli_app.command()
def run():
    """Launch the KITTY Unified Launcher TUI."""
    app = KittyLauncherApp()
    app.run()


def main():
    """Entry point for the kitty command."""
    cli_app()


if __name__ == "__main__":
    main()
