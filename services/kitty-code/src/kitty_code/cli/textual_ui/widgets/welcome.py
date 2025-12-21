from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from rich.align import Align
from rich.console import Group
from rich.text import Text
from textual.color import Color
from textual.widgets import Static

from kitty_code import __version__
from kitty_code.core.config import VibeConfig


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    normalized = hex_color.lstrip("#")
    r, g, b = (int(normalized[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b)


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def interpolate_color(
    start_rgb: tuple[int, int, int], end_rgb: tuple[int, int, int], progress: float
) -> str:
    progress = max(0.0, min(1.0, progress))
    r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * progress)
    g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * progress)
    b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * progress)
    return rgb_to_hex(r, g, b)


@dataclass
class LineAnimationState:
    progress: float = 0.0
    cached_color: str | None = None
    cached_progress: float = -1.0
    rendered_color: str | None = None


# Short & Stout Voxel Cat - from CodeCat.py
# Compact, sturdy, cute blocky design
CAT_PATTERN = [
    "████                      ",  # Tail Tip
    "██████                    ",  # Tail Step
    "████                      ",  # Tail Stem
    "████          ██  ██      ",  # Tail + Ears
    "████          ██████      ",  # Tail + Head
    "████████████████████      ",  # Body Top
    "████████████████████      ",  # Body Mid
    "████████████████████      ",  # Body Low
    "  ████      ████          ",  # Legs Top
    "  ████      ████          ",  # Legs Bottom
]

# Tiny version for compact displays
CAT_PATTERN_SMALL = [
    "██            ",
    "██      █  █  ",
    "██      ████  ",
    "████████████  ",
    " ██    ██     ",
]


