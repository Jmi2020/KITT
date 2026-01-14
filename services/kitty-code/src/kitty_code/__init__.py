from __future__ import annotations

from pathlib import Path

KITTY_CODE_ROOT = Path(__file__).parent
# Alias for compatibility with upstream vibe code
VIBE_ROOT = KITTY_CODE_ROOT
__version__ = "0.2.0"  # Reset version for vanilla base
