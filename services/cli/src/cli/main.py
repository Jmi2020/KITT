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
        if host == "host.docker.internal" and not RUNNING_IN_CONTAINER:
            # Host alias is only reachable from inside containers; skip when on host
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
FABRICATION_API_BASE = _first_valid_url(
    (
        os.getenv("KITTY_FAB_API"),
        os.getenv("FABRICATION_API"),
        os.getenv("GATEWAY_API"),
        os.getenv("GATEWAY_PUBLIC_URL"),
        "http://gateway:8080",
        "http://localhost:8080",
    ),
    "http://localhost:8080",
)
USER_NAME = _env("USER_NAME", "ssh-operator")
USER_UUID = _env(
    "KITTY_USER_ID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_NAME)),
)
DEFAULT_VERBOSITY = int(_env("VERBOSITY", "3"))
CLI_TIMEOUT = float(_env("KITTY_CLI_TIMEOUT", "900"))
MAX_REFERENCE_CONTEXT = int(_env("KITTY_REFERENCE_CONTEXT", "6"))
TRIPO_REFERENCE_LIMIT = int(_env("TRIPO_MAX_IMAGE_REFS", "2"))
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
        item.setdefault("storedAt", datetime.utcnow().isoformat() + "Z")
        download_key = item.get("download_url") or item.get("storage_uri")
        if download_key in existing_urls:
            continue
        state.stored_images.append(item)
        existing_urls.add(download_key)
        changed = True
    if changed:
        _persist_stored_images()


def _stored_images_newest_first() -> List[Dict[str, Any]]:
    if not state.stored_images:
        return []
    if any("storedAt" in entry for entry in state.stored_images):
        return sorted(
            state.stored_images,
            key=lambda item: item.get("storedAt") or "",
            reverse=True,
        )
    return list(reversed(state.stored_images))


def _image_display_name(entry: Dict[str, Any]) -> str:
    return (
        entry.get("friendlyName")
        or entry.get("friendly_name")
        or entry.get("title")
        or entry.get("id")
        or "reference"
    )


def _format_reference_block(limit: int = MAX_REFERENCE_CONTEXT) -> str:
    images = _stored_images_newest_first()
    if not images:
        return ""
    lines = []
    for idx, entry in enumerate(images[:limit], start=1):
        name = _image_display_name(entry)
        source = entry.get("source") or "unknown"
        download = entry.get("download_url") or "n/a"
        storage = entry.get("storage_uri") or "n/a"
        lines.append(
            f"{idx}. {name} | source={source} | download={download} | storage={storage}"
        )
    return "<available_image_refs>\n" + "\n".join(lines) + "\n</available_image_refs>"


def _image_payload(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry.get("id"),
        "downloadUrl": entry.get("download_url"),
        "storageUri": entry.get("storage_uri"),
        "sourceUrl": entry.get("image_url"),
        "title": entry.get("title"),
        "source": entry.get("source"),
        "caption": entry.get("caption"),
        "friendlyName": entry.get("friendlyName") or entry.get("friendly_name"),
    }


def _match_reference_keywords(prompt: str, limit: int) -> List[Dict[str, Any]]:
    images = _stored_images_newest_first()
    if not images:
        return []
    tokens = {token for token in re.split(r"[^A-Za-z0-9]+", prompt.lower()) if token}
    if not tokens:
        return images[:limit]

    def _score(entry: Dict[str, Any]) -> int:
        haystacks = [
            _image_display_name(entry).lower(),
            (entry.get("title") or "").lower(),
            (entry.get("source") or "").lower(),
            (entry.get("caption") or "").lower(),
        ]
        score = 0
        for token in tokens:
            for hay in haystacks:
                if token and token in hay:
                    score += 1
                    break
        return score

    ranked = sorted(
        images,
        key=lambda item: (_score(item), item.get("storedAt") or ""),
        reverse=True,
    )
    return ranked[:limit]