class WelcomeBanner(Static):
    FLASH_COLOR = "#FFFFFF"
    # Gradient: Electric Cyan (40, 230, 255) -> Hot Pink (255, 60, 180)
    # Matched to CodeCat.py colors
    GRADIENT_COLORS = [
        "#28E6FF",  # Electric Cyan (tail tip)
        "#40D4F0",  # Cyan-blue
        "#60C0E0",  # Light cyan
        "#80A8D0",  # Cyan transitioning
        "#A090C0",  # Purple-blue
        "#C078B0",  # Purple-magenta
        "#E060A0",  # Magenta
        "#F04890",  # Pink-magenta
        "#FF3CB4",  # Hot pink (legs)
        "#FF3CB4",  # Hot pink (feet)
    ]
    BORDER_TARGET_COLOR = "#A060C0"  # Purple accent

    # Animation timing
    LINE_ANIMATION_DURATION_MS = 150
    LINE_STAGGER_MS = 80
    FLASH_RESET_DURATION_MS = 400
    ANIMATION_TICK_INTERVAL = 0.05

    # Wave animation settings
    WAVE_SPEED = 3.0  # How fast the wave moves through the cat
    WAVE_WIDTH = 0.3  # Width of the bright wave

    COLOR_FLASH_MIDPOINT = 0.5
    COLOR_PHASE_SCALE = 2.0
    COLOR_CACHE_THRESHOLD = 0.001
    BORDER_PROGRESS_THRESHOLD = 0.01

    def __init__(self, config: VibeConfig) -> None:
        super().__init__(" ")
        self.config = config
        self.animation_timer = None
        self._animation_start_time: float | None = None
        self._use_small_logo = False

        self._cached_skeleton_color: str | None = None
        self._cached_skeleton_rgb: tuple[int, int, int] | None = None
        self._flash_rgb = hex_to_rgb(self.FLASH_COLOR)
        self._gradient_rgbs = [hex_to_rgb(c) for c in self.GRADIENT_COLORS]
        self._border_target_rgb = hex_to_rgb(self.BORDER_TARGET_COLOR)

        self._cat_pattern = CAT_PATTERN
        num_lines = len(self._cat_pattern)
        self._line_states = [LineAnimationState() for _ in range(num_lines)]
        self.border_progress = 0.0
        self._cached_border_color: str | None = None
        self._cached_border_progress = -1.0
        self._wave_phase = 0.0

        self._line_duration = self.LINE_ANIMATION_DURATION_MS / 1000
        self._line_stagger = self.LINE_STAGGER_MS / 1000
        self._border_duration = self.FLASH_RESET_DURATION_MS / 1000
        self._line_start_times = [
            idx * self._line_stagger for idx in range(num_lines)
        ]
        self._all_lines_finish_time = (
            (num_lines - 1) * self.LINE_STAGGER_MS
            + self.LINE_ANIMATION_DURATION_MS
        ) / 1000

        self._initialize_info_lines()

    def _initialize_info_lines(self) -> None:
        """Initialize the info text that appears next to the logo."""
        self._info_line1 = f"[b]Kitty Code v{__version__}[/]"
        self._info_line2 = f"[dim]{self.config.active_model}[/]"
        mcp_count = len(self.config.mcp_servers)
        model_count = len(self.config.models)
        self._info_line3 = f"[dim]{model_count} models · {mcp_count} MCP servers[/]"
        self._info_line4 = f"[dim]{self.config.effective_workdir}[/]"
        self._help_line = (
            f"[dim]Type[/] [{self.BORDER_TARGET_COLOR}]/help[/] [dim]for commands • [/]"
            f"[{self.BORDER_TARGET_COLOR}]/mcp[/][dim] for servers[/]"
        )

    @property
    def skeleton_color(self) -> str:
        return self._cached_skeleton_color or "#1e1e1e"

    @property
    def skeleton_rgb(self) -> tuple[int, int, int]:
        return self._cached_skeleton_rgb or hex_to_rgb("#1e1e1e")

    def on_mount(self) -> None:
        if not self.config.disable_welcome_banner_animation:
            self.call_after_refresh(self._init_after_styles)
        else:
            self.call_after_refresh(self._show_static_banner)

    def _show_static_banner(self) -> None:
        """Show the banner without animation."""
        self._cache_skeleton_color()
        # Set all lines to complete
        for state in self._line_states:
            state.progress = 1.0
        self.border_progress = 1.0
        self._update_display()

    def _init_after_styles(self) -> None:
        self._cache_skeleton_color()
        self._update_display()
        self._start_animation()

    def _cache_skeleton_color(self) -> None:
        try:
            border = self.styles.border
            if (
                hasattr(border, "top")
                and isinstance(edge := border.top, tuple)
                and len(edge) >= 2
                and isinstance(color := edge[1], Color)
            ):
                self._cached_skeleton_color = color.hex
                self._cached_skeleton_rgb = hex_to_rgb(color.hex)
                return
        except (AttributeError, TypeError):
            pass

        self._cached_skeleton_color = "#1e1e1e"
        self._cached_skeleton_rgb = hex_to_rgb("#1e1e1e")

    def _stop_timer(self) -> None:
        if self.animation_timer:
            try:
                self.animation_timer.stop()
            except Exception:
                pass
            self.animation_timer = None

    def on_unmount(self) -> None:
        self._stop_timer()

    def _start_animation(self) -> None:
        self._animation_start_time = monotonic()

        def tick() -> None:
            if self._animation_start_time is None:
                return

            elapsed = monotonic() - self._animation_start_time

            # Phase 1: Draw in the cat line by line
            if not self._is_draw_complete():
                updated_lines = self._advance_line_progress(elapsed)
                border_updated = self._advance_border_progress(elapsed)

                if border_updated:
                    self._update_border_color()
                if updated_lines or border_updated:
                    self._update_display()
            else:
                # Phase 2: Color wave animation (runs for a bit then stops)
                wave_start = self._all_lines_finish_time + self._border_duration
                wave_elapsed = elapsed - wave_start

                if wave_elapsed > 0 and wave_elapsed < 3.0:  # Wave for 3 seconds
                    self._wave_phase = wave_elapsed * self.WAVE_SPEED
                    self._update_display()
                elif wave_elapsed >= 3.0:
                    # Animation complete
                    self._wave_phase = 0.0
                    self._update_display()
                    self._stop_timer()

        self.animation_timer = self.set_interval(self.ANIMATION_TICK_INTERVAL, tick)

    def _advance_line_progress(self, elapsed: float) -> bool:
        any_updates = False
        for line_idx, state in enumerate(self._line_states):
            if state.progress >= 1.0:
                continue
            start_time = self._line_start_times[line_idx]
            if elapsed < start_time:
                continue
            progress = min(1.0, (elapsed - start_time) / self._line_duration)
            if progress > state.progress:
                state.progress = progress
                any_updates = True
        return any_updates

    def _advance_border_progress(self, elapsed: float) -> bool:
        if elapsed < self._all_lines_finish_time:
            return False

        new_progress = min(
            1.0, (elapsed - self._all_lines_finish_time) / self._border_duration
        )

        if abs(new_progress - self.border_progress) > self.BORDER_PROGRESS_THRESHOLD:
            self.border_progress = new_progress
            return True

        return False

    def _is_draw_complete(self) -> bool:
        return (
            all(state.progress >= 1.0 for state in self._line_states)
            and self.border_progress >= 1.0
        )

    def _update_border_color(self) -> None:
        progress = self.border_progress
        if abs(progress - self._cached_border_progress) < self.COLOR_CACHE_THRESHOLD:
            return

        border_color = self._compute_color_for_progress(
            progress, self._border_target_rgb
        )
        self._cached_border_color = border_color
        self._cached_border_progress = progress
        self.styles.border = ("round", border_color)

    def _compute_color_for_progress(
        self, progress: float, target_rgb: tuple[int, int, int]
    ) -> str:
        if progress <= 0:
            return self.skeleton_color

        if progress <= self.COLOR_FLASH_MIDPOINT:
            phase = progress * self.COLOR_PHASE_SCALE
            return interpolate_color(self.skeleton_rgb, self._flash_rgb, phase)

        phase = (progress - self.COLOR_FLASH_MIDPOINT) * self.COLOR_PHASE_SCALE
        return interpolate_color(self._flash_rgb, target_rgb, phase)

    def _get_gradient_color(self, line_idx: int, total_lines: int) -> str:
        """Get the gradient color for a line based on its position."""
        if total_lines <= 1:
            return self.GRADIENT_COLORS[len(self.GRADIENT_COLORS) // 2]

        # Map line index to gradient color
        gradient_pos = line_idx / (total_lines - 1)
        color_idx = int(gradient_pos * (len(self.GRADIENT_COLORS) - 1))
        color_idx = min(color_idx, len(self.GRADIENT_COLORS) - 1)

        return self.GRADIENT_COLORS[color_idx]

    def _get_wave_brightness(self, line_idx: int, total_lines: int) -> float:
        """Calculate wave brightness for a line (0.0 to 1.0 extra brightness)."""
        if self._wave_phase <= 0:
            return 0.0

        # Calculate position in the wave
        line_pos = line_idx / max(1, total_lines - 1)
        wave_pos = (self._wave_phase % 2.0) / 2.0  # Normalize to 0-1, repeating

        # Distance from wave center
        distance = abs(line_pos - wave_pos)
        if distance > self.WAVE_WIDTH:
            return 0.0

        # Smooth brightness falloff
        brightness = 1.0 - (distance / self.WAVE_WIDTH)
        return brightness * 0.4  # Max 40% brighter

    def _brighten_color(self, hex_color: str, amount: float) -> str:
        """Brighten a color by a percentage (0.0 to 1.0)."""
        if amount <= 0:
            return hex_color

        r, g, b = hex_to_rgb(hex_color)
        # Lerp towards white
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return rgb_to_hex(r, g, b)

    def _build_cat_line(self, line_idx: int, pattern: str) -> Text:
        """Build a single line of the cat with proper coloring."""
        state = self._line_states[line_idx]
        total_lines = len(self._cat_pattern)

        # Get base gradient color for this line
        base_color = self._get_gradient_color(line_idx, total_lines)

        # Apply wave brightness if animation is running
        wave_brightness = self._get_wave_brightness(line_idx, total_lines)
        if wave_brightness > 0:
            base_color = self._brighten_color(base_color, wave_brightness)

        # If line isn't fully drawn yet, compute animation color
        if state.progress < 1.0:
            target_rgb = hex_to_rgb(base_color)
            base_color = self._compute_color_for_progress(state.progress, target_rgb)

        # Build the line with colored blocks
        result = Text()
        for char in pattern:
            if char in "█▀▄▌▐▇":
                result.append(char, style=base_color)
            else:
                result.append(char)

        return result

    def _update_display(self) -> None:
        """Update the full display with cat logo and info."""
        lines: list[Text] = []
        total_cat_lines = len(self._cat_pattern)

        # Build each line of the cat
        for idx, pattern in enumerate(self._cat_pattern):
            cat_line = self._build_cat_line(idx, pattern)

            # Add info text to specific lines (positioned to the right of the cat)
            # Adjusted for 10-row voxel cat pattern
            info_gap = "  "
            if idx == 3:
                cat_line.append(info_gap)
                cat_line.append_text(Text.from_markup(self._info_line1))
            elif idx == 5:
                cat_line.append(info_gap)
                cat_line.append_text(Text.from_markup(self._info_line2))
            elif idx == 7:
                cat_line.append(info_gap)
                cat_line.append_text(Text.from_markup(self._info_line3))
            elif idx == 9:
                cat_line.append(info_gap)
                cat_line.append_text(Text.from_markup(self._info_line4))

            lines.append(cat_line)

        # Add spacing and help line
        lines.append(Text(""))
        lines.append(Text.from_markup(self._help_line))

        self.update(Align.center(Group(*lines)))
