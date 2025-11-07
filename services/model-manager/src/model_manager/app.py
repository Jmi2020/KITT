# noqa: D401
"""Main Textual TUI application for KITTY Model Manager."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from .config import ConfigManager
from .health import HealthChecker, HealthCheckResult
from .models import ServerStatus
from .process import ProcessManager
from .scanner import ModelRegistry, ModelScanner
from .supervisor import ServerSupervisor, SupervisorState

logger = logging.getLogger(__name__)


class StatusPanel(Static):
    """Widget displaying current server status."""

    DEFAULT_CSS = """
    StatusPanel {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
    }

    StatusPanel .status-ready {
        color: $success;
    }

    StatusPanel .status-loading {
        color: $warning;
    }

    StatusPanel .status-failed {
        color: $error;
    }

    StatusPanel .status-stopped {
        color: $text-muted;
    }
    """

    status: reactive[ServerStatus] = reactive(ServerStatus.STOPPED)
    pid: reactive[Optional[int]] = reactive(None)
    model_name: reactive[str] = reactive("None")
    model_alias: reactive[str] = reactive("N/A")
    endpoint: reactive[str] = reactive("N/A")
    uptime: reactive[str] = reactive("00:00:00")
    restart_count: reactive[int] = reactive(0)
    latency: reactive[Optional[float]] = reactive(None)
    slots_idle: reactive[Optional[int]] = reactive(None)
    slots_processing: reactive[Optional[int]] = reactive(None)

    def render(self) -> str:
        """Render status panel content."""
        status_class = f"status-{self.status.value}"
        status_display = self.status.value.upper()

        lines = [
            f"[bold]Server Status[/bold]",
            f"",
            f"Status: [{status_class}]{status_display}[/{status_class}]",
            f"PID: {self.pid if self.pid else '-'}",
            f"Model: {self.model_name}",
            f"Alias: {self.model_alias}",
            f"Endpoint: {self.endpoint}",
        ]

        if self.status not in [ServerStatus.STOPPED, ServerStatus.CRASHED]:
            lines.append(f"Uptime: {self.uptime}")

        if self.restart_count > 0:
            lines.append(f"Restarts: {self.restart_count}")

        if self.latency is not None:
            lines.append(f"Latency: {self.latency:.0f}ms")

        if self.slots_idle is not None:
            lines.append(
                f"Slots: {self.slots_idle} idle, {self.slots_processing} processing"
            )

        return "\n".join(lines)

    def update_from_state(self, state: SupervisorState) -> None:
        """Update display from supervisor state."""
        self.status = state.status
        self.pid = state.pid
        self.model_name = state.config.primary_model
        self.model_alias = state.config.model_alias
        self.endpoint = state.config.endpoint
        self.restart_count = state.restart_count

        # Format uptime
        if state.uptime_seconds > 0:
            hours = int(state.uptime_seconds // 3600)
            minutes = int((state.uptime_seconds % 3600) // 60)
            seconds = int(state.uptime_seconds % 60)
            self.uptime = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            self.uptime = "00:00:00"

        # Update health check info
        if state.last_health_check:
            hc = state.last_health_check
            self.latency = hc.latency_ms
            self.slots_idle = hc.slots_idle
            self.slots_processing = hc.slots_processing


class ModelListPanel(Static):
    """Widget displaying available models."""

    DEFAULT_CSS = """
    ModelListPanel {
        height: auto;
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
    }

    ModelListPanel .model-complete {
        color: $success;
    }

    ModelListPanel .model-incomplete {
        color: $warning;
    }
    """

    registry: reactive[Optional[ModelRegistry]] = reactive(None)
    selected_family: reactive[Optional[str]] = reactive(None)

    def render(self) -> str:
        """Render model list content."""
        if not self.registry:
            return "[dim]Scanning for models...[/dim]"

        lines = [
            f"[bold]Available Models[/bold]",
            f"",
            f"Found {self.registry.total_models} models in {self.registry.total_families} families",
            f"Total size: {self.registry.total_size_gb:.1f} GB",
            f"",
        ]

        # List families
        for i, family_name in enumerate(sorted(self.registry.families.keys()), 1):
            models = self.registry.families[family_name]
            prefix = "▶" if family_name == self.selected_family else " "
            lines.append(f"{prefix} {i}. [cyan]{family_name}[/cyan] ({len(models)} models)")

            # Show models if selected
            if family_name == self.selected_family:
                for model in models:
                    status_class = (
                        "model-complete" if model.is_complete else "model-incomplete"
                    )
                    status_icon = "✓" if model.is_complete else "⚠"
                    size_gb = model.size_bytes / (1024**3)

                    details = [
                        f"{model.quantization.value}",
                        f"{size_gb:.1f}GB",
                    ]

                    if model.shard_total and model.shard_total > 1:
                        details.append(f"{model.file_count}/{model.shard_total} shards")

                    if model.estimated_params_billions:
                        details.append(f"~{model.estimated_params_billions:.0f}B params")

                    lines.append(
                        f"   [{status_class}]{status_icon}[/{status_class}] {model.name} [dim]({', '.join(details)})[/dim]"
                    )

        return "\n".join(lines)


class LogPanel(Static):
    """Widget displaying recent log messages."""

    DEFAULT_CSS = """
    LogPanel {
        height: 8;
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
        overflow-y: scroll;
    }
    """

    max_lines: int = 50

    def __init__(self) -> None:
        """Initialize log panel."""
        super().__init__()
        self._log_lines: list[str] = []

    def render(self) -> str:
        """Render log content."""
        if not self._log_lines:
            return "[dim]No logs yet...[/dim]"

        return "\n".join(self._log_lines[-20:])  # Show last 20 lines

    def add_log(self, message: str, level: str = "info") -> None:
        """Add a log message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = {
            "debug": "dim",
            "info": "white",
            "warning": "yellow",
            "error": "red",
            "success": "green",
        }.get(level, "white")

        formatted = f"[{color}]{timestamp}[/{color}] {message}"
        self._log_lines.append(formatted)

        # Trim old logs
        if len(self._log_lines) > self.max_lines:
            self._log_lines = self._log_lines[-self.max_lines :]

        self.refresh()


