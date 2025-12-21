"""
Local project artifact helpers.

Exposes listing + download endpoints for all artifact types that live on
the host filesystem. This is used by the Projects UI to surface locally
generated CAD artifacts even when the full projects API/DB is not
available.

Supports: STL, GLB, GLTF, 3MF, STEP, GCODE, PNG, JPG
"""

from __future__ import annotations

import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Root directory for all artifacts. Defaults to /app/storage which maps to
# the host's /Users/Shared/KITTY/artifacts directory via Docker compose.
ARTIFACTS_ROOT = Path(os.getenv("KITTY_ARTIFACTS_ROOT", "/app/storage")).expanduser()

# Legacy STL root for backwards compatibility
STL_ROOT = Path(os.getenv("KITTY_STL_ROOT", "/app/storage/stl")).expanduser()


class ArtifactCategory(str, Enum):
    """Categories of artifacts for grouping."""

    MESH = "mesh"
    PRINTABLE = "printable"
    CAD = "cad"
    INSTRUCTION = "instruction"
    IMAGE = "image"
    CODE = "code"


# Artifact type definitions: extension(s), media type, category, subdirectory
ARTIFACT_TYPES: Dict[str, Dict] = {
    "stl": {
        "extensions": [".stl"],
        "media_type": "model/stl",
        "category": ArtifactCategory.MESH,
        "subdir": "stl",
    },
    "glb": {
        "extensions": [".glb"],
        "media_type": "model/gltf-binary",
        "category": ArtifactCategory.MESH,
        "subdir": "glb",
    },
    "gltf": {
        "extensions": [".gltf"],
        "media_type": "model/gltf+json",
        "category": ArtifactCategory.MESH,
        "subdir": "gltf",
    },
    "3mf": {
        "extensions": [".3mf"],
        "media_type": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        "category": ArtifactCategory.PRINTABLE,
        "subdir": "3mf",
    },
    "step": {
        "extensions": [".step", ".stp"],
        "media_type": "application/step",
        "category": ArtifactCategory.CAD,
        "subdir": "step",
    },
    "gcode": {
        "extensions": [".gcode"],
        "media_type": "text/plain",
        "category": ArtifactCategory.INSTRUCTION,
        "subdir": "gcode",
    },
    "png": {
        "extensions": [".png"],
        "media_type": "image/png",
        "category": ArtifactCategory.IMAGE,
        "subdir": "images",
    },
    "jpg": {
        "extensions": [".jpg", ".jpeg"],
        "media_type": "image/jpeg",
        "category": ArtifactCategory.IMAGE,
        "subdir": "images",
    },
    "py": {
        "extensions": [".py"],
        "media_type": "text/x-python",
        "category": ArtifactCategory.CODE,
        "subdir": "code",
    },
    "js": {
        "extensions": [".js"],
        "media_type": "text/javascript",
        "category": ArtifactCategory.CODE,
        "subdir": "code",
    },
    "ts": {
        "extensions": [".ts"],
        "media_type": "text/typescript",
        "category": ArtifactCategory.CODE,
        "subdir": "code",
    },
}


class LocalArtifact(BaseModel):
    """Model for a local artifact file."""

    filename: str
    artifactType: str
    category: str
    sizeBytes: int
    modifiedAt: str
    downloadUrl: str
    parentDir: Optional[str] = None  # For gcode: the job UUID


class ArtifactStats(BaseModel):
    """Aggregate statistics for artifacts."""

    totalCount: int
    totalSizeBytes: int
    byType: Dict[str, int]
    byCategory: Dict[str, int]
    mostRecent: Optional[str] = None


SortField = Literal["date", "name", "size", "type"]
SortOrder = Literal["asc", "desc"]