def _resolve_cad_image_refs(selectors: Optional[List[str]]) -> List[Dict[str, Any]]:
    images = _stored_images_newest_first()
    if not images:
        return []
    if not selectors:
        return images
    selected: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    indexed = list(enumerate(images, start=1))
    name_map: Dict[str, Dict[str, Any]] = {}
    for entry in images:
        display = _image_display_name(entry)
        if display:
            name_map.setdefault(display.lower(), entry)
    id_map = {str(entry.get("id")).lower(): entry for entry in images if entry.get("id")}

    for raw in selectors:
        token = (raw or "").strip()
        if not token:
            continue
        entry = None
        if token.isdigit():
            idx = int(token)
            entry = indexed[idx - 1][1] if 1 <= idx <= len(indexed) else None
        if entry is None:
            entry = name_map.get(token.lower()) or id_map.get(token.lower())
        if entry is None:
            console.print(f"[yellow]No stored reference matches '{token}'.[/yellow]")
            continue
        key = entry.get("download_url") or entry.get("storage_uri") or entry.get("id")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        selected.append(entry)
    return selected


class CommandCompleter(Completer):
    """Custom completer for "/" commands with descriptions."""

    def __init__(self):
        self.commands = {
            "help": "Show this help message",
            "verbosity": "Set response detail level (1-5)",
            "cad": "Generate CAD model from description",
            "generate": "Generate image with Stable Diffusion",
            "list": "List cached CAD artifacts",
            "queue": "Queue artifact to printer",
            "usage": "Show provider usage dashboard",
            "vision": "Search + select reference images",
            "images": "List stored reference images",
            "trace": "Toggle agent reasoning trace",
            "agent": "Toggle ReAct agent mode",
            "collective": "Multi-agent collaboration (council/debate/pipeline)",
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


def _typewriter_print(text: str, speed: float = 0.01, panel_title: str = "KITTY", border_style: str = "green") -> None:
    """Print text with typewriter effect, line by line for smooth performance."""
    import time
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text as RichText

    lines = text.split('\n')
    displayed_lines = []

    # Create initial empty panel
    display_text = RichText()
    panel = Panel(display_text, title=f"[bold {border_style}]{panel_title}", border_style=border_style)

    with Live(panel, console=console, refresh_per_second=20) as live:
        for line in lines:
            # Add full line at once (line-by-line is smoother than char-by-char)
            displayed_lines.append(line)
            display_text = RichText('\n'.join(displayed_lines))
            panel = Panel(display_text, title=f"[bold {border_style}]{panel_title}", border_style=border_style)
            live.update(panel)
            time.sleep(speed)  # Small delay per line

    # Final static display
    console.print(Panel(text, title=f"[bold {border_style}]{panel_title}", border_style=border_style))


def _request_with_continuation(
    url: str,
    payload: Dict[str, Any],
    status_text: str = "KITTY is thinking",
    max_continuations: int = 5
) -> tuple[str, Dict[str, Any]]:
    """Make API call with automatic continuation support for truncated responses.

    Returns:
        Tuple of (full_output, final_metadata)
    """
    full_output = ""
    final_metadata = {}
    continuation_count = 0

    # Show thinking spinner for initial request
    spinner = Spinner("dots", text=Text(status_text, style="cyan"))

    with Live(spinner, console=console, transient=True):
        with _client() as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

    output = data.get("result", {}).get("output", "")
    full_output = output
    routing = data.get("routing", {})
    metadata = routing.get("metadata", {})
    final_metadata = routing

    # Display first chunk with typewriter effect
    if output:
        _typewriter_print(output)

    # Check for truncation and auto-continue
    while metadata.get("truncated") and continuation_count < max_continuations:
        continuation_count += 1
        console.print(f"\n[dim]← Response truncated, requesting continuation {continuation_count}/{max_continuations}...[/dim]\n")

        # Create continuation payload
        continuation_payload = payload.copy()
        continuation_payload["prompt"] = "[Continue from where you left off. Do not repeat what you already said, just continue.]"

        # Request continuation with spinner
        spinner = Spinner("dots", text=Text(f"Continuing ({continuation_count}/{max_continuations})...", style="yellow"))
        with Live(spinner, console=console, transient=True):
            with _client() as client:
                response = client.post(url, json=continuation_payload)
                response.raise_for_status()
                data = response.json()

        output = data.get("result", {}).get("output", "")
        if output:
            full_output += "\n" + output
            _typewriter_print(output, panel_title="KITTY (continued)", border_style="yellow")

        routing = data.get("routing", {})
        metadata = routing.get("metadata", {})
        final_metadata = routing

    if continuation_count >= max_continuations and metadata.get("truncated"):
        console.print(f"\n[yellow]⚠️  Reached maximum continuations ({max_continuations}). Response may still be incomplete.[/yellow]")
        console.print("[dim]Tip: Increase LLAMACPP_N_PREDICT in .env for longer responses in a single generation.[/dim]\n")

    return full_output, final_metadata


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
    """Pretty-print agent reasoning steps if present with typewriter effect."""
    import time

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

        # Use typewriter effect for agent steps
        step_content = "\n".join(lines)
        _typewriter_print(
            step_content,
            speed=0.005,  # Faster for agent steps
            panel_title=f"Step {idx}",
            border_style="magenta"
        )
        time.sleep(0.1)  # Brief pause between steps


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


def _maybe_offer_slicer(artifacts: List[Dict[str, Any]]) -> None:
    """Interactive helper to open a generated STL in the appropriate slicer."""

    if not artifacts:
        return

    try:
        wants_print = typer.confirm(
            "Open a slicer with one of these models now?", default=False
        )
    except typer.Abort:
        return

    if not wants_print:
        return

    total = len(artifacts)
    selected = artifacts[0]
    if total > 1:
        while True:
            choice = typer.prompt(f"Select artifact index (1-{total})", default="1")
            try:
                idx = int(choice)
            except ValueError:
                console.print(f"[red]Please enter a number between 1 and {total}.")
                continue
            if 1 <= idx <= total:
                selected = artifacts[idx - 1]
                break
            console.print(f"[red]Please enter a number between 1 and {total}.")

    location = selected.get("location")
    if not location:
        console.print("[red]Selected artifact does not include a local path.")
        return

    height_input = typer.prompt(
        "Desired printed height (e.g., 6 in, 150 mm)", default=""
    ).strip()

    payload = {"stl_path": location}
    if height_input:
        payload["target_height"] = height_input

    try:
        data = _post_json_with_spinner(
            f"{FABRICATION_API_BASE}/api/fabrication/open_in_slicer",
            payload,
            "Opening slicer",
        )
        app_name = data.get("slicer_app") or "slicer"
        console.print(
            f"[green]Launched {app_name} for {os.path.basename(location)}[/green]"
        )
        reasoning = data.get("reasoning")
        if reasoning:
            console.print(f"[dim]{reasoning}[/dim]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to open slicer: {exc}")


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
    reference_block = _format_reference_block()
    if not reference_block:
        return user_prompt
    return f"{user_prompt}\n\n{reference_block}"


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
        full_output, routing_metadata = _request_with_continuation(
            f"{API_BASE}/api/query",
            payload,
            "KITTY is thinking",
            max_continuations=5
        )
    except httpx.TimeoutException:
        console.print("[red]Request timed out - check if KITTY services are running")
        raise typer.Exit(1)
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]HTTP {exc.response.status_code}: {exc.response.text}")
        raise typer.Exit(1) from exc
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Request failed: {exc}")
        raise typer.Exit(1) from exc

    if not full_output:
        console.print("[yellow]No response received")

    # Show routing info / traces when requested
    if state.verbosity >= 4 or trace_enabled:
        _print_routing(routing_metadata, show_trace=trace_enabled)


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
    image_filters: Optional[List[str]] = typer.Option(
        None,
        "--image",
        "-i",
        help="Limit CAD input to specific stored references (friendly name, ID, or newest-first index). Repeat to include multiple.",
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

    auto_selected: List[Dict[str, Any]] = []
    if state.stored_images:
        if image_filters:
            selected_refs = _resolve_cad_image_refs(image_filters)
            if image_filters and not selected_refs:
                console.print("[red]No stored references matched the requested filters.[/red]")
                raise typer.Exit(1)
        else:
            selected_refs = _match_reference_keywords(text, TRIPO_REFERENCE_LIMIT)
            auto_selected = selected_refs

        if selected_refs:
            payload["imageRefs"] = [_image_payload(entry) for entry in selected_refs]
            if chosen_mode is None:
                chosen_mode = "organic"
            if auto_selected:
                friendly = ", ".join(_image_display_name(entry) for entry in auto_selected)
                console.print(f"[dim]Auto-selected references: {friendly}[/dim]")
    elif image_filters:
        console.print("[yellow]No stored references available—ignoring --image filters.[/yellow]")

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
        _maybe_offer_slicer(artifacts)
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
def autonomy(
    action: str = typer.Argument(..., help="Action: list, approve, reject, status"),
    goal_id: Optional[str] = typer.Argument(None, help="Goal ID for approve/reject actions"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n", help="Approval/rejection notes"),
    user_id: Optional[str] = typer.Option("cli-user", "--user", "-u", help="User ID for approval"),
):
    """Manage autonomous goals and view system status.

    Actions:
        list      - List pending autonomous goals
        approve   - Approve a goal by ID
        reject    - Reject a goal by ID
        status    - Show autonomy system status

    Examples:
        kitty-cli autonomy list
        kitty-cli autonomy approve <goal-id>
        kitty-cli autonomy reject <goal-id> --notes "Not a priority"
        kitty-cli autonomy status
    """
    if action == "list":
        # List pending goals
        try:
            response = httpx.get(
                f"{API_BASE}/api/autonomy/goals",
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            console.print(f"[red]Error fetching goals: {exc}")
            raise typer.Exit(1)

        goals = data.get("goals", [])
        pending_count = data.get("pending_count", 0)

        if not goals:
            console.print("\n[yellow]No pending autonomous goals[/yellow]")
            console.print("[dim]KITTY will identify new goals during the next weekly cycle (Monday 5am PST)[/dim]\n")
            return

        console.print(f"\n[bold cyan]Pending Autonomous Goals ({pending_count})[/bold cyan]\n")

        for i, goal in enumerate(goals, 1):
            goal_type = goal["goal_type"]
            description = goal["description"]
            rationale = goal["rationale"]
            budget = goal["estimated_budget"]
            hours = goal.get("estimated_duration_hours")
            goal_id = goal["id"]
            metadata = goal.get("goal_metadata", {})
            source = metadata.get("source", "unknown")

            # Color by goal type
            type_colors = {
                "research": "blue",
                "fabrication": "green",
                "improvement": "yellow",
                "optimization": "magenta",
            }
            color = type_colors.get(goal_type, "white")

            console.print(f"[bold {color}]{i}. [{goal_type.upper()}] {description}[/bold {color}]")
            console.print(f"   [dim]ID: {goal_id[:16]}...[/dim]")
            console.print(f"   Rationale: {rationale}")
            console.print(f"   Estimated: ${budget:.2f}, {hours}h")
            console.print(f"   Source: {source}")
            console.print()

        console.print("[dim]Use 'kitty-cli autonomy approve <goal-id>' to approve a goal[/dim]")
        console.print("[dim]Use 'kitty-cli autonomy reject <goal-id>' to reject a goal[/dim]\n")

    elif action == "approve":
        if not goal_id:
            console.print("[red]Error: goal_id required for approve action[/red]")
            console.print("[dim]Usage: kitty-cli autonomy approve <goal-id>[/dim]")
            raise typer.Exit(1)

        # Approve goal
        try:
            response = httpx.post(
                f"{API_BASE}/api/autonomy/goals/{goal_id}/approve",
                json={"user_id": user_id, "notes": notes},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            console.print(f"[red]Error approving goal: {exc}")
            raise typer.Exit(1)

        console.print(f"\n[green]✓ Goal Approved[/green]")
        console.print(f"   {data['message']}")
        console.print(f"   Approved by: {data['approved_by']}")
        console.print(f"   Status: {data['status']}\n")

    elif action == "reject":
        if not goal_id:
            console.print("[red]Error: goal_id required for reject action[/red]")
            console.print("[dim]Usage: kitty-cli autonomy reject <goal-id>[/dim]")
            raise typer.Exit(1)

        # Reject goal
        try:
            response = httpx.post(
                f"{API_BASE}/api/autonomy/goals/{goal_id}/reject",
                json={"user_id": user_id, "notes": notes},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            console.print(f"[red]Error rejecting goal: {exc}")
            raise typer.Exit(1)

        console.print(f"\n[yellow]✗ Goal Rejected[/yellow]")
        console.print(f"   {data['message']}")
        console.print(f"   Rejected by: {data['approved_by']}")
        console.print(f"   Status: {data['status']}\n")

    elif action == "status":
        # Show autonomy system status
        try:
            response = httpx.get(
                f"{API_BASE}/api/autonomy/status",
                timeout=30.0
            )
            response.raise_for_status()
            status_data = response.json()

            budget_response = httpx.get(
                f"{API_BASE}/api/autonomy/budget?days=7",
                timeout=30.0
            )
            budget_response.raise_for_status()
            budget_data = budget_response.json()
        except httpx.HTTPError as exc:
            console.print(f"[red]Error fetching status: {exc}")
            raise typer.Exit(1)

        # Display status
        console.print("\n[bold cyan]Autonomous System Status[/bold cyan]\n")

        can_run = status_data["can_run_autonomous"]
        reason = status_data["reason"]
        status_icon = "✓" if can_run else "✗"
        status_color = "green" if can_run else "yellow"

        console.print(f"[{status_color}]{status_icon} Ready: {can_run}[/{status_color}]")
        console.print(f"   {reason}\n")

        console.print("[bold]Resource Status:[/bold]")
        console.print(f"   Budget Available: ${status_data['budget_available']:.2f} / ${budget_data['budget_limit_per_day']:.2f} per day")
        console.print(f"   Budget Used Today: ${status_data['budget_used_today']:.2f}")
        console.print(f"   System Idle: {status_data['is_idle']}")
        console.print(f"   CPU Usage: {status_data['cpu_usage_percent']:.1f}%")
        console.print(f"   Memory Usage: {status_data['memory_usage_percent']:.1f}%\n")

        console.print(f"[bold]7-Day Budget Summary:[/bold]")
        console.print(f"   Total Cost: ${budget_data['total_cost_usd']:.2f}")
        console.print(f"   Total Requests: {budget_data['total_requests']}")
        console.print(f"   Average/Day: ${budget_data['average_cost_per_day']:.2f}\n")

    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        console.print("[dim]Valid actions: list, approve, reject, status[/dim]")
        raise typer.Exit(1)


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
    console.print("  [cyan]/generate <prompt>[/cyan] - Generate image with Stable Diffusion")
    console.print("  [cyan]/list[/cyan]             - Show cached artifacts")
    console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact to printer")
    console.print("  [cyan]/vision <query>[/cyan]   - Search & store reference images")
    console.print("  [cyan]/images[/cyan]           - List stored reference images")
    console.print("  [cyan]/usage [seconds][/cyan]  - Show usage dashboard (auto-refresh optional)")
    console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace (no args toggles)")
    console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode (tool orchestration)")
    console.print("  [cyan]/collective <pattern> <task>[/cyan] - Multi-agent collaboration")
    console.print("      [dim]Patterns: council [k=N], debate, pipeline[/dim]")
    console.print("      [dim]Example: /collective council k=3 Compare PETG vs ABS[/dim]")
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
                console.print("  [cyan]/generate <prompt>[/cyan] - Generate image with Stable Diffusion")
                console.print("  [cyan]/list[/cyan]             - List cached CAD artifacts")
                console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact #idx to printer")
                console.print("  [cyan]/vision <query>[/cyan]   - Search/select reference images")
                console.print("  [cyan]/images[/cyan]           - Show stored reference images")
                console.print(
                    "  [cyan]/usage [seconds][/cyan]  - Show provider usage dashboard"
                )
                console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace view")
                console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode")
                console.print("  [cyan]/collective <pattern> <task>[/cyan] - Multi-agent collaboration")
                console.print("      [dim]Patterns: council [k=3], debate, pipeline[/dim]")
                console.print("      [dim]Example: /collective council k=3 Compare PETG vs ABS[/dim]")
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

            if cmd == "generate":
                if not args:
                    console.print("[yellow]Usage: /generate <prompt>")
                    console.print("[dim]Example: /generate studio photo of a water bottle[/dim]")
                else:
                    # Call the generate_image command with default parameters
                    try:
                        generate_image(
                            prompt=args,
                            width=1024,
                            height=1024,
                            steps=30,
                            cfg=7.0,
                            seed=None,
                            model="sdxl_base",
                            refiner=None,
                            wait=True  # Wait for completion in interactive mode
                        )
                    except typer.Exit:
                        pass  # Handle exit gracefully in shell
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
                    console.print("[bold]Stored reference images (newest first):[/bold]")
                    for idx, item in enumerate(_stored_images_newest_first(), 1):
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

            if cmd == "collective":
                if not args:
                    console.print("[yellow]Usage: /collective <pattern> [k=N] <task>")
                    console.print("[dim]Patterns: council, debate, pipeline")
                    console.print("[dim]Example: /collective council k=3 Compare PETG vs ABS for outdoor use")
                    console.print("[dim]Example: /collective debate Should I use tree supports?")
                    continue

                # Parse pattern and optional k=N parameter
                pattern = args[0].lower()
                if pattern not in {"council", "debate", "pipeline"}:
                    console.print(f"[red]Invalid pattern '{pattern}'. Use: council, debate, or pipeline")
                    continue

                # Check for k=N parameter
                k = 3  # default
                task_start_idx = 1
                if len(args) > 1 and args[1].startswith("k="):
                    try:
                        k = int(args[1][2:])
                        if k < 2 or k > 7:
                            console.print("[red]k must be between 2 and 7")
                            continue
                        task_start_idx = 2
                    except ValueError:
                        console.print(f"[red]Invalid k value: {args[1]}")
                        continue

                # Reconstruct task from remaining args
                if len(args) <= task_start_idx:
                    console.print("[red]Please provide a task description")
                    continue

                task = " ".join(args[task_start_idx:])

                # Call collective API
                console.print(f"\n[bold]Running {pattern} pattern (k={k})...[/]")
                console.print(f"[dim]Task: {task}[/]")

                with console.status("[bold green]Generating proposals..."):
                    try:
                        response = httpx.post(
                            f"{API_BASE}/api/collective/run",
                            json={"task": task, "pattern": pattern, "k": k},
                            timeout=180.0  # 3 minutes for Quality-First mode
                        )
                        response.raise_for_status()
                        data = response.json()
                    except httpx.HTTPError as exc:
                        console.print(f"[red]Error: {exc}")
                        continue

                # Display proposals with typewriter effect
                console.print(f"\n[bold cyan]Proposals ({len(data['proposals'])}):[/]")
                for i, prop in enumerate(data["proposals"], 1):
                    role = prop["role"]
                    text = prop["text"]
                    # Show full proposal with typewriter effect
                    _typewriter_print(
                        text,
                        speed=0.008,
                        panel_title=f"{i}. {role}",
                        border_style="cyan"
                    )

                # Display verdict with typewriter effect
                console.print(f"\n[bold green]⚖️  Judge Verdict:[/]")
                _typewriter_print(
                    data["verdict"],
                    speed=0.01,
                    panel_title="Final Verdict",
                    border_style="green"
                )
                console.print()  # blank line
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
