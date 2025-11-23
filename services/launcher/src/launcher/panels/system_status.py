"""System status panel showing Ollama (GPT-OSS), llama.cpp, and Docker health."""

import asyncio

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static
from textual.worker import Worker

from launcher.managers.docker_manager import DockerManager
from launcher.managers.llama_manager import LlamaInstanceStatus, LlamaManager
from launcher.managers.ollama_manager import OllamaManager, OllamaStatus


class SystemStatusPanel(Static):
    """Real-time system status display."""

    DEFAULT_CSS = """
    SystemStatusPanel {
        border: solid $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }

    .status-grid {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 2fr;
        padding: 0 1;
    }

    .status-label {
        text-style: bold;
        color: $text-muted;
    }

    .status-value {
        color: $text;
    }

    .status-healthy {
        color: $success;
    }

    .status-warning {
        color: $warning;
    }

    .status-error {
        color: $error;
    }

    .service-list {
        padding: 1 0;
    }

    .service-item {
        padding: 0 1;
    }
    """

    # Reactive properties that trigger UI updates
    ollama_status = reactive("Unknown")
    ollama_detail = reactive("")
    llama_status = reactive("Unknown")
    llama_model = reactive("")
    docker_status = reactive("Unknown")
    service_count = reactive(0)
    running_count = reactive(0)

    def __init__(self):
        """Initialize status panel."""
        super().__init__()
        self.llama_manager = LlamaManager()
        self.ollama_manager = OllamaManager()
        self.docker_manager = DockerManager()
        self._update_worker: Worker | None = None
        self.llama_instances: list[LlamaInstanceStatus] = []
        self.ollama: OllamaStatus | None = None

    def compose(self) -> ComposeResult:
        """Compose the status panel layout."""
        yield Static("[bold cyan]KITTY System Status[/bold cyan]\n")

        with Container(classes="status-grid"):
            # Ollama status
            yield Static("Ollama (GPT-OSS):", classes="status-label")
            yield Static(self._format_ollama_status(), id="ollama-status", classes="status-value")
            yield Static("", classes="status-label")
            yield Static("[dim]Checking models...[/dim]", id="ollama-status-detail", classes="service-list")

            # llama.cpp status
            yield Static("llama.cpp Servers:", classes="status-label")
            yield Static(self._format_llama_status(), id="llama-status", classes="status-value")
            yield Static("", classes="status-label")
            yield Static("[dim]Detecting instances...[/dim]", id="llama-status-detail", classes="service-list")

            # Docker status
            yield Static("Docker Services:", classes="status-label")
            yield Static(self._format_docker_status(), id="docker-status", classes="status-value")

    def on_mount(self) -> None:
        """Start status updates when panel is mounted."""
        self.start_update_loop()

    def on_unmount(self) -> None:
        """Stop updates when panel is unmounted."""
        if self._update_worker:
            self._update_worker.cancel()

    @work(exclusive=True)
    async def start_update_loop(self) -> None:
        """Background task to update status every 3 seconds."""
        while True:
            await self.update_status()
            await asyncio.sleep(3.0)

    async def update_status(self) -> None:
        """Fetch and update status information."""
        # Update Ollama (GPT-OSS) status
        self.ollama = await self.ollama_manager.get_status()
        if self.ollama.running:
            models = self.ollama.models or []
            if models:
                self.ollama_status = "Healthy"
                top = models[:3]
                more = f" (+{len(models) - len(top)})" if len(models) > len(top) else ""
                self.ollama_detail = ", ".join(top) + more if top else "online"
            else:
                self.ollama_status = "Degraded"
                self.ollama_detail = "No models running"
        else:
            self.ollama_status = "Offline"
            self.ollama_detail = self.ollama.error or "unreachable"

        # Update llama.cpp status
        llama_instances = await self.llama_manager.get_all_statuses()
        self.llama_instances = llama_instances

        enabled_instances = [inst for inst in llama_instances if inst.enabled]
        running_instances = [inst for inst in enabled_instances if inst.running]

        if not enabled_instances:
            self.llama_status = "Offline"
            self.llama_model = ""
        elif len(running_instances) == len(enabled_instances):
            self.llama_status = "Healthy"
            self.llama_model = running_instances[0].model or "unknown"
        elif running_instances:
            self.llama_status = "Degraded"
            self.llama_model = running_instances[0].model or "unknown"
        else:
            self.llama_status = "Offline"
            self.llama_model = ""

        # Update Docker status
        docker_running = self.docker_manager.is_docker_running()
        if docker_running:
            services = self.docker_manager.list_services()
            self.service_count = len(services)
            self.running_count = sum(1 for s in services if s.state == "running")
            self.docker_status = "Healthy"
        else:
            self.service_count = 0
            self.running_count = 0
            self.docker_status = "Offline"

        # Update UI
        self.refresh_display()

    def refresh_display(self) -> None:
        """Refresh the display with current status."""
        # Update llama.cpp status display
        llama_widget = self.query_one("#llama-status", Static)
        llama_widget.update(self._format_llama_status())

        # Update Ollama status display
        ollama_widget = self.query_one("#ollama-status", Static)
        ollama_widget.update(self._format_ollama_status())
        ollama_detail_widget = self.query_one("#ollama-status-detail", Static)
        ollama_detail_widget.update(self._format_ollama_detail())

        # Update list of llama servers
        detail_widget = self.query_one("#llama-status-detail", Static)
        detail_widget.update(self._format_llama_instances())

        # Update Docker status display
        docker_widget = self.query_one("#docker-status", Static)
        docker_widget.update(self._format_docker_status())

    def _format_llama_status(self) -> str:
        """Format llama.cpp status with color coding."""
        if self.llama_status == "Healthy":
            status_str = "[green]✓ All llama.cpp servers running[/green]"
        elif self.llama_status == "Degraded":
            status_str = "[yellow]⚠ Partial availability[/yellow]"
        else:
            status_str = "[red]✗ Offline[/red]"

        return status_str

    def _format_ollama_status(self) -> str:
        """Format Ollama (GPT-OSS) status with color coding."""
        if self.ollama_status == "Healthy":
            version = f" v{self.ollama.version}" if self.ollama and self.ollama.version else ""
            return f"[green]✓ Ollama online{version}[/green]"
        if self.ollama_status == "Degraded":
            return "[yellow]⚠ Ollama online (no models running)[/yellow]"
        return f"[red]✗ Ollama offline[/red]"

    def _format_ollama_detail(self) -> str:
        """Show top models or error detail."""
        if not self.ollama:
            return "[dim]Checking...[/dim]"
        if self.ollama.running and self.ollama_status == "Healthy":
            models = self.ollama.models or []
            if not models:
                return "[dim]No models listed[/dim]"
            return "[green]" + ", ".join(models[:3]) + ("[/green]" if models else "")
        if self.ollama_status == "Degraded":
            return "[yellow]No models running[/yellow]"
        return f"[dim]{self.ollama_detail}[/dim]"

    def _format_llama_instances(self) -> str:
        """Format the list of llama.cpp instances."""
        if not self.llama_instances:
            return "[dim]No instances detected[/dim]"

        lines = []
        for inst in self.llama_instances:
            label = f"{inst.name} [dim](:{inst.port})[/dim]"

            if not inst.enabled:
                lines.append(f"[dim]⏸ {label} — disabled[/dim]")
            elif inst.running:
                lines.append(f"[green]✓ {label}[/green]")
            else:
                reason = inst.error or "offline"
                if reason and "connection failed" in reason.lower():
                    reason = "not currently connected"
                lines.append(f"[yellow]• {label}[/yellow] [dim]- {reason}[/dim]")

        return "\n".join(lines)

    def _format_docker_status(self) -> str:
        """Format Docker status with color coding."""
        if self.docker_status == "Healthy":
            if self.service_count == 0:
                return "[yellow]⚠ No services discovered[/yellow]"

            if self.running_count == self.service_count:
                status_str = "[green]✓ Running[/green]\n"
            else:
                status_str = "[yellow]⚠ Partial[/yellow]\n"

            status_str += f"  Services: {self.running_count}/{self.service_count} running"

            if self.running_count < self.service_count:
                status_str += (
                    f"\n  [yellow]{self.service_count - self.running_count} "
                    "service(s) stopped[/yellow]"
                )
        else:
            status_str = "[red]✗ Offline[/red]\n  Docker daemon not running"

        return status_str


