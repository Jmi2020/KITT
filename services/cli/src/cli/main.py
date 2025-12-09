"""SSH-friendly CLI interface for KITTY."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import quote_plus, urlencode, urlparse
from pathlib import Path

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
ARTIFACTS_DIR = Path(_env("KITTY_ARTIFACTS_DIR", "/Users/Shared/KITTY/artifacts"))
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
DISCOVERY_BASE = _first_valid_url(
    (
        os.getenv("DISCOVERY_BASE"),
        os.getenv("DISCOVERY_SERVICE_URL"),
        os.getenv("DISCOVERY_API"),
        os.getenv("GATEWAY_API"),
        "http://localhost:8500",
        "http://gateway:8080",
    ),
    "http://localhost:8500",
)
USER_NAME = _env("USER_NAME", "ssh-operator")
USER_UUID = _env(
    "KITTY_USER_ID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_NAME)),
)
DEFAULT_VERBOSITY = int(_env("VERBOSITY", "3"))
CLI_TIMEOUT = float(_env("KITTY_CLI_TIMEOUT", "1200"))
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


def _parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Assume UTC if no timezone info is provided
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _format_history_time(value: Optional[str], show_date: bool = False) -> str:
    parsed = _parse_iso_timestamp(value)
    if not parsed:
        return "—"
    try:
        local_tz = datetime.now().astimezone().tzinfo
        parsed = parsed.astimezone(local_tz)
        fmt = "%Y-%m-%d %H:%M" if show_date else "%m-%d %H:%M"
        return parsed.strftime(fmt)
    except Exception:  # noqa: BLE001
        return value or "—"


def _truncate_text(text: str, limit: Optional[int]) -> str:
    """Truncate text with a dim suffix; limit<=0 returns full text."""
    if not limit or limit <= 0 or len(text) <= limit:
        return text
    return text[:limit] + "\n\n[dim]... (truncated; use --truncate 0 for full)[/dim]"


def _conversation_preview(entry: Dict[str, Any]) -> str:
    title = entry.get("title")
    if title:
        return title
    last_user = entry.get("lastUserMessage")
    last_assistant = entry.get("lastAssistantMessage")
    for candidate in (last_user, last_assistant):
        if candidate:
            text = candidate.strip().replace("\n", " ")
            return text[:80] + ("…" if len(text) > 80 else "")
    return entry.get("conversationId", "unknown")


def _fetch_conversation_history(limit: int = 10, search: Optional[str] = None) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"limit": limit, "userId": state.user_id}
    if search:
        params["search"] = search
    url = f"{API_BASE}/api/conversations?{urlencode(params)}"
    data = _get_json(url)
    return data.get("conversations", [])


def _history_picker(limit: int = 10, search: Optional[str] = None) -> None:
    try:
        conversations = _fetch_conversation_history(limit=limit, search=search)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to load conversation history: {exc}")
        return

    if not conversations:
        console.print("[yellow]No past conversations found.")
        return

    table = Table(title="Conversation History", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Last Active")
    table.add_column("Messages", justify="right")
    table.add_column("Preview")

    for idx, entry in enumerate(conversations, start=1):
        table.add_row(
            str(idx),
            _format_history_time(entry.get("lastMessageAt"), show_date=True),
            str(entry.get("messageCount", 0)),
            _conversation_preview(entry),
        )

    console.print(table)
    prompt = "Select a session to resume (number, id prefix, or blank to cancel): "
    selection = console.input(f"\n[bold]{prompt}[/bold]").strip()
    if not selection:
        console.print("[dim]History picker cancelled.[/dim]")
        return

    chosen: Optional[Dict[str, Any]] = None
    if selection.isdigit():
        idx = int(selection)
        if 1 <= idx <= len(conversations):
            chosen = conversations[idx - 1]
    else:
        normalized = selection.lower()
        for entry in conversations:
            conv_id = entry.get("conversationId", "").lower()
            if conv_id.startswith(normalized):
                chosen = entry
                break

    if not chosen:
        console.print("[red]Selection did not match any saved session.")
        return

    conversation_id = chosen.get("conversationId")
    if not conversation_id:
        console.print("[red]Selected entry is missing an ID.")
        return

    state.conversation_id = conversation_id
    state.last_artifacts = []
    preview = _conversation_preview(chosen)
    console.print(
        f"[green]Resumed session {conversation_id[:8]}...[/green] "
        f"[dim]({preview})[/dim]"
    )

    transcript_url = f"{API_BASE}/api/conversations/{conversation_id}/messages?limit=20"
    try:
        transcript = _get_json(transcript_url).get("messages", [])
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Unable to load transcript: {exc}")
        return

    if not transcript:
        console.print("[dim]No messages recorded yet for this session.")
        return

    console.print("\n[bold]Recent messages:[/bold]")
    for entry in transcript:
        ts = _format_history_time(entry.get("createdAt"))
        role = entry.get("role", "?").capitalize()
        content = entry.get("content", "")
        console.print(f" [dim]{ts}[/dim] [cyan]{role}: [/cyan]{content}")


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
    stream_enabled: bool = False  # Enable streaming mode with real-time thinking traces
    provider: Optional[str] = None  # Multi-provider collective: selected provider
    model: Optional[str] = None  # Multi-provider collective: selected model


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
    # Filter out short stopwords that would match almost anything
    stopwords = {"a", "an", "the", "to", "of", "in", "on", "at", "for", "is", "it", "as", "be", "or", "and", "with"}
    tokens = {
        token for token in re.split(r"[^A-Za-z0-9]+", prompt.lower())
        if token and len(token) > 2 and token not in stopwords
    }
    if not tokens:
        return []

    def _score(entry: Dict[str, Any]) -> int:
        # Tokenize haystacks for whole-word matching
        haystacks = [
            _image_display_name(entry).lower(),
            (entry.get("title") or "").lower(),
            (entry.get("source") or "").lower(),
            (entry.get("caption") or "").lower(),
        ]
        haystack_tokens = set()
        for hay in haystacks:
            haystack_tokens.update(t.lower() for t in re.split(r"[^A-Za-z0-9]+", hay) if t)
        # Use whole-word matching instead of substring
        score = sum(1 for token in tokens if token in haystack_tokens)
        return score

    scored = [(img, _score(img)) for img in images]
    # Only include images that actually match keywords (score > 0)
    matched = [(img, s) for img, s in scored if s > 0]
    if not matched:
        return []
    ranked = sorted(
        matched,
        key=lambda item: (item[1], item[0].get("storedAt") or ""),
        reverse=True,
    )
    return [img for img, _ in ranked[:limit]]


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
            "research": "Start autonomous research with streaming",
            "sessions": "List all research sessions",
            "session": "View detailed session info and metrics",
            "stream": "Stream progress of active research session",
            "cad": "Generate CAD model from description",
            "generate": "Generate image with Stable Diffusion",
            "list": "List cached CAD artifacts",
            "queue": "Queue artifact to printer",
            "split": "Segment large 3D model for multi-part printing",
            "usage": "Show provider usage dashboard",
            "vision": "Search + select reference images",
            "images": "List stored reference images",
            "trace": "Toggle agent reasoning trace",
            "agent": "Toggle ReAct agent mode",
            "collective": "Multi-agent collaboration (council/debate/pipeline)",
            "discover": "Network discovery (scan/status/list/approve/reject)",
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


def _request_with_streaming(
    url: str,
    payload: Dict[str, Any],
    status_text: str = "KITTY is thinking",
) -> tuple[str, Dict[str, Any]]:
    """Make streaming API call with real-time thinking traces.

    Displays thinking traces and response content as they stream in.

    Returns:
        Tuple of (full_output, final_metadata)
    """
    import json

    full_content = ""
    full_thinking = ""
    final_metadata = {}

    # Create dual-panel display: thinking (dim cyan) + response (green)
    thinking_text = Text()
    response_text = Text()

    thinking_panel = Panel(
        thinking_text,
        title="[bold dim cyan]Thinking",
        border_style="dim cyan",
        padding=(0, 1),
    )
    response_panel = Panel(
        response_text,
        title="[bold green]KITTY",
        border_style="green",
        padding=(0, 1),
    )

    # Use table to display panels side-by-side (or stacked on narrow terminals)
    from rich.columns import Columns

    display = Columns([thinking_panel, response_panel], expand=True, equal=True)

    with Live(display, console=console, refresh_per_second=10) as live:
        with httpx.stream("POST", url, json=payload, timeout=CLI_TIMEOUT) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line.strip():
                    continue

                # Parse SSE format: "data: {json}"
                if line.startswith("data:"):
                    line = line[5:].strip()
                else:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                chunk_type = chunk.get("type", "chunk")

                if chunk_type == "chunk":
                    # Accumulate deltas
                    delta = chunk.get("delta", "")
                    delta_thinking = chunk.get("delta_thinking")

                    if delta:
                        full_content += delta
                        response_text = Text(full_content)

                    if delta_thinking:
                        full_thinking += delta_thinking
                        thinking_text = Text(full_thinking, style="dim cyan")

                    # Update display
                    thinking_panel = Panel(
                        thinking_text,
                        title="[bold dim cyan]Thinking",
                        border_style="dim cyan",
                        padding=(0, 1),
                    )
                    response_panel = Panel(
                        response_text,
                        title="[bold green]KITTY",
                        border_style="green",
                        padding=(0, 1),
                    )
                    display = Columns([thinking_panel, response_panel], expand=True, equal=True)
                    live.update(display)

                elif chunk_type == "complete":
                    # Final metadata
                    final_metadata = chunk.get("routing", {})
                    break

                elif chunk_type == "error":
                    error_msg = chunk.get("error", "Unknown error")
                    console.print(f"[red]Streaming error: {error_msg}")
                    break

    # If no thinking was shown, just print the response in a single panel
    if not full_thinking:
        console.print(
            Panel(
                Text(full_content),
                title="[bold green]KITTY",
                border_style="green",
                padding=(0, 1),
            )
        )

    return full_content, final_metadata


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


def _discovery_url(path: str) -> str:
    return f"{DISCOVERY_BASE.rstrip('/')}/{path.lstrip('/')}"


def _discovery_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _client() as client:
        response = client.get(_discovery_url(path), params=params)
        response.raise_for_status()
        return response.json()


def _discovery_post(
    path: str,
    payload: Dict[str, Any],
    *,
    spinner_text: Optional[str] = None,
) -> Dict[str, Any]:
    url = _discovery_url(path)
    if spinner_text:
        return _post_json_with_spinner(url, payload, spinner_text)
    with _client() as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _safe_value(val: Any, default: str = "N/A") -> str:
    """Stringify with a fallback."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return str(val)
    text = str(val).strip()
    return text if text else default


def _format_services(services: Optional[List[Dict[str, Any]]]) -> str:
    if not services:
        return "—"
    entries = []
    for svc in services[:3]:
        name = svc.get("name") or svc.get("protocol") or "svc"
        port = svc.get("port")
        if port:
            entries.append(f"{name}:{port}")
        else:
            entries.append(name)
    extra = max(0, len(services) - 3)
    if extra:
        entries.append(f"+{extra} more")
    return ", ".join(entries)


def _format_conf(val: Optional[float]) -> str:
    return f"{val:.2f}" if isinstance(val, (int, float)) else "—"


