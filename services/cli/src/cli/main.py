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
from rich.console import Console
from rich.prompt import Prompt

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
DEFAULT_MODEL = _env_any(
    (
        "KITTY_DEFAULT_MODEL",
        "LOCAL_MODEL_PRIMARY_ALIAS",
        "LLAMACPP_PRIMARY_ALIAS",
        "LOCAL_MODEL_PRIMARY",
    ),
    "kitty-primary",
)
DEFAULT_VERBOSITY = int(_env("VERBOSITY", "3"))


@dataclass
class SessionState:
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = USER_UUID
    user_name: str = USER_NAME or "ssh-operator"
    model_alias: Optional[str] = DEFAULT_MODEL
    verbosity: int = DEFAULT_VERBOSITY
    last_artifacts: List[Dict[str, Any]] = field(default_factory=list)


state = SessionState()


def _client() -> httpx.Client:
    return httpx.Client(timeout=60.0)


def _post_json(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
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
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Override local model alias"
    ),
    verbosity: Optional[int] = typer.Option(None, "--verbosity", "-v", min=1, max=5),
    no_agent: bool = typer.Option(
        False, "--no-agent", help="Disable agentic mode (direct LLM response)"
    ),
) -> None:
    """Send a one-off conversational message with intelligent agent reasoning."""

    text = " ".join(message)
    formatted_prompt = _format_prompt(text)
    payload: Dict[str, Any] = {
        "conversationId": state.conversation_id,
        "userId": state.user_id,
        "intent": "chat.prompt",
        "prompt": formatted_prompt,
        "useAgent": not no_agent,  # Enable agentic mode by default
    }
    chosen_model = model or state.model_alias or DEFAULT_MODEL
    if chosen_model:
        state.model_alias = chosen_model
        payload["modelAlias"] = chosen_model
    chosen_verbosity = verbosity or state.verbosity or DEFAULT_VERBOSITY
    if chosen_verbosity:
        state.verbosity = chosen_verbosity
        payload["verbosity"] = chosen_verbosity

    try:
        data = _post_json(f"{API_BASE}/api/query", payload)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Request failed: {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]KITTY:[/] {data.get('result', {}).get('output', '')}")
    _print_routing(data.get("routing"))


@app.command()
def cad(prompt: List[str] = typer.Argument(..., help="CAD generation prompt")) -> None:
    """Generate CAD artifacts and store latest results."""

    text = " ".join(prompt)
    payload = {"conversationId": state.conversation_id, "prompt": text}
    try:
        data = _post_json(f"{CAD_BASE}/api/cad/generate", payload)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]CAD generation failed: {exc}")
        raise typer.Exit(1) from exc

    artifacts = data.get("artifacts", [])
    state.last_artifacts = artifacts
    console.print(f"[green]Generated {len(artifacts)} artifact(s).")
    _print_artifacts(artifacts)


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
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Model alias to start with"
    ),
    verbosity: Optional[int] = typer.Option(
        None, "--verbosity", "-v", min=1, max=5, help="Verbosity level"
    ),
) -> None:
    """Interactive shell interaction."""

    if conversation:
        try:
            uuid.UUID(conversation)
            state.conversation_id = conversation
        except ValueError:
            console.print(
                "[yellow]Conversation IDs must be UUIDs. Generating a new session ID."
            )
            state.conversation_id = str(uuid.uuid4())
    if model:
        state.model_alias = model
    if verbosity:
        state.verbosity = verbosity

    console.print("[bold]KITTY interactive shell[/]")
    console.print(
        "Commands: /model <alias>, /verbosity <1-5>, /cad <prompt>, /list, /queue <idx> <printer>, /exit"
    )
    console.print(
        f"[dim]Default model: {state.model_alias}  |  Verbosity: {state.verbosity}"
    )
    console.print(
        "[dim]Agentic mode enabled – KITTY will reason about your requests and use tools as needed."
    )

    while True:
        try:
            line = Prompt.ask("[cyan]you[/]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended.[/]")
            break

        if not line:
            continue
        if line.startswith("/"):
            parts = line[1:].split()
            cmd = parts[0].lower()
            args = parts[1:]
            if cmd in {"quit", "exit"}:
                break
            if cmd == "model":
                if not args:
                    console.print(f"[yellow]Current model: {state.model_alias}")
                else:
                    state.model_alias = args[0]
                    console.print(f"[green]Model set to {state.model_alias}")
                continue
            if cmd == "verbosity":
                if not args:
                    console.print(f"[yellow]Current verbosity: {state.verbosity}")
                else:
                    try:
                        level = int(args[0])
                        if not (1 <= level <= 5):
                            raise ValueError
                        state.verbosity = level
                        console.print(f"[green]Verbosity set to {level}")
                    except ValueError:
                        console.print("[red]Verbosity must be between 1 and 5.")
                continue
            if cmd == "cad":
                if not args:
                    console.print("[yellow]Usage: /cad <prompt>")
                else:
                    cad(" ".join(args).split())
                continue
            if cmd == "list":
                _print_artifacts(state.last_artifacts)
                continue
            if cmd == "queue":
                if len(args) < 2:
                    console.print("[yellow]Usage: /queue <artifact_index> <printer_id>")
                else:
                    try:
                        idx = int(args[0])
                    except ValueError:
                        console.print("[red]Artifact index must be an integer.")
                        continue
                    queue(idx, args[1])
                continue
            if cmd == "models":
                models()
                continue

            console.print(f"[yellow]Unknown command: /{cmd}")
            continue

        # default to conversation
        try:
            say([line], model=None, verbosity=None)
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
