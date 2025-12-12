# Seam Visibility Scoring (Phase 1B)

## Overview

The segmentation engine prefers cuts on less visible surfaces of the model. This places seams where they're less noticeable in the final assembled piece.

## How It Works

### Visibility Heuristics

The engine calculates visibility based on the cut plane position relative to the mesh:

| Cut Location | Visibility Score | Reasoning |
|--------------|------------------|-----------|
| Bottom (low Z) | 0.9 | Hidden when displayed on shelf |
| Back (low Y) | 0.7 | Usually faces wall |
| Sides (X axis) | 0.5 | Partially visible |
| Front (high Y) | 0.3 | Viewer-facing |
| Top (high Z) | 0.3 | Often visible |

### Scoring Integration

Visibility is 15% of the total cut score:

```
score = fit×0.35 + utilization×0.20 + balance×0.10 + overhang×0.20 + visibility×0.15
```

### Calculation Method

From `engine/base.py`:

```python
def calculate_seam_visibility(self, mesh: MeshWrapper, plane: CuttingPlane) -> float:
    """
    Estimate how visible a seam would be (0.0 = very visible, 1.0 = hidden).
    """
    bounds = mesh.bounds
    center = mesh.centroid

    # Normalize plane position within mesh bounds
    if plane.plane_type == "vertical_z":  # Horizontal cut
        z_range = bounds[1][2] - bounds[0][2]
        z_pos = (plane.origin[2] - bounds[0][2]) / z_range
        # Bottom cuts are hidden (score ~0.9), top cuts visible (score ~0.3)
        return 0.9 - 0.6 * z_pos

    elif plane.plane_type == "vertical_y":  # Front/back cut
        y_range = bounds[1][1] - bounds[0][1]
        y_pos = (plane.origin[1] - bounds[0][1]) / y_range
        # Back cuts hidden (score ~0.7), front cuts visible (score ~0.3)
        return 0.7 - 0.4 * y_pos

    else:  # Side cuts (vertical_x)
        return 0.5  # Moderate visibility
```

## Configuration

Visibility scoring is always enabled. The weight can be adjusted by modifying the scoring formula in `planar_engine.py`.

## Example: Statue Segmentation

Consider a standing statue that needs 3 horizontal cuts:

**Without visibility scoring:**
- Cuts placed purely for balance/fit
- Seams may appear at eye level or on prominent features

**With visibility scoring:**
- Prefers cuts near the base (pedestal area)
- Avoids cuts through face/chest region
- Results in less noticeable seams when displayed

## Visual Verification

1. Segment a tall model (like a figure or vase)
2. Check where horizontal cuts are placed
3. Bottom cuts should be preferred over top cuts
4. Back cuts should be preferred over front cuts

## Key Files

| File | Purpose |
|------|---------|
| `engine/base.py:333-380` | `calculate_seam_visibility()` implementation |
| `engine/planar_engine.py:491-498` | Visibility integration in scoring formula |

## Limitations

- Simple heuristic based on position only
- Doesn't analyze actual surface features
- Assumes "front" is +Y direction and "up" is +Z
- May not be optimal for all model orientations