def _render_devices_table(devices: List[Dict[str, Any]], total: int, filters: Optional[Dict[str, Any]] = None) -> None:
    if not devices:
        console.print("[yellow]No devices found.[/yellow]")
        if filters:
            console.print(f"[dim]Filters: {filters}[/dim]")
        return

    table = Table(show_edge=False, header_style="bold cyan")
    table.add_column("Type", style="cyan")
    table.add_column("IP")
    table.add_column("Host")
    table.add_column("Vendor/Model")
    table.add_column("Services")
    table.add_column("Conf")
    table.add_column("Approved", justify="center")
    table.add_column("Last Seen")

    for dev in devices:
        caps = dev.get("capabilities") or {}
        kind = caps.get("candidate_kind") or dev.get("device_type") or "unknown"
        vendor_parts = [dev.get("manufacturer"), dev.get("model")]
        vendor_model = " ".join([part for part in vendor_parts if part]).strip() or "—"
        last_seen = _format_history_time(dev.get("last_seen"), show_date=True)
        approved = "yes" if dev.get("approved") else "no"
        conf_val = caps.get("candidate_confidence") or dev.get("confidence_score")
        table.add_row(
            kind,
            dev.get("ip_address") or "—",
            dev.get("hostname") or "—",
            vendor_model,
            _format_services(dev.get("services")),
            _format_conf(conf_val),
            approved,
            last_seen,
        )

    console.print(table)
    console.print(f"[dim]Total: {total}[/dim]")
    if filters:
        console.print(f"[dim]Filters: {filters}[/dim]")


def _print_scan_status(status: Dict[str, Any]) -> None:
    table = Table(title="Discovery Scan", show_edge=False, header_style="bold cyan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Scan ID", str(status.get("scan_id")))
    table.add_row("Status", status.get("status", "unknown"))
    table.add_row("Methods", ", ".join(status.get("methods", [])) or "default")
    table.add_row("Devices Found", str(status.get("devices_found", 0)))
    if status.get("errors"):
        table.add_row("Errors", "; ".join(status.get("errors", [])))
    if status.get("started_at"):
        table.add_row("Started", _format_history_time(status.get("started_at"), show_date=True))
    if status.get("completed_at"):
        table.add_row("Completed", _format_history_time(status.get("completed_at"), show_date=True))
    console.print(table)


def _parse_bool_str(val: Optional[str]) -> Optional[bool]:
    if val is None:
        return None
    lowered = val.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _run_discover(
    action: str,
    *,
    scan_id: Optional[str] = None,
    device_id: Optional[str] = None,
    methods: Optional[List[str]] = None,
    timeout_seconds: int = 30,
    search: Optional[str] = None,
    device_type: Optional[str] = None,
    approved: Optional[bool] = None,
    online: Optional[bool] = None,
    manufacturer: Optional[str] = None,
    limit: int = 100,
    notes: Optional[str] = None,
) -> None:
    action = action.lower()

    if action == "scan":
        payload: Dict[str, Any] = {"timeout_seconds": timeout_seconds}
        if methods:
            payload["methods"] = methods
        status = _discovery_post("api/discovery/scan", payload, spinner_text="Starting discovery scan")
        _print_scan_status(status)
        console.print("[dim]Use `kitty-cli discover status <scan_id>` to follow progress.[/dim]")
        return

    if action == "status":
        if not scan_id:
            console.print("[red]Scan ID is required.[/red]")
            raise typer.Exit(1)
        status = _discovery_get(f"api/discovery/scan/{scan_id}")
        _print_scan_status(status)
        return

    if action == "list":
        params: Dict[str, Any] = {"limit": limit}
        if device_type:
            params["device_type"] = device_type
        if approved is not None:
            params["approved"] = approved
        if online is not None:
            params["is_online"] = online
        if manufacturer:
            params["manufacturer"] = manufacturer

        if search:
            data = _discovery_get("api/discovery/search", {"q": search, "limit": limit})
        else:
            data = _discovery_get("api/discovery/devices", params)

        devices = data.get("devices", [])
        total = data.get("total", len(devices))
        filters = data.get("filters_applied", {})
        _render_devices_table(devices, total, filters)
        return

    if action in {"approve", "reject"}:
        if not device_id:
            console.print("[red]Device ID is required.[/red]")
            raise typer.Exit(1)
        path = f"api/discovery/devices/{device_id}/approve" if action == "approve" else f"api/discovery/devices/{device_id}/reject"
        payload = {"notes": notes} if notes else {}
        result = _discovery_post(path, payload or {}, spinner_text=f"{action.title()}ing device")
        status = "approved" if action == "approve" else "rejected"
        console.print(f"[green]Device {device_id} {status}.[/green]")
        if result.get("notes"):
            console.print(f"[dim]Notes: {result.get('notes')}[/dim]")
        return

    console.print("[red]Unknown discovery action. Use scan | status | list | approve | reject.[/red]")
    raise typer.Exit(1)


def _render_research_report(detail: Dict[str, Any], results: Dict[str, Any]) -> str:
    """Render a research session into the GPTOSS research template."""
    now = datetime.utcnow().replace(tzinfo=None)
    created_at = detail.get("created_at") or now.isoformat()
    config = detail.get("config") or {}

    total_findings = results.get("total_findings", 0)
    total_sources = results.get("total_sources", 0)
    total_cost = results.get("total_cost_usd", 0.0)
    final_synthesis = results.get("final_synthesis") or "N/A"
    findings = results.get("findings") or []

    sample_findings = []
    for idx, finding in enumerate(findings[:3], 1):
        content = finding.get("content", "") or ""
        snippet = content[:500] + ("…" if len(content) > 500 else "")
        sample_findings.append(f"Finding {idx}: {snippet}")
    rep_block_parts = ["Synthesis:\n" + final_synthesis]
    if sample_findings:
        rep_block_parts.append("\n".join(sample_findings))
    rep_block = "\n\n".join(rep_block_parts) if rep_block_parts else "N/A"

    temperature = config.get("temperature", "N/A")
    top_p = config.get("top_p", "N/A")
    max_tokens = (
        config.get("max_output_tokens")
        or config.get("max_tokens")
        or "N/A"
    )
    stop_sequences = config.get("stop_sequences") or "N/A"
    strategy = config.get("strategy", "N/A")

    report = f"""
<LLM_RESEARCH_OUTPUT>

# 0. METADATA
Run_ID: {detail.get('session_id', 'N/A')}
Date: {created_at[:10]}
Researcher: {USER_NAME}
Model_Name: GPTOSS-120B
Model_Revision: N/A
KITTY_Pipeline_Stage: analysis
Dataset_Name: research_sessions
Task_Type: research
Experiment_Tag: strategy={strategy}

# 1. RESEARCH QUESTION
Primary_Question: {_safe_value(detail.get('query'))}
Secondary_Questions:
- N/A
- N/A

# 2. HYPOTHESES
Null_Hypothesis: N/A
Working_Hypotheses:
- H1: N/A
- H2: N/A
- H3: N/A

# 3. EXPERIMENT DESIGN

## 3.1 Variables
Independent_Variables:
- strategy: {strategy}
- max_iterations: {_safe_value(config.get('max_iterations', 'N/A'))}
Dependent_Variables:
- findings: total findings collected
- cost_usd: total cost in USD

## 3.2 Model Configuration
Temperature: {temperature}
Top_p: {top_p}
Max_Tokens: {max_tokens}
Stop_Sequences: {stop_sequences}
System_Prompt_Summary: N/A
Other_Params: {json.dumps(config)}

## 3.3 Data & Sampling
Input_Source: web + tools
Sample_Size: {total_findings}
Sampling_Strategy: iterative search
Train_Dev_Test_Split: N/A
Filtering_Notes:
- N/A
- N/A

# 4. PROMPT SETUP

## 4.1 System Prompt (verbatim)
<BEGIN_BLOCK:SYSTEM_PROMPT>
N/A
<END_BLOCK:SYSTEM_PROMPT>

## 4.2 User Prompt / Template (verbatim)
<BEGIN_BLOCK:USER_PROMPT_TEMPLATE>
N/A
<END_BLOCK:USER_PROMPT_TEMPLATE>

## 4.3 Few-Shot Examples
Has_Few_Shot: no
<BEGIN_BLOCK:FEW_SHOT_EXAMPLES>
N/A
<END_BLOCK:FEW_SHOT_EXAMPLES>

# 5. RESULTS

## 5.1 Quantitative Results
Metrics:
- total_findings: {total_findings} (all)
- total_sources: {total_sources} (all)
- total_cost_usd: {total_cost:.4f} (all)
Aggregate_Summary:
- Findings collected: {total_findings}
- Sources referenced: {total_sources}
- Spend: ${total_cost:.4f}

## 5.2 Qualitative Results
Representative_Outputs:
<BEGIN_BLOCK:REPRESENTATIVE_OUTPUTS>
{rep_block}
<END_BLOCK:REPRESENTATIVE_OUTPUTS>

Error_Patterns:
- N/A
- N/A

# 6. ANALYSIS

Interpretation:
- Session status: {_safe_value(detail.get('status'))}
- Completeness score: {_safe_value(results.get('completeness_score'))}
- Confidence score: {_safe_value(results.get('confidence_score'))}

Surprises:
- N/A

Threats_to_Validity:
- Internal: N/A
- External: Findings not audited; relies on upstream sources

# 7. DECISIONS & NEXT STEPS
Decisions:
- N/A

Followup_Experiments:
- Run further iterations if findings are sparse
- N/A

Notes_for_KITTY_Pipeline:
- Session exported from CLI report command
- N/A

# 8. RAW LOG / TRACE (OPTIONAL)
<BEGIN_BLOCK:RAW_LOG>
N/A
<END_BLOCK:RAW_LOG>

</LLM_RESEARCH_OUTPUT>
"""
    return report.strip() + "\n"


def _write_report_file(report: str, session_id: str, output_dir: str) -> Path:
    """Persist report to disk."""
    out_dir_path = Path(output_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)
    path = out_dir_path / f"{session_id}.md"
    path.write_text(report, encoding="utf-8")
    return path


def _open_report(path: Path, editor: Optional[str]) -> None:
    """Open a report file in an editor/pager."""
    cmd = shlex.split(editor) if editor else shlex.split(os.getenv("EDITOR", ""))
    if not cmd:
        cmd = ["nano"]
    cmd.append(str(path))
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        subprocess.run(["less", "-R", str(path)], check=False)


def _export_research_report(
    session_id: str,
    output_dir: str = "Research/exports",
    open_file: bool = True,
    editor: Optional[str] = None,
) -> Path:
    """Fetch session + results, render a template report, save, and optionally open."""
    detail = _get_json(f"{API_BASE}/api/research/sessions/{session_id}")
    results = _get_json(f"{API_BASE}/api/research/sessions/{session_id}/results")

    report = _render_research_report(detail, results)
    path = _write_report_file(report, session_id, output_dir)
    console.print(f"[green]Saved report:[/green] {path}")

    if open_file:
        _open_report(path, editor)

    return path


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
        meta = artifact.get("metadata") or {}
        glb_loc = meta.get("glb_location", "")
        stl_loc = meta.get("stl_location", "")

        console.print(
            f"[cyan]{idx}[/] provider={artifact.get('provider')} "
            f"type={artifact.get('artifactType')} "
            f"url={artifact.get('location')}"
        )
        # Show both formats if available
        if glb_loc:
            console.print(f"    [dim]GLB (preview): {glb_loc}[/dim]")
        if stl_loc:
            console.print(f"    [dim]STL (slicer):  {stl_loc}[/dim]")


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

    # Translate relative artifact path to absolute host path
    # CAD service returns paths like "artifacts/xyz.stl" (relative from container /app)
    # We need to translate to absolute host path like "/Users/Shared/KITTY/artifacts/xyz.stl"
    if location.startswith("artifacts/"):
        host_path = ARTIFACTS_DIR / location[len("artifacts/"):]
    elif location.startswith("storage/artifacts/"):
        # Legacy path format - map storage/artifacts/ to artifacts dir
        host_path = ARTIFACTS_DIR / location[len("storage/artifacts/"):]
    elif location.startswith("/"):
        # Already absolute path
        host_path = Path(location)
    else:
        # Assume relative path from artifacts dir
        host_path = ARTIFACTS_DIR / location

    if not host_path.exists():
        console.print(f"[red]Artifact file not found: {host_path}")
        return

    height_input = typer.prompt(
        "Desired printed height (e.g., 6 in, 150 mm)", default=""
    ).strip()

    payload = {"stl_path": str(host_path), "print_mode": "3d_print"}
    if height_input:
        payload["target_height"] = height_input

    try:
        # Get printer/slicer recommendation from fabrication service
        data = _post_json_with_spinner(
            f"{FABRICATION_API_BASE}/api/fabrication/analyze_model",
            payload,
            "Analyzing model",
        )
        app_name = data.get("slicer_app") or "BambuStudio"
        reasoning = data.get("reasoning")
        if reasoning:
            console.print(f"[dim]{reasoning}[/dim]")

        # Launch slicer locally (fabrication service runs in Docker, can't launch macOS apps)
        import subprocess
        try:
            subprocess.run(
                ["open", "-a", app_name, str(host_path)],
                check=True,
                capture_output=True,
                timeout=10
            )
            console.print(
                f"[green]Launched {app_name} for {host_path.name}[/green]"
            )
        except subprocess.CalledProcessError as e:
            console.print(f"[red]Failed to launch {app_name}: {e.stderr.decode() if e.stderr else str(e)}")
        except subprocess.TimeoutExpired:
            console.print(f"[red]Timeout launching {app_name}")
        except FileNotFoundError:
            console.print(f"[red]{app_name} not found. Please install it first.")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to analyze model: {exc}")


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


