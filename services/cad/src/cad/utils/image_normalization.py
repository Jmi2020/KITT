"""Ensure reference images use Tripo-supported formats."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

SUPPORTED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}


class ImageNormalizationError(RuntimeError):
    """Raised when image normalization fails."""


@dataclass(frozen=True)
class NormalizedImage:
    data: bytes
    filename: str
    content_type: str


def _sanitize_filename(filename: Optional[str], suffix: str) -> str:
    base = Path(filename or "reference").stem or "reference"
    return f"{base}{suffix}"


def normalize_image_payload(
    data: bytes, filename: Optional[str], content_type: Optional[str]
) -> NormalizedImage:
    """Return bytes/filename/content-type in a Tripo-supported format."""

    if not data:
        raise ImageNormalizationError("Image payload is empty")

    ctype = (content_type or "").lower()
    if ctype in SUPPORTED_CONTENT_TYPES:
        suffix = SUPPORTED_CONTENT_TYPES[ctype]
        sanitized = _sanitize_filename(filename, suffix)
        canonical = "image/jpeg" if ctype == "image/jpg" else ctype
        return NormalizedImage(data=data, filename=sanitized, content_type=canonical)

    # Fallback to inspecting the filename extension if content-type missing
    if not ctype and filename:
        guess = mimetypes.guess_type(filename)[0]
        if guess in SUPPORTED_CONTENT_TYPES:
            suffix = SUPPORTED_CONTENT_TYPES[guess]
            sanitized = _sanitize_filename(filename, suffix)
            return NormalizedImage(
                data=data, filename=sanitized, content_type=guess or "image/jpeg"
            )

    # Convert unsupported formats (gif, bmp, etc.) to PNG
    try:
        image = Image.open(BytesIO(data))
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        converted = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        raise ImageNormalizationError(f"Failed to convert image: {exc}") from exc

    sanitized = _sanitize_filename(filename, ".png")
    return NormalizedImage(
        data=converted,
        filename=sanitized,
        content_type="image/png",
    )


__all__ = ["ImageNormalizationError", "normalize_image_payload", "NormalizedImage"]
