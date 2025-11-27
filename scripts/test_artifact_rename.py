#!/usr/bin/env python3
"""Test script to rename existing artifacts using Gemma 3 vision.

For existing files without thumbnails, this script renders a preview
from GLB files and uses that for vision-based naming.
"""

import asyncio
import base64
import io
import os
import sys
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

ARTIFACTS_DIR = Path(os.getenv("KITTY_ARTIFACTS_DIR", "/Users/Shared/KITTY/artifacts"))
VISION_HOST = os.getenv("LLAMACPP_VISION_HOST", "http://localhost:8086")


def render_glb_preview(glb_path: Path) -> bytes | None:
    """Render a preview image from a GLB file using matplotlib (headless)."""
    try:
        import trimesh
        import numpy as np
        from PIL import Image
        import matplotlib
        matplotlib.use('Agg')  # Headless backend
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        # Load the mesh
        scene = trimesh.load(str(glb_path))

        # Handle both single mesh and scene
        if isinstance(scene, trimesh.Scene):
            meshes = list(scene.geometry.values())
            if not meshes:
                print(f"  No meshes found in {glb_path.name}")
                return None
            mesh = trimesh.util.concatenate(meshes)
        else:
            mesh = scene

        # Create matplotlib 3D plot
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection='3d')

        # Get vertices and faces
        vertices = mesh.vertices
        faces = mesh.faces

        # Sample faces if too many (for performance)
        if len(faces) > 5000:
            indices = np.random.choice(len(faces), 5000, replace=False)
            faces = faces[indices]

        # Create collection of triangles
        triangles = vertices[faces]
        collection = Poly3DCollection(triangles, alpha=0.8, edgecolor='none')
        collection.set_facecolor([0.5, 0.7, 0.9])  # Light blue color
        ax.add_collection3d(collection)

        # Set axis limits
        scale = vertices.flatten()
        ax.auto_scale_xyz(scale, scale, scale)

        # Better viewing angle
        ax.view_init(elev=30, azim=45)
        ax.set_xlabel('')
        ax.set_ylabel('')
        ax.set_zlabel('')
        ax.set_axis_off()
        ax.set_facecolor('white')
        fig.patch.set_facecolor('white')

        # Render to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        print(f"  Failed to render {glb_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_filename_from_image(image_bytes: bytes, max_chars: int = 19) -> str | None:
    """Call Gemma 3 vision to generate a descriptive filename."""
    # Encode image as base64 data URI
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
            return sanitize_filename(filename, max_chars)
    except Exception as e:
        print(f"  Vision API error: {e}")
        return None


def sanitize_filename(name: str, max_chars: int) -> str:
    """Sanitize to lowercase, hyphens only, max length."""
    import re
    name = name.lower().strip()
    name = name.strip("\"'`")
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name[:max_chars]


def rename_file(old_path: Path, description: str) -> Path | None:
    """Rename file to {description}_{4-char-hash}.{ext}"""
    ext = old_path.suffix
    hash_suffix = old_path.stem[:4]

    # Max 28 chars total: desc (19) + _ (1) + hash (4) + ext (4)
    new_name = f"{description}_{hash_suffix}{ext}"
    new_path = old_path.parent / new_name

    # Handle collision
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


async def process_glb_file(glb_path: Path) -> bool:
    """Process a single GLB file: render, analyze, rename."""
    print(f"\nProcessing: {glb_path.name}")

    # Render preview
    print("  Rendering preview...")
    image_bytes = render_glb_preview(glb_path)
    if not image_bytes:
        print("  Failed to render preview, skipping")
        return False

    # Generate filename from vision
    print("  Calling Gemma 3 vision...")
    description = await generate_filename_from_image(image_bytes)
    if not description:
        print("  Vision failed to generate filename, skipping")
        return False

    print(f"  Generated description: {description}")

    # Rename GLB file
    new_glb = rename_file(glb_path, description)
    if new_glb:
        print(f"  Renamed GLB: {glb_path.name} -> {new_glb.name}")

    # Look for matching STL file
    stl_dir = glb_path.parent.parent / "stl"
    if stl_dir.exists():
        # Find STL with similar timestamp or UUID pattern
        glb_uuid = glb_path.stem
        for stl_file in stl_dir.glob("*.stl"):
            # If STL was created around the same time, rename it too
            stl_uuid = stl_file.stem
            # Check if UUIDs share a timestamp window (within 60 seconds)
            if abs(glb_path.stat().st_mtime - stl_file.stat().st_mtime) < 60:
                new_stl = rename_file(stl_file, description)
                if new_stl:
                    print(f"  Renamed STL: {stl_file.name} -> {new_stl.name}")
                break

    return True


async def main():
    print("=" * 60)
    print("Artifact Rename Test - Using Gemma 3 Vision")
    print("=" * 60)

    # Check vision service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{VISION_HOST}/health")
            if response.status_code != 200:
                print(f"Vision service not healthy: {response.status_code}")
                return
    except Exception as e:
        print(f"Vision service not available: {e}")
        return

    print(f"\nVision service: {VISION_HOST} [OK]")
    print(f"Artifacts dir:  {ARTIFACTS_DIR}")

    # Find GLB files
    glb_dir = ARTIFACTS_DIR / "glb"
    if not glb_dir.exists():
        print(f"\nNo glb directory found at {glb_dir}")
        return

    glb_files = list(glb_dir.glob("*.glb"))
    if not glb_files:
        print("\nNo GLB files found to process")
        return

    print(f"\nFound {len(glb_files)} GLB file(s) to process")

    # Process each file
    success_count = 0
    for glb_path in glb_files:
        # Skip already renamed files (those without full UUID names)
        if len(glb_path.stem) < 32:
            print(f"\nSkipping {glb_path.name} (already renamed)")
            continue

        if await process_glb_file(glb_path):
            success_count += 1

    print(f"\n{'=' * 60}")
    print(f"Complete: {success_count}/{len(glb_files)} files renamed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
