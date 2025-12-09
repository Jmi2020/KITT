# Overhang-Aware Cut Scoring (Phase 1A)

## Overview

The segmentation engine now scores cutting planes based on how well the resulting parts can be printed with minimal overhangs. Parts are evaluated across 6 print orientations to find the optimal placement.

## How It Works

### 1. Cut Candidate Generation

When evaluating where to cut a mesh, the engine generates candidates along each axis (X, Y, Z) at various positions. Each candidate is scored using:

```
score = fit×0.40 + utilization×0.25 + balance×0.15 + overhang×0.20
```

| Factor | Weight | Description |
|--------|--------|-------------|
| Fit | 40% | Do resulting parts fit in build volume? |
| Utilization | 25% | How efficiently do parts use build volume? |
| Balance | 15% | Are parts roughly equal in size? |
| **Overhang** | **20%** | Can parts print with minimal overhangs? |

### 2. Overhang Estimation (Pre-Cut)

Before actually cutting the mesh, the engine estimates overhangs for each potential result:

1. **Identify faces on each side** of the proposed cut plane using face centroids
2. **Test 6 cardinal orientations** for printing:
   - Z-up (original)
   - Z-down (flipped)
   - Y-up / Y-down (on side)
   - X-up / X-down (on other side)
3. **Return minimum overhang ratio** across all orientations

This means a cut that produces a part with 45° overhangs in one orientation may score well if the part can be rotated to print cleanly.

### 3. Overhang Detection

A face is considered an "overhang" if:
- It faces downward (away from build plate)
- Its angle from vertical exceeds the threshold (default: 30°)

```
overhang_ratio = overhang_area / total_area
overhang_score = 1.0 - max(overhang_positive, overhang_negative)
```

## Configuration

### Overhang Threshold

```python
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine

# Strict threshold (30°) - cleaner surfaces, more supports needed
engine = PlanarSegmentationEngine(
    build_volume=(256, 256, 256),
    overhang_threshold_deg=30.0,  # Default
)

# Standard FDM threshold (45°) - allows more overhang
engine = PlanarSegmentationEngine(
    build_volume=(256, 256, 256),
    overhang_threshold_deg=45.0,
)
```

## Testing the Feature

### Quick Test via Python

```python
import trimesh
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper
from fabrication.segmentation.geometry.plane import CuttingPlane

# Load a mesh
mesh = trimesh.load("/path/to/model.stl")
wrapper = MeshWrapper(mesh)

# Create engine
engine = PlanarSegmentationEngine(
    build_volume=(256, 256, 256),
    overhang_threshold_deg=30.0,
)

# Check overhang ratio for the whole mesh
ratio = engine.calculate_overhang_ratio(wrapper, threshold_angle=30.0)
print(f"Mesh overhang ratio: {ratio:.2%}")

# Estimate overhangs for a potential cut
plane = CuttingPlane.vertical_x(100.0)  # Cut at X=100
overhang_pos = engine.estimate_part_overhangs(wrapper, plane, "positive", 30.0)
overhang_neg = engine.estimate_part_overhangs(wrapper, plane, "negative", 30.0)
print(f"Positive side min overhang: {overhang_pos:.2%}")
print(f"Negative side min overhang: {overhang_neg:.2%}")
```

### Test via CLI

```bash
# Default 30° threshold (strict, cleaner surfaces)
kitt segment model.3mf --printer bamboo_h2d --yes

# Standard FDM 45° threshold (allows more overhang)
kitt segment model.3mf --printer bamboo_h2d --overhang-threshold 45 --yes

# With short flag
kitt segment model.3mf -p bamboo_h2d -o 30 -y
```

### Test via API

```bash
curl -X POST http://localhost:8002/segmentation/segment \
  -H "Content-Type: application/json" \
  -d '{
    "mesh_path": "/path/to/large_model.3mf",
    "printer_id": "bamboo_h2d",
    "joint_type": "integrated",
    "enable_hollowing": true,
    "overhang_threshold_deg": 30.0
  }'
```

### Run Tests

```bash
# Run Phase 1A specific tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/test_engine.py::TestOverhangAwareScoring -v

# Run full test suite
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/ -v
```

## Visual Verification

To verify the engine is selecting cuts that minimize overhangs:

1. **Segment a model with diagonal surfaces** (like a ramp or wedge)
2. **Check each resulting part** - it should be orientable to print with minimal support
3. **Compare cuts** - the engine should prefer cuts that create flat-bottomed parts over cuts that create parts with steep undersides

## Key Files

| File | Purpose |
|------|---------|
| `engine/base.py:185-227` | `calculate_overhang_ratio()` - analyzes face normals |
| `engine/base.py:228-331` | `estimate_part_overhangs()` - tests 6 orientations |
| `engine/planar_engine.py:244-326` | `_generate_axis_cuts()` - integrates overhang scoring |
| `schemas.py:93-94` | `overhang_threshold_deg` config parameter |

## Example: Diagonal Mesh

Consider a triangular prism with a 45° sloped face:

```
    /|
   / |
  /  |  <- 45° face (potential overhang)
 /   |
/____|
```

**Without orientation optimization:**
- Printing as-is requires supports for the 45° face

**With orientation optimization:**
- The engine tests rotating 90° so the diagonal becomes vertical
- Overhang ratio drops from ~30% to ~0%
- This cut scores higher than alternatives that don't allow clean reorientation
