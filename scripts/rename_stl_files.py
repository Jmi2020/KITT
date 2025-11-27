#!/usr/bin/env python3
"""Rename STL and GLB files using Gemma 3 vision.

Supports copying names from counterpart files (GLB<->STL) when available.
"""

import asyncio
import base64
import io
import os
import re
import sys
from pathlib import Path

import httpx

ARTIFACTS_DIR = Path(os.getenv("KITTY_ARTIFACTS_DIR", "/Users/Shared/KITTY/artifacts"))
VISION_HOST = os.getenv("LLAMACPP_VISION_HOST", "http://localhost:8086")


def render_stl_preview(stl_path: Path) -> bytes | None:
    """Render a preview image from an STL file using matplotlib."""
    try:
        import trimesh
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        # Load the mesh
        mesh = trimesh.load(str(stl_path))

        if not hasattr(mesh, 'vertices') or not hasattr(mesh, 'faces'):
            print(f"  Invalid mesh in {stl_path.name}")
            return None

        # Create matplotlib 3D plot
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='3d')

        vertices = mesh.vertices
        faces = mesh.faces

        # Sample faces if too many
        if len(faces) > 5000:
            indices = np.random.choice(len(faces), 5000, replace=False)
            faces = faces[indices]

        triangles = vertices[faces]
        collection = Poly3DCollection(triangles, alpha=0.8, edgecolor='none')
        collection.set_facecolor([0.5, 0.7, 0.9])
        ax.add_collection3d(collection)

        scale = vertices.flatten()
        ax.auto_scale_xyz(scale, scale, scale)
        ax.view_init(elev=30, azim=45)
        ax.set_axis_off()
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        print(f"  Failed to render {stl_path.name}: {e}")
        return None


def find_renamed_counterpart(file_path: Path) -> str | None:
    """Find a renamed counterpart file (GLB<->STL) and extract description.

    Returns the description portion if found, None otherwise.
    """
    stem = file_path.stem
    ext = file_path.suffix.lower()

    # Only look for counterparts of UUID-named files
    if len(stem) < 32:
        return None

    # Determine counterpart extension and directories to search
    if ext == ".stl":
        counterpart_ext = ".glb"
        search_dirs = [ARTIFACTS_DIR / "glb", ARTIFACTS_DIR]
    else:
        counterpart_ext = ".stl"
        search_dirs = [ARTIFACTS_DIR / "stl", ARTIFACTS_DIR]

    # Look for renamed files with same hash prefix
    hash_prefix = stem[:4]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for f in search_dir.glob(f"*_{hash_prefix}{counterpart_ext}"):
            # Extract description from filename like "description_hash.ext"
            match = re.match(r"(.+)_[a-f0-9]{4}$", f.stem)
            if match:
                return match.group(1)

    return None


async def generate_filename_from_image(image_bytes: bytes, max_chars: int = 19) -> str | None:
    """Call Gemma 3 vision to generate a descriptive filename."""
    b64 = base64.b64encode(image_bytes).decode()
    image_uri = f"data:image/png;base64,{b64}"

    prompt = f"""Generate a short, descriptive filename for this 3D model.
Rules:
- Max {max_chars} characters
- Lowercase only
- Use hyphens between words
- No file extension
- Be specific about what the object is
Return ONLY the filename, nothing else."""

    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": image_uri}},
    ]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{VISION_HOST}/v1/chat/completions",
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

            # Sanitize
            filename = filename.lower().strip().strip("\"'`")
            filename = re.sub(r"[^a-z0-9-]", "-", filename)
            filename = re.sub(r"-+", "-", filename).strip("-")
            return filename[:max_chars]
    except Exception as e:
        print(f"  Vision API error: {e}")
        return None


