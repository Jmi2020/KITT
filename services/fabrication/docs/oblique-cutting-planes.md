# Oblique Cutting Planes (Phase 1C)

## Overview

When axis-aligned cuts (X, Y, Z) produce poor results, the engine can generate oblique cutting planes based on the mesh's principal axes using PCA (Principal Component Analysis).

## When to Use

Oblique cuts are most useful for:
- Diagonal meshes that don't align with world axes
- Elongated shapes at odd angles
- Models where axis-aligned cuts create excessive parts

## How It Works

### 1. Principal Component Analysis

The engine analyzes mesh vertices to find natural axes:

```python
def _compute_principal_axes(self, mesh: MeshWrapper) -> np.ndarray:
    """Use PCA to find mesh principal axes."""
    vertices = mesh.vertices
    centered = vertices - vertices.mean(axis=0)
    covariance = np.cov(centered.T)
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)

    # Sort by eigenvalue (largest = primary axis)
    order = np.argsort(eigenvalues)[::-1]
    return eigenvectors[:, order]
```

### 2. Oblique Plane Generation

For each principal axis, generate cutting planes perpendicular to it:

```python
def _generate_oblique_cuts(self, mesh: MeshWrapper) -> List[CutCandidate]:
    principal_axes = self._compute_principal_axes(mesh)
    candidates = []

    for axis in principal_axes.T:
        # Generate cuts at different positions along this axis
        for offset in [-0.3, 0.0, 0.3]:  # Relative positions
            plane = CuttingPlane(
                origin=mesh.centroid + axis * offset * mesh_extent,
                normal=tuple(axis),
                plane_type="oblique"
            )
            candidates.append(self._score_candidate(mesh, plane))

    return candidates
```

### 3. Fallback Mechanism

Oblique cuts only activate when axis-aligned cuts score poorly:

```python
if best_axis_aligned_score < self.config.oblique_fallback_threshold:
    oblique_candidates = self._generate_oblique_cuts(mesh)
    all_candidates = axis_aligned_candidates + oblique_candidates
    best = max(all_candidates, key=lambda c: c.score)
```

## Configuration

```python
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine

engine = PlanarSegmentationEngine(
    build_volume=(256, 256, 256),
    enable_oblique_cuts=True,           # Enable the feature
    oblique_fallback_threshold=0.5,     # Use when axis-aligned < 0.5
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_oblique_cuts` | `False` | Feature toggle |
| `oblique_fallback_threshold` | `0.5` | Score threshold for fallback |

## Example: Diagonal Beam

Consider a beam oriented at 45° to all axes:

```
    /
   /
  /    <- 45° diagonal beam
 /
/
```

**Axis-aligned cuts:** Would create many small triangular parts

**Oblique cuts:** PCA finds the beam's long axis, cuts perpendicular to it, creates clean rectangular cross-sections

## Testing

```bash
# Run oblique cut tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/test_engine.py::TestObliqueCuttingPlanes -v
```

### Test Cases

| Test | Purpose |
|------|---------|
| `test_oblique_cuts_disabled_by_default` | Feature is opt-in |
| `test_oblique_cuts_can_be_enabled` | Config works |
| `test_pca_finds_principal_axes` | PCA algorithm correct |
| `test_oblique_cuts_have_valid_scores` | Scoring works for oblique |
| `test_oblique_only_used_when_axis_aligned_poor` | Fallback logic |

## CuttingPlane API

```python
from fabrication.segmentation.geometry.plane import CuttingPlane

# From spherical coordinates (theta=azimuth, phi=elevation)
plane = CuttingPlane.from_spherical(
    theta=45.0,    # degrees from X axis
    phi=30.0,      # degrees from XY plane
    origin=(0, 0, 0)
)

# From arbitrary normal vector
plane = CuttingPlane.from_normal(
    normal=(0.707, 0.707, 0),  # 45° in XY plane
    origin=mesh.centroid
)
```

## Key Files

| File | Purpose |
|------|---------|
| `geometry/plane.py:50-85` | `from_spherical()`, `from_normal()` factories |
| `engine/planar_engine.py:328-380` | `_generate_oblique_cuts()` |
| `engine/planar_engine.py:248-270` | `_compute_principal_axes()` |
| `schemas.py:110-112` | Config parameters |

## Limitations

- PCA may not find optimal cuts for all shapes
- Only 3 oblique orientations tested (one per principal axis)
- Increases computation time when enabled
- May create cuts that are harder to assemble (non-flat mating surfaces)
