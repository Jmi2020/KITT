"""Dependency wiring for the CAD service."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from common.config import settings

from .cycler import CADCycler
from .fallback.freecad_runner import FreeCADRunner
from .providers.tripo_client import TripoClient
from .providers.tripo_local import LocalMeshRunner
from .providers.zoo_client import ZooClient
from .storage.artifact_store import ArtifactStore


@lru_cache(maxsize=1)
def get_artifact_store() -> ArtifactStore:
    return ArtifactStore()


@lru_cache(maxsize=1)
def get_zoo_client() -> ZooClient:
    return ZooClient()


@lru_cache(maxsize=1)
def get_tripo_client() -> Optional[TripoClient]:
    if settings.tripo_api_key:
        return TripoClient()
    return None


@lru_cache(maxsize=1)
def get_local_mesh_runner() -> Optional[LocalMeshRunner]:
    return LocalMeshRunner()


@lru_cache(maxsize=1)
def get_freecad_runner() -> Optional[FreeCADRunner]:
    return FreeCADRunner()


@lru_cache(maxsize=1)
def get_cad_cycler() -> CADCycler:
    return CADCycler(
        zoo_client=get_zoo_client(),
        tripo_client=get_tripo_client(),
        artifact_store=get_artifact_store(),
        local_runner=get_local_mesh_runner(),
        freecad_runner=get_freecad_runner(),
        max_tripo_images=settings.tripo_max_image_refs,
        tripo_model_version=settings.tripo_model_version,
        tripo_texture_quality=settings.tripo_texture_quality,
        tripo_texture_alignment=settings.tripo_texture_alignment,
        tripo_orientation=settings.tripo_orientation,
        tripo_poll_interval=settings.tripo_poll_interval,
        tripo_poll_timeout=settings.tripo_poll_timeout,
        storage_root=Path(os.getenv("KITTY_STORAGE_ROOT", "storage")),
        gateway_internal_url=os.getenv("GATEWAY_INTERNAL_URL"),
        tripo_convert_enabled=settings.tripo_convert_enabled,
        tripo_stl_format=settings.tripo_stl_format,
        tripo_face_limit=settings.tripo_face_limit,
        tripo_unit=settings.tripo_unit,
    )


__all__ = ["get_cad_cycler"]
