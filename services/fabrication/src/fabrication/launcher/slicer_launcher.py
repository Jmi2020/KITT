"""Launch macOS slicer applications."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from common.logging import get_logger

LOGGER = get_logger(__name__)


class SlicerLauncher:
    """Launch slicer applications on macOS."""

    # Application names and bundle identifiers
    APPS = {
        "BambuStudio": "com.bambulab.bambu-studio",
        "ElegySlicer": "com.elegoo.elegyslicer",  # May vary
        "Luban": "com.snapmaker.luban"
    }

    def launch(self, app_name: str, stl_path: Path) -> bool:
        """
        Launch slicer app with STL file on macOS.

        Args:
            app_name: Application name (BambuStudio, ElegySlicer, Luban)
            stl_path: Path to STL file to open

        Returns:
            True if launched successfully

        Raises:
            FileNotFoundError: Slicer app not installed
            RuntimeError: Failed to launch app
        """

        if not stl_path.exists():
            raise FileNotFoundError(f"STL file not found: {stl_path}")

        # Check if app is installed
        if not self._app_exists(app_name):
            raise FileNotFoundError(
                f"{app_name} not installed. "
                f"Download from: {self._get_download_link(app_name)}"
            )

        # Launch app with file
        try:
            subprocess.run(
                ["open", "-a", app_name, str(stl_path)],
                check=True,
                capture_output=True,
                timeout=10
            )
            LOGGER.info("Launched slicer app", app=app_name, file=stl_path.name)
            return True

        except subprocess.CalledProcessError as e:
            LOGGER.error(
                "Failed to launch slicer",
                app=app_name,
                error=e.stderr.decode()
            )
            raise RuntimeError(f"Failed to launch {app_name}: {e.stderr.decode()}")

        except subprocess.TimeoutExpired:
            LOGGER.error("Slicer launch timed out", app=app_name)
            raise RuntimeError(f"Timeout launching {app_name}")

    def _app_exists(self, app_name: str) -> bool:
        """Check if macOS app is installed."""
        try:
            result = subprocess.run(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{self.APPS.get(app_name, app_name)}'"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return bool(result.stdout.strip())
        except Exception:
            # Fallback: try launching and see if it fails
            return True

    def _get_download_link(self, app_name: str) -> str:
        """Get download URL for slicer app."""
        links = {
            "BambuStudio": "https://bambulab.com/en/download",
            "ElegySlicer": "https://www.elegoo.com/pages/3d-printing-user-support",
            "Luban": "https://snapmaker.com/product/snapmaker-luban"
        }
        return links.get(app_name, "Check manufacturer website")