def _parse_inline_provider(query: str) -> tuple[str, Optional[str], Optional[str]]:
    """Parse inline provider/model syntax from query.

    Syntax:
        @provider: <query>  - One-off provider override
        #model: <query>     - One-off model override

    Returns:
        Tuple of (cleaned_query, provider, model)
    """
    provider_override = None
    model_override = None

    # Check for @provider: syntax
    provider_match = re.match(r'^@(\w+):\s*(.+)$', query, re.IGNORECASE)
    if provider_match:
        provider_override = provider_match.group(1).lower()
        query = provider_match.group(2)

    # Check for #model: syntax
    model_match = re.match(r'^#([\w-]+):\s*(.+)$', query, re.IGNORECASE)
    if model_match:
        model_override = model_match.group(1).lower()
        query = model_match.group(2)
        # Auto-detect provider from model name
        provider_map = {
            "gpt": "openai",
            "claude": "anthropic",
            "mistral": "mistral",
            "sonar": "perplexity",
            "gemini": "gemini",
        }
        for prefix, prov in provider_map.items():
            if model_override.startswith(prefix):
                provider_override = prov
                break

    return query, provider_override, model_override


def _format_prompt(user_prompt: str, include_refs: bool = False) -> str:
    """Format prompt, optionally including image references.

    Image refs are only included for CAD/generate operations where they're relevant.
    This prevents pollution of tool arguments (e.g., web_search queries) with
    irrelevant image reference data.
    """
    # Only append image refs when explicitly requested (CAD/generate operations)
    if not include_refs:
        return user_prompt

    reference_block = _format_reference_block()
    if not reference_block:
        return user_prompt
    return f"{user_prompt}\n\n{reference_block}"


def _should_include_refs(prompt: str) -> bool:
    """Check if prompt likely involves CAD/image generation that needs refs."""
    prompt_lower = prompt.lower()
    cad_keywords = {
        "cad", "model", "3d", "print", "generate", "create", "design",
        "sculpt", "statue", "figurine", "organic", "mesh", "stl",
        "reference", "using image", "from image", "based on"
    }
    return any(kw in prompt_lower for kw in cad_keywords)


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


@app.command()
def discover(
    action: str = typer.Argument(..., help="Action: scan | status | list | approve | reject"),
    target: Optional[str] = typer.Argument(
        None,
        help="Scan ID (for status) or Device ID (for approve/reject).",
    ),
    methods: Optional[List[str]] = typer.Option(
        None,
        "--method",
        "-m",
        help="Discovery methods to use for scan (mdns, ssdp, bamboo_udp, snapmaker_udp, network_scan).",
    ),
    timeout_seconds: int = typer.Option(
        30,
        "--timeout",
        "-t",
        help="Scan timeout in seconds.",
        min=5,
        max=300,
    ),
    search: Optional[str] = typer.Option(
        None,
        "--search",
        "-q",
        help="Search devices by hostname/model/manufacturer/IP.",
    ),
    device_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-k",
        help="Filter by device type (e.g., printer_3d, esp32, raspberry_pi).",
    ),
    approved: Optional[bool] = typer.Option(
        None,
        "--approved",
        help="Filter by approval status (true/false) when listing.",
    ),
    online: Optional[bool] = typer.Option(
        None,
        "--online",
        help="Filter by online status (true/false) when listing.",
    ),
    manufacturer: Optional[str] = typer.Option(
        None,
        "--manufacturer",
        help="Filter by manufacturer name.",
    ),
    limit: int = typer.Option(
        100,
        "--limit",
        "-l",
        help="Max results to display.",
        min=1,
        max=500,
    ),
    notes: Optional[str] = typer.Option(
        None,
        "--notes",
        help="Optional notes for approve/reject.",
    ),
) -> None:
    """Network discovery helpers."""
    scan_id = target if action == "status" else None
    device_id = target if action in {"approve", "reject"} else None
    _run_discover(
        action,
        scan_id=scan_id,
        device_id=device_id,
        methods=methods,
        timeout_seconds=timeout_seconds,
        search=search,
        device_type=device_type,
        approved=approved,
        online=online,
        manufacturer=manufacturer,
        limit=limit,
        notes=notes,
    )


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


