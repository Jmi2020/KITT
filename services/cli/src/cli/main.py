"""SSH-friendly CLI interface for KITTY."""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import quote_plus, urlparse

import httpx
import typer
from typer.models import OptionInfo
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .storage import load_stored_images, save_stored_images

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
        os.getenv("BRAIN_API_BASE"),
        os.getenv("BRAIN_API"),
    ),
    "http://localhost:8000",
)
CAD_BASE = _env("KITTY_CAD_API", "http://localhost:8200")
IMAGES_BASE = _first_valid_url(
    (
        os.getenv("IMAGES_BASE"),
        os.getenv("KITTY_IMAGES_API"),
        os.getenv("GATEWAY_API"),
        "http://gateway:8080",
        "http://localhost:8080",
    ),
    "http://localhost:8080",
)
UI_BASE = _env("KITTY_UI_BASE", "http://localhost:4173")
VISION_API_BASE = _first_valid_url(
    (
        os.getenv("KITTY_VISION_API_BASE"),
        os.getenv("GATEWAY_API"),
        os.getenv("GATEWAY_PUBLIC_URL"),
        "http://gateway:8080",
        "http://localhost:8080",
    ),
    API_BASE,
)
USER_NAME = _env("USER_NAME", "ssh-operator")
USER_UUID = _env(
    "KITTY_USER_ID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_NAME)),
)
DEFAULT_VERBOSITY = int(_env("VERBOSITY", "3"))
CLI_TIMEOUT = float(_env("KITTY_CLI_TIMEOUT", "900"))
_SLUG_PATTERN = re.compile(r"[A-Za-z0-9]+")


def _slugify_component(text: Optional[str], fallback: str = "reference") -> str:
    words = _SLUG_PATTERN.findall(text or "")
    if not words:
        words = [fallback]
    head = words[0].lower()
    tail = [word.capitalize() for word in words[1:]]
    return head + "".join(tail)


def _unique_slug(base: str, existing: Set[str]) -> str:
    if base not in existing:
        return base
    counter = 2
    while True:
        candidate = f"{base}{counter}"
        if candidate not in existing:
            return candidate
        counter += 1


def _friendly_name(title: Optional[str], source: Optional[str], existing: Set[str]) -> str:
    base = _slugify_component(title or source or "reference")
    slug = _unique_slug(base, existing)
    existing.add(slug)
    return slug


@dataclass
class SessionState:
    """Session state for CLI interactions."""

    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = USER_UUID
    user_name: str = USER_NAME or "ssh-operator"
    verbosity: int = max(DEFAULT_VERBOSITY, 4)
    last_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    stored_images: List[Dict[str, Any]] = field(default_factory=list)
    show_trace: bool = True
    agent_enabled: bool = True


state = SessionState()
state.stored_images = load_stored_images()


def _persist_stored_images() -> None:
    save_stored_images(state.stored_images)


def _merge_persisted_images(items: List[Dict[str, Any]]) -> None:
    if not items:
        return
    existing_urls = {
        entry.get("download_url") or entry.get("storage_uri")
        for entry in state.stored_images
    }
    existing_names: Set[str] = {
        entry.get("friendlyName") or entry.get("friendly_name")
        for entry in state.stored_images
        if entry.get("friendlyName") or entry.get("friendly_name")
    }
    changed = False
    for item in items:
        friendly = item.get("friendlyName") or item.get("friendly_name")
        if not friendly:
            friendly = _friendly_name(item.get("title"), item.get("source"), existing_names)
            item["friendlyName"] = friendly
        download_key = item.get("download_url") or item.get("storage_uri")
        if download_key in existing_urls:
            continue
        state.stored_images.append(item)
        existing_urls.add(download_key)
        changed = True
    if changed:
        _persist_stored_images()


