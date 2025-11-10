"""Shared data models for the CAD service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class ImageReference:
    """Reference metadata for user-selected images."""

    reference_id: Optional[str] = None
    download_url: Optional[str] = None
    storage_uri: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    caption: Optional[str] = None
    friendly_name: Optional[str] = None

    def dedupe_key(self) -> Optional[str]:
        """Key used to avoid submitting duplicate references."""

        return (
            self.storage_uri
            or self.download_url
            or self.source_url
            or self.reference_id
        )


@dataclass(slots=True)
class ReferencePayload:
    """Loaded binary payload for a reference image."""

    data: bytes
    filename: str
    content_type: str
    friendly_name: Optional[str] = None


__all__ = ["ImageReference", "ReferencePayload"]
