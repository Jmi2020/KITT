from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from kitty_code import VIBE_ROOT


class GlobalPath:
    def __init__(self, resolver: Callable[[], Path]) -> None:
        self._resolver = resolver

    @property
    def path(self) -> Path:
        return self._resolver()


_DEFAULT_KITTY_CODE_HOME = Path.home() / ".kitty-code"


def _get_kitty_code_home() -> Path:
    # Check KITTY_CODE_HOME first, then fall back to VIBE_HOME for compatibility
    if kitty_home := os.getenv("KITTY_CODE_HOME"):
        return Path(kitty_home).expanduser().resolve()
    if vibe_home := os.getenv("VIBE_HOME"):
        return Path(vibe_home).expanduser().resolve()
    return _DEFAULT_KITTY_CODE_HOME


KITTY_CODE_HOME = GlobalPath(_get_kitty_code_home)
GLOBAL_CONFIG_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "config.toml")
GLOBAL_ENV_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / ".env")
GLOBAL_TOOLS_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "tools")
GLOBAL_SKILLS_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "skills")
SESSION_LOG_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "logs" / "session")
TRUSTED_FOLDERS_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "trusted_folders.toml")
LOG_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "logs")
LOG_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "kitty-code.log")
CURRENT_PLAN_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "current_plan.md")

DEFAULT_TOOL_DIR = GlobalPath(lambda: VIBE_ROOT / "core" / "tools" / "builtins")
