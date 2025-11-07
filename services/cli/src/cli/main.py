"""SSH-friendly CLI interface for KITTY."""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import httpx
import typer
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text

load_dotenv()

console = Console()
app = typer.Typer(help="Command-line assistant for KITTY.")
RUNNING_IN_CONTAINER = os.path.exists("/.dockerenv")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_any(names: Iterable[str], default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _first_valid_url(candidates: Iterable[str], default: str) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate)
        except ValueError:
            continue
        host = parsed.hostname
        if not host:
            continue
        if host in {"localhost", "127.0.0.1", "0.0.0.0"} or "." in host:
            return candidate
        if RUNNING_IN_CONTAINER:
            return candidate
    return default


API_BASE = _first_valid_url(
    (
        os.getenv("KITTY_API_BASE"),
        os.getenv("KITTY_CLI_API_BASE"),
        os.getenv("GATEWAY_API"),
        os.getenv("GATEWAY_PUBLIC_URL"),
        os.getenv("BRAIN_API_BASE"),
        os.getenv("BRAIN_API"),
    ),
    "http://localhost:8000",
)
CAD_BASE = _env("KITTY_CAD_API", "http://localhost:8200")
USER_NAME = _env("USER_NAME", "ssh-operator")
USER_UUID = _env(
    "KITTY_USER_ID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_NAME)),
)
DEFAULT_VERBOSITY = int(_env("VERBOSITY", "3"))


@dataclass
class SessionState:
    """Session state for CLI interactions."""

    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = USER_UUID
    user_name: str = USER_NAME or "ssh-operator"
    verbosity: int = DEFAULT_VERBOSITY
    last_artifacts: List[Dict[str, Any]] = field(default_factory=list)


state = SessionState()


class CommandCompleter(Completer):
    """Custom completer for "/" commands with descriptions."""

    def __init__(self):
        self.commands = {
            "help": "Show this help message",
            "verbosity": "Set response detail level (1-5)",
            "cad": "Generate CAD model from description",
            "list": "List cached CAD artifacts",
            "queue": "Queue artifact to printer",
            "exit": "Exit interactive shell",
        }

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # Only complete if we're typing a command (starts with /)
        if not text.startswith("/"):
            return

        word = text[1:]  # Remove the leading /

        for cmd, description in self.commands.items():
            if cmd.startswith(word.lower()):
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=f"/{cmd}",
                    display_meta=description,
                )


def _client() -> httpx.Client:
    return httpx.Client(timeout=120.0)