def _safe_artifact_path(artifact_type: str, filename: str) -> Tuple[Path, str]:
    """
    Return a safe path to an artifact file, rejecting traversal attempts.

    Returns tuple of (path, media_type).
    """
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown artifact type: {artifact_type}")

    type_config = ARTIFACT_TYPES[artifact_type]
    valid_exts = type_config["extensions"]

    # Validate extension
    filename_lower = filename.lower()
    if not any(filename_lower.endswith(ext) for ext in valid_exts):
        raise HTTPException(status_code=404, detail=f"Not a valid {artifact_type} file")

    subdir = type_config["subdir"]

    # Special handling for gcode (stored in UUID subdirectories)
    if artifact_type == "gcode":
        return _resolve_gcode_path(filename), type_config["media_type"]

    # Standard path resolution
    type_root = ARTIFACTS_ROOT / subdir
    candidate = (type_root / filename).resolve()
    root_resolved = type_root.resolve()

    # Path traversal check
    if not candidate.is_relative_to(root_resolved):
        raise HTTPException(status_code=404, detail="File not found")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return candidate, type_config["media_type"]


def _resolve_gcode_path(filename: str) -> Path:
    """
    Resolve GCode path from UUID subdirectories.

    GCode files are stored as: gcode/{job-uuid}/{filename}.gcode
    """
    gcode_root = ARTIFACTS_ROOT / "gcode"
    if not gcode_root.exists():
        raise HTTPException(status_code=404, detail="GCode directory not found")

    # Search through job directories
    for uuid_dir in gcode_root.iterdir():
        if uuid_dir.is_dir():
            candidate = uuid_dir / filename
            if candidate.exists() and candidate.is_file():
                # Verify path traversal safety
                if candidate.resolve().is_relative_to(gcode_root.resolve()):
                    return candidate

    raise HTTPException(status_code=404, detail="GCode file not found")


def _scan_artifacts(artifact_type: Optional[str] = None) -> List[LocalArtifact]:
    """Scan the artifacts directory and return all matching files."""
    artifacts: List[LocalArtifact] = []

    types_to_scan = [artifact_type] if artifact_type else list(ARTIFACT_TYPES.keys())

    for atype in types_to_scan:
        if atype not in ARTIFACT_TYPES:
            continue

        config = ARTIFACT_TYPES[atype]
        subdir = config["subdir"]
        type_root = ARTIFACTS_ROOT / subdir

        if not type_root.exists():
            continue

        # Special handling for gcode (nested directories)
        if atype == "gcode":
            for uuid_dir in type_root.iterdir():
                if not uuid_dir.is_dir():
                    continue
                for path in uuid_dir.iterdir():
                    if not path.is_file():
                        continue
                    if any(path.name.lower().endswith(ext) for ext in config["extensions"]):
                        stat = path.stat()
                        artifacts.append(
                            LocalArtifact(
                                filename=path.name,
                                artifactType=atype,
                                category=config["category"].value,
                                sizeBytes=stat.st_size,
                                modifiedAt=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                                downloadUrl=f"/api/projects/artifacts/{atype}/{path.name}",
                                parentDir=uuid_dir.name,
                            )
                        )
        else:
            # Standard flat directory scanning
            for path in type_root.iterdir():
                if not path.is_file():
                    continue
                if any(path.name.lower().endswith(ext) for ext in config["extensions"]):
                    stat = path.stat()
                    artifacts.append(
                        LocalArtifact(
                            filename=path.name,
                            artifactType=atype,
                            category=config["category"].value,
                            sizeBytes=stat.st_size,
                            modifiedAt=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            downloadUrl=f"/api/projects/artifacts/{atype}/{path.name}",
                        )
                    )

    return artifacts