def _run_split_command(
    stl_path: str,
    printer_id: Optional[str] = None,
    *,
    quality: str = "high",
    joint_type: str = "integrated",
    wall_thickness: Optional[float] = None,
    max_parts: Optional[int] = None,
    enable_hollowing: Optional[bool] = None,
    overhang_threshold_deg: Optional[float] = None,
    interactive: bool = True,
) -> None:
    """Segment a mesh for multi-part 3D printing.

    Args:
        stl_path: Path to 3MF or STL file
        printer_id: Target printer for build volume constraints
        quality: Hollowing quality preset (fast/medium/high)
        joint_type: Joint type (integrated/dowel/none)
        wall_thickness: Wall thickness in mm (default: 10.0)
        max_parts: Max parts to generate (0 = auto)
        enable_hollowing: Enable hollowing (default: True)
        overhang_threshold_deg: Overhang angle threshold (default: 30.0)
        interactive: Prompt for confirmation and options
    """
    from pathlib import Path

    # Quality presets
    quality_presets = {
        "fast": {"resolution": 200, "desc": "~10s"},
        "medium": {"resolution": 500, "desc": "~30s"},
        "high": {"resolution": 1000, "desc": "~1-2min"},
    }

    # Validate file exists
    path = Path(stl_path)
    if not path.exists():
        console.print(f"[red]File not found: {stl_path}")
        return

    if not path.suffix.lower() in {".stl", ".3mf"}:
        console.print(f"[yellow]Warning: Expected .stl or .3mf file, got {path.suffix}")

    # First check if segmentation is needed
    console.print(f"\n[cyan]Analyzing mesh: {path.name}[/cyan]")

    check_payload = {"stl_path": str(path.absolute())}
    if printer_id:
        check_payload["printer_id"] = printer_id

    try:
        spinner = Spinner("dots", text=Text("Checking dimensions...", style="cyan"))
        with Live(spinner, console=console, transient=True):
            with _client() as client:
                response = client.post(
                    f"{FABRICATION_BASE}/api/segmentation/check",
                    json=check_payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                check_result = response.json()
    except httpx.RequestError as exc:
        console.print(f"[red]Failed to connect to Fabrication service: {exc}")
        console.print("[dim]Make sure the Fabrication service is running on port 8300[/dim]")
        return
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Check failed: {exc.response.text}")
        return

    # Display check results
    dims = check_result.get("model_dimensions_mm", (0, 0, 0))
    build_vol = check_result.get("build_volume_mm", (250, 250, 250))
    exceeds = check_result.get("exceeds_by_mm", (0, 0, 0))
    needs_seg = check_result.get("needs_segmentation", False)

    console.print(f"\n[bold]Model Dimensions:[/bold] {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    console.print(f"[bold]Build Volume:[/bold] {build_vol[0]:.0f} × {build_vol[1]:.0f} × {build_vol[2]:.0f} mm")

    if not needs_seg:
        console.print("\n[green]✓ Model fits within build volume - no segmentation needed![/green]")
        return

    console.print(f"\n[yellow]Model exceeds build volume by: {exceeds[0]:.1f} × {exceeds[1]:.1f} × {exceeds[2]:.1f} mm[/yellow]")
    console.print(f"[dim]Recommended cuts: {check_result.get('recommended_cuts', 1)}[/dim]")

    # Apply defaults
    final_wall_thickness = wall_thickness if wall_thickness is not None else 10.0
    final_max_parts = max_parts if max_parts is not None else 0  # 0 = auto
    final_enable_hollowing = enable_hollowing if enable_hollowing is not None else True
    final_overhang_threshold = overhang_threshold_deg if overhang_threshold_deg is not None else 30.0
    final_joint_type = joint_type
    final_quality = quality

    # Track custom build volume if user enters one
    custom_build_volume = None
    selected_printer_id = printer_id

    if interactive:
        # Prompt for segmentation
        proceed = console.input("\n[cyan]Proceed with segmentation?[/] [dim](y/n)[/] [[dim]y[/dim]]: ").strip().lower()
        if proceed not in ['', 'y', 'yes']:
            console.print("[dim]Segmentation cancelled[/dim]")
            return

        # Configure segmentation options
        console.print("\n[bold cyan]Configure Segmentation[/bold cyan]")
        console.print("[dim](Press Enter to use defaults)[/dim]\n")

        # Printer selection - fetch available printers
        printers = []
        try:
            with _client() as client:
                response = client.get(f"{FABRICATION_BASE}/api/segmentation/printers", timeout=10.0)
                if response.status_code == 200:
                    printers = response.json()
        except Exception:
            pass  # Will just show custom option if API fails

        console.print("[cyan]Target printer (build volume):[/]")
        printer_options = []
        for i, p in enumerate(printers, start=1):
            vol = p.get("build_volume_mm", (250, 250, 250))
            name = p.get("name", p.get("printer_id", f"Printer {i}"))
            console.print(f"  [dim]{i}.[/] {name} [dim]({vol[0]:.0f}×{vol[1]:.0f}×{vol[2]:.0f} mm)[/]")
            printer_options.append(p)
        custom_idx = len(printers) + 1
        console.print(f"  [dim]{custom_idx}.[/] Custom dimensions [dim](enter your own)[/]")

        default_choice = "1" if printers else str(custom_idx)
        printer_input = console.input(f"[cyan]Printer[/] [[dim]{default_choice}[/dim]]: ").strip()

        if not printer_input:
            printer_input = default_choice

        try:
            choice = int(printer_input)
            if 1 <= choice <= len(printers):
                selected_printer_id = printer_options[choice - 1].get("printer_id")
                vol = printer_options[choice - 1].get("build_volume_mm", (250, 250, 250))
                console.print(f"[dim]Selected: {printer_options[choice - 1].get('name')} ({vol[0]:.0f}×{vol[1]:.0f}×{vol[2]:.0f} mm)[/dim]")
            else:
                # Custom dimensions
                console.print("\n[cyan]Enter custom build volume (mm):[/]")
                x_input = console.input("  [cyan]X (width)[/] [[dim]250[/dim]]: ").strip()
                y_input = console.input("  [cyan]Y (depth)[/] [[dim]250[/dim]]: ").strip()
                z_input = console.input("  [cyan]Z (height)[/] [[dim]250[/dim]]: ").strip()
                custom_build_volume = (
                    float(x_input) if x_input else 250.0,
                    float(y_input) if y_input else 250.0,
                    float(z_input) if z_input else 250.0,
                )
                console.print(f"[dim]Custom volume: {custom_build_volume[0]:.0f}×{custom_build_volume[1]:.0f}×{custom_build_volume[2]:.0f} mm[/dim]")
                selected_printer_id = None  # Clear printer_id when using custom
        except ValueError:
            console.print("[yellow]Invalid selection, using default printer[/yellow]")

        # Quality selector
        console.print("[cyan]Quality presets:[/]")
        console.print("  [dim]1.[/] Fast   [dim](200 voxels, ~10s)[/]")
        console.print("  [dim]2.[/] Medium [dim](500 voxels, ~30s)[/]")
        console.print("  [dim]3.[/] High   [dim](1000 voxels, ~1-2min)[/]")
        quality_input = console.input("[cyan]Quality[/] [[dim]3 (high)[/dim]]: ").strip()
        if quality_input == "1":
            final_quality = "fast"
        elif quality_input == "2":
            final_quality = "medium"
        else:
            final_quality = "high"

        # Joint type selector
        console.print("\n[cyan]Joint types:[/]")
        console.print("  [dim]1.[/] Integrated [dim](printed pins & holes - no hardware)[/]")
        console.print("  [dim]2.[/] Dowel      [dim](holes for external pins)[/]")
        console.print("  [dim]3.[/] None       [dim](manual alignment)[/]")
        joint_input = console.input("[cyan]Joint type[/] [[dim]1 (integrated)[/dim]]: ").strip()
        if joint_input == "2":
            final_joint_type = "dowel"
        elif joint_input == "3":
            final_joint_type = "none"
        else:
            final_joint_type = "integrated"

        wall_input = console.input("[cyan]Wall thickness (mm)[/] [[dim]10.0[/dim]]: ").strip()
        final_wall_thickness = float(wall_input) if wall_input else 10.0

        hollow_input = console.input("[cyan]Enable hollowing?[/] [dim](y/n)[/] [[dim]y[/dim]]: ").strip().lower()
        final_enable_hollowing = hollow_input not in ['n', 'no']

        max_parts_input = console.input("[cyan]Maximum parts[/] [[dim]0 (auto)[/dim]]: ").strip()
        final_max_parts = int(max_parts_input) if max_parts_input else 0

    # Get hollowing resolution from quality preset
    hollowing_resolution = quality_presets.get(final_quality, quality_presets["high"])["resolution"]

    # Run segmentation
    segment_payload = {
        "stl_path": str(path.absolute()),
        "wall_thickness_mm": final_wall_thickness,
        "enable_hollowing": final_enable_hollowing,
        "max_parts": final_max_parts,
        "joint_type": final_joint_type,
        "hollowing_resolution": hollowing_resolution,
        "overhang_threshold_deg": final_overhang_threshold,
    }
    if selected_printer_id:
        segment_payload["printer_id"] = selected_printer_id
    if custom_build_volume:
        segment_payload["custom_build_volume"] = list(custom_build_volume)

    console.print("\n[cyan]Segmenting mesh...[/cyan]")

    try:
        spinner = Spinner("dots", text=Text("This may take a few minutes...", style="cyan"))
        with Live(spinner, console=console, transient=True):
            with _client() as client:
                response = client.post(
                    f"{FABRICATION_BASE}/api/segmentation/segment",
                    json=segment_payload,
                    timeout=300.0,  # 5 minute timeout for large models
                )
                response.raise_for_status()
                result = response.json()
    except httpx.RequestError as exc:
        console.print(f"[red]Segmentation failed: {exc}")
        return
    except httpx.HTTPStatusError as exc:
        console.print(f"[red]Segmentation error: {exc.response.text}")
        return

    if not result.get("success"):
        console.print(f"[red]Segmentation failed: {result.get('error', 'Unknown error')}")
        return

    # Display results
    num_parts = result.get("num_parts", 0)
    parts = result.get("parts", [])

    console.print(f"\n[green]✓ Segmentation complete! Created {num_parts} parts[/green]\n")

    # Parts table
    table = Table(title="Segmented Parts", show_lines=False)
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Name")
    table.add_column("Dimensions (mm)")
    table.add_column("Volume (cm³)")
    table.add_column("Supports")

    for part in parts:
        dims = part.get("dimensions_mm", (0, 0, 0))
        table.add_row(
            str(part.get("index", 0) + 1),
            part.get("name", ""),
            f"{dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f}",
            f"{part.get('volume_cm3', 0):.1f}",
            "Yes" if part.get("requires_supports") else "No",
        )

    console.print(table)

    # Hardware requirements
    hardware = result.get("hardware_required", {})
    if hardware:
        console.print("\n[bold]Hardware Required:[/bold]")
        if "dowel_pins" in hardware:
            dp = hardware["dowel_pins"]
            console.print(f"  • Dowel pins: {dp.get('quantity', 0)}× Ø{dp.get('diameter_mm', 4)}mm × {dp.get('length_mm', 20)}mm")
        if "adhesive" in hardware:
            adh = hardware["adhesive"]
            console.print(f"  • Adhesive: {adh.get('type', 'CA glue')} (~{adh.get('estimated_ml', 0)}ml)")

    # Output paths
    output_3mf = result.get("combined_3mf_path")
    if output_3mf:
        console.print(f"\n[bold]Output:[/bold] {output_3mf}")

    # Assembly notes
    assembly_notes = result.get("assembly_notes", "")
    if assembly_notes:
        console.print("\n[dim]Assembly instructions included in 3MF file metadata[/dim]")


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
    stream: Optional[bool] = typer.Option(
        None,
        "--stream/--no-stream",
        help="Enable streaming mode with real-time thinking traces (requires Ollama reasoner).",
    ),
) -> None:
    """Send a conversational message with intelligent agent reasoning.

    Models are automatically managed by the Model Manager - no need to specify.

    Supports inline provider/model override:
        @openai: <query>           - Use OpenAI for this query
        #gpt-4o-mini: <query>      - Use specific model (auto-detects provider)
    """
    text = " ".join(message)

    # Parse inline provider/model syntax
    cleaned_text, provider_override, model_override = _parse_inline_provider(text)

    # Only include image refs for CAD/generate-related prompts
    formatted_prompt = _format_prompt(cleaned_text, include_refs=_should_include_refs(cleaned_text))
    payload: Dict[str, Any] = {
        "conversationId": state.conversation_id,
        "userId": state.user_id,
        "intent": "chat.prompt",
        "prompt": formatted_prompt,
    }

    # Add provider/model from state or inline override
    active_provider = provider_override or state.provider
    active_model = model_override or state.model
    if active_provider:
        payload["provider"] = active_provider
    if active_model:
        payload["model"] = active_model

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

    # Determine if streaming should be used
    use_streaming = stream if stream is not None else False

    try:
        if use_streaming:
            # Use streaming endpoint with real-time thinking traces
            full_output, routing_metadata = _request_with_streaming(
                f"{API_BASE}/api/query/stream",
                payload,
                "KITTY is thinking",
            )
        else:
            # Use traditional non-streaming endpoint with continuation support
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
    return "organic"


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


@app.command()
def segment(
    mesh_path: str = typer.Argument(..., help="Path to 3MF or STL file to segment"),
    printer_id: Optional[str] = typer.Option(
        None, "--printer", "-p", help="Target printer ID for build volume"
    ),
    quality: str = typer.Option(
        "high",
        "--quality",
        "-q",
        help="Quality preset: fast (200 voxels), medium (500), high (1000)",
    ),
    joint_type: str = typer.Option(
        "integrated",
        "--joint-type",
        "-j",
        help="Joint type: integrated (printed pins), dowel (external pins), none",
    ),
    wall_thickness: float = typer.Option(
        10.0, "--wall-thickness", "-w", help="Wall thickness for hollowing (mm)"
    ),
    max_parts: int = typer.Option(
        0, "--max-parts", "-m", help="Maximum parts to generate (0 = auto-calculate)"
    ),
    no_hollowing: bool = typer.Option(
        False, "--no-hollowing", help="Disable mesh hollowing"
    ),
    overhang_threshold: float = typer.Option(
        30.0,
        "--overhang-threshold",
        "-o",
        help="Overhang angle threshold in degrees (30=strict, 45=standard FDM)",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip confirmation prompts"
    ),
) -> None:
    """Segment large 3D models for multi-part printing.

    Splits oversized meshes into parts that fit your printer's build volume,
    with automatic hollowing and alignment joints.

    Examples:
        kitt segment model.3mf --printer bamboo_h2d
        kitt segment duck.stl -q high -j integrated --yes
        kitt segment large_model.3mf -m 0 -w 10.0 -y
    """
    # Validate quality preset
    if quality not in ("fast", "medium", "high"):
        console.print(f"[red]Invalid quality preset '{quality}'. Use: fast, medium, high")
        raise typer.Exit(1)

    # Validate joint type
    if joint_type not in ("integrated", "dowel", "none"):
        console.print(f"[red]Invalid joint type '{joint_type}'. Use: integrated, dowel, none")
        raise typer.Exit(1)

    _run_split_command(
        mesh_path,
        printer_id,
        quality=quality,
        joint_type=joint_type,
        wall_thickness=wall_thickness,
        max_parts=max_parts,
        enable_hollowing=not no_hollowing,
        overhang_threshold_deg=overhang_threshold,
        interactive=not yes,
    )


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


def _format_research_sessions_table(sessions: List[Dict[str, Any]]) -> Table:
    """Format research sessions as a rich table."""
    table = Table(title="Research Sessions", show_lines=False, header_style="bold cyan")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Session ID", style="green")
    table.add_column("Query", overflow="fold")
    table.add_column("Status")
    table.add_column("Strategy")
    table.add_column("Iterations", justify="right")
    table.add_column("Findings", justify="right")
    table.add_column("Budget", justify="right")
    table.add_column("Created")

    for idx, session in enumerate(sessions, 1):
        # Show full session ID for clarity and uniqueness
        session_id = session.get("session_id", "")
        query = session.get("query", "")[:40]
        status = session.get("status", "unknown")
        # Get strategy from config object
        config = session.get("config", {})
        strategy = config.get("strategy", "N/A") if config else "N/A"
        # Use total_iterations and total_findings from API
        iterations = str(session.get("total_iterations", 0))
        findings_count = str(session.get("total_findings", 0))
        budget_used = f"${float(session.get('total_cost_usd', 0)):.2f}"
        created = _format_history_time(session.get("created_at"))

        # Color status
        status_color = {
            "active": "green",
            "completed": "blue",
            "failed": "red",
            "paused": "yellow"
        }.get(status, "white")

        table.add_row(
            str(idx),
            session_id,
            query,
            f"[{status_color}]{status}[/{status_color}]",
            strategy,
            iterations,
            findings_count,
            budget_used,
            created
        )

    return table


def _load_research_results(session_id: str, quiet: bool = False) -> Optional[Dict[str, Any]]:
    """Load full research results; return None on failure."""
    try:
        return _get_json(f"{API_BASE}/api/research/sessions/{session_id}/results")
    except Exception as exc:  # noqa: BLE001
        if not quiet:
            console.print(f"[yellow]Could not load full results for {session_id}: {exc}[/yellow]")
        return None


def _render_research_results(session_id: str, results: Dict[str, Any], truncate: int = 800, show_findings: bool = True) -> None:
    """Render synthesis, sources, and findings from /results."""
    if not results:
        return

    # Metrics panel
    metrics = Table.grid(padding=(0, 2))
    metrics.add_column(style="cyan")
    metrics.add_column()
    metrics.add_row("Status:", results.get("status", "unknown"))
    metrics.add_row("Findings:", str(results.get("total_findings", 0)))
    metrics.add_row("Sources:", str(results.get("total_sources", 0)))
    metrics.add_row("Cost:", f"${float(results.get('total_cost_usd', 0) or 0):.2f}")

    completeness = results.get("completeness_score")
    confidence = results.get("confidence_score")
    if completeness is not None:
        metrics.add_row("Completeness:", f"{float(completeness):.2f}")
    if confidence is not None:
        metrics.add_row("Confidence:", f"{float(confidence):.2f}")

    console.print(Panel(metrics, title="[bold]Results Summary[/bold]", border_style="cyan"))

    # Synthesis
    synthesis = results.get("final_synthesis")
    if synthesis:
        console.print(Panel(
            _truncate_text(synthesis, truncate),
            title="[bold green]Synthesis[/bold green]",
            border_style="green"
        ))

    # Sources (flattened from findings)
    sources = []
    seen_sources = set()
    for finding in results.get("findings", []):
        iteration = finding.get("iteration")
        for src in finding.get("sources", []) or []:
            if not isinstance(src, dict):
                continue
            url = src.get("url") or src.get("source_url") or ""
            title = src.get("title") or src.get("source_title") or url or "Unknown source"
            key = (title, url)
            if key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "title": title,
                "url": url,
                "iteration": iteration,
            })

    if sources:
        src_table = Table(title="Sources", show_lines=False, header_style="bold cyan")
        src_table.add_column("#", justify="right", style="cyan")
        src_table.add_column("Title", overflow="fold")
        src_table.add_column("URL", overflow="fold")
        src_table.add_column("Iter", justify="right")
        for idx, src in enumerate(sources, 1):
            src_table.add_row(
                str(idx),
                src["title"],
                src["url"] or "—",
                str(src.get("iteration", "—"))
            )
        console.print(src_table)

    # Findings
    findings = results.get("findings", [])
    if show_findings and findings:
        console.print(f"\n[bold cyan]Findings ({len(findings)}):[/bold cyan]\n")
        for idx, finding in enumerate(findings, 1):
            content = finding.get("content", "") or ""
            confidence = finding.get("confidence", 0)
            iteration = finding.get("iteration", 0)
            ftype = finding.get("finding_type", "unknown")
            header = f"Finding #{idx} | Type: {ftype} | Confidence: {float(confidence):.2f} | Iteration: {iteration}"
            console.print(Panel(
                _truncate_text(content, truncate),
                title=header,
                border_style="green",
                expand=False
            ))
            console.print()


