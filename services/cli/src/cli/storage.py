"""Persistent storage helpers for the KITTY CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CACHE_DIR = Path(
    os.environ.get("KITTY_CACHE_DIR", "~/.kitty-cli")
).expanduser()
IMAGE_CACHE_FILE = DEFAULT_CACHE_DIR / "stored_images.json"


def _ensure_cache_dir() -> None:
    DEFAULT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_stored_images() -> List[Dict[str, Any]]:
    """Load persisted reference images from disk."""

    _ensure_cache_dir()
    if not IMAGE_CACHE_FILE.exists():
        return []
    try:
        raw = json.loads(IMAGE_CACHE_FILE.read_text())
        if isinstance(raw, dict) and "images" in raw:
            return list(raw["images"])
        if isinstance(raw, list):
            return raw
    except Exception:
        pass
    return []


def save_stored_images(images: List[Dict[str, Any]]) -> None:
    """Persist reference images to disk atomically."""

    _ensure_cache_dir()
    payload = {"images": images}
    tmp_path = IMAGE_CACHE_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2))
    tmp_path.replace(IMAGE_CACHE_FILE)


__all__ = ["load_stored_images", "save_stored_images"]
