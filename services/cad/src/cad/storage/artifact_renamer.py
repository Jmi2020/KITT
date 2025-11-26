"""Artifact file renaming with descriptive names."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import structlog

LOGGER = structlog.get_logger(__name__)


class ArtifactRenamer:
    """Rename artifact files with descriptive names."""

    def generate_new_path(
        self,
        old_path: str,
        description: str,
        max_total_chars: int = 28,
    ) -> str:
        """Generate new path with format: {description}_{4-char-hash}.{ext}

        Args:
            old_path: Current file path with UUID name
            description: Descriptive name from vision
            max_total_chars: Maximum total filename length including extension

        Returns:
            New file path string
        """
        path = Path(old_path)
        ext = path.suffix  # .glb or .stl

        # Extract 4-char hash from original UUID filename
        original_stem = path.stem
        hash_suffix = original_stem[:4]

        # Calculate max description length:
        # max_total - 4 (hash) - 1 (underscore) - len(ext)
        max_desc_len = max_total_chars - 4 - 1 - len(ext)
        desc_truncated = description[:max_desc_len]

        new_name = f"{desc_truncated}_{hash_suffix}{ext}"
        new_path = path.parent / new_name

        return str(new_path)

    def rename_file(self, old_path: str, new_path: str) -> Optional[str]:
        """Rename file, handling collisions.

        Args:
            old_path: Current file path
            new_path: Desired new path

        Returns:
            Actual new path (may differ if collision occurred) or None on failure
        """
        try:
            old = Path(old_path)
            new = Path(new_path)

            if not old.exists():
                LOGGER.warning("Source file not found for rename", path=old_path)
                return None

            # Handle collision - add numeric suffix if needed
            final_path = new
            if new.exists():
                base = new.stem
                ext = new.suffix
                counter = 1
                while final_path.exists():
                    final_path = new.parent / f"{base}-{counter}{ext}"
                    counter += 1
                LOGGER.info(
                    "Renamed with collision suffix",
                    original_target=str(new),
                    actual=str(final_path),
                )

            shutil.move(str(old), str(final_path))
            LOGGER.info("Renamed artifact", old=old_path, new=str(final_path))
            return str(final_path)

        except PermissionError:
            LOGGER.error("Permission denied renaming artifact", old=old_path)
            return None
        except Exception as e:
            LOGGER.error("Failed to rename artifact", old=old_path, error=str(e))
            return None
