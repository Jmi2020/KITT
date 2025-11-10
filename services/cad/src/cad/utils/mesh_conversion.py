"""Helpers for converting mesh formats."""

from __future__ import annotations

from io import BytesIO
from typing import Optional

try:  # pragma: no cover - optional dependency for conversion
    import trimesh
except ImportError:  # pragma: no cover
    trimesh = None  # type: ignore[assignment]


class MeshConversionError(RuntimeError):
    """Raised when mesh conversion fails."""


def convert_mesh_to_stl(data: bytes, source_format: Optional[str] = None) -> bytes:
    """Convert arbitrary mesh bytes into STL format.

    Parameters
    ----------
    data:
        The mesh bytes (e.g., GLB, GLTF, OBJ).
    source_format:
        Optional hint for trimesh regarding the original format.

    Returns
    -------
    bytes
        STL binary data suitable for 3D printing workflows.
    """

    if not data:
        raise MeshConversionError("Mesh payload is empty")
    if trimesh is None:
        raise MeshConversionError(
            "trimesh is required for conversion but is not installed"
        )

    fmt = (source_format or "glb").lower()
    mesh = trimesh.load(BytesIO(data), file_type=fmt)
    if mesh.is_empty:
        raise MeshConversionError("Loaded mesh is empty")

    exported = mesh.export(file_type="stl")
    if isinstance(exported, bytes):
        return exported
    if isinstance(exported, str):
        return exported.encode("utf-8")
    # trimesh may return bytearray-like objects
    return bytes(exported)


__all__ = ["MeshConversionError", "convert_mesh_to_stl"]
