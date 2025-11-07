# noqa: D401
"""CLI entry point for KITTY Model Manager."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import load_config
from .scanner import ModelScanner
from .supervisor import get_supervisor

app = typer.Typer(
    name="kitty-model-manager",
    help="KITTY Model Manager - Terminal TUI for llama.cpp model management",
    add_completion=False,
)

console = Console()
logger = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"KITTY Model Manager version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-V",
        help="Enable verbose logging",
    ),
) -> None:
    """KITTY Model Manager - Terminal TUI for llama.cpp model management."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


@app.command()
def tui(
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
) -> None:
    """Launch the TUI application."""
    try:
        from .app import ModelManagerApp

        app_instance = ModelManagerApp(env_path=env_path)
        app_instance.run()
    except ImportError as e:
        console.print(f"[red]Error: Failed to import TUI: {e}[/red]")
        console.print("[yellow]Make sure textual is installed: pip install textual[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def start(
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="Wait for server to be ready",
    ),
) -> None:
    """Start llama.cpp server."""
    try:
        supervisor = get_supervisor(env_path=env_path)

        with console.status("[bold green]Starting server..."):
            state = supervisor.start(wait_for_ready=wait)

        console.print(f"[green]✓[/green] Server started (PID: {state.pid})")
        if wait and state.last_health_check:
            console.print(f"[dim]  Ready in {state.last_health_check.latency_ms:.0f}ms[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stop(
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force kill the process",
    ),
) -> None:
    """Stop llama.cpp server."""
    try:
        supervisor = get_supervisor(env_path=env_path)

        with console.status("[bold yellow]Stopping server..."):
            state = supervisor.stop(force=force)

        console.print("[green]✓[/green] Server stopped")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def restart(
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force kill the process",
    ),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="Wait for server to be ready",
    ),
) -> None:
    """Restart llama.cpp server."""
    try:
        supervisor = get_supervisor(env_path=env_path)

        with console.status("[bold blue]Restarting server..."):
            state = supervisor.restart(force=force, wait_for_ready=wait)

        console.print(f"[green]✓[/green] Server restarted (PID: {state.pid})")
        if wait and state.last_health_check:
            console.print(f"[dim]  Ready in {state.last_health_check.latency_ms:.0f}ms[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
) -> None:
    """Show server status."""
    try:
        supervisor = get_supervisor(env_path=env_path)
        state = supervisor.get_state()

        # Create status table
        table = Table(title="Server Status", show_header=False)
        table.add_column("Property", style="cyan")
        table.add_column("Value")

        table.add_row("Status", f"[bold]{state.status.value.upper()}[/bold]")
        table.add_row("PID", str(state.pid) if state.pid else "-")
        table.add_row("Model", state.config.primary_model)
        table.add_row("Alias", state.config.model_alias)
        table.add_row("Endpoint", state.config.endpoint)

        if state.uptime_seconds > 0:
            hours = int(state.uptime_seconds // 3600)
            minutes = int((state.uptime_seconds % 3600) // 60)
            seconds = int(state.uptime_seconds % 60)
            table.add_row("Uptime", f"{hours:02d}:{minutes:02d}:{seconds:02d}")

        if state.restart_count > 0:
            table.add_row("Restarts", str(state.restart_count))

        console.print(table)

        # Run health check if running
        if state.status not in ["stopped", "crashed"]:
            state = supervisor.check_health()
            if state.last_health_check:
                hc = state.last_health_check
                console.print(f"\n[dim]Health: {hc.latency_ms:.0f}ms latency[/dim]")
                if hc.slots_idle is not None:
                    console.print(f"[dim]Slots: {hc.slots_idle} idle, {hc.slots_processing} processing[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def scan(
    models_dir: Optional[Path] = typer.Option(
        None,
        "--dir",
        "-d",
        help="Models directory to scan",
    ),
) -> None:
    """Scan for available models."""
    try:
        if models_dir is None:
            config = load_config()
            models_dir = config.models_dir

        with console.status(f"[bold]Scanning {models_dir}..."):
            scanner = ModelScanner(models_dir)
            registry = scanner.scan()

        # Summary
        console.print(f"\n[bold]Found {registry.total_models} models in {registry.total_families} families[/bold]")
        console.print(f"[dim]Total size: {registry.total_size_gb:.1f} GB[/dim]")
        console.print(f"[dim]Scan time: {registry.scan_duration_seconds:.2f}s[/dim]\n")

        # Models by family
        for family_name in sorted(registry.families.keys()):
            models = registry.families[family_name]
            console.print(f"[bold cyan]{family_name}[/bold cyan] ({len(models)} models)")

            for model in models:
                status = "✓" if model.is_complete else "⚠"
                size = model.size_bytes / (1024 ** 3)

                details = []
                details.append(f"{model.quantization.value}")
                details.append(f"{size:.1f}GB")

                if model.shard_total and model.shard_total > 1:
                    details.append(f"{model.file_count}/{model.shard_total} shards")

                if model.estimated_params_billions:
                    details.append(f"~{model.estimated_params_billions:.0f}B params")

                console.print(f"  {status} {model.name} [dim]({', '.join(details)})[/dim]")

            console.print()

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def switch(
    model_path: str = typer.Argument(..., help="Model path (relative to models_dir)"),
    alias: Optional[str] = typer.Option(
        None,
        "--alias",
        "-a",
        help="Model alias (defaults to filename)",
    ),
    env_path: Optional[Path] = typer.Option(
        None,
        "--env",
        "-e",
        help="Path to .env file",
    ),
    wait: bool = typer.Option(
        True,
        "--wait/--no-wait",
        help="Wait for server to be ready",
    ),
) -> None:
    """Switch to a different model (hot-swap)."""
    try:
        supervisor = get_supervisor(env_path=env_path)

        with console.status(f"[bold]Switching to {model_path}..."):
            state = supervisor.switch_model(model_path, alias=alias, wait_for_ready=wait)

        console.print(f"[green]✓[/green] Switched to {model_path}")
        console.print(f"[dim]  Alias: {state.config.model_alias}[/dim]")
        console.print(f"[dim]  PID: {state.pid}[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