def _post_json_with_spinner(
    url: str, payload: Dict[str, Any], status_text: str = "Thinking"
) -> Dict[str, Any]:
    """Make API call with thinking animation."""
    spinner = Spinner("dots", text=Text(status_text, style="cyan"))

    with Live(spinner, console=console, transient=True):
        with _client() as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Make API call without spinner (for internal use)."""
    with _client() as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _print_routing(routing: Optional[Dict[str, Any]]) -> None:
    if not routing:
        return
    console.print("[dim]Routing:")
    console.print(routing)


def _print_artifacts(artifacts: List[Dict[str, Any]]) -> None:
    if not artifacts:
        console.print("[yellow]No artifacts available.")
        return
    for idx, artifact in enumerate(artifacts, start=1):
        console.print(
            f"[cyan]{idx}[/] provider={artifact.get('provider')} "
            f"type={artifact.get('artifactType')} "
            f"url={artifact.get('location')}"
        )


def _format_prompt(user_prompt: str) -> str:
    # No longer needed - ReAct agent handles reasoning internally
    return user_prompt


@app.command()
def models() -> None:
    """List known local/frontier models."""

    try:
        data = _post_json(f"{API_BASE}/api/routing/models", {})
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to fetch models: {exc}")
        raise typer.Exit(1) from exc

    console.print("[bold]Local models:[/]")
    for item in data.get("local", []):
        console.print(f" - {item}")
    frontier = data.get("frontier")
    if frontier:
        console.print("[bold]Frontier providers:[/]")
        for item in frontier:
            console.print(f" - {item}")


@app.command()
def hash_password(
    password: str = typer.Argument(..., help="Password to hash with bcrypt"),
) -> None:
    """Generate a bcrypt hash (use for ADMIN_USERS)."""

    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    console.print(ctx.hash(password))


@app.command()
def say(
    message: List[str] = typer.Argument(..., help="Message for KITTY"),
    verbosity: Optional[int] = typer.Option(None, "--verbosity", "-v", min=1, max=5),
    no_agent: bool = typer.Option(
        False, "--no-agent", help="Disable agentic mode (direct LLM response)"
    ),
) -> None:
    """Send a conversational message with intelligent agent reasoning.

    Models are automatically managed by the Model Manager - no need to specify.
    """
    text = " ".join(message)
    formatted_prompt = _format_prompt(text)
    payload: Dict[str, Any] = {
        "conversationId": state.conversation_id,
        "userId": state.user_id,
        "intent": "chat.prompt",
        "prompt": formatted_prompt,
        "useAgent": not no_agent,  # Enable agentic mode by default
    }
    chosen_verbosity = verbosity or state.verbosity or DEFAULT_VERBOSITY
    if chosen_verbosity:
        state.verbosity = chosen_verbosity
        payload["verbosity"] = chosen_verbosity

    try:
        data = _post_json_with_spinner(f"{API_BASE}/api/query", payload, "KITTY is thinking")
    except httpx.TimeoutException:
        console.print("[red]Request timed out - check if KITTY services are running")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(1) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Request failed: {exc}")
        raise typer.Exit(1) from exc

    output = data.get("result", {}).get("output", "")
    if output:
        console.print(Panel(output, title="[bold green]KITTY", border_style="green"))
    else:
        console.print("[yellow]No response received")

    # Show routing info if verbosity is high
    if state.verbosity >= 4:
        _print_routing(data.get("routing"))


@app.command()
def cad(prompt: List[str] = typer.Argument(..., help="CAD generation prompt")) -> None:
    """Generate CAD artifacts using Zoo/Tripo/local providers."""
    text = " ".join(prompt)
    payload = {"conversationId": state.conversation_id, "prompt": text}

    try:
        data = _post_json_with_spinner(
            f"{CAD_BASE}/api/cad/generate", payload, "Generating CAD model"
        )
    except httpx.TimeoutException:
        console.print("[red]CAD generation timed out")
        raise typer.Exit(1)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]CAD generation failed: {exc}")
        raise typer.Exit(1) from exc

    artifacts = data.get("artifacts", [])
    state.last_artifacts = artifacts

    if artifacts:
        console.print(f"\n[green]Generated {len(artifacts)} artifact(s)")
        _print_artifacts(artifacts)
        console.print("\n[dim]Use '/list' to view or '/queue <index> <printer>' to print[/dim]")
    else:
        console.print("[yellow]No artifacts generated")


@app.command()
def queue(
    artifact_index: int = typer.Argument(
        ..., help="Artifact index from last CAD run (1-based)"
    ),
    printer_id: str = typer.Argument(
        ..., help="Target printer ID (matches `/api/device/<id>`)."
    ),
) -> None:
    """Queue the selected artifact for printing via gateway."""

    if not state.last_artifacts:
        console.print("[yellow]No artifacts cached. Run `kitty-cli cad` first.")
        raise typer.Exit(1)

    if not (1 <= artifact_index <= len(state.last_artifacts)):
        console.print(f"[red]Invalid artifact index {artifact_index}.")
        raise typer.Exit(1)

    artifact = state.last_artifacts[artifact_index - 1]
    location = artifact.get("location")
    payload = {
        "intent": "start_print",
        "payload": {"jobId": f"{printer_id}-{uuid.uuid4().hex}", "gcodePath": location},
    }

    try:
        data = _post_json(f"{API_BASE}/api/device/{printer_id}/command", payload)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to queue print: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Queued print on {printer_id}: {data}")


@app.command()
def shell(
    conversation: Optional[str] = typer.Option(
        None, "--conversation", "-c", help="Conversation ID override"
    ),
    verbosity: Optional[int] = typer.Option(
        None, "--verbosity", "-v", min=1, max=5, help="Verbosity level (1-5)"
    ),
) -> None:
    """Interactive shell for conversational AI and fabrication control.

    Chat with KITTY, generate CAD models, queue prints, and control devices.
    Models are automatically managed by the Model Manager.
    """
    if conversation:
        try:
            uuid.UUID(conversation)
            state.conversation_id = conversation
        except ValueError:
            console.print(
                "[yellow]Conversation IDs must be UUIDs. Generating a new session ID."
            )
            state.conversation_id = str(uuid.uuid4())
    if verbosity:
        state.verbosity = verbosity

    # Welcome header
    console.print(Panel.fit(
        "[bold cyan]KITTY Interactive Shell[/bold cyan]\n"
        "[dim]Intelligent fabrication assistant with agentic reasoning[/dim]",
        border_style="cyan"
    ))

    # Commands help
    console.print("\n[bold]Commands:[/bold]")
    console.print("  [cyan]/verbosity <1-5>[/cyan]  - Set response detail level")
    console.print("  [cyan]/cad <prompt>[/cyan]     - Generate CAD models")
    console.print("  [cyan]/list[/cyan]             - Show cached artifacts")
    console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact to printer")
    console.print("  [cyan]/help[/cyan]             - Show this help")
    console.print("  [cyan]/exit[/cyan]             - Exit shell")

    # Current settings
    console.print(f"\n[dim]Verbosity: {state.verbosity}/5  |  Session: {state.conversation_id[:8]}...[/dim]")
    console.print("[dim]Agentic mode active - KITTY can use tools and reason about tasks[/dim]")
    console.print("[dim]Type '/' and press Tab to see available commands[/dim]\n")

    # Create prompt_toolkit session with command completion
    session = PromptSession(completer=CommandCompleter())

    while True:
        try:
            line = session.prompt(HTML("<ansimagenta>you</ansimagenta>> "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended. Goodbye![/]")
            break

        if not line:
            continue

        if line.startswith("/"):
            parts = line[1:].split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in {"quit", "exit"}:
                console.print("[dim]Goodbye![/]")
                break

            if cmd == "help":
                console.print("\n[bold]Available Commands:[/bold]")
                console.print("  [cyan]/verbosity <1-5>[/cyan]  - Set verbosity (1=terse, 5=exhaustive)")
                console.print("  [cyan]/cad <prompt>[/cyan]     - Generate CAD model from description")
                console.print("  [cyan]/list[/cyan]             - List cached CAD artifacts")
                console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact #idx to printer")
                console.print("  [cyan]/help[/cyan]             - Show this help message")
                console.print("  [cyan]/exit[/cyan]             - Exit interactive shell")
                console.print("\n[dim]Type any message to chat with KITTY[/dim]\n")
                continue

            if cmd == "verbosity":
                if not args:
                    console.print(f"[yellow]Current verbosity: {state.verbosity}/5")
                else:
                    try:
                        level = int(args[0])
                        if not (1 <= level <= 5):
                            raise ValueError
                        state.verbosity = level
                        console.print(f"[green]Verbosity set to {level}/5")
                    except ValueError:
                        console.print("[red]Verbosity must be between 1 and 5")
                continue

            if cmd == "cad":
                if not args:
                    console.print("[yellow]Usage: /cad <prompt>")
                    console.print("[dim]Example: /cad design a wall mount bracket[/dim]")
                else:
                    cad(" ".join(args).split())
                continue

            if cmd == "list":
                if state.last_artifacts:
                    console.print(f"\n[bold]Cached Artifacts ({len(state.last_artifacts)}):[/bold]")
                    _print_artifacts(state.last_artifacts)
                else:
                    console.print("[yellow]No artifacts cached. Use /cad to generate models")
                continue

            if cmd == "queue":
                if len(args) < 2:
                    console.print("[yellow]Usage: /queue <artifact_index> <printer_id>")
                    console.print("[dim]Example: /queue 1 printer_01[/dim]")
                else:
                    try:
                        idx = int(args[0])
                    except ValueError:
                        console.print("[red]Artifact index must be a number")
                        continue
                    queue(idx, args[1])
                continue

            console.print(f"[yellow]Unknown command: /{cmd}")
            console.print("[dim]Type /help for available commands[/dim]")
            continue

        # Default to conversation
        try:
            say([line], verbosity=None)
        except typer.Exit:
            continue


if __name__ == "__main__":
    try:
        app()
    except httpx.HTTPStatusError as exc:
        console.print(
            f"[red]HTTP error {exc.response.status_code}: {exc.response.text}"
        )
        sys.exit(1)
    except httpx.RequestError as exc:
        console.print(f"[red]Request error: {exc}")
        sys.exit(1)