def rename_file(old_path: Path, description: str) -> Path | None:
    """Rename file to {description}_{4-char-hash}.{ext}"""
    ext = old_path.suffix
    hash_suffix = old_path.stem[:4]
    new_name = f"{description}_{hash_suffix}{ext}"
    new_path = old_path.parent / new_name

    if new_path.exists() and new_path != old_path:
        counter = 1
        base = f"{description}_{hash_suffix}"
        while new_path.exists():
            new_name = f"{base}-{counter}{ext}"
            new_path = old_path.parent / new_name
            counter += 1

    try:
        old_path.rename(new_path)
        return new_path
    except Exception as e:
        print(f"  Failed to rename: {e}")
        return None


def render_glb_preview(glb_path: Path) -> bytes | None:
    """Render a preview image from a GLB file using matplotlib."""
    try:
        import trimesh
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        scene = trimesh.load(str(glb_path))

        if isinstance(scene, trimesh.Scene):
            meshes = list(scene.geometry.values())
            if not meshes:
                print(f"  No meshes found in {glb_path.name}")
                return None
            mesh = trimesh.util.concatenate(meshes)
        else:
            mesh = scene

        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='3d')

        vertices = mesh.vertices
        faces = mesh.faces

        if len(faces) > 5000:
            indices = np.random.choice(len(faces), 5000, replace=False)
            faces = faces[indices]

        triangles = vertices[faces]
        collection = Poly3DCollection(triangles, alpha=0.8, edgecolor='none')
        collection.set_facecolor([0.5, 0.7, 0.9])
        ax.add_collection3d(collection)

        scale = vertices.flatten()
        ax.auto_scale_xyz(scale, scale, scale)
        ax.view_init(elev=30, azim=45)
        ax.set_axis_off()
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        print(f"  Failed to render {glb_path.name}: {e}")
        return None


async def process_file(file_path: Path) -> bool:
    """Process a single STL or GLB file."""
    print(f"\nProcessing: {file_path.name}")
    ext = file_path.suffix.lower()

    # First check for renamed counterpart
    print("  Checking for renamed counterpart...")
    description = find_renamed_counterpart(file_path)
    if description:
        print(f"  Found counterpart with description: {description}")
    else:
        # Render preview and call vision
        print("  No counterpart found, rendering preview...")
        if ext == ".stl":
            image_bytes = render_stl_preview(file_path)
        else:
            image_bytes = render_glb_preview(file_path)

        if not image_bytes:
            return False

        print("  Calling Gemma 3 vision...")
        description = await generate_filename_from_image(image_bytes)
        if not description:
            print("  Vision failed, skipping")
            return False

        print(f"  Generated description: {description}")

    new_path = rename_file(file_path, description)
    if new_path:
        print(f"  Renamed: {file_path.name} -> {new_path.name}")
        return True
    return False


async def main():
    print("=" * 60)
    print("Artifact Rename - Using Gemma 3 Vision")
    print("=" * 60)

    # Find all STL and GLB files
    all_files = []
    for pattern in ["*.stl", "stl/*.stl", "*.glb", "glb/*.glb"]:
        all_files.extend(ARTIFACTS_DIR.glob(pattern))

    # Filter to UUID-named files only (32+ chars means it's a UUID)
    uuid_files = [f for f in all_files if len(f.stem) >= 32]

    if not uuid_files:
        print("\nNo UUID-named files found to rename")
        return

    # Sort GLB files first so STL can copy from renamed GLB
    uuid_files.sort(key=lambda f: (0 if f.suffix.lower() == ".glb" else 1, f.name))

    print(f"\nFound {len(uuid_files)} file(s) to process")
    glb_count = sum(1 for f in uuid_files if f.suffix.lower() == ".glb")
    stl_count = len(uuid_files) - glb_count
    print(f"  GLB: {glb_count}, STL: {stl_count}")

    success = 0
    for file_path in uuid_files:
        if await process_file(file_path):
            success += 1

    print(f"\n{'=' * 60}")
    print(f"Complete: {success}/{len(uuid_files)} files renamed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
