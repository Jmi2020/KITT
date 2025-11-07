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
        height: 1fr;
        border: solid $primary;
        padding: 1 2;
        margin: 1 0;
        overflow-y: auto;
        overflow-x: hidden;
    }

    ModelListPanel .model-complete {
        color: $success;
    }

    ModelListPanel .model-incomplete {
        color: $warning;
    }

    ModelListPanel .selected {
        background: $accent;
        color: $text;
    }
    """

    registry: reactive[Optional[ModelRegistry]] = reactive(None)
    selected_family_idx: reactive[int] = reactive(0)
    selected_model_idx: reactive[int] = reactive(-1)  # -1 means family selected, >=0 means model selected
    expanded_family: reactive[Optional[str]] = reactive(None)

    def render(self) -> str:
        """Render model list content."""
        if not self.registry:
            return "[dim]Scanning for models...[/dim]"

        lines = [
            f"[bold]Available Models[/bold]",
            f"",
            f"Found {self.registry.total_models} models in {self.registry.total_families} families",
            f"Total size: {self.registry.total_size_gb:.1f} GB",
            f"[dim]↑/↓: Navigate  Enter: Expand/Switch  Esc: Collapse[/dim]",
            f"",
        ]

        # List families
        sorted_families = sorted(self.registry.families.keys())
        for i, family_name in enumerate(sorted_families):
            models = self.registry.families[family_name]

            # Determine selection indicators
            is_family_selected = (i == self.selected_family_idx and self.selected_model_idx == -1)
            is_expanded = family_name == self.expanded_family

            # Family line
            prefix = "▼" if is_expanded else "▶"
            family_line = f"{prefix} {i + 1}. [cyan]{family_name}[/cyan] ({len(models)} models)"

            if is_family_selected:
                family_line = f"[reverse]{family_line}[/reverse]"

            lines.append(family_line)

            # Show models if expanded
            if is_expanded:
                for j, model in enumerate(models):
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

                    model_line = f"   [{status_class}]{status_icon}[/{status_class}] {model.name} [dim]({', '.join(details)})[/dim]"

                    # Highlight selected model
                    if i == self.selected_family_idx and j == self.selected_model_idx:
                        model_line = f"[reverse]{model_line}[/reverse]"

                    lines.append(model_line)

        return "\n".join(lines)

    def get_selected_model(self):
        """Get the currently selected model object."""
        if not self.registry or self.selected_model_idx < 0:
            return None

        sorted_families = sorted(self.registry.families.keys())
        if self.selected_family_idx >= len(sorted_families):
            return None

        family_name = sorted_families[self.selected_family_idx]
        models = self.registry.families[family_name]

        if self.selected_model_idx >= len(models):
            return None

        return models[self.selected_model_idx]


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
        Binding("up", "navigate_up", "Up", show=False),
        Binding("down", "navigate_down", "Down", show=False),
        Binding("enter", "select_item", "Select", show=False),
        Binding("escape", "collapse", "Collapse", show=False),
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
        import time

        if self.log_panel:
            self.log_panel.add_log("Starting server...", "info")

        start_time = time.time()

        # Progress callback for model loading
        def on_progress(result, attempt, max_attempts):
            """Handle progress updates from health checker."""
            try:
                elapsed = int(time.time() - start_time)
                status_msg = result.status.value if result.status else "unknown"

                # Create progress message based on status
                if status_msg == "READY":
                    msg = f"Model loaded ({attempt} checks, {elapsed}s elapsed)"
                    log_type = "success"
                elif status_msg == "LOADING":
                    msg = f"Loading model... ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "info"
                elif status_msg == "STARTING":
                    msg = f"Server starting... ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "info"
                else:
                    msg = f"Status: {status_msg} ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "warning"

                # Thread-safe UI update - post to event loop
                if self.log_panel:
                    self.call_from_thread(self.log_panel.add_log, msg, log_type)
            except Exception as e:
                # Log errors in progress callback without failing
                import logging
                logging.error(f"Progress callback error: {e}")

        try:
            state = await asyncio.to_thread(
                self.supervisor.start, wait_for_ready=True, on_progress=on_progress
            )
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
        import time

        if self.log_panel:
            self.log_panel.add_log("Restarting server...", "info")

        start_time = time.time()

        # Progress callback for model loading
        def on_progress(result, attempt, max_attempts):
            """Handle progress updates from health checker."""
            try:
                elapsed = int(time.time() - start_time)
                status_msg = result.status.value if result.status else "unknown"

                # Create progress message based on status
                if status_msg == "READY":
                    msg = f"Model loaded ({attempt} checks, {elapsed}s elapsed)"
                    log_type = "success"
                elif status_msg == "LOADING":
                    msg = f"Loading model... ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "info"
                elif status_msg == "STARTING":
                    msg = f"Server starting... ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "info"
                else:
                    msg = f"Status: {status_msg} ({attempt}/{max_attempts}, {elapsed}s elapsed)"
                    log_type = "warning"

                # Thread-safe UI update - post to event loop
                if self.log_panel:
                    self.call_from_thread(self.log_panel.add_log, msg, log_type)
            except Exception as e:
                # Log errors in progress callback without failing
                import logging
                logging.error(f"Progress callback error: {e}")

        try:
            state = await asyncio.to_thread(
                self.supervisor.restart, wait_for_ready=True, on_progress=on_progress
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

    def action_navigate_up(self) -> None:
        """Navigate up in the model list."""
        if not self.model_panel or not self.model_panel.registry:
            return

        sorted_families = sorted(self.model_panel.registry.families.keys())
        if not sorted_families:
            return

        # If we're in a model, move up within models or back to family
        if self.model_panel.selected_model_idx >= 0:
            self.model_panel.selected_model_idx -= 1
            # If we've gone past the first model, go back to family selection
            if self.model_panel.selected_model_idx < 0:
                self.model_panel.selected_model_idx = -1

        # If we're on a family, move to previous family
        elif self.model_panel.selected_family_idx > 0:
            self.model_panel.selected_family_idx -= 1
            # Collapse the previous expanded family
            self.model_panel.expanded_family = None

    def action_navigate_down(self) -> None:
        """Navigate down in the model list."""
        if not self.model_panel or not self.model_panel.registry:
            return

        sorted_families = sorted(self.model_panel.registry.families.keys())
        if not sorted_families:
            return

        family_name = sorted_families[self.model_panel.selected_family_idx]
        models = self.model_panel.registry.families[family_name]

        # If we're on a family (not expanded or not in models yet)
        if self.model_panel.selected_model_idx == -1:
            # If family is expanded, move into first model
            if self.model_panel.expanded_family == family_name:
                if models:
                    self.model_panel.selected_model_idx = 0
            # Otherwise move to next family
            elif self.model_panel.selected_family_idx < len(sorted_families) - 1:
                self.model_panel.selected_family_idx += 1

        # If we're in models, move to next model or next family
        else:
            if self.model_panel.selected_model_idx < len(models) - 1:
                self.model_panel.selected_model_idx += 1
            # At last model, move to next family
            elif self.model_panel.selected_family_idx < len(sorted_families) - 1:
                self.model_panel.selected_family_idx += 1
                self.model_panel.selected_model_idx = -1
                self.model_panel.expanded_family = None

    async def action_select_item(self) -> None:
        """Expand family or switch to selected model."""
        if not self.model_panel or not self.model_panel.registry:
            return

        sorted_families = sorted(self.model_panel.registry.families.keys())
        if not sorted_families:
            return

        family_name = sorted_families[self.model_panel.selected_family_idx]

        # If on family line, toggle expand/collapse
        if self.model_panel.selected_model_idx == -1:
            if self.model_panel.expanded_family == family_name:
                self.model_panel.expanded_family = None
            else:
                self.model_panel.expanded_family = family_name
        # If on model line, switch to that model
        else:
            model = self.model_panel.get_selected_model()
            if model and model.is_complete:
                if self.log_panel:
                    self.log_panel.add_log(f"Switching to {model.name}...", "info")

                try:
                    # Get the config to determine model alias
                    config = await asyncio.to_thread(self.config_manager.load)

                    # Determine model path relative to models_dir
                    model_path = f"{family_name}/{model.name}"

                    state = await asyncio.to_thread(
                        self.supervisor.switch_model,
                        model_path,
                        alias=None,  # Let supervisor determine alias
                        wait_for_ready=True
                    )

                    if self.log_panel:
                        self.log_panel.add_log(
                            f"Switched to {model.name} (PID: {state.pid})",
                            "success",
                        )
                except Exception as e:
                    if self.log_panel:
                        self.log_panel.add_log(f"Failed to switch: {e}", "error")
            elif model and not model.is_complete:
                if self.log_panel:
                    self.log_panel.add_log(
                        f"Cannot switch to incomplete model: {model.name}",
                        "warning",
                    )

    def action_collapse(self) -> None:
        """Collapse expanded family and return to family selection."""
        if not self.model_panel:
            return

        self.model_panel.expanded_family = None
        self.model_panel.selected_model_idx = -1

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
