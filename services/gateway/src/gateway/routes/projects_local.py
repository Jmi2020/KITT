"""
Local project artifact helpers.

Exposes a simple listing + download endpoint for STL models that live on
the host filesystem. This is used by the Projects UI to surface locally
generated CAD artifacts even when the full projects API/DB is not
available.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Host directory where STL artifacts are stored. Defaults to the container
# mount location for artifacts (compose maps the host's /Users/Shared/KITTY/artifacts
# into /app/storage).
STL_ROOT = Path(os.getenv("KITTY_STL_ROOT", "/app/storage/stl")).expanduser()


def _safe_stl_path(filename: str) -> Path:
    """Return a safe path to an STL file, rejecting traversal attempts."""
    if not filename.lower().endswith(".stl"):
        raise HTTPException(status_code=404, detail="Not an STL file")

    candidate = (STL_ROOT / filename).resolve()
    try:
        if not candidate.is_relative_to(STL_ROOT.resolve()):
            raise HTTPException(status_code=404, detail="File not found")
    except AttributeError:
        # Python <3.9 fallback, though we target 3.11 in this repo.
        root = str(STL_ROOT.resolve())
        if not str(candidate).startswith(root):
            raise HTTPException(status_code=404, detail="File not found")

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return candidate


@router.get("/stl")
async def list_local_stl() -> List[dict]:
    """List STL artifacts available on the host."""
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
    """Serve a local STL artifact for download."""
    path = _safe_stl_path(filename)
    return FileResponse(path, media_type="model/stl", filename=path.name)
