"""System status panel showing llama.cpp and Docker service health."""

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static
from textual.worker import Worker

from launcher.managers.docker_manager import DockerManager
from launcher.managers.llama_manager import LlamaManager


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
    llama_status = reactive("Unknown")
    llama_model = reactive("")
    docker_status = reactive("Unknown")
    service_count = reactive(0)
    running_count = reactive(0)

    def __init__(self):
        """Initialize status panel."""
        super().__init__()
        self.llama_manager = LlamaManager()
        self.docker_manager = DockerManager()
        self._update_worker: Worker | None = None

    def compose(self) -> ComposeResult:
        """Compose the status panel layout."""
        yield Static("[bold cyan]KITTY System Status[/bold cyan]\n")

        with Container(classes="status-grid"):
            # llama.cpp status
            yield Static("llama.cpp Server:", classes="status-label")
            yield Static(self._format_llama_status(), id="llama-status", classes="status-value")

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
            await self.app.sleep(3.0)

    async def update_status(self) -> None:
        """Fetch and update status information."""
        # Update llama.cpp status
        llama_status = await self.llama_manager.get_status()

        if llama_status.running:
            self.llama_status = "Healthy"
            self.llama_model = llama_status.model or "unknown"
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

        # Update Docker status display
        docker_widget = self.query_one("#docker-status", Static)
        docker_widget.update(self._format_docker_status())

    def _format_llama_status(self) -> str:
        """Format llama.cpp status with color coding."""
        if self.llama_status == "Healthy":
            status_str = f"[green]✓ Running[/green]"
            if self.llama_model:
                # Shorten model name if too long
                model_name = self.llama_model.split("/")[-1] if "/" in self.llama_model else self.llama_model
                if len(model_name) > 40:
                    model_name = model_name[:37] + "..."
                status_str += f"\n  Model: [dim]{model_name}[/dim]"
            status_str += f"\n  URL: [dim]{self.llama_manager.base_url}[/dim]"
        else:
            status_str = f"[red]✗ Offline[/red]\n  URL: [dim]{self.llama_manager.base_url}[/dim]"

        return status_str

    def _format_docker_status(self) -> str:
        """Format Docker status with color coding."""
        if self.docker_status == "Healthy":
            status_str = f"[green]✓ Running[/green]\n"
            status_str += f"  Services: {self.running_count}/{self.service_count} running"

            if self.running_count < self.service_count:
                status_str = status_str.replace("[green]", "[yellow]")
                status_str += f"\n  [yellow]{self.service_count - self.running_count} service(s) stopped[/yellow]"
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
