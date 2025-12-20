from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

from kitty_code import KITTY_CODE_ROOT


class GlobalPath:
    def __init__(self, resolver: Callable[[], Path]) -> None:
        self._resolver = resolver

    @property
    def path(self) -> Path:
        return self._resolver()


_DEFAULT_KITTY_CODE_HOME = Path.home() / ".kitty-code"


def _get_kitty_code_home() -> Path:
    if kitty_code_home := os.getenv("KITTY_CODE_HOME"):
        return Path(kitty_code_home).expanduser().resolve()
    return _DEFAULT_KITTY_CODE_HOME


KITTY_CODE_HOME = GlobalPath(_get_kitty_code_home)
GLOBAL_CONFIG_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "config.toml")
GLOBAL_ENV_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / ".env")
GLOBAL_TOOLS_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "tools")
SESSION_LOG_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "logs" / "session")
TRUSTED_FOLDERS_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "trusted_folders.toml")
LOG_DIR = GlobalPath(lambda: KITTY_CODE_HOME.path / "logs")
LOG_FILE = GlobalPath(lambda: KITTY_CODE_HOME.path / "kitty-code.log")

DEFAULT_TOOL_DIR = GlobalPath(lambda: KITTY_CODE_ROOT / "core" / "tools" / "builtins")