class ModelManagerApp(App):
    """KITTY Model Manager TUI Application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
        width: 100%;
    }

    #left-panel {
        width: 60%;
        height: 100%;
    }

    #right-panel {
        width: 40%;
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "start_server", "Start"),
        Binding("x", "stop_server", "Stop"),
        Binding("t", "restart_server", "Restart"),
        Binding("h", "check_health", "Health"),
        Binding("m", "scan_models", "Scan"),
    ]

    def __init__(
        self,
        env_path: Optional[Path] = None,
        pid_file: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ) -> None:
        """Initialize application.

        Args:
            env_path: Optional path to .env file
            pid_file: Optional PID file path
            log_file: Optional log file path
        """
        super().__init__()

        # Initialize components
        self.config_manager = ConfigManager(env_path)
        self.process_manager = ProcessManager(pid_file=pid_file, log_file=log_file)
        self.supervisor = ServerSupervisor(
            config_manager=self.config_manager,
            process_manager=self.process_manager,
        )

        # Set up status callback
        self.supervisor.set_status_callback(self._on_status_change)

        # UI components (will be set in compose)
        self.status_panel: Optional[StatusPanel] = None
        self.model_panel: Optional[ModelListPanel] = None
        self.log_panel: Optional[LogPanel] = None

        # Background tasks
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    def compose(self) -> ComposeResult:
        """Compose application layout."""
        yield Header()

        with Container(id="main-container"):
            with Horizontal():
                with Vertical(id="left-panel"):
                    self.status_panel = StatusPanel()
                    yield self.status_panel

                    self.log_panel = LogPanel()
                    yield self.log_panel

                with Vertical(id="right-panel"):
                    self.model_panel = ModelListPanel()
                    yield self.model_panel

        yield Footer()

    async def on_mount(self) -> None:
        """Handle application mount."""
        self.title = "KITTY Model Manager"
        self.sub_title = "llama.cpp server management"

        # Log startup
        if self.log_panel:
            self.log_panel.add_log("KITTY Model Manager started", "success")

        # Initial state update
        await self._update_status()

        # Scan for models
        await self._scan_models()

        # Start background monitoring
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def on_unmount(self) -> None:
        """Handle application unmount."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def action_quit(self) -> None:
        """Quit application."""
        self.exit()

    async def action_refresh(self) -> None:
        """Refresh status."""
        if self.log_panel:
            self.log_panel.add_log("Refreshing status...", "info")
        await self._update_status()

    async def action_start_server(self) -> None:
        """Start llama.cpp server."""
        if self.log_panel:
            self.log_panel.add_log("Starting server...", "info")

        try:
            state = await asyncio.to_thread(self.supervisor.start, wait_for_ready=True)
            if self.log_panel:
                self.log_panel.add_log(
                    f"Server started (PID: {state.pid})", "success"
                )
        except Exception as e:
            if self.log_panel:
                self.log_panel.add_log(f"Failed to start: {e}", "error")

    async def action_stop_server(self) -> None:
        """Stop llama.cpp server."""
        if self.log_panel:
            self.log_panel.add_log("Stopping server...", "info")

        try:
            state = await asyncio.to_thread(self.supervisor.stop)
            if self.log_panel:
                self.log_panel.add_log("Server stopped", "success")
        except Exception as e:
            if self.log_panel:
                self.log_panel.add_log(f"Failed to stop: {e}", "error")

    async def action_restart_server(self) -> None:
        """Restart llama.cpp server."""
        if self.log_panel:
            self.log_panel.add_log("Restarting server...", "info")

        try:
            state = await asyncio.to_thread(
                self.supervisor.restart, wait_for_ready=True
            )
            if self.log_panel:
                self.log_panel.add_log(
                    f"Server restarted (PID: {state.pid})", "success"
                )
        except Exception as e:
            if self.log_panel:
                self.log_panel.add_log(f"Failed to restart: {e}", "error")

    async def action_check_health(self) -> None:
        """Perform health check."""
        if self.log_panel:
            self.log_panel.add_log("Running health check...", "info")

        try:
            state = await asyncio.to_thread(self.supervisor.check_health)
            if state.last_health_check:
                hc = state.last_health_check
                if self.log_panel:
                    self.log_panel.add_log(
                        f"Health: {hc.status.value} ({hc.latency_ms:.0f}ms)", "success"
                    )
            else:
                if self.log_panel:
                    self.log_panel.add_log(f"Status: {state.status.value}", "info")
        except Exception as e:
            if self.log_panel:
                self.log_panel.add_log(f"Health check failed: {e}", "error")

    async def action_scan_models(self) -> None:
        """Scan for available models."""
        if self.log_panel:
            self.log_panel.add_log("Scanning for models...", "info")

        await self._scan_models()

        if self.log_panel and self.model_panel and self.model_panel.registry:
            reg = self.model_panel.registry
            self.log_panel.add_log(
                f"Found {reg.total_models} models in {reg.total_families} families",
                "success",
            )

    async def _update_status(self) -> None:
        """Update status panel."""
        try:
            state = await asyncio.to_thread(self.supervisor.get_state)
            if self.status_panel:
                self.status_panel.update_from_state(state)
        except Exception as e:
            logger.error(f"Failed to update status: {e}")

    async def _scan_models(self) -> None:
        """Scan for models and update panel."""
        try:
            config = await asyncio.to_thread(self.config_manager.load)
            scanner = ModelScanner(config.models_dir)
            registry = await asyncio.to_thread(scanner.scan)

            if self.model_panel:
                self.model_panel.registry = registry
        except Exception as e:
            logger.error(f"Failed to scan models: {e}")
            if self.log_panel:
                self.log_panel.add_log(f"Model scan failed: {e}", "error")

    def _on_status_change(self, state: SupervisorState) -> None:
        """Handle status change callback from supervisor."""
        if self.status_panel:
            self.status_panel.update_from_state(state)

    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(5)  # Update every 5 seconds
                await self._update_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")


__all__ = ["ModelManagerApp"]
