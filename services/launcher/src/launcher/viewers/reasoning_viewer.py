"""Real-time reasoning log viewer with analytics."""

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Label, DataTable
from textual.reactive import reactive


class LogEntry:
    """Parsed log entry."""

    def __init__(self, raw_line: str):
        self.raw = raw_line
        self.timestamp = None
        self.level = None
        self.reasoning_type = None
        self.model = None
        self.tier = None
        self.confidence = None
        self.cost = None
        self.message = None

        self._parse()

    def _parse(self):
        """Parse log line into structured data."""
        # Example format:
        # 2025-01-15 14:30:45 - brain.routing - INFO - routing - kitty-primary - local - 0.85 - 0.0001 - Routing decision: local tier selected

        # Try to extract timestamp
        ts_match = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", self.raw)
        if ts_match:
            try:
                self.timestamp = datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        # Extract level
        level_match = re.search(r" - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ", self.raw)
        if level_match:
            self.level = level_match.group(1)

        # Extract structured fields
        type_match = re.search(r"reasoning_type['\"]:\s*['\"]([^'\"]+)", self.raw)
        if type_match:
            self.reasoning_type = type_match.group(1)

        model_match = re.search(r"model_used['\"]:\s*['\"]([^'\"]+)", self.raw)
        if model_match:
            self.model = model_match.group(1)

        tier_match = re.search(r"tier['\"]:\s*['\"]([^'\"]+)", self.raw)
        if tier_match:
            self.tier = tier_match.group(1)

        confidence_match = re.search(r"confidence['\"]:\s*([0-9.]+)", self.raw)
        if confidence_match:
            self.confidence = float(confidence_match.group(1))

        cost_match = re.search(r"cost['\"]:\s*([0-9.]+)", self.raw)
        if cost_match:
            self.cost = float(cost_match.group(1))

        # Extract message (everything after the structured fields)
        msg_match = re.search(r" - ([^-]+)$", self.raw)
        if msg_match:
            self.message = msg_match.group(1).strip()


class LogStats:
    """Statistics for reasoning logs."""

    def __init__(self):
        self.total_entries = 0
        self.by_tier: Dict[str, int] = defaultdict(int)
        self.by_type: Dict[str, int] = defaultdict(int)
        self.by_model: Dict[str, int] = defaultdict(int)
        self.total_cost = 0.0
        self.confidences: List[float] = []
        self.low_confidence_count = 0

    def add_entry(self, entry: LogEntry):
        """Add log entry to statistics."""
        self.total_entries += 1

        if entry.tier:
            self.by_tier[entry.tier] += 1

        if entry.reasoning_type:
            self.by_type[entry.reasoning_type] += 1

        if entry.model:
            self.by_model[entry.model] += 1

        if entry.cost:
            self.total_cost += entry.cost

        if entry.confidence is not None:
            self.confidences.append(entry.confidence)
            if entry.confidence < 0.8:
                self.low_confidence_count += 1


