"""Background worker for renaming artifacts using user prompt or vision fallback."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from ..storage.artifact_renamer import ArtifactRenamer
from ..vision.gemma_client import GemmaVisionClient

LOGGER = structlog.get_logger(__name__)

# Words to filter out when extracting filename from prompt
STOPWORDS = {
    "a", "an", "the", "of", "for", "with", "and", "or", "in", "on", "to",
    "create", "make", "generate", "design", "build", "model", "render",
    "3d", "stl", "glb", "file", "please", "can", "you", "i", "want",
    "need", "like", "would", "should", "could", "detailed", "simple",
    "realistic", "stylized", "low", "poly", "high", "resolution",
}


def extract_filename_from_prompt(prompt: str, max_chars: int = 19) -> Optional[str]:
    """Extract descriptive filename from user prompt.

    Filters stopwords and extracts meaningful keywords.

    Args:
        prompt: User's generation prompt
        max_chars: Maximum filename length

    Returns:
        Sanitized filename or None if extraction fails
    """
    if not prompt:
        return None

    # Lowercase and extract words
    words = re.findall(r"[a-z]+", prompt.lower())

    # Filter stopwords and short words
    keywords = [w for w in words if w not in STOPWORDS and len(w) > 2]

    if not keywords:
        return None

    # Build filename from keywords, respecting max_chars
    filename = ""
    for word in keywords:
        candidate = f"{filename}-{word}" if filename else word
        if len(candidate) <= max_chars:
            filename = candidate
        else:
            break  # Stop adding words when we'd exceed limit

    return filename if filename else None


class ArtifactRenameWorker:
    """Background worker to rename artifacts using prompt extraction or vision fallback."""

    def __init__(self):
        self.vision_client = GemmaVisionClient()
        self.renamer = ArtifactRenamer()
        self._enabled = os.getenv("ARTIFACT_RENAME_ENABLED", "true").lower() == "true"

    async def process_artifact(
        self,
        glb_location: Optional[str],
        stl_location: Optional[str],
        thumbnail_url: Optional[str],
        user_prompt: Optional[str],
    ) -> Dict[str, Any]:
        """Process and rename artifact files.

        Args:
            glb_location: Path to GLB file (or None)
            stl_location: Path to STL file (or None)
            thumbnail_url: URL to thumbnail image for vision analysis
            user_prompt: Original user request for context

        Returns:
            Dict with success status and new file paths
        """
        result: Dict[str, Any] = {
            "success": False,
            "glb_new": None,
            "stl_new": None,
            "description": None,
        }

        if not self._enabled:
            LOGGER.debug("Artifact renaming disabled via ARTIFACT_RENAME_ENABLED")
            return result

        if not thumbnail_url:
            LOGGER.warning("No thumbnail URL provided for rename")
            return result

        # Check if at least one file exists
        glb_exists = glb_location and Path(glb_location).exists()
        stl_exists = stl_location and Path(stl_location).exists()

        if not glb_exists and not stl_exists:
            LOGGER.warning(
                "No artifact files found for rename",
                glb=glb_location,
                stl=stl_location,
            )
            return result

        # Strategy 1: Extract filename from user prompt (most accurate)
        description = extract_filename_from_prompt(user_prompt, max_chars=19)
        if description:
            LOGGER.info(
                "Extracted filename from prompt",
                prompt=user_prompt,
                description=description,
            )
        else:
            # Strategy 2: Fall back to vision analysis
            if thumbnail_url:
                LOGGER.info("No prompt available, falling back to vision")
                description = await self.vision_client.generate_filename(
                    thumbnail_url=thumbnail_url,
                    user_prompt=user_prompt,
                    max_chars=19,  # Leave room for _hash.ext (28 - 4 - 1 - 4 = 19)
                )

        if not description:
            LOGGER.warning(
                "Failed to generate filename from prompt or vision, keeping UUID",
                prompt=user_prompt,
                thumbnail=thumbnail_url,
            )
            return result

        result["description"] = description
        LOGGER.info("Generated description for artifact", description=description)

        # Rename GLB file
        if glb_exists:
            new_glb = self.renamer.generate_new_path(glb_location, description)
            actual_new = self.renamer.rename_file(glb_location, new_glb)
            if actual_new:
                result["glb_new"] = actual_new

        # Rename STL file (use same description for consistency)
        if stl_exists:
            new_stl = self.renamer.generate_new_path(stl_location, description)
            actual_new = self.renamer.rename_file(stl_location, new_stl)
            if actual_new:
                result["stl_new"] = actual_new

        result["success"] = bool(result["glb_new"] or result["stl_new"])

        if result["success"]:
            LOGGER.info(
                "Artifact rename complete",
                description=description,
                glb_new=result["glb_new"],
                stl_new=result["stl_new"],
            )

        return result


# Global worker instance (singleton pattern)
_worker: Optional[ArtifactRenameWorker] = None


def get_rename_worker() -> ArtifactRenameWorker:
    """Get or create the singleton rename worker instance."""
    global _worker
    if _worker is None:
        _worker = ArtifactRenameWorker()
    return _worker


async def handle_artifact_saved(event_data: Dict[str, Any]) -> Dict[str, Any]:
    """Event handler for artifact saved events.

    Called asynchronously after artifacts are saved to trigger
    vision-based renaming.

    Args:
        event_data: Dict containing glb_location, stl_location,
                   thumbnail, and prompt

    Returns:
        Result dict from worker processing
    """
    worker = get_rename_worker()
    return await worker.process_artifact(
        glb_location=event_data.get("glb_location"),
        stl_location=event_data.get("stl_location"),
        thumbnail_url=event_data.get("thumbnail"),
        user_prompt=event_data.get("prompt"),
    )
