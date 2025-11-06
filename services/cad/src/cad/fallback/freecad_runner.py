"""Fallback STEP/DXF generation using FreeCAD scripts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from common.logging import get_logger

LOGGER = get_logger(__name__)


class FreeCADRunner:
    def __init__(self, freecad_cmd: str = "freecadcmd") -> None:
        self._cmd = freecad_cmd

    def run_script(self, script_path: Path, output_path: Path) -> bool:
        cmd = [self._cmd, str(script_path), str(output_path)]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                LOGGER.warning("FreeCAD script failed", stderr=proc.stderr)
                return False
            return True
        except FileNotFoundError:
            LOGGER.error("FreeCAD command not found", command=self._cmd)
            return False