def _display_session_detail(session_id: str, full: bool = True, truncate: int = 800, show_findings: bool = True) -> None:
    """Display detailed research session information."""
    try:
        data = _get_json(f"{API_BASE}/api/research/sessions/{session_id}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to fetch session: {exc}")
        raise typer.Exit(1) from exc

    session = data
    if not session or not session.get("session_id"):
        console.print(f"[red]Session {session_id} not found")
        raise typer.Exit(1)

    # Header
    console.print(Panel.fit(
        f"[bold cyan]Research Session: {session_id}[/bold cyan]\n"
        f"[dim]{session.get('query', 'No query')}[/dim]",
        border_style="cyan"
    ))

    # Status panel
    status_table = Table.grid(padding=(0, 2))
    status_table.add_column(style="cyan")
    status_table.add_column()

    status_table.add_row("Status:", session.get("status", "unknown"))
    # Get strategy from config object, matching the list table format
    config = session.get("config", {})
    strategy = config.get("strategy", "N/A") if config else "N/A"
    status_table.add_row("Strategy:", strategy)
    # Use total_iterations instead of current_iteration
    total_iters = session.get('total_iterations', 0)
    max_iters = config.get('max_iterations', 15) if config else 15
    status_table.add_row("Iteration:", f"{total_iters}/{max_iters}")
    status_table.add_row("Budget:", f"${float(session.get('total_cost_usd', 0)):.2f} / ${float(session.get('budget_remaining', 0)):.2f} remaining")
    status_table.add_row("Ext. Calls:", f"{session.get('external_calls_used', 0)}/{session.get('external_calls_remaining', 0) + session.get('external_calls_used', 0)}")

    console.print(Panel(status_table, title="[bold]Session Info", border_style="green"))

    # Hint if running local-only (no external calls allowed)
    if session.get('external_calls_used', 0) == 0 and session.get('external_calls_remaining', 0) == 0:
        console.print("[yellow]Note: External calls are disabled; enable paid tools or raise budget to use web providers.[/yellow]")

    results = _load_research_results(session_id, quiet=not full)
    if results and full:
        _render_research_results(session_id, results, truncate=truncate, show_findings=show_findings)
        return

    # Fetch and display detailed findings
    total_findings = session.get("total_findings", 0)
    total_sources = session.get("total_sources", 0)

    if total_findings > 0:
        try:
            findings_data = _get_json(f"{API_BASE}/api/research/sessions/{session_id}/findings")
            findings = findings_data.get("findings", [])

            console.print(f"\n[bold cyan]Research Findings ({len(findings)}):[/bold cyan]\n")

            for idx, finding in enumerate(findings, 1):
                content = finding.get("content", "")
                confidence = finding.get("confidence", 0)
                iteration = finding.get("iteration", 0)
                finding_type = finding.get("finding_type", "unknown")

                # Create a panel for each finding
                finding_header = f"Finding #{idx} | Type: {finding_type} | Confidence: {confidence:.2f} | Iteration: {iteration}"

                # Truncate very long content for display
                display_content = content
                if len(content) > 1500:
                    display_content = content[:1500] + "\n\n[dim]... (content truncated, see full details in web interface)[/dim]"

                console.print(Panel(
                    display_content,
                    title=finding_header,
                    border_style="green",
                    expand=False
                ))
                console.print()  # Add spacing between findings

        except Exception as exc:  # noqa: BLE001
            console.print(f"[yellow]Could not load detailed findings: {exc}[/yellow]")
            console.print(f"[dim]Summary: {total_findings} findings, {total_sources} sources[/dim]\n")
    else:
        console.print("[yellow]No findings yet[/yellow]\n")

    # Quality metrics
    quality_scores = session.get("quality_scores", [])
    if quality_scores:
        latest_quality = quality_scores[-1]
        console.print(f"[bold]Latest Quality Score:[/bold] {latest_quality:.2f}")

    # Saturation
    saturation = session.get("saturation_status")
    if saturation:
        is_saturated = saturation.get("is_saturated", False)
        novelty_rate = saturation.get("novelty_rate", 0)
        sat_color = "yellow" if is_saturated else "green"
        console.print(f"[bold]Saturation:[/bold] [{sat_color}]{'Yes' if is_saturated else 'No'}[/{sat_color}] (novelty: {novelty_rate:.2%})")

    # Knowledge gaps
    gaps = session.get("knowledge_gaps", [])
    if gaps:
        console.print(f"\n[bold yellow]Knowledge Gaps ({len(gaps)}):[/bold yellow]")
        for gap in gaps[:5]:
            console.print(f"  - {gap.get('description', 'Unknown')}")

    # Models used
    models = session.get("models_used", [])
    if models:
        console.print(f"\n[bold]Models Used:[/bold] {', '.join(models)}")

    # Final answer
    final_answer = session.get("final_answer")
    if final_answer:
        console.print(Panel(
            final_answer,
            title="[bold green]Final Answer",
            border_style="green"
        ))


def _stream_research_progress(session_id: str, user_id: str, query: str, render_results: bool = True, truncate: int = 800) -> None:
    """Stream research progress with real-time updates; fall back to polling if WS fails."""
    import json
    import asyncio
    import websockets

    console.print(Panel.fit(
        f"[bold cyan]Starting Autonomous Research[/bold cyan]\n"
        f"[dim]{query}[/dim]",
        border_style="cyan"
    ))

    async def stream():
        # Use WebSocket to stream research progress
        ws_url = f"ws://{API_BASE.replace('http://', '').replace('https://', '')}/api/research/sessions/{session_id}/stream"

        async def poll_status_fallback(reason: Optional[str] = None) -> None:
            """Poll session status when streaming is unavailable."""
            if reason:
                console.print(f"\n[yellow]WebSocket stream unavailable ({reason}). Falling back to HTTP polling...[/yellow]")
            poll_interval = 5

            with Live(console=console, refresh_per_second=1) as live:
                while True:
                    try:
                        session = await asyncio.to_thread(
                            _get_json,
                            f"{API_BASE}/api/research/sessions/{session_id}"
                        )
                    except Exception as exc:  # noqa: BLE001
                        console.print(f"[red]Failed to poll session status: {exc}[/red]")
                        return

                    status = (session.get("status") or "unknown").lower()
                    config = session.get("config") or {}
                    max_iters = config.get("max_iterations") or config.get("max_iters") or "—"

                    progress_table = Table.grid(padding=(0, 2))
                    progress_table.add_column(style="cyan")
                    progress_table.add_column()

                    progress_table.add_row("Status:", status.capitalize())
                    progress_table.add_row("Iteration:", f"{session.get('total_iterations', 0)}/{max_iters}")
                    progress_table.add_row("Findings:", str(session.get("total_findings", 0)))
                    progress_table.add_row("Cost:", f"${float(session.get('total_cost_usd', 0) or 0):.2f}")

                    saturation = session.get("saturation_status") or {}
                    if saturation:
                        is_sat = saturation.get("is_saturated", False)
                        novelty = saturation.get("novelty_rate")
                        novelty_text = f" (novelty {novelty:.2%})" if isinstance(novelty, (int, float)) else ""
                        progress_table.add_row(
                            "Saturation:",
                            f"{'🟡' if is_sat else '🟢'} {'Yes' if is_sat else 'No'}{novelty_text}"
                        )

                    live.update(Panel(
                        progress_table,
                        title="[bold cyan]Research Status (polling)[/bold cyan]",
                        border_style="cyan"
                    ))

                    if status in {"completed", "failed", "paused"}:
                        color = "green" if status == "completed" else "red" if status == "failed" else "yellow"
                        console.print(f"\n[{color}]{status.capitalize()}[/] – check /session {session_id} for details\n")
                        if status == "completed" and render_results:
                            results = _load_research_results(session_id, quiet=True)
                            if results:
                                _render_research_results(session_id, results, truncate=truncate)
                        return

                    await asyncio.sleep(poll_interval)

        try:
            # Use open_timeout for connection establishment (websockets 12.0+ API)
            # The stream itself can run indefinitely
            async with websockets.connect(
                ws_url,
                open_timeout=30,
                ping_interval=None,  # disable client keepalive pings; some proxies drop them
                ping_timeout=None,
            ) as websocket:
                with Live(console=console, refresh_per_second=2) as live:
                    current_iteration = 0
                    findings_count = 0

                    async for message in websocket:
                        data = json.loads(message)
                        msg_type = data.get("type")

                        if msg_type == "progress":
                            # Update live display
                            node = data.get("node", "")
                            iteration = data.get("iteration", 0)
                            findings_count = data.get("findings_count", 0)
                            saturation = data.get("saturation", {})

                            if iteration > current_iteration:
                                current_iteration = iteration

                            # Build progress table
                            progress_table = Table.grid(padding=(0, 2))
                            progress_table.add_column(style="cyan")
                            progress_table.add_column()

                            progress_table.add_row("Current Node:", f"[green]{node}[/green]")
                            progress_table.add_row("Iteration:", f"{iteration}")
                            progress_table.add_row("Findings:", f"{findings_count}")

                            if saturation:
                                is_saturated = saturation.get("is_saturated", False)
                                sat_emoji = "🟡" if is_saturated else "🟢"
                                progress_table.add_row("Saturation:", f"{sat_emoji} {'Yes' if is_saturated else 'No'}")

                            panel = Panel(
                                progress_table,
                                title=f"[bold cyan]Research in Progress...",
                                border_style="cyan"
                            )
                            live.update(panel)

                        elif msg_type == "complete":
                            console.print("\n[bold green]✓ Research Complete![/bold green]")
                            console.print(f"[dim]{data.get('message', '')}[/dim]\n")
                            break

                        elif msg_type == "error":
                            console.print(f"\n[bold red]✗ Research Failed[/bold red]")
                            console.print(f"[red]{data.get('error', 'Unknown error')}[/red]\n")
                            break

        except Exception as exc:
            await poll_status_fallback(str(exc))

        # After streaming completes, try to show full results
        if render_results:
            results = _load_research_results(session_id, quiet=True)
            if results:
                _render_research_results(session_id, results, truncate=truncate)

    # Run async stream
    try:
        asyncio.run(stream())
    except Exception as exc:
        console.print(f"[red]Failed to stream: {exc}[/red]")
        console.print(f"[yellow]Session may still be running. Check with /session {session_id}[/yellow]\n")


