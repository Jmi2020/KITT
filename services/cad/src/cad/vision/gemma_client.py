"""Gemma 3 Vision client for generating descriptive filenames from thumbnails."""

from __future__ import annotations

import os
import re
from typing import Optional

import httpx
import structlog

LOGGER = structlog.get_logger(__name__)

GEMMA_VISION_HOST = os.getenv("LLAMACPP_VISION_HOST", "http://localhost:8086")


class GemmaVisionClient:
    """Client for Gemma 3 vision model to generate descriptive filenames."""

    def __init__(self, base_url: str = GEMMA_VISION_HOST):
        self.base_url = base_url

    async def generate_filename(
        self,
        thumbnail_url: str,
        user_prompt: Optional[str] = None,
        max_chars: int = 20,
    ) -> Optional[str]:
        """Generate descriptive filename from thumbnail using Gemma 3 vision.

        Args:
            thumbnail_url: URL to the thumbnail image
            user_prompt: Original user request for context
            max_chars: Maximum characters for the description (excluding hash/ext)

        Returns:
            Sanitized filename string or None if generation fails
        """
        system_prompt = f"""Generate a short, descriptive filename for this 3D model.
Rules:
- Max {max_chars} characters
- Lowercase only
- Use hyphens between words
- No file extension
- Be specific about what the object is
Return ONLY the filename, nothing else."""

        context = f"User requested: {user_prompt}" if user_prompt else ""

        content = [
            {"type": "text", "text": f"{system_prompt}\n\n{context}"},
            {"type": "image_url", "image_url": {"url": thumbnail_url}},
        ]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={
                        "model": "gemma-vision",
                        "messages": [{"role": "user", "content": content}],
                        "temperature": 0.3,
                        "max_tokens": 50,
                    },
                )
                response.raise_for_status()
                data = response.json()
                filename = data["choices"][0]["message"]["content"].strip()
                sanitized = self._sanitize_filename(filename, max_chars)
                LOGGER.info(
                    "Generated filename from vision",
                    raw=filename,
                    sanitized=sanitized,
                )
                return sanitized
        except httpx.TimeoutException:
            LOGGER.warning("Vision request timed out", url=self.base_url)
            return None
        except httpx.HTTPStatusError as e:
            LOGGER.warning(
                "Vision API error",
                status=e.response.status_code,
                detail=e.response.text[:200],
            )
            return None
        except Exception as e:
            LOGGER.warning("Vision filename generation failed", error=str(e))
            return None

    def _sanitize_filename(self, name: str, max_chars: int) -> str:
        """Sanitize to lowercase, hyphens only, max length.

        Args:
            name: Raw filename from vision model
            max_chars: Maximum length

        Returns:
            Sanitized filename string
        """
        # Lowercase and strip whitespace
        name = name.lower().strip()
        # Remove quotes that models sometimes add
        name = name.strip("\"'`")
        # Replace non-alphanumeric with hyphens
        name = re.sub(r"[^a-z0-9-]", "-", name)
        # Collapse multiple hyphens
        name = re.sub(r"-+", "-", name)
        # Strip leading/trailing hyphens
        name = name.strip("-")
        # Truncate to max length
        return name[:max_chars]
