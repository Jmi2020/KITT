"""
Lightweight OUI lookup helper.

Expects a manuf-style file with lines like:
FC-62-B9   (hex)   Raspberry Pi Trading Ltd

Environment:
- OUI_DB_PATH: path to manuf/oui file (default: /app/config/oui.manuf)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

OUI_DB_PATH = os.getenv("OUI_DB_PATH", "/app/config/oui.manuf")


def _parse_oui_file(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if not path.exists():
        return mapping
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(("#", ";")):
                    continue
                # manuf format: "FC-62-B9   (hex)   Raspberry Pi Trading Ltd"
                parts = line.split()
                if len(parts) < 3:
                    continue
                prefix = parts[0].upper().replace("-", ":")
                vendor = " ".join(parts[2:]).strip()
                if len(prefix) == 8:  # e.g., FC:62:B9
                    mapping[prefix] = vendor
    except Exception:
        return {}
    return mapping


class OUILookup:
    def __init__(self, path: Optional[str] = None):
        self.path = Path(path or OUI_DB_PATH)
        self._mapping = _parse_oui_file(self.path)

    def get_vendor(self, mac: Optional[str]) -> Optional[str]:
        if not mac:
            return None
        mac_norm = mac.upper().replace("-", ":")
        prefix = mac_norm[:8]
        return self._mapping.get(prefix)


_DEFAULT_OUI = OUILookup()


def get_vendor(mac: Optional[str]) -> Optional[str]:
    """Convenience function using the default loader."""
    return _DEFAULT_OUI.get_vendor(mac)