def _start_research(query: str, config: Optional[Dict[str, Any]] = None) -> str:
    """Start autonomous research session."""
    payload = {
        "user_id": state.user_id,
        "query": query,
        "config": config or {}
    }

    try:
        data = _post_json(f"{API_BASE}/api/research/sessions", payload)
        session_id = data.get("session_id")
        if not session_id:
            console.print("[red]Failed to create research session")
            raise typer.Exit(1)

        console.print(f"[green]Created session: {session_id}[/green]")
        return session_id
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to start research: {exc}")
        raise typer.Exit(1) from exc


def _list_research_sessions(limit: int = 10) -> List[Dict[str, Any]]:
    """List recent research sessions and return the list."""
    try:
        data = _get_json(f"{API_BASE}/api/research/sessions?limit={limit}&user_id={state.user_id}")
        sessions = data.get("sessions", [])

        if not sessions:
            console.print("[yellow]No research sessions found[/yellow]")
            console.print("[dim]Start one with /research <query>[/dim]\n")
            return []

        table = _format_research_sessions_table(sessions)
        console.print(table)
        console.print(f"\n[dim]View details with /session <id>[/dim]")
        console.print(f"[dim]Stream progress with /stream <id>[/dim]")
        console.print(f"[dim]Or type the row number to view that session[/dim]\n")

        return sessions

    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list sessions: {exc}")
        raise typer.Exit(1) from exc


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
def research(
    query: str = typer.Argument(..., help="Research query to investigate"),
    no_config: bool = typer.Option(False, "--no-config", help="Skip configuration prompts, use defaults"),
    use_debate: bool = typer.Option(False, "--debate/--no-debate", help="Use multi-model debate for synthesis when enabled"),
) -> None:
    """Start an autonomous research session with interactive configuration.

    Examples:
        kitty-cli research "What are the latest advances in 3D printing?"
        kitty-cli research "Compare PETG vs ABS materials" --no-config
    """
    # Show configuration prompts unless --no-config is specified
    if not no_config:
        console.print("\n[bold cyan]Configure Research Session[/bold cyan]")
        console.print("[dim](Press Enter to use defaults)[/dim]\n")

        # Strategy selection
        strategy_input = typer.prompt(
            "Strategy (hybrid/breadth_first/depth_first/task_decomposition)",
            default="hybrid",
            show_default=True
        )

        # Max iterations
        max_iterations_input = typer.prompt(
            "Max iterations",
            default="10",
            show_default=True
        )
        try:
            max_iterations = int(max_iterations_input)
        except ValueError:
            console.print("[yellow]Invalid input, using default: 10[/yellow]")
            max_iterations = 10

        # Max cost
        max_cost_input = typer.prompt(
            "Max cost USD",
            default="2.0",
            show_default=True
        )
        try:
            max_cost = float(max_cost_input)
        except ValueError:
            console.print("[yellow]Invalid input, using default: 2.0[/yellow]")
            max_cost = 2.0

        # Enable paid tools
        enable_paid_input = typer.prompt(
            "Enable paid tools (Perplexity)? (y/n)",
            default="n",
            show_default=True
        )
        enable_paid = enable_paid_input.lower() in ['y', 'yes']

        # Enable hierarchical research
        enable_hierarchical_input = typer.prompt(
            "Enable hierarchical research (multi-stage synthesis)? (y/n)",
            default="n",
            show_default=True
        )
        enable_hierarchical = enable_hierarchical_input.lower() in ['y', 'yes']

        # Enable debate
        use_debate = typer.prompt(
            "Enable debate (multi-model synthesis)? (y/n)",
            default="n",
            show_default=True
        ).lower() in ["y", "yes"]

        # If hierarchical, prompt for sub-question limits
        max_sub_questions = 5
        if enable_hierarchical:
            max_sub_input = typer.prompt(
                "Max sub-questions (2-5)",
                default="5",
                show_default=True
            )
            try:
                max_sub_questions = min(5, max(2, int(max_sub_input)))
            except ValueError:
                console.print("[yellow]Invalid input, using default: 5[/yellow]")
                max_sub_questions = 5

        console.print()
    else:
        # Use defaults
        strategy_input = "hybrid"
        max_iterations = 10
        max_cost = 2.0
        enable_paid = False
        enable_hierarchical = False
        max_sub_questions = 5
        # use_debate remains from option default

    # Build config
    config = {
        "strategy": strategy_input,
        "max_iterations": max_iterations,
        "max_cost_usd": max_cost,
        "use_debate": use_debate,
    }

    # Add base_priority if paid tools enabled (sets priority >= 0.7 to use Perplexity)
    if enable_paid:
        config["base_priority"] = 0.7
        console.print("[yellow]✓ Paid tools enabled - research will use Perplexity when beneficial[/yellow]")

    # Add hierarchical config if enabled
    if enable_hierarchical:
        config["enable_hierarchical"] = True
        config["max_sub_questions"] = max_sub_questions
        config["min_sub_questions"] = 2
        config["sub_question_min_iterations"] = 2
        config["sub_question_max_iterations"] = 5
        console.print(f"[cyan]✓ Hierarchical research enabled - will decompose into {max_sub_questions} sub-questions[/cyan]")

    session_id = _start_research(query, config)

    # Always stream by default
    _stream_research_progress(session_id, state.user_id, query)
    console.print(f"\n[dim]View details: kitty-cli research-session {session_id}[/dim]\n")


@app.command(name="research-sessions")
def research_sessions(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of sessions to show"),
) -> None:
    """List recent research sessions.

    Examples:
        kitty-cli research-sessions
        kitty-cli research-sessions --limit 20
    """
    _list_research_sessions(limit=limit)


@app.command(name="research-session")
def research_session(
    session_id: str = typer.Argument(..., help="Research session ID"),
    full: bool = typer.Option(True, "--full/--no-full", help="Show synthesis/sources/findings from /results"),
    truncate: int = typer.Option(800, "--truncate", "-t", help="Character limit for long sections (0 = no limit)"),
    show_findings: bool = typer.Option(True, "--findings/--no-findings", help="Show findings body content"),
) -> None:
    """View detailed information about a research session.

    Examples:
        kitty-cli research-session d99a3593-5710-4297-baf3-9e4c017adf56
    """
    _display_session_detail(session_id, full=full, truncate=truncate, show_findings=show_findings)


@app.command(name="research-stream")
def research_stream(
    session_id: str = typer.Argument(..., help="Research session ID to stream"),
) -> None:
    """Stream real-time progress of an active research session.

    Examples:
        kitty-cli research-stream d99a3593-5710-4297-baf3-9e4c017adf56
    """
    try:
        data = _get_json(f"{API_BASE}/api/research/sessions/{session_id}")
        session = data
        query = session.get("query", "Research session")
        _stream_research_progress(session_id, state.user_id, query)
    except Exception as exc:
        console.print(f"[red]Failed to stream session: {exc}")
        raise typer.Exit(1) from exc


# ---------------------------------------------------------------------------
# Autonomy Calendar (schedules)
# ---------------------------------------------------------------------------


def _calendar_list(user_id: str) -> List[Dict[str, Any]]:
    try:
        data = _get_json(f"{API_BASE}/api/autonomy/calendar/schedules?user_id={quote_plus(user_id)}")
        schedules = data if isinstance(data, list) else data.get("schedules", [])
        if not schedules:
            console.print("[yellow]No schedules found[/yellow]")
            return []
        table = Table(title="Autonomy Schedules", show_lines=False, header_style="bold cyan")
        table.add_column("ID", overflow="fold")
        table.add_column("Job", overflow="fold")
        table.add_column("Type")
        table.add_column("Cron/NL", overflow="fold")
        table.add_column("Enabled")
        table.add_column("Next")
        for s in schedules:
            table.add_row(
                s.get("id", ""),
                s.get("job_name", ""),
                s.get("job_type", ""),
                s.get("natural_language_schedule") or s.get("cron_expression") or "",
                "yes" if s.get("enabled") else "no",
                s.get("next_execution_at") or "—",
            )
        console.print(table)
        return schedules
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to list schedules: {exc}")
        raise typer.Exit(1) from exc


def _calendar_create(
    user_id: str,
    job_name: str,
    job_type: str,
    nl: Optional[str],
    cron: Optional[str],
    budget: Optional[float],
    priority: int,
    enabled: bool,
) -> None:
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "job_name": job_name,
        "job_type": job_type,
        "natural_language_schedule": nl,
        "cron_expression": cron,
        "budget_limit_usd": budget,
        "priority": priority,
        "enabled": enabled,
    }
    try:
        data = _post_json(f"{API_BASE}/api/autonomy/calendar/schedules", payload)
        console.print(f"[green]Created schedule:[/green] {data.get('id')}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to create schedule: {exc}")
        raise typer.Exit(1) from exc


def _calendar_delete(schedule_id: str) -> None:
    try:
        with _client() as client:
            resp = client.delete(f"{API_BASE}/api/autonomy/calendar/schedules/{schedule_id}")
            resp.raise_for_status()
        console.print(f"[green]Deleted schedule:[/green] {schedule_id}")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to delete schedule: {exc}")
        raise typer.Exit(1) from exc


@app.command(name="calendar")
def calendar_cmd(
    action: str = typer.Argument("list", help="Action: list | create | delete"),
    schedule_id: Optional[str] = typer.Argument(None, help="Schedule ID (for delete)"),
    job_name: Optional[str] = typer.Option(None, "--name", "-n", help="Job name (create)"),
    job_type: str = typer.Option("research", "--type", "-t", help="Job type"),
    nl: Optional[str] = typer.Option(None, "--nl", help="Natural language schedule, e.g., 'every monday at 5'"),
    cron: Optional[str] = typer.Option(None, "--cron", help="Cron expression, e.g., '0 5 * * 1'"),
    budget: Optional[float] = typer.Option(None, "--budget", help="Budget limit per run (USD)"),
    priority: int = typer.Option(5, "--priority", "-p", min=1, max=10, help="Priority 1-10"),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable the schedule"),
    user_id: str = typer.Option(state.user_id, "--user", "-u", help="User ID"),
) -> None:
    """Manage autonomy calendar schedules."""
    action = action.lower()
    if action == "list":
        _calendar_list(user_id=user_id)
    elif action == "create":
        if not job_name:
            console.print("[red]--name is required for create[/red]")
            raise typer.Exit(1)
        if not nl and not cron:
            console.print("[yellow]Provide --nl or --cron (natural language or cron expression)[/yellow]")
            raise typer.Exit(1)
        _calendar_create(
            user_id=user_id,
            job_name=job_name,
            job_type=job_type,
            nl=nl,
            cron=cron,
            budget=budget,
            priority=priority,
            enabled=enable,
        )
    elif action == "delete":
        if not schedule_id:
            console.print("[red]schedule_id required for delete[/red]")
            raise typer.Exit(1)
        _calendar_delete(schedule_id)
    else:
        console.print("[red]Unknown action. Use list | create | delete[/red]")
        raise typer.Exit(1)


