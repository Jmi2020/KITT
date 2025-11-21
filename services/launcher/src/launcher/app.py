"""KITTY Access-All Console - unified launcher for everything in the stack."""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import webbrowser
from asyncio.subprocess import PIPE, STDOUT
from typing import Awaitable, Callable, Optional

import typer
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from dotenv import load_dotenv

from launcher.managers.docker_manager import DockerManager
from launcher.managers.llama_manager import LlamaManager
from launcher.panels.control_center import (
    ControlActionRequested,
    ControlCenterPanel,
)
from launcher.panels.operation_log import OperationLogPanel
from launcher.panels.system_status import DetailedStatusPanel, SystemStatusPanel
from launcher.utils.paths import find_first_existing, get_project_root
from launcher.viewers import ReasoningLogViewer


def _load_environment() -> None:
    """Load .env so launcher picks up configured ports and aliases."""
    try:
        env_path = get_project_root() / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
    except Exception:
        # Fallback silently if loading fails; launcher still works with defaults.
        pass


_load_environment()


class StartupPanel(Static):
    """Startup instructions for users who want the manual path."""

    DEFAULT_CSS = """
    StartupPanel {
        border: solid $accent;
        padding: 2 3;
        margin: 1 2;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Manual Startup Reference[/bold]\n\n"
            "1. Launch llama.cpp dual servers:\n"
            "   [cyan]kitty-model-manager tui[/cyan]\n\n"
            "2. Start stack (validated):\n"
            "   [cyan]./ops/scripts/start-all.sh[/cyan]\n\n"
            "3. Open CLI shell:\n"
            "   [cyan]kitty-cli shell[/cyan]\n\n"
            "[dim]Tip: Use the Access-All quick actions instead of typing these manually.[/dim]"
        )


class KittyLauncherApp(App):
    """Textual TUI that acts as the central control desk for KITTY."""

    TITLE = "KITTY Access-All Console"
    CSS = """
    Screen {
        align: center top;
    }

    #main-container {
        width: 110;
        padding-bottom: 1;
    }

    #hero-row {
        width: 100%;
    }

    #hero-row ControlCenterPanel {
        min-width: 65;
        width: 2fr;
    }

    #hero-row SystemStatusPanel {
        min-width: 30;
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("k", "start_stack", "Start KITTY"),
        Binding("x", "stop_stack", "Stop KITTY"),
        Binding("c", "launch_cli", "CLI"),
        Binding("m", "launch_model_manager", "Model Manager"),
        Binding("o", "open_web_console", "Web Console"),
        Binding("i", "launch_io_dashboard", "I/O Dashboard"),
        Binding("h", "toggle_health", "Health Status"),
        Binding("d", "toggle_details", "Service Details"),
        Binding("r", "toggle_reasoning", "Reasoning Logs"),
        Binding("s", "toggle_startup", "Startup Info"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.show_startup = False
        self.show_health = True
        self.show_details = False
        self.show_reasoning = False
        self._operation_busy = False
        self._log_panel: OperationLogPanel | None = None
        self.project_root = get_project_root()
        self.docker_manager = DockerManager()
        self.llama_manager = LlamaManager()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="content"):
                with Horizontal(id="hero-row"):
                    yield ControlCenterPanel()
                    if self.show_health:
                        yield SystemStatusPanel()
                if self.show_details:
                    yield DetailedStatusPanel()
                if self.show_reasoning:
                    yield ReasoningLogViewer()
                yield OperationLogPanel()
                if self.show_startup:
                    yield StartupPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize handles once the DOM is ready."""
        try:
            self._log_panel = self.query_one(OperationLogPanel)
        except Exception:
            self._log_panel = None

    # ---------------------------------------------------------------------
    # Panel toggles
    # ---------------------------------------------------------------------

    def action_toggle_health(self) -> None:
        self.show_health = not self.show_health
        self.refresh(recompose=True)
        status = "shown" if self.show_health else "hidden"
        self.notify(f"Health panel {status}")

    def action_toggle_details(self) -> None:
        self.show_details = not self.show_details
        self.refresh(recompose=True)

    def action_toggle_startup(self) -> None:
        self.show_startup = not self.show_startup
        self.refresh(recompose=True)

    def action_toggle_reasoning(self) -> None:
        self.show_reasoning = not self.show_reasoning
        self.refresh(recompose=True)

    # ---------------------------------------------------------------------
    # Quick actions
    # ---------------------------------------------------------------------

    def action_start_stack(self) -> None:
        """Run the validated startup script."""
        self._schedule_stack_task(
            "Starting KITTY stack",
            ("ops/scripts/start-all.sh", "ops/scripts/start-kitty-validated.sh"),
        )

    def action_stop_stack(self) -> None:
        """Stop llama.cpp, Docker, and helper services."""
        self._schedule_stack_task(
            "Stopping KITTY stack",
            ("ops/scripts/stop-all.sh", "ops/scripts/stop-kitty.sh"),
        )

    def action_start_llama(self) -> None:
        """Launch only the llama.cpp servers."""
        script = find_first_existing(("ops/scripts/llama/start.sh",))
        if not script:
            msg = "Llama start script not found (ops/scripts/llama/start.sh)"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command("Starting llama.cpp servers", ["bash", str(script)])

    def action_stop_llama(self) -> None:
        """Stop llama.cpp servers."""
        script = find_first_existing(("ops/scripts/llama/stop.sh",))
        if not script:
            msg = "Llama stop script not found (ops/scripts/llama/stop.sh)"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command("Stopping llama.cpp servers", ["bash", str(script)])

    def action_restart_llama(self) -> None:
        """Restart llama.cpp servers."""
        script = find_first_existing(("ops/scripts/llama/start.sh",))
        stop_script = find_first_existing(("ops/scripts/llama/stop.sh",))
        if not script or not stop_script:
            msg = "Llama start/stop scripts not found"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command(
            "Restarting llama.cpp servers",
            ["bash", "-lc", f"{stop_script} && {script}"],
        )

    def action_start_ollama(self) -> None:
        """Start Ollama (GPT-OSS) server."""
        script = find_first_existing(("ops/scripts/ollama/start.sh",))
        if not script:
            msg = "Ollama start script not found (ops/scripts/ollama/start.sh)"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command("Starting Ollama (GPT-OSS)", ["bash", str(script)])

    def action_stop_ollama(self) -> None:
        """Stop Ollama server."""
        script = find_first_existing(("ops/scripts/ollama/stop.sh",))
        if not script:
            msg = "Ollama stop script not found (ops/scripts/ollama/stop.sh)"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command("Stopping Ollama (GPT-OSS)", ["bash", str(script)])

    def action_restart_ollama(self) -> None:
        """Restart Ollama server."""
        start_script = find_first_existing(("ops/scripts/ollama/start.sh",))
        stop_script = find_first_existing(("ops/scripts/ollama/stop.sh",))
        if not start_script or not stop_script:
            msg = "Ollama start/stop scripts not found"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command(
            "Restarting Ollama (GPT-OSS)",
            ["bash", "-lc", f"{stop_script} && {start_script}"],
        )

    def action_start_docker(self) -> None:
        """Launch only the docker compose stack."""
        command = [
            "docker",
            "compose",
            "-f",
            "infra/compose/docker-compose.yml",
            "up",
            "-d",
            "--build",
        ]
        self._schedule_command("Starting Docker stack", command)

    def action_stop_docker(self) -> None:
        """Stop docker compose stack."""
        command = [
            "docker",
            "compose",
            "-f",
            "infra/compose/docker-compose.yml",
            "down",
        ]
        self._schedule_command("Stopping Docker stack", command)

    def action_restart_docker(self) -> None:
        """Restart docker compose stack."""
        command = [
            "bash",
            "-lc",
            "docker compose -f infra/compose/docker-compose.yml down && docker compose -f infra/compose/docker-compose.yml up -d --build",
        ]
        self._schedule_command("Restarting Docker stack", command)

    def action_launch_model_manager(self) -> None:
        """Replace the console with kitty-model-manager."""
        self._log("Launching Model Manager...", "cyan")
        self.exit()
        os.execvp("kitty-model-manager", ["kitty-model-manager", "tui"])

    async def action_launch_cli(self) -> None:
        """Validate health before starting kitty-cli shell."""
        self.notify("Validating stack health before launching CLI...")
        self._log("Checking llama.cpp + Docker before CLI launch...", "cyan")

        llama_status = await self.llama_manager.get_status()
        if not llama_status.running:
            msg = "llama.cpp is offline. Use Start KITTY first."
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return

        if not self.docker_manager.is_docker_running():
            msg = "Docker daemon is not running."
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return

        services = self.docker_manager.list_services()
        running_count = sum(1 for s in services if s.state == "running")
        if running_count == 0:
            msg = "No Docker services running. Start KITTY first."
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return

        self.notify("Stack healthy. Launching CLI...")
        self._log("Stack healthy. Launching kitty-cli shell.", "green")
        await asyncio.sleep(0.5)
        self.exit()
        os.execvp("kitty-cli", ["kitty-cli", "shell"])

    def action_open_web_console(self) -> None:
        """Open the React/Vision UI in the default browser."""
        url = os.getenv("KITTY_UI_BASE", "http://localhost:4173")
        self._open_url(url, "Web Console")

    def action_launch_io_dashboard(self) -> None:
        """Replace the console with the I/O control dashboard."""
        script = find_first_existing(("ops/scripts/kitty-io-control.py",))
        if not script:
            msg = "I/O dashboard script not found (ops/scripts/kitty-io-control.py)"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return

        self._log("Launching I/O dashboard...", "cyan")
        self.exit()
        os.execvp(sys.executable, [sys.executable, str(script)])

    # ---------------------------------------------------------------------
    # Event wiring for the control center buttons
    # ---------------------------------------------------------------------

    @on(ControlActionRequested)
    async def handle_control_action(self, event: ControlActionRequested) -> None:
        """Route panel button presses to Textual actions."""
        method_name = f"action_{event.action}"
        handler: Optional[Callable[[], Awaitable[None] | None]] = getattr(
            self, method_name, None
        )

        if not handler:
            self._log(f"Unknown action: {event.action}", "yellow")
            return

        result = handler()
        if inspect.isawaitable(result):
            await result

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def _schedule_stack_task(self, label: str, candidates: tuple[str, ...]) -> None:
        """Schedule a long-running stack command without freezing the UI."""
        script = find_first_existing(candidates)
        if not script:
            msg = f"Script not found for: {label}"
            self.notify(msg, severity="error")
            self._log(msg, "red")
            return
        self._schedule_command(label, ["bash", str(script)])

    def _schedule_command(self, label: str, command: list[str]) -> None:
        """Schedule a shell command without blocking the UI."""
        if self._operation_busy:
            self.notify("Another operation is in progress", severity="warning")
            return

        self._operation_busy = True

        async def runner() -> None:
            try:
                await self._stream_command(command, label)
            finally:
                self._operation_busy = False

        asyncio.create_task(runner())

    async def _stream_command(self, command: list[str], label: str) -> None:
        """Run a long-lived command and stream output into the log panel."""
        self._log(f"{label}...", "cyan")
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(self.project_root),
                stdout=PIPE,
                stderr=STDOUT,
            )

            assert process.stdout
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore").rstrip()
                if text:
                    self._log(text)

            return_code = await process.wait()
            if return_code == 0:
                self._log(f"{label} complete.", "green")
                self.notify(f"{label} finished")
            else:
                msg = f"{label} failed (exit {return_code})"
                self._log(msg, "red")
                self.notify(msg, severity="error")
        except FileNotFoundError:
            msg = f"Unable to run command: {command[0]} not found"
            self._log(msg, "red")
            self.notify(msg, severity="error")

    def _open_url(self, url: str, label: str) -> None:
        """Open a URL and log the action."""
        try:
            webbrowser.open(url, new=2)
            self._log(f"Opened {label}: {url}", "green")
            self.notify(f"{label} opened in browser")
        except Exception as exc:  # pragma: no cover - depends on OS browser
            msg = f"Failed to open {label}: {exc}"
            self._log(msg, "red")
            self.notify(msg, severity="error")

    def _log(self, message: str, style: str = "white") -> None:
        """Write to the operation log safely."""
        try:
            panel = self._log_panel or self.query_one(OperationLogPanel)
        except Exception:
            panel = None

        if panel:
            panel.write(message, style)


cli_app = typer.Typer(help="KITTY Access-All console")


@cli_app.command()
def run() -> None:
    """Launch the Textual console."""
    app = KittyLauncherApp()
    app.run()


def main() -> None:
    """Entry point for the kitty console."""
    cli_app()


if __name__ == "__main__":
    main()
