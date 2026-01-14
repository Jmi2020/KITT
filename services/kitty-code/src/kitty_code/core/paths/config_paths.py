from __future__ import annotations

from pathlib import Path
from typing import Literal

from kitty_code.core.paths.global_paths import KITTY_CODE_HOME, GlobalPath
from kitty_code.core.trusted_folders import trusted_folders_manager

_config_paths_locked: bool = True

# Project-local config directories (checked in order of preference)
_LOCAL_CONFIG_DIRS = [".kitty-code", ".vibe"]


class ConfigPath(GlobalPath):
    @property
    def path(self) -> Path:
        if _config_paths_locked:
            raise RuntimeError("Config path is locked")
        return super().path


def _resolve_config_path(basename: str, type: Literal["file", "dir"]) -> Path:
    cwd = Path.cwd()
    is_folder_trusted = trusted_folders_manager.is_trusted(cwd)
    if not is_folder_trusted:
        return KITTY_CODE_HOME.path / basename
    # Check local config dirs in order of preference
    for config_dir in _LOCAL_CONFIG_DIRS:
        if type == "file":
            if (candidate := cwd / config_dir / basename).is_file():
                return candidate
        elif type == "dir":
            if (candidate := cwd / config_dir / basename).is_dir():
                return candidate
    return KITTY_CODE_HOME.path / basename


def resolve_local_tools_dir(dir: Path) -> Path | None:
    if not trusted_folders_manager.is_trusted(dir):
        return None
    for config_dir in _LOCAL_CONFIG_DIRS:
        if (candidate := dir / config_dir / "tools").is_dir():
            return candidate
    return None


def resolve_local_skills_dir(dir: Path) -> Path | None:
    if not trusted_folders_manager.is_trusted(dir):
        return None
    for config_dir in _LOCAL_CONFIG_DIRS:
        if (candidate := dir / config_dir / "skills").is_dir():
            return candidate
    return None


def unlock_config_paths() -> None:
    global _config_paths_locked
    _config_paths_locked = False


CONFIG_FILE = ConfigPath(lambda: _resolve_config_path("config.toml", "file"))
CONFIG_DIR = ConfigPath(lambda: CONFIG_FILE.path.parent)
AGENT_DIR = ConfigPath(lambda: _resolve_config_path("agents", "dir"))
PROMPT_DIR = ConfigPath(lambda: _resolve_config_path("prompts", "dir"))
INSTRUCTIONS_FILE = ConfigPath(lambda: _resolve_config_path("instructions.md", "file"))
HISTORY_FILE = ConfigPath(lambda: _resolve_config_path("kitty-code-history", "file"))