def _sort_artifacts(
    artifacts: List[LocalArtifact], sort_by: SortField, order: SortOrder
) -> List[LocalArtifact]:
    """Sort artifacts by the specified field and order."""
    reverse = order == "desc"

    if sort_by == "date":
        return sorted(artifacts, key=lambda a: a.modifiedAt, reverse=reverse)
    elif sort_by == "name":
        return sorted(artifacts, key=lambda a: a.filename.lower(), reverse=reverse)
    elif sort_by == "size":
        return sorted(artifacts, key=lambda a: a.sizeBytes, reverse=reverse)
    elif sort_by == "type":
        return sorted(artifacts, key=lambda a: a.artifactType, reverse=reverse)

    return artifacts


# =============================================================================
# New Multi-Type Endpoints
# =============================================================================


@router.get("/artifacts", response_model=List[LocalArtifact])
async def list_artifacts(
    type: Optional[str] = Query(None, description="Filter by artifact type (stl, glb, 3mf, etc.)"),
    sort: SortField = Query("date", description="Sort field: date, name, size, type"),
    order: SortOrder = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(100, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
) -> List[LocalArtifact]:
    """
    List all local artifacts with optional filtering and sorting.

    Scans the artifacts directory for all supported file types.
    """
    # Validate type filter if provided
    if type and type not in ARTIFACT_TYPES:
        valid_types = ", ".join(ARTIFACT_TYPES.keys())
        raise HTTPException(
            status_code=400, detail=f"Invalid artifact type '{type}'. Valid types: {valid_types}"
        )

    artifacts = _scan_artifacts(type)
    artifacts = _sort_artifacts(artifacts, sort, order)

    # Apply pagination
    return artifacts[offset : offset + limit]


@router.get("/artifacts/stats", response_model=ArtifactStats)
async def get_artifact_stats() -> ArtifactStats:
    """Get aggregate statistics for all local artifacts."""
    artifacts = _scan_artifacts()

    by_type: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    total_size = 0
    most_recent: Optional[str] = None

    for artifact in artifacts:
        by_type[artifact.artifactType] = by_type.get(artifact.artifactType, 0) + 1
        by_category[artifact.category] = by_category.get(artifact.category, 0) + 1
        total_size += artifact.sizeBytes

        if most_recent is None or artifact.modifiedAt > most_recent:
            most_recent = artifact.modifiedAt

    return ArtifactStats(
        totalCount=len(artifacts),
        totalSizeBytes=total_size,
        byType=by_type,
        byCategory=by_category,
        mostRecent=most_recent,
    )


@router.get("/artifacts/{artifact_type}/{filename}")
async def download_artifact(artifact_type: str, filename: str):
    """Download a specific artifact file by type and filename."""
    path, media_type = _safe_artifact_path(artifact_type, filename)
    return FileResponse(path, media_type=media_type, filename=path.name)


# =============================================================================
# Legacy STL Endpoints (backwards compatibility)
# =============================================================================


def _safe_stl_path(filename: str) -> Path:
    """Return a safe path to an STL file, rejecting traversal attempts."""
    if not filename.lower().endswith(".stl"):
        raise HTTPException(status_code=404, detail="Not an STL file")

    candidate = (STL_ROOT / filename).resolve()
    if not candidate.is_relative_to(STL_ROOT.resolve()):
        raise HTTPException(status_code=404, detail="File not found")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return candidate


@router.get("/stl")
async def list_local_stl() -> List[dict]:
    """List STL artifacts available on the host (legacy endpoint)."""
    if not STL_ROOT.exists():
        return []

    files = []
    for path in STL_ROOT.glob("*.stl"):
        if not path.is_file():
            continue

        stat = path.stat()
        files.append(
            {
                "filename": path.name,
                "sizeBytes": stat.st_size,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "downloadUrl": f"/api/projects/stl/{path.name}",
            }
        )

    files.sort(key=lambda f: f["modifiedAt"], reverse=True)
    return files


@router.get("/stl/{filename}")
async def download_local_stl(filename: str):
    """Serve a local STL artifact for download (legacy endpoint)."""
    path = _safe_stl_path(filename)
    return FileResponse(path, media_type="model/stl", filename=path.name)
