"""
Artifacts API - List and browse generated artifacts.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/cad/artifacts", tags=["artifacts"])

ARTIFACTS_DIR = Path(os.getenv("CAD_ARTIFACTS_DIR", "artifacts"))

# Supported artifact types and their directories
ARTIFACT_TYPES = {
    "glb": "glb",
    "stl": "stl",
    "3mf": "3mf",
    "gcode": "gcode",
    "step": "step",
    "gltf": "gltf",
}


class ArtifactInfo(BaseModel):
    """Information about a single artifact."""
    filename: str
    type: str
    path: str
    download_url: str
    size_bytes: int
    created_at: str
    modified_at: str


class ArtifactListResponse(BaseModel):
    """Response for artifact listing."""
    artifacts: list[ArtifactInfo]
    total: int
    type_filter: str | None


@router.get("/list", response_model=ArtifactListResponse)
async def list_artifacts(
    type: Literal["all", "glb", "stl", "3mf", "gcode", "step", "gltf"] = "all",
    limit: int = 100,
    offset: int = 0,
) -> ArtifactListResponse:
    """
    List artifacts in storage.

    Args:
        type: Filter by artifact type ("all" for all types)
        limit: Maximum number of artifacts to return
        offset: Number of artifacts to skip (for pagination)
    """
    if not ARTIFACTS_DIR.exists():
        return ArtifactListResponse(artifacts=[], total=0, type_filter=type if type != "all" else None)

    artifacts: list[ArtifactInfo] = []

    # Determine which directories to scan
    if type == "all":
        dirs_to_scan = list(ARTIFACT_TYPES.items())
    else:
        if type not in ARTIFACT_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid artifact type: {type}")
        dirs_to_scan = [(type, ARTIFACT_TYPES[type])]

    # Collect all artifacts
    all_artifacts: list[tuple[Path, str]] = []
    for artifact_type, subdir in dirs_to_scan:
        type_dir = ARTIFACTS_DIR / subdir
        if type_dir.exists() and type_dir.is_dir():
            for file_path in type_dir.iterdir():
                if file_path.is_file() and not file_path.name.startswith('.'):
                    all_artifacts.append((file_path, artifact_type))

    # Sort by modification time (newest first)
    all_artifacts.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)

    # Apply pagination
    total = len(all_artifacts)
    paginated = all_artifacts[offset:offset + limit]

    # Build response
    for file_path, artifact_type in paginated:
        stat = file_path.stat()
        artifacts.append(ArtifactInfo(
            filename=file_path.name,
            type=artifact_type,
            path=f"{artifact_type}/{file_path.name}",
            download_url=f"/api/cad/files/{artifact_type}/{file_path.name}",
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
        ))

    return ArtifactListResponse(
        artifacts=artifacts,
        total=total,
        type_filter=type if type != "all" else None,
    )


@router.get("/stats")
async def get_artifact_stats() -> dict:
    """
    Get storage statistics for artifacts.
    """
    if not ARTIFACTS_DIR.exists():
        return {"total_files": 0, "total_size_bytes": 0, "by_type": {}}

    stats = {
        "total_files": 0,
        "total_size_bytes": 0,
        "by_type": {},
    }

    for artifact_type, subdir in ARTIFACT_TYPES.items():
        type_dir = ARTIFACTS_DIR / subdir
        type_stats = {"count": 0, "size_bytes": 0}

        if type_dir.exists() and type_dir.is_dir():
            for file_path in type_dir.iterdir():
                if file_path.is_file() and not file_path.name.startswith('.'):
                    type_stats["count"] += 1
                    type_stats["size_bytes"] += file_path.stat().st_size

        stats["by_type"][artifact_type] = type_stats
        stats["total_files"] += type_stats["count"]
        stats["total_size_bytes"] += type_stats["size_bytes"]

    return stats


@router.delete("/{artifact_type}/{filename}")
async def delete_artifact(artifact_type: str, filename: str) -> dict:
    """
    Delete a specific artifact.
    """
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid artifact type: {artifact_type}")

    file_path = ARTIFACTS_DIR / ARTIFACT_TYPES[artifact_type] / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    # Security check: ensure we're not escaping the artifacts directory
    try:
        file_path.resolve().relative_to(ARTIFACTS_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    file_path.unlink()

    return {"status": "deleted", "filename": filename}
