from __future__ import annotations

__all__ = ["run_programmatic"]


def __getattr__(name: str):
    """Lazy import to avoid loading full agent stack when only importing config."""
    if name == "run_programmatic":
        from kitty_code.core.programmatic import run_programmatic
        return run_programmatic
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