class CommandCompleter(Completer):
    """Custom completer for "/" commands with descriptions."""

    def __init__(self):
        self.commands = {
            "help": "Show this help message",
            "verbosity": "Set response detail level (1-5)",
            "cad": "Generate CAD model from description",
            "list": "List cached CAD artifacts",
            "queue": "Queue artifact to printer",
            "usage": "Show provider usage dashboard",
            "vision": "Search + select reference images",
            "reset": "Start a fresh conversation session",
            "remember": "Store a long-term memory note",
            "memories": "Search saved memory notes",
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
    return httpx.Client(timeout=CLI_TIMEOUT)


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


def _get_json(url: str) -> Dict[str, Any]:
    with _client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _vision_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{VISION_API_BASE}/api/vision/{path}"
    with _client() as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _print_agent_trace(metadata: Dict[str, Any]) -> None:
    """Pretty-print agent reasoning steps if present."""
    steps = metadata.get("agent_steps")
    if not steps:
        return

    console.print("\n[bold magenta]Agent trace[/bold magenta]")
    for idx, step in enumerate(steps, 1):
        lines = []
        thought = step.get("thought")
        if thought:
            lines.append(f"[cyan]Thought:[/] {thought}")
        action = step.get("action")
        if action:
            action_input = step.get("action_input")
            action_text = f"{action}({action_input})" if action_input else action
            lines.append(f"[cyan]Action:[/] {action_text}")
        observation = step.get("observation")
        if observation:
            lines.append(f"[cyan]Observation:[/] {observation}")
        if not lines:
            continue
        console.print(
            Panel(
                "\n".join(lines),
                title=f"Step {idx}",
                border_style="magenta",
            )
        )


def _print_routing(routing: Optional[Dict[str, Any]], *, show_trace: bool = False) -> None:
    if not routing:
        return
    tier = routing.get("tier")
    confidence = routing.get("confidence")
    latency = routing.get("latencyMs")
    cached = routing.get("cached")
    metadata = routing.get("metadata") or {}

    summary_parts = []
    if tier:
        summary_parts.append(f"tier={tier}")
    if confidence is not None:
        summary_parts.append(f"confidence={confidence:.2f}")
    if latency is not None:
        summary_parts.append(f"latency={latency}ms")
    if cached is not None:
        summary_parts.append(f"cached={cached}")

    provider = metadata.get("provider")
    model = metadata.get("model")
    if provider:
        summary_parts.append(f"provider={provider}")
    if model:
        summary_parts.append(f"model={model}")
    tools_used = metadata.get("tools_used")
    if tools_used is not None:
        summary_parts.append(f"tools={tools_used}")

    if summary_parts:
        console.print("[dim]Routing:[/] " + ", ".join(summary_parts))

    if show_trace and metadata:
        _print_agent_trace(metadata)

    if metadata.get("truncated"):
        console.print(
            "[yellow]Note:[/] Model output hit the local token limit. "
            "Ask KITTY to continue or raise LLAMACPP_N_PREDICT for longer replies."
        )


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


def _start_new_session() -> None:
    state.conversation_id = str(uuid.uuid4())
    state.last_artifacts = []
    console.print(
        f"[green]Started new session: {state.conversation_id[:8]}... "
        "(conversation context cleared)"
    )


def _remember_note(content: str) -> None:
    payload = {
        "conversationId": state.conversation_id,
        "userId": state.user_id,
        "content": content,
    }
    try:
        _post_json(f"{API_BASE}/api/memory/remember", payload)
        console.print("[green]Saved to long-term memory.")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to save memory: {exc}")


def _search_memories(query: str, limit: int = 5) -> None:
    payload = {
        "conversationId": state.conversation_id,
        "userId": state.user_id,
        "query": query or "*",
        "limit": limit,
    }
    try:
        data = _post_json(f"{API_BASE}/api/memory/search", payload)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to search memories: {exc}")
        return

    memories = data.get("memories", [])
    if not memories:
        console.print("[yellow]No matching memories found.")
        return

    console.print(f"[bold]Memories ({len(memories)}):[/bold]")
    for idx, memory in enumerate(memories, start=1):
        snippet = memory.get("content", "").strip()
        created = memory.get("created_at", "")
        console.print(f"[cyan]{idx}[/] {created} | {snippet}")


def _format_prompt(user_prompt: str) -> str:
    # No longer needed - ReAct agent handles reasoning internally
    return user_prompt


def _fetch_usage_metrics() -> Dict[str, Dict[str, Any]]:
    return _get_json(f"{API_BASE}/api/usage/metrics")


def _format_last_used(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        # Support FastAPI's ISO formatting with timezone info
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ts.strftime("%Y-%m-%d %H:%M:%S") + " UTC"
    except ValueError:
        return value


def _build_usage_table(metrics: Dict[str, Dict[str, Any]]) -> Table:
    table = Table(show_edge=False, header_style="bold cyan")
    table.add_column("Provider", overflow="fold")
    table.add_column("Tier")
    table.add_column("Calls", justify="right")
    table.add_column("Cost (USD)", justify="right")
    table.add_column("Last Used", overflow="fold")

    if not metrics:
        table.add_row("—", "—", "0", "$0.00", "No usage recorded")
        return table

    for provider in sorted(metrics.keys()):
        entry = metrics[provider]
        tier = entry.get("tier", "—")
        calls = entry.get("calls", 0)
        cost = float(entry.get("total_cost", 0.0))
        last_used = _format_last_used(entry.get("last_used"))
        table.add_row(
            provider,
            tier,
            f"{calls}",
            f"${cost:.4f}",
            last_used,
        )

    return table


def _render_usage_panel(metrics: Dict[str, Dict[str, Any]]) -> Panel:
    timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")
    return Panel(
        _build_usage_table(metrics),
        title="[bold cyan]Provider Usage[/bold cyan]",
        subtitle=f"Updated {timestamp}",
        border_style="cyan",
    )


def _display_usage_dashboard(refresh: Optional[int] = None, *, exit_on_error: bool = True) -> None:
    try:
        metrics = _fetch_usage_metrics()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to fetch usage metrics: {exc}")
        if exit_on_error:
            raise typer.Exit(1) from exc
        return

    interval = refresh or 0
    if interval <= 0:
        console.print(_render_usage_panel(metrics))
        return

    console.print(
        f"[dim]Live dashboard refreshes every {interval}s. Press Ctrl+C to stop.[/dim]"
    )
    try:
        with Live(console=console, refresh_per_second=4) as live:
            while True:
                live.update(_render_usage_panel(metrics))
                time.sleep(interval)
                metrics = _fetch_usage_metrics()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped usage dashboard.[/dim]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Usage dashboard error: {exc}")
        if exit_on_error:
            raise typer.Exit(1) from exc
        return


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
def usage(
    refresh: Optional[int] = typer.Option(
        None,
        "--refresh",
        "-r",
        min=2,
        help="Refresh interval in seconds for live dashboard (default: no refresh).",
    ),
) -> None:
    """Display provider-level usage stats and recent paid calls."""
    _display_usage_dashboard(refresh)


def _prompt_for_selection(count: int, picks: Optional[str]) -> List[int]:
    selection = picks or console.input("Select image #s (comma separated, blank to skip): ")
    if not selection:
        return []
    chosen: List[int] = []
    for part in selection.replace(" ", "").split(","):
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            console.print(f"[red]Invalid selection '{part}' ignored")
            continue
        if 1 <= idx <= count:
            chosen.append(idx)
        else:
            console.print(f"[red]Selection {idx} out of range (1-{count})")
    return chosen


def _run_vision_flow(
    query: str,
    *,
    max_results: int = 8,
    min_score: float = 0.0,
    picks: Optional[str] = None,
) -> None:
    payload = {"query": query, "max_results": max_results}
    gallery_link = f"{UI_BASE}/?view=vision&session={state.conversation_id}&query={quote_plus(query)}"
    console.print(f"[dim]Open gallery for manual selection: {gallery_link}")
    try:
        search = _vision_post("search", payload)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Image search failed: {exc}")
        raise typer.Exit(1) from exc

    results = search.get("results", [])
    if not results:
        console.print("[yellow]No images found.")
        return

    try:
        filtered = _vision_post(
            "filter",
            {"query": query, "images": results, "min_score": min_score},
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Image filter failed: {exc}")
        raise typer.Exit(1) from exc

    ranked = filtered.get("results", results)
    if not ranked:
        console.print("[yellow]No images passed the filter threshold.")
        return

    table = Table(title=f"Vision results for '{query}'", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Score")
    table.add_column("Title")
    table.add_column("Source")
    table.add_column("Image URL")
    for idx, item in enumerate(ranked, start=1):
        table.add_row(
            str(idx),
            f"{item.get('score', 0):.2f}",
            (item.get("title") or "")[:40],
            item.get("source") or "",
            item.get("image_url") or "",
        )
    console.print(table)

    selections = _prompt_for_selection(len(ranked), picks)
    if not selections:
        console.print("[dim]No selections made")
        return

    existing_names = {
        img.get("friendlyName") or img.get("friendly_name")
        for img in state.stored_images
        if (img.get("friendlyName") or img.get("friendly_name"))
    }
    chosen_images: List[Dict[str, Any]] = []
    for idx in selections:
        entry = ranked[idx - 1]
        friendly = _friendly_name(entry.get("title"), entry.get("source"), existing_names)
        chosen_images.append(
            {
                "id": entry.get("id"),
                "image_url": entry.get("image_url"),
                "title": entry.get("title"),
                "source": entry.get("source"),
                "caption": entry.get("description"),
                "friendlyName": friendly,
                "name": friendly,
            }
        )

    try:
        stored = _vision_post(
            "store",
            {
                "session_id": state.conversation_id,
                "images": chosen_images,
            },
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to store selections: {exc}")
        raise typer.Exit(1) from exc

    stored_items = stored.get("stored", [])
    if not stored_items:
        console.print("[yellow]Selections failed to store.")
        return

    console.print(f"[green]Stored {len(stored_items)} reference image(s):")
    for item in stored_items:
        friendly = item.get("friendlyName") or item.get("friendly_name")
        console.print(
            f" - {(friendly or item.get('title') or 'untitled')} | source={item.get('source')} "
            f"| url={item.get('download_url')}"
        )
    _merge_persisted_images(stored_items)


@app.command()
def images(
    query: List[str] = typer.Argument(..., help="Image search query"),
    max_results: int = typer.Option(8, "--max-results", "-k", min=1, max=24),
    min_score: float = typer.Option(0.0, "--min-score", min=0.0, max=1.0),
    picks: Optional[str] = typer.Option(
        None,
        "--pick",
        help="Comma-separated selections (skip interactive prompt)",
    ),
) -> None:
    """Search and select reference images for future use."""

    text = " ".join(query).strip()
    if not text:
        console.print("[red]Please provide a query.")
        raise typer.Exit(1)
    _run_vision_flow(text, max_results=max_results, min_score=min_score, picks=picks)


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
    agent: Optional[bool] = typer.Option(
        None,
        "--agent/--no-agent",
        help="Enable ReAct agent mode (defaults to session setting, currently on).",
    ),
    trace: Optional[bool] = typer.Option(
        None,
        "--trace/--no-trace",
        help="Show agent reasoning trace and tool calls (forces verbosity≥4, enabled by default).",
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
    }
    if isinstance(agent, OptionInfo):
        agent = None

    use_agent = state.agent_enabled if agent is None else agent
    state.agent_enabled = use_agent
    payload["useAgent"] = use_agent
    chosen_verbosity = verbosity or state.verbosity or DEFAULT_VERBOSITY
    trace_enabled = state.show_trace if trace is None else trace
    effective_verbosity = max(chosen_verbosity, 4) if trace_enabled else chosen_verbosity
    if effective_verbosity:
        state.verbosity = effective_verbosity
        payload["verbosity"] = effective_verbosity

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

    # Show routing info / traces when requested
    if state.verbosity >= 4 or trace_enabled:
        _print_routing(data.get("routing"), show_trace=trace_enabled)


def _infer_cad_mode(prompt: str, has_images: bool) -> str:
    text = prompt.lower()
    organic_keywords = {
        "organic",
        "sculpt",
        "statue",
        "figurine",
        "creature",
        "character",
        "dog",
        "cat",
        "animal",
        "frog",
        "mesh",
        "render",
        "art",
        "toy",
    }
    parametric_keywords = {
        "bracket",
        "mount",
        "plate",
        "adapter",
        "housing",
        "enclosure",
        "chassis",
        "hinge",
        "fixture",
        "panel",
        "beam",
        "flange",
    }
    if has_images:
        return "organic"
    if any(word in text for word in organic_keywords):
        return "organic"
    if any(word in text for word in parametric_keywords):
        return "parametric"
    return "auto"


@app.command()
def cad(
    prompt: List[str] = typer.Argument(..., help="CAD generation prompt"),
    organic: bool = typer.Option(
        False,
        "--o",
        "--organic",
        help="Force Tripo organic workflow",
        is_flag=True,
    ),
    parametric: bool = typer.Option(
        False,
        "--p",
        "--parametric",
        help="Force Zoo parametric workflow",
        is_flag=True,
    ),
) -> None:
    """Generate CAD artifacts using Zoo/Tripo/local providers."""
    if organic and parametric:
        console.print("[red]Choose either --o or --p, not both.")
        raise typer.Exit(1)

    text = " ".join(prompt)
    payload: Dict[str, Any] = {
        "conversationId": state.conversation_id,
        "prompt": text,
    }

    chosen_mode: Optional[str] = None
    if organic:
        chosen_mode = "organic"
    elif parametric:
        chosen_mode = "parametric"

    if state.stored_images:
        refs: List[Dict[str, Any]] = []
        for item in state.stored_images:
            refs.append(
                {
                    "id": item.get("id"),
                    "downloadUrl": item.get("download_url"),
                    "storageUri": item.get("storage_uri"),
                    "sourceUrl": item.get("image_url"),
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "caption": item.get("caption"),
                    "friendlyName": item.get("friendlyName") or item.get("friendly_name"),
                }
            )
        payload["imageRefs"] = refs
        if chosen_mode is None:
            chosen_mode = "organic"

    if chosen_mode is None:
        inferred = _infer_cad_mode(text, bool(state.stored_images))
        if inferred != "auto":
            chosen_mode = inferred

    if chosen_mode:
        payload["mode"] = chosen_mode

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


def _images_post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST helper for images service API calls."""
    url = f"{IMAGES_BASE}/api/images/{endpoint}"
    try:
        resp = httpx.post(url, json=payload, timeout=CLI_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Images API error {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(1) from exc
    except httpx.RequestError as exc:
        console.print(f"[red]Images API request failed: {exc}")
        raise typer.Exit(1) from exc


def _images_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET helper for images service API calls."""
    url = f"{IMAGES_BASE}/api/images/{endpoint}"
    try:
        resp = httpx.get(url, params=params or {}, timeout=CLI_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Images API error {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(1) from exc
    except httpx.RequestError as exc:
        console.print(f"[red]Images API request failed: {exc}")
        raise typer.Exit(1) from exc


@app.command(name="generate-image")
def generate_image(
    prompt: List[str] = typer.Argument(..., help="Text prompt for image generation"),
    width: int = typer.Option(1024, "--width", "-w", help="Image width"),
    height: int = typer.Option(1024, "--height", "-h", help="Image height"),
    steps: int = typer.Option(30, "--steps", "-s", help="Number of inference steps"),
    cfg: float = typer.Option(7.0, "--cfg", "-c", help="Guidance scale"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed"),
    model: str = typer.Option("sdxl_base", "--model", "-m", help="Model name"),
    refiner: Optional[str] = typer.Option(None, "--refiner", "-r", help="Refiner model"),
    wait: bool = typer.Option(False, "--wait", help="Wait for generation to complete"),
) -> None:
    """Generate an image using Stable Diffusion.

    Examples:
        kitty-cli generate-image "studio photo of a matte black water bottle"
        kitty-cli generate-image "photoreal robot arm" --width 1024 --height 768 --wait
        kitty-cli generate-image "futuristic drone" --model sdxl_base --refiner sdxl_refiner
    """
    text = " ".join(prompt)
    payload = {
        "prompt": text,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg": cfg,
        "model": model,
    }
    if seed is not None:
        payload["seed"] = seed
    if refiner:
        payload["refiner"] = refiner

    console.print(f"[cyan]Generating image:[/cyan] {text}")
    console.print(f"[dim]Model: {model}, Size: {width}x{height}, Steps: {steps}")

    # Submit generation job
    result = _images_post("generate", payload)
    job_id = result.get("job_id")

    if not job_id:
        console.print("[red]Failed to get job ID from server")
        raise typer.Exit(1)

    console.print(f"[green]Job queued:[/green] {job_id}")

    if not wait:
        console.print(f"[dim]Check status with: kitty-cli image-status {job_id}")
        console.print(f"[dim]Or list latest with: kitty-cli list-images")
        return

    # Poll for completion
    console.print("[cyan]Waiting for generation to complete...")
    with console.status("[cyan]Generating...", spinner="dots"):
        while True:
            status_data = _images_get(f"jobs/{job_id}")
            status = status_data.get("status")

            if status == "finished":
                result_data = status_data.get("result", {})
                png_key = result_data.get("png_key")
                console.print(f"[green]Image generated successfully!")
                console.print(f"[cyan]S3 Key:[/cyan] {png_key}")
                console.print(f"[dim]View in gallery: {UI_BASE}/?view=vision")
                break
            elif status == "failed":
                error = status_data.get("error", "Unknown error")
                console.print(f"[red]Generation failed: {error}")
                raise typer.Exit(1)
            elif status in ("queued", "started"):
                time.sleep(2)
            else:
                console.print(f"[yellow]Unknown status: {status}")
                time.sleep(2)


@app.command(name="image-status")
def image_status(
    job_id: str = typer.Argument(..., help="Job ID from generate-image"),
) -> None:
    """Check status of an image generation job."""
    status_data = _images_get(f"jobs/{job_id}")
    status = status_data.get("status")

    console.print(f"[cyan]Job {job_id}:[/cyan] {status}")

    if status == "finished":
        result_data = status_data.get("result", {})
        png_key = result_data.get("png_key")
        meta_key = result_data.get("meta_key")
        console.print(f"[green]Image generated successfully!")
        console.print(f"[cyan]PNG:[/cyan] {png_key}")
        console.print(f"[cyan]Metadata:[/cyan] {meta_key}")
        console.print(f"[dim]View in gallery: {UI_BASE}/?view=vision")
    elif status == "failed":
        error = status_data.get("error", "Unknown error")
        console.print(f"[red]Error:[/red] {error}")
    elif status in ("queued", "started"):
        console.print("[yellow]Generation in progress...")


@app.command(name="list-images")
def list_images(
    limit: int = typer.Option(20, "--limit", "-l", help="Number of images to list"),
) -> None:
    """List recently generated images."""
    data = _images_get("latest", {"limit": limit})
    items = data.get("items", [])

    if not items:
        console.print("[yellow]No images found.")
        return

    table = Table(title=f"Latest Generated Images (showing {len(items)})", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("S3 Key", style="green")
    table.add_column("Size", justify="right")
    table.add_column("Modified", style="dim")

    for idx, item in enumerate(items, 1):
        key = item["key"]
        size_kb = item["size"] / 1024
        modified = item["last_modified"]

        # Extract filename from key
        filename = key.split("/")[-1] if "/" in key else key

        table.add_row(
            str(idx),
            filename,
            f"{size_kb:.1f} KB",
            modified[:19],  # Trim to YYYY-MM-DD HH:MM:SS
        )

    console.print(table)
    console.print(f"\n[dim]View in gallery: {UI_BASE}/?view=vision")
    console.print(f"[dim]Select image with: kitty-cli select-image <#>")


@app.command(name="select-image")
def select_image(
    index: int = typer.Argument(..., help="Image index from list-images"),
) -> None:
    """Select an image and get download URL (for use with CAD/Tripo)."""
    # Fetch latest images
    data = _images_get("latest", {"limit": 50})
    items = data.get("items", [])

    if not items:
        console.print("[yellow]No images found.")
        raise typer.Exit(1)

    if index < 1 or index > len(items):
        console.print(f"[red]Index {index} out of range (1-{len(items)})")
        raise typer.Exit(1)

    # Get the selected item
    selected = items[index - 1]
    key = selected["key"]

    # Call select API
    select_data = _images_post("select", {"key": key})
    image_ref = select_data.get("imageRef", {})

    download_url = image_ref.get("downloadUrl")
    storage_uri = image_ref.get("storageUri")

    console.print(f"[green]Image selected:[/green] {key}")
    console.print(f"[cyan]Download URL:[/cyan] {download_url}")
    console.print(f"[cyan]Storage URI:[/cyan] {storage_uri}")
    console.print(f"\n[dim]Use this URL with Tripo for image-to-3D conversion")


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
    console.print("  [cyan]/vision <query>[/cyan]   - Search & store reference images")
    console.print("  [cyan]/images[/cyan]           - List stored reference images")
    console.print("  [cyan]/usage [seconds][/cyan]  - Show usage dashboard (auto-refresh optional)")
    console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace (no args toggles)")
    console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode (tool orchestration)")
    console.print("  [cyan]/remember <note>[/cyan]  - Store a long-term memory note")
    console.print("  [cyan]/memories [query][/cyan] - Search saved memories")
    console.print("  [cyan]/reset[/cyan]            - Start a new conversation session")
    console.print("  [cyan]/help[/cyan]             - Show this help")
    console.print("  [cyan]/exit[/cyan]             - Exit shell")

    # Current settings
    effective = max(state.verbosity, 4) if state.show_trace else state.verbosity
    agent_status = "ON" if state.agent_enabled else "OFF"
    console.print(f"\n[dim]Verbosity: {effective}/5  |  Session: {state.conversation_id[:8]}...[/dim]")
    console.print(f"[dim]Agent mode: {agent_status} (use /agent to toggle)[/dim]")
    trace_status = "ON" if state.show_trace else "OFF"
    console.print(f"[dim]Trace mode: {trace_status} (use /trace to toggle)[/dim]")
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
                console.print("  [cyan]/vision <query>[/cyan]   - Search/select reference images")
                console.print("  [cyan]/images[/cyan]           - Show stored reference images")
                console.print(
                    "  [cyan]/usage [seconds][/cyan]  - Show provider usage dashboard"
                )
                console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace view")
                console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode")
                console.print("  [cyan]/remember <note>[/cyan]  - Store a long-term memory note")
                console.print("  [cyan]/memories [query][/cyan] - Search saved memories")
                console.print("  [cyan]/reset[/cyan]            - Start a new conversation session")
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

            if cmd == "reset":
                _start_new_session()
                continue

            if cmd == "remember":
                if not args:
                    console.print("[yellow]Usage: /remember <note to store>")
                else:
                    _remember_note(" ".join(args))
                continue

            if cmd in {"memories", "recall"}:
                query = " ".join(args)
                _search_memories(query)
                continue

            if cmd == "cad":
                if not args:
                    console.print("[yellow]Usage: /cad <prompt>")
                    console.print("[dim]Example: /cad design a wall mount bracket[/dim]")
                else:
                    organic_flag = False
                    param_flag = False
                    prompt_tokens: List[str] = []
                    for token in args:
                        lower = token.lower()
                        if lower in {"--o", "--organic"}:
                            organic_flag = True
                            continue
                        if lower in {"--p", "--parametric"}:
                            param_flag = True
                            continue
                        prompt_tokens.append(token)
                    cad(prompt_tokens, organic=organic_flag, parametric=param_flag)
                continue

            if cmd == "vision":
                if not args:
                    console.print("[yellow]Usage: /vision <query>")
                else:
                    _run_vision_flow(" ".join(args))
                continue

            if cmd == "images":
                if args and args[0].lower() in {"clear", "reset"}:
                    state.stored_images.clear()
                    _persist_stored_images()
                    console.print("[green]Cleared stored reference images.")
                    continue
                if not state.stored_images:
                    console.print("[yellow]No stored reference images.")
                else:
                    console.print("[bold]Stored reference images:[/bold]")
                    for idx, item in enumerate(state.stored_images, 1):
                        friendly = (
                            item.get("friendlyName")
                            or item.get("friendly_name")
                            or item.get("title")
                            or f"image{idx}"
                        )
                        console.print(
                            f" [cyan]{idx}[/] {friendly} "
                            f"| source={item.get('source','')} | url={item.get('download_url')}"
                        )
                continue

            if cmd == "usage":
                interval = None
                if args:
                    try:
                        interval = int(args[0])
                        if interval < 2:
                            raise ValueError
                    except ValueError:
                        console.print("[red]Usage: /usage [refresh_seconds>=2]")
                        continue
                _display_usage_dashboard(interval, exit_on_error=False)
                continue

            if cmd == "list":
                if state.last_artifacts:
                    console.print(f"\n[bold]Cached Artifacts ({len(state.last_artifacts)}):[/bold]")
                    _print_artifacts(state.last_artifacts)
                else:
                    console.print("[yellow]No artifacts cached. Use /cad to generate models")
                continue

            if cmd == "trace":
                if not args:
                    state.show_trace = not state.show_trace
                    console.print(
                        f"[green]Trace mode {'enabled' if state.show_trace else 'disabled'} "
                        f"({'verbosity forced to >=4' if state.show_trace else 'responses back to normal'})"
                    )
                else:
                    setting = args[0].lower()
                    if setting in {"on", "true", "1"}:
                        state.show_trace = True
                        console.print("[green]Trace mode enabled (verbosity forced to >=4)")
                    elif setting in {"off", "false", "0"}:
                        state.show_trace = False
                        console.print("[green]Trace mode disabled")
                    else:
                        console.print("[red]Usage: /trace on|off")
                continue

            if cmd == "agent":
                if not args:
                    state.agent_enabled = not state.agent_enabled
                    console.print(
                        f"[green]Agent mode {'enabled' if state.agent_enabled else 'disabled'}"
                    )
                else:
                    setting = args[0].lower()
                    if setting in {"on", "true", "1"}:
                        state.agent_enabled = True
                        console.print("[green]Agent mode enabled")
                    elif setting in {"off", "false", "0"}:
                        state.agent_enabled = False
                        console.print("[green]Agent mode disabled")
                    else:
                        console.print("[red]Usage: /agent on|off")
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
