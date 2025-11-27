#!/usr/bin/env python3
"""Rename artifacts using CLIP zero-shot classification.

More accurate than generative vision models for classification tasks.
"""

import asyncio
import io
import os
import re
from pathlib import Path
from typing import Optional

import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel

ARTIFACTS_DIR = Path(os.getenv("KITTY_ARTIFACTS_DIR", "/Users/Shared/KITTY/artifacts"))

# Common 3D model categories for zero-shot classification
CATEGORIES = [
    # Vehicles
    "car", "truck", "motorcycle", "bicycle", "airplane", "helicopter",
    "boat", "ship", "tank", "train", "bus", "spacecraft", "rocket",
    # Animals
    "dog", "cat", "horse", "bird", "fish", "dragon", "dinosaur",
    "elephant", "lion", "tiger", "bear", "wolf", "rabbit", "snake",
    # Characters
    "human figure", "robot", "alien", "monster", "warrior", "knight",
    "soldier", "superhero", "skeleton", "zombie",
    # Objects
    "chair", "table", "lamp", "vase", "cup", "bottle", "box",
    "phone", "computer", "watch", "clock", "camera", "weapon",
    "sword", "gun", "shield", "helmet", "armor",
    # Architecture
    "house", "building", "castle", "tower", "bridge", "monument",
    # Nature
    "tree", "flower", "rock", "mountain", "crystal",
    # Tools
    "hammer", "wrench", "axe", "knife", "tool",
    # Abstract
    "geometric shape", "abstract sculpture", "organic form",
]

# Map categories to filename-friendly versions
CATEGORY_TO_FILENAME = {
    "human figure": "human-figure",
    "geometric shape": "geometric-shape",
    "abstract sculpture": "abstract-form",
    "organic form": "organic-form",
}


class CLIPClassifier:
    """CLIP-based zero-shot image classifier."""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        print(f"Loading CLIP model: {model_name}")
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        print(f"CLIP loaded on {self.device}")

    def classify(
        self,
        image: Image.Image,
        categories: list[str] = CATEGORIES,
        top_k: int = 3,
    ) -> list[tuple[str, float]]:
        """Classify image against categories.

        Returns list of (category, score) tuples, sorted by score descending.
        """
        # Prepare text prompts
        text_prompts = [f"a 3D model of a {cat}" for cat in categories]

        # Process inputs
        inputs = self.processor(
            text=text_prompts,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Get similarity scores
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)

        # Get top-k results
        scores = probs[0].cpu().numpy()
        indexed_scores = [(categories[i], float(scores[i])) for i in range(len(categories))]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)

        return indexed_scores[:top_k]


def render_mesh_preview(mesh_path: Path) -> Image.Image | None:
    """Render a preview image from a mesh file."""
    try:
        import trimesh
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection

        # Load the mesh
        scene = trimesh.load(str(mesh_path))

        if isinstance(scene, trimesh.Scene):
            meshes = list(scene.geometry.values())
            if not meshes:
                return None
            mesh = trimesh.util.concatenate(meshes)
        elif hasattr(scene, 'vertices'):
            mesh = scene
        else:
            return None

        if not hasattr(mesh, 'vertices') or not hasattr(mesh, 'faces'):
            return None

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

        return Image.open(buf)

    except Exception as e:
        print(f"  Failed to render {mesh_path.name}: {e}")
        return None


def sanitize_filename(name: str, max_chars: int = 19) -> str:
    """Convert category to filename-friendly format."""
    # Check for special mappings
    if name in CATEGORY_TO_FILENAME:
        name = CATEGORY_TO_FILENAME[name]

    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip("-")
    return name[:max_chars]


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


def process_file(file_path: Path, classifier: CLIPClassifier) -> bool:
    """Process a single mesh file."""
    print(f"\nProcessing: {file_path.name}")

    print("  Rendering preview...")
    image = render_mesh_preview(file_path)
    if image is None:
        print("  Failed to render")
        return False

    print("  Classifying with CLIP...")
    results = classifier.classify(image, top_k=5)

    print("  Top matches:")
    for cat, score in results:
        print(f"    {cat}: {score:.3f}")

    best_category, best_score = results[0]
    if best_score < 0.05:
        print(f"  Low confidence ({best_score:.3f}), skipping")
        return False

    filename = sanitize_filename(best_category)
    print(f"  Selected: {best_category} -> {filename}")

    new_path = rename_file(file_path, filename)
    if new_path:
        print(f"  Renamed: {file_path.name} -> {new_path.name}")
        return True
    return False


def main():
    print("=" * 60)
    print("Artifact Rename - Using CLIP Zero-Shot Classification")
    print("=" * 60)

    # Initialize CLIP
    classifier = CLIPClassifier()

    # Find all mesh files
    all_files = []
    for pattern in ["*.stl", "stl/*.stl", "*.glb", "glb/*.glb"]:
        all_files.extend(ARTIFACTS_DIR.glob(pattern))

    # Filter to UUID-named files only
    uuid_files = [f for f in all_files if len(f.stem) >= 32]

    if not uuid_files:
        print("\nNo UUID-named files found to rename")
        return

    # Sort GLB first
    uuid_files.sort(key=lambda f: (0 if f.suffix.lower() == ".glb" else 1, f.name))

    print(f"\nFound {len(uuid_files)} file(s) to process")

    success = 0
    for file_path in uuid_files:
        if process_file(file_path, classifier):
            success += 1

    print(f"\n{'=' * 60}")
    print(f"Complete: {success}/{len(uuid_files)} files renamed")
    print("=" * 60)


if __name__ == "__main__":
    main()
