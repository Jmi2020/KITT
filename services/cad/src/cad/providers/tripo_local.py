"""Local TripoSR/InstantMesh runner for offline mesh generation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from common.logging import get_logger

LOGGER = get_logger(__name__)


class LocalMeshRunner:
    def __init__(self, script: Optional[str] = None) -> None:
        self._script = script or "triposr-cli"

    def generate(self, image_path: Path, output_path: Path) -> bool:
        """Invoke local mesh generator (best-effort)."""

        cmd = [self._script, "--input", str(image_path), "--output", str(output_path)]
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                LOGGER.warning("Local mesh runner failed", stderr=proc.stderr)
                return False
            LOGGER.info("Local mesh generated", output=str(output_path))
            return True
        except FileNotFoundError:
            LOGGER.error("Local mesh runner not found", command=self._script)
            return False