@app.command(name="report")
def research_report(
    session_id: str = typer.Argument(..., help="Research session ID to export"),
    output_dir: str = typer.Option("Research/exports", "--output-dir", "-o", help="Directory to save the report"),
    open_file: bool = typer.Option(True, "--open/--no-open", help="Open in editor after export"),
    editor: Optional[str] = typer.Option(None, "--editor", "-e", help="Editor command (default: $EDITOR, fallback nano/less)"),
) -> None:
    """Export a research session to the GPTOSS template and optionally open it."""
    try:
        _export_research_report(session_id, output_dir=output_dir, open_file=open_file, editor=editor)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Failed to export report: {exc}")
        raise typer.Exit(1) from exc


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
    console.print("\n[bold]Research Pipeline:[/bold]")
    console.print("  [cyan]/research <query>[/cyan]   - Start autonomous research with real-time streaming")
    console.print("  [cyan]/sessions [limit][/cyan]   - List all research sessions")
    console.print("  [cyan]/session <id>[/cyan]       - View detailed session info and metrics")
    console.print("  [cyan]/stream <id>[/cyan]        - Stream progress of active research session")
    console.print("  [cyan]/report <id>[/cyan]        - Export & open full report (GPTOSS template)")

    console.print("\n[bold]Conversational AI:[/bold]")
    console.print("  [cyan]/verbosity <1-5>[/cyan]  - Set response detail level")
    console.print("  [cyan]/provider <name>[/cyan]  - Select LLM provider (openai, anthropic, mistral, gemini, local)")
    console.print("  [cyan]/model <name>[/cyan]     - Select specific model (auto-detects provider)")
    console.print("  [cyan]/providers[/cyan]        - List available providers and their status")
    console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace (no args toggles)")
    console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode (tool orchestration)")
    console.print("  [cyan]/stream [on|off][/cyan]   - Toggle real-time streaming with thinking traces")
    console.print("  [cyan]/collective <pattern> <task>[/cyan] - Multi-agent collaboration")
    console.print("      [dim]Patterns: council [k=N], debate, pipeline[/dim]")
    console.print("      [dim]Example: /collective council k=3 Compare PETG vs ABS[/dim]")

    console.print("\n[bold]Fabrication:[/bold]")
    console.print("  [cyan]/cad <prompt>[/cyan]     - Generate CAD models")
    console.print("  [cyan]/generate <prompt>[/cyan] - Generate image with Stable Diffusion")
    console.print("  [cyan]/list[/cyan]             - Show cached artifacts")
    console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact to printer")
    console.print("  [cyan]/split <path> [printer][/cyan] - Segment large model for printing")
    console.print("  [cyan]/vision <query>[/cyan]   - Search & store reference images")
    console.print("  [cyan]/images[/cyan]           - List stored reference images")

    console.print("\n[bold]Network & Discovery:[/bold]")
    console.print("  [cyan]/discover scan[/cyan]           - Start a network discovery scan")
    console.print("  [cyan]/discover status <id>[/cyan]    - Check scan status")
    console.print("  [cyan]/discover list[/cyan]           - List discovered devices (use search/type filters)")
    console.print("  [cyan]/discover approve <id>[/cyan]   - Approve a device")
    console.print("  [cyan]/discover reject <id>[/cyan]    - Reject a device")

    console.print("\n[bold]Memory & Sessions:[/bold]")
    console.print("  [cyan]/remember <note>[/cyan]  - Store a long-term memory note")
    console.print("  [cyan]/memories [query][/cyan] - Search saved memories")
    console.print("  [cyan]/history [limit] [filter][/cyan] - Browse and resume earlier sessions")
    console.print("  [cyan]/reset[/cyan]            - Start a new conversation session")
    console.print("  [cyan]/usage [seconds][/cyan]  - Show usage dashboard (auto-refresh optional)")
    console.print("  [cyan]/help[/cyan]             - Show this help")
    console.print("  [cyan]/exit[/cyan]             - Exit shell")

    # Current settings
    effective = max(state.verbosity, 4) if state.show_trace else state.verbosity
    agent_status = "ON" if state.agent_enabled else "OFF"
    console.print(f"\n[dim]Verbosity: {effective}/5  |  Session: {state.conversation_id[:8]}...[/dim]")
    console.print(f"[dim]Agent mode: {agent_status} (use /agent to toggle)[/dim]")
    trace_status = "ON" if state.show_trace else "OFF"
    console.print(f"[dim]Trace mode: {trace_status} (use /trace to toggle)[/dim]")
    stream_status = "ON" if state.stream_enabled else "OFF"
    console.print(f"[dim]Streaming: {stream_status} (use /stream to toggle - auto-selects GPT-OSS 120B)[/dim]")
    console.print("[dim]Type '/' and press Tab to see available commands[/dim]\n")

    # Create prompt_toolkit session with command completion
    session = PromptSession(completer=CommandCompleter())

    # Track last displayed research sessions for numbered selection
    last_research_sessions: List[Dict[str, Any]] = []

    while True:
        try:
            line = session.prompt(HTML("<ansimagenta>you</ansimagenta>> "))
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session ended. Goodbye![/]")
            break

        if not line:
            continue

        # Check if user typed a number to select from last sessions list
        if line.strip().isdigit() and last_research_sessions:
            idx = int(line.strip())
            if 1 <= idx <= len(last_research_sessions):
                session_id = last_research_sessions[idx - 1].get("session_id")
                if session_id:
                    _display_session_detail(session_id)
                    continue
            else:
                console.print(f"[yellow]Invalid session number. Please enter a number between 1 and {len(last_research_sessions)}[/yellow]")
                continue

        if line.startswith("/"):
            parts = line[1:].split()
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd in {"quit", "exit"}:
                console.print("[dim]Goodbye![/]")
                break

            if cmd == "help":
                console.print("\n[bold]Research Pipeline:[/bold]")
                console.print("  [cyan]/research <query>[/cyan]   - Start autonomous research with real-time streaming")
                console.print("  [cyan]/sessions [limit] [-i][/cyan] - List all research sessions")
                console.print("      [dim]-i, --interactive: Use arrow-key picker to select session[/dim]")
                console.print("      [dim]Or type row number after listing to view that session[/dim]")
                console.print("  [cyan]/session <id>[/cyan]       - View detailed session info and metrics")
                console.print("  [cyan]/stream <id>[/cyan]        - Stream progress of active research session")
                console.print("  [cyan]/report <id>[/cyan]        - Export & open full report (GPTOSS template)")

                console.print("\n[bold]Conversational AI:[/bold]")
                console.print("  [cyan]/verbosity <1-5>[/cyan]  - Set verbosity (1=terse, 5=exhaustive)")
                console.print("  [cyan]/provider <name>[/cyan]  - Select LLM provider (openai, anthropic, mistral, gemini, local)")
                console.print("  [cyan]/model <name>[/cyan]     - Select specific model (gpt-4o-mini, claude-3-5-haiku, etc)")
                console.print("  [cyan]/providers[/cyan]        - List all available providers and status")
                console.print("  [cyan]/trace [on|off][/cyan]    - Toggle agent reasoning trace view")
                console.print("  [cyan]/agent [on|off][/cyan]    - Toggle ReAct agent mode")
                console.print("  [cyan]/stream [on|off][/cyan]   - Toggle real-time streaming (GPT-OSS 120B with thinking)")
                console.print("  [cyan]/collective <pattern> <task>[/cyan] - Multi-agent collaboration")
                console.print("      [dim]Patterns: council [k=3], debate, pipeline[/dim]")
                console.print("      [dim]Example: /collective council k=3 Compare PETG vs ABS[/dim]")

                console.print("\n[bold]Fabrication:[/bold]")
                console.print("  [cyan]/cad <prompt>[/cyan]     - Generate CAD model from description")
                console.print("  [cyan]/generate <prompt>[/cyan] - Generate image with Stable Diffusion")
                console.print("  [cyan]/list[/cyan]             - List cached CAD artifacts")
                console.print("  [cyan]/queue <idx> <id>[/cyan] - Queue artifact #idx to printer")
                console.print("  [cyan]/split <path> [printer][/cyan] - Segment large model for printing")
                console.print("  [cyan]/vision <query>[/cyan]   - Search/select reference images")
                console.print("  [cyan]/images[/cyan]           - Show stored reference images")

                console.print("\n[bold]Network & Discovery:[/bold]")
                console.print("  [cyan]/discover scan[/cyan]           - Start a network discovery scan")
                console.print("  [cyan]/discover status <id>[/cyan]    - Check scan status")
                console.print("  [cyan]/discover list[/cyan]           - List discovered devices (search/type filters)")
                console.print("  [cyan]/discover approve <id>[/cyan]   - Approve a device")
                console.print("  [cyan]/discover reject <id>[/cyan]    - Reject a device")

                console.print("\n[bold]Memory & Sessions:[/bold]")
                console.print("  [cyan]/remember <note>[/cyan]  - Store a long-term memory note")
                console.print("  [cyan]/memories [query][/cyan] - Search saved memories")
                console.print("  [cyan]/history [limit] [filter][/cyan] - Browse & resume sessions")
                console.print("  [cyan]/reset[/cyan]            - Start a new conversation session")
                console.print("  [cyan]/usage [seconds][/cyan]  - Show provider usage dashboard")
                console.print("  [cyan]/help[/cyan]             - Show this help message")
                console.print("  [cyan]/exit[/cyan]             - Exit interactive shell")
                console.print("\n[dim]Type any message to chat with KITTY[/dim]\n")
                continue

            if cmd == "research":
                if not args:
                    console.print("[yellow]Usage: /research <query>")
                    console.print("[dim]Example: /research latest advances in 3D printing materials[/dim]")
                    continue

                query = " ".join(args)

                # Prompt for configuration
                console.print("\n[bold cyan]Configure Research Session[/bold cyan]")
                console.print("[dim](Press Enter to use defaults)[/dim]\n")

                # Strategy
                strategy_input = console.input("[cyan]Strategy[/] [dim](hybrid/breadth_first/depth_first/task_decomposition)[/] [[dim]hybrid[/dim]]: ").strip()
                strategy = strategy_input if strategy_input else "hybrid"

                # Max iterations
                max_iterations_input = console.input("[cyan]Max iterations[/] [[dim]10[/dim]]: ").strip()
                try:
                    max_iterations = int(max_iterations_input) if max_iterations_input else 10
                except ValueError:
                    console.print("[yellow]Invalid input, using default: 10[/yellow]")
                    max_iterations = 10

                # Max cost
                max_cost_input = console.input("[cyan]Max cost USD[/] [[dim]2.0[/dim]]: ").strip()
                try:
                    max_cost = float(max_cost_input) if max_cost_input else 2.0
                except ValueError:
                    console.print("[yellow]Invalid input, using default: 2.0[/yellow]")
                    max_cost = 2.0

                # Enable paid tools
                enable_paid_input = console.input("[cyan]Enable paid tools (Perplexity)?[/] [dim](y/n)[/] [[dim]n[/dim]]: ").strip().lower()
                enable_paid = enable_paid_input in ['y', 'yes']

                # Enable debate
                enable_debate_input = console.input("[cyan]Enable debate (multi-model synthesis)?[/] [dim](y/n)[/] [[dim]n[/dim]]: ").strip().lower()
                enable_debate = enable_debate_input in ['y', 'yes']

                # Build config
                config = {
                    "strategy": strategy,
                    "max_iterations": max_iterations,
                    "max_cost_usd": max_cost,
                    "use_debate": enable_debate,
                }

                # Add base_priority if paid tools enabled
                if enable_paid:
                    config["base_priority"] = 0.7
                    console.print("\n[yellow]✓ Paid tools enabled - research will use Perplexity when beneficial[/yellow]\n")
                else:
                    console.print()

                # Start research session
                session_id = _start_research(query, config)
                # Stream progress
                _stream_research_progress(session_id, state.user_id, query)
                # Show final results
                console.print(f"\n[dim]View details with /session {session_id}[/dim]\n")
                continue

            if cmd == "sessions":
                # Check for interactive flag
                interactive = False
                limit = 10

                # Parse args for flags and limit
                for arg in args:
                    if arg in ["-i", "--interactive"]:
                        interactive = True
                    elif arg.isdigit():
                        try:
                            limit = int(arg)
                        except ValueError:
                            pass

                # Store returned sessions for numbered selection
                last_research_sessions = _list_research_sessions(limit=limit)

                # If interactive mode requested, show picker
                if interactive and last_research_sessions:
                    selected_id = _interactive_session_picker(last_research_sessions)
                    if selected_id:
                        _display_session_detail(selected_id)

                continue

            if cmd == "session":
                if not args:
                    console.print("[yellow]Usage: /session <session_id>")
                    console.print("[dim]List sessions with /sessions[/dim]")
                    continue

                session_id = args[0]
                _display_session_detail(session_id)
                continue

            if cmd == "stream":
                if not args:
                    console.print("[yellow]Usage: /stream <session_id>")
                    console.print("[dim]Stream real-time progress of an active research session[/dim]")
                    continue

                session_id = args[0]
                # Need to get session info for query
                try:
                    data = _get_json(f"{API_BASE}/api/research/sessions/{session_id}")
                    session = data
                    query = session.get("query", "Research session")
                    _stream_research_progress(session_id, state.user_id, query)
                except Exception as exc:
                    console.print(f"[red]Failed to stream session: {exc}")
                continue

            if cmd == "report":
                if not args:
                    console.print("[yellow]Usage: /report <session_id> [--no-open] [--editor <cmd>] [--output-dir <path>]")
                    console.print("[dim]Example: /report d99a3593 --editor 'less -R'[/dim]")
                    continue

                session_id = args[0]
                output_dir = "Research/exports"
                open_file = True
                editor = None

                idx = 1
                while idx < len(args):
                    arg = args[idx]
                    if arg in {"--no-open", "--noopen"}:
                        open_file = False
                    elif arg == "--open":
                        open_file = True
                    elif arg in {"-e", "--editor"} and idx + 1 < len(args):
                        idx += 1
                        editor = args[idx]
                    elif arg in {"-o", "--output-dir"} and idx + 1 < len(args):
                        idx += 1
                        output_dir = args[idx]
                    idx += 1

                try:
                    _export_research_report(
                        session_id,
                        output_dir=output_dir,
                        open_file=open_file,
                        editor=editor,
                    )
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]Failed to export report: {exc}")
                continue

            if cmd == "history":
                limit = 10
                search_tokens = args
                if args and args[0].isdigit():
                    try:
                        limit = max(1, min(50, int(args[0])))
                    except ValueError:
                        limit = 10
                    search_tokens = args[1:]
                search = " ".join(search_tokens).strip() or None
                _history_picker(limit=limit, search=search)
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
                    console.print("[yellow]Usage: /cad <prompt> [--o|--organic] [--p|--parametric] [--image <ref>]")
                    console.print("[dim]Example: /cad design a wall mount bracket[/dim]")
                    console.print("[dim]Example: /cad convert to 3D --image 1[/dim]")
                else:
                    organic_flag = False
                    param_flag = False
                    image_filters_list: List[str] = []
                    prompt_tokens: List[str] = []
                    skip_next = False
                    for i, token in enumerate(args):
                        if skip_next:
                            skip_next = False
                            continue
                        lower = token.lower()
                        if lower in {"--o", "--organic"}:
                            organic_flag = True
                            continue
                        if lower in {"--p", "--parametric"}:
                            param_flag = True
                            continue
                        if lower in {"--image", "-i"}:
                            if i + 1 < len(args):
                                image_filters_list.append(args[i + 1])
                                skip_next = True
                            continue
                        prompt_tokens.append(token)
                    cad(
                        prompt_tokens,
                        organic=organic_flag,
                        parametric=param_flag,
                        image_filters=image_filters_list if image_filters_list else None,
                    )
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

            if cmd == "stream":
                if not args:
                    state.stream_enabled = not state.stream_enabled
                else:
                    setting = args[0].lower()
                    if setting in {"on", "true", "1"}:
                        state.stream_enabled = True
                    elif setting in {"off", "false", "0"}:
                        state.stream_enabled = False
                    else:
                        console.print("[red]Usage: /stream on|off")
                        continue

                # When enabling streaming, automatically switch to GPT-OSS 120B (Ollama)
                if state.stream_enabled:
                    console.print(
                        "[green]Streaming mode enabled[/green]\n"
                        "[dim]→ Real-time thinking traces with GPT-OSS 120B[/dim]"
                    )
                else:
                    console.print("[green]Streaming mode disabled (using standard responses)")
                continue

            if cmd == "provider":
                if not args:
                    if state.provider:
                        console.print(f"[yellow]Current provider: {state.provider}")
                    else:
                        console.print("[yellow]No provider selected (using local Q4 default)")
                    console.print("[dim]Available: openai, anthropic, mistral, perplexity, gemini, local")
                else:
                    provider_name = args[0].lower()
                    if provider_name in {"local", "none", "default", "q4"}:
                        state.provider = None
                        state.model = None
                        console.print("[green]Provider reset to local Q4")
                    elif provider_name in {"openai", "anthropic", "mistral", "perplexity", "gemini"}:
                        state.provider = provider_name
                        state.model = None  # Reset model when changing provider
                        console.print(f"[green]Provider set to: {provider_name}")
                        console.print("[dim]Note: Provider must be enabled in I/O Control for this to work")
                    else:
                        console.print(f"[red]Unknown provider: {provider_name}")
                        console.print("[dim]Available: openai, anthropic, mistral, perplexity, gemini, local")
                continue

            if cmd == "model":
                if not args:
                    if state.model:
                        console.print(f"[yellow]Current model: {state.model} (provider: {state.provider or 'auto-detect'})")
                    else:
                        console.print("[yellow]No specific model selected")
                else:
                    model_name = args[0].lower()
                    # Auto-detect provider from common model names
                    provider_map = {
                        "gpt-4": "openai",
                        "gpt-4o": "openai",
                        "gpt-4o-mini": "openai",
                        "gpt-3.5": "openai",
                        "claude": "anthropic",
                        "claude-3": "anthropic",
                        "claude-3-5-haiku": "anthropic",
                        "claude-3-5-sonnet": "anthropic",
                        "mistral": "mistral",
                        "mistral-small": "mistral",
                        "mistral-medium": "mistral",
                        "sonar": "perplexity",
                        "gemini": "gemini",
                        "gemini-flash": "gemini",
                        "gemini-pro": "gemini",
                    }
                    detected_provider = None
                    for prefix, prov in provider_map.items():
                        if model_name.startswith(prefix):
                            detected_provider = prov
                            break

                    if detected_provider:
                        state.provider = detected_provider
                        state.model = model_name
                        console.print(f"[green]Model set to: {model_name} (provider: {detected_provider})")
                    else:
                        # Assume it's a local model alias
                        state.provider = None
                        state.model = None
                        console.print(f"[yellow]Unknown model: {model_name}. Reset to local Q4.")
                        console.print("[dim]Tip: Use full model names like 'gpt-4o-mini' or 'claude-3-5-haiku'")
                continue

            if cmd == "providers":
                console.print("\n[bold]Multi-Provider Collective Status:[/bold]")
                console.print("[dim]Enable providers in I/O Control Dashboard[/dim]\n")
                try:
                    # Try to fetch provider status from API
                    data = _get_json(f"{API_BASE}/api/providers/available")
                    providers = data.get("providers", {})
                    if providers:
                        for prov_name, prov_info in providers.items():
                            enabled = prov_info.get("enabled", False)
                            status = "[green]✓ ENABLED" if enabled else "[dim]✗ disabled"
                            models = ", ".join(prov_info.get("models", []))
                            cost = prov_info.get("cost_info", "")
                            console.print(f"{status}[/] {prov_name}: {models}")
                            if cost and enabled:
                                console.print(f"       [dim]{cost}[/]")
                    else:
                        console.print("[yellow]No provider status available from API")
                except Exception:
                    # Fallback to environment-based status check
                    console.print("[cyan]openai[/]:     GPT-4o-mini, GPT-4o")
                    console.print("[cyan]anthropic[/]:  Claude 3.5 Haiku, Sonnet")
                    console.print("[cyan]mistral[/]:    Mistral-small, Mistral-medium")
                    console.print("[cyan]perplexity[/]: Sonar")
                    console.print("[cyan]gemini[/]:     Gemini Flash, Gemini Pro")
                    console.print("\n[dim]Enable in I/O Control to use these providers[/]")

                # Show current selection
                if state.provider:
                    console.print(f"\n[bold]Current selection:[/] {state.provider}")
                    if state.model:
                        console.print(f"[bold]Current model:[/] {state.model}")
                else:
                    console.print("\n[bold]Current selection:[/] local Q4 (default)")
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

                payload = {
                    "task": task,
                    "pattern": pattern,
                    "k": k,
                    "conversationId": state.conversation_id,
                    "userId": state.user_id,
                }

                with console.status("[bold green]Generating proposals..."):
                    try:
                        response = httpx.post(
                            f"{API_BASE}/api/collective/run",
                            json=payload,
                            timeout=CLI_TIMEOUT
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

            if cmd == "discover":
                if not args:
                    console.print("[yellow]Usage: /discover scan | status <scan_id> | list | approve <id> | reject <id> [key=value options]")
                    console.print("[dim]Options: methods=mdns,ssdp  search=term  type=printer_3d  approved=true  online=true  limit=50[/dim]")
                    continue

                action = args[0].lower()
                option_tokens = args[1:]
                positional: List[str] = []
                options: Dict[str, str] = {}
                for tok in option_tokens:
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        options[k.lower()] = v
                    else:
                        positional.append(tok)

                target_id = positional[0] if positional else None
                methods_raw = options.get("methods") or options.get("method")
                methods_list = methods_raw.split(",") if methods_raw else None
                approved_flag = _parse_bool_str(options.get("approved"))
                online_flag = _parse_bool_str(options.get("online"))

                try:
                    _run_discover(
                        action,
                        scan_id=target_id if action == "status" else None,
                        device_id=target_id if action in {"approve", "reject"} else None,
                        methods=methods_list,
                        timeout_seconds=int(options.get("timeout", "30")),
                        search=options.get("search") or options.get("q"),
                        device_type=options.get("type") or options.get("device_type"),
                        approved=approved_flag,
                        online=online_flag,
                        manufacturer=options.get("manufacturer"),
                        limit=int(options.get("limit", "100")),
                        notes=options.get("notes"),
                    )
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]Discovery command failed: {exc}[/red]")
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

            if cmd == "split":
                if not args:
                    console.print("[yellow]Usage: /split <stl_path> [printer_id]")
                    console.print("[dim]Example: /split /path/to/large_model.stl bamboo_h2d[/dim]")
                    console.print("[dim]Segments models that exceed printer build volume[/dim]")
                else:
                    stl_path = args[0]
                    printer_id = args[1] if len(args) > 1 else None
                    _run_split_command(stl_path, printer_id)
                continue

            console.print(f"[yellow]Unknown command: /{cmd}")
            console.print("[dim]Type /help for available commands[/dim]")
            continue

        # Default to conversation
        try:
            say([line], verbosity=None, stream=state.stream_enabled if state.stream_enabled else None)
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