class ReasoningLogViewer(Static):
    """Real-time viewer for reasoning logs with analytics."""

    DEFAULT_CSS = """
    ReasoningLogViewer {
        border: solid $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }

    #stats-container {
        height: auto;
        border: solid $accent;
        padding: 1 2;
        margin-bottom: 1;
    }

    #log-container {
        height: 20;
        border: solid $success;
        padding: 1 2;
    }

    .stat-row {
        height: auto;
    }

    .stat-label {
        width: 30;
        text-style: bold;
        color: $text-muted;
    }

    .stat-value {
        color: $success;
    }

    .log-entry {
        height: auto;
        padding: 0 1;
    }

    .log-routing {
        color: $primary;
    }

    .log-agent {
        color: $warning;
    }

    .log-tool {
        color: $success;
    }

    .log-confidence {
        color: $accent;
    }
    """

    log_file: reactive[Optional[Path]] = reactive(None)
    entries: reactive[List[LogEntry]] = reactive([])

    def __init__(self, log_file: str = ".logs/reasoning.log"):
        """Initialize reasoning log viewer.

        Args:
            log_file: Path to reasoning log file
        """
        super().__init__()
        self.log_file = Path(log_file)
        self.stats = LogStats()

    def compose(self) -> ComposeResult:
        """Compose the viewer layout."""
        yield Static("[bold cyan]Reasoning & Routing Log Viewer[/bold cyan]\n")

        with Container(id="stats-container"):
            yield Static("[bold]Statistics[/bold]", classes="stat-label")
            yield Static("Loading...", id="stats-display")

        with VerticalScroll(id="log-container"):
            yield Static("Loading logs...", id="log-display")

    def on_mount(self) -> None:
        """Load logs when mounted."""
        self.load_logs()
        self.set_interval(2.0, self.load_logs)  # Refresh every 2 seconds

    def load_logs(self) -> None:
        """Load and parse log file."""
        if not self.log_file.exists():
            self.update_display("Log file not found: " + str(self.log_file))
            return

        try:
            with open(self.log_file) as f:
                lines = f.readlines()

            # Parse entries
            self.entries = [LogEntry(line.strip()) for line in lines if line.strip()]

            # Update statistics
            self.stats = LogStats()
            for entry in self.entries:
                self.stats.add_entry(entry)

            # Update display
            self.update_display()
        except Exception as e:
            self.update_display(f"Error reading log: {e}")

    def update_display(self, error: Optional[str] = None) -> None:
        """Update the display with current data."""
        # Update statistics
        stats_widget = self.query_one("#stats-display", Static)

        if error:
            stats_widget.update(f"[red]{error}[/red]")
            return

        stats_text = []

        # Total entries
        stats_text.append(f"[bold]Total Entries:[/bold] {self.stats.total_entries}")

        # Tier distribution
        if self.stats.by_tier:
            stats_text.append("\n[bold]By Tier:[/bold]")
            for tier, count in sorted(self.stats.by_tier.items()):
                pct = (count / self.stats.total_entries * 100) if self.stats.total_entries > 0 else 0
                stats_text.append(f"  {tier}: {count} ({pct:.1f}%)")

        # Model distribution
        if self.stats.by_model:
            stats_text.append("\n[bold]By Model:[/bold]")
            for model, count in sorted(self.stats.by_model.items(), key=lambda x: x[1], reverse=True):
                pct = (count / self.stats.total_entries * 100) if self.stats.total_entries > 0 else 0
                stats_text.append(f"  {model}: {count} ({pct:.1f}%)")

        # Confidence stats
        if self.stats.confidences:
            avg_conf = sum(self.stats.confidences) / len(self.stats.confidences)
            stats_text.append(f"\n[bold]Confidence:[/bold]")
            stats_text.append(f"  Average: {avg_conf:.3f}")
            stats_text.append(f"  Low confidence (<0.8): {self.stats.low_confidence_count}")

        # Cost
        stats_text.append(f"\n[bold]Total Cost:[/bold] ${self.stats.total_cost:.4f}")

        stats_widget.update("\n".join(stats_text))

        # Update log display (last 50 entries)
        log_widget = self.query_one("#log-display", Static)

        if not self.entries:
            log_widget.update("[dim]No log entries found[/dim]")
            return

        log_lines = []
        for entry in self.entries[-50:]:  # Show last 50
            # Color code by type
            color = "white"
            if entry.reasoning_type == "routing":
                color = "cyan"
            elif entry.reasoning_type and "agent" in entry.reasoning_type:
                color = "yellow"
            elif entry.reasoning_type == "tool_execution":
                color = "green"
            elif entry.reasoning_type == "confidence":
                color = "magenta"

            # Format entry
            parts = []
            if entry.timestamp:
                parts.append(f"[dim]{entry.timestamp.strftime('%H:%M:%S')}[/dim]")

            if entry.level:
                level_color = {
                    "DEBUG": "dim",
                    "INFO": "blue",
                    "WARNING": "yellow",
                    "ERROR": "red",
                    "CRITICAL": "bold red",
                }.get(entry.level, "white")
                parts.append(f"[{level_color}]{entry.level:8}[/{level_color}]")

            if entry.reasoning_type:
                parts.append(f"[{color}]{entry.reasoning_type:15}[/{color}]")

            if entry.tier:
                parts.append(f"[cyan]{entry.tier:10}[/cyan]")

            if entry.model:
                parts.append(f"[bold]{entry.model:20}[/bold]")

            if entry.confidence is not None:
                conf_color = "green" if entry.confidence >= 0.8 else "yellow"
                parts.append(f"[{conf_color}]conf:{entry.confidence:.2f}[/{conf_color}]")

            if entry.cost is not None and entry.cost > 0:
                parts.append(f"[red]${entry.cost:.4f}[/red]")

            if entry.message:
                parts.append(entry.message[:60])

            log_lines.append(" | ".join(parts))

        log_widget.update("\n".join(log_lines))