class DetailedStatusPanel(Static):
    """Detailed status panel with service list."""

    DEFAULT_CSS = """
    DetailedStatusPanel {
        border: solid $accent;
        padding: 1 2;
        margin: 1 2;
        height: auto;
        max-height: 20;
        overflow-y: auto;
    }

    .service-header {
        text-style: bold;
        padding: 1 0;
    }

    .service-item {
        padding: 0 2;
    }
    """

    def __init__(self):
        """Initialize detailed status panel."""
        super().__init__()
        self.docker_manager = DockerManager()

    def compose(self) -> ComposeResult:
        """Compose the detailed status layout."""
        yield Static("[bold]Docker Services[/bold]", classes="service-header")
        yield Static("Loading...", id="service-list")

    def on_mount(self) -> None:
        """Load services when mounted."""
        self.update_services()

    @work(exclusive=True)
    async def update_services(self) -> None:
        """Update the service list."""
        services = self.docker_manager.list_services()

        if not services:
            service_text = "[dim]No services found[/dim]"
        else:
            service_lines = []
            for service in services:
                # Color code by state
                if service.state == "running":
                    state_color = "green"
                    state_icon = "✓"
                elif service.state == "exited":
                    state_color = "red"
                    state_icon = "✗"
                else:
                    state_color = "yellow"
                    state_icon = "◆"

                # Format health indicator
                health = ""
                if service.health != "none":
                    if service.health == "healthy":
                        health = " [green](healthy)[/green]"
                    elif service.health == "unhealthy":
                        health = " [red](unhealthy)[/red]"
                    else:
                        health = f" [yellow]({service.health})[/yellow]"

                service_lines.append(
                    f"[{state_color}]{state_icon}[/{state_color}] {service.name:<15} "
                    f"[dim]{service.state}[/dim]{health}"
                )

            service_text = "\n".join(service_lines)

        # Update the service list widget
        service_widget = self.query_one("#service-list", Static)
        service_widget.update(service_text)
