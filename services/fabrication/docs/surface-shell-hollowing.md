# Surface Shell Hollowing

## Overview

Surface shell hollowing preserves 100% of the original mesh surface detail while creating a hollow interior. Unlike voxel-based hollowing which destroys surface detail through rasterization, surface shell uses vertex normal offset and boolean subtraction.

## Comparison of Hollowing Methods

| Method | Surface Detail | Face Count | Speed | Best For |
|--------|----------------|------------|-------|----------|
| **Voxel** (default) | Lost | Low (~70K) | Medium | Functional parts |
| **Surface Shell** | Preserved | High (~650K) | Fast | Display models |

### Visual Comparison (King.3mf)

| Metric | Original | Voxel (res=200) | Surface Shell |
|--------|----------|-----------------|---------------|
| Faces | 578,052 | 70,868 | 650,692 |
| Volume | 83,975 cm³ | 9,046 cm³ | 13,716 cm³ |
| Material Savings | - | 89.2% | 83.7% |
| Surface Detail | 100% | ~0% | 100% |

## How It Works

### Algorithm

1. **Keep outer surface** at full resolution (original mesh)
2. **Create inner surface** by offsetting each vertex inward along its normal
3. **Simplify inner surface** to 10% of faces (not visible anyway)
4. **Boolean subtract** inner from outer using manifold3d

```python
def _hollow_surface_shell(self, mesh: MeshWrapper) -> HollowingResult:
    tm = mesh.as_trimesh.copy()

    # Step 1: Get vertex normals
    vertex_normals = tm.vertex_normals

    # Step 2: Create inner surface (offset inward)
    inner_vertices = tm.vertices - vertex_normals * wall_thickness
    inner_tm = trimesh.Trimesh(vertices=inner_vertices, faces=tm.faces.copy())

    # Step 3: Simplify inner surface (10% of original)
    inner_target = max(1000, len(tm.faces) // 10)
    inner_tm = inner_tm.simplify_quadric_decimation(face_count=inner_target)

    # Step 4: Boolean subtraction
    outer_manifold = m3d.Manifold(outer_mesh)
    inner_manifold = m3d.Manifold(inner_mesh)
    shell_manifold = outer_manifold - inner_manifold

    return shell_mesh
```

### Inner Surface Simplification

The inner surface is aggressively simplified because:
- **Not visible** - inside the shell
- **Reduces file size** - 578K → 58K faces (90% reduction)
- **Faster boolean** - less geometry to process
- **Same wall thickness** - simplification doesn't affect offset distance

## Configuration

```python
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.schemas import HollowingStrategy

engine = PlanarSegmentationEngine(
    build_volume=(300.0, 320.0, 325.0),
    enable_hollowing=True,
    hollowing_strategy=HollowingStrategy.SURFACE_SHELL,
    wall_thickness_mm=5.0,
)
```

### Available Strategies

| Strategy | Enum Value | Description |
|----------|------------|-------------|
| Hollow then segment | `HOLLOW_THEN_SEGMENT` | Voxel hollow first, then cut (default) |
| Segment then hollow | `SEGMENT_THEN_HOLLOW` | Cut first, then hollow each piece |
| **Surface shell** | `SURFACE_SHELL` | Preserve surface, offset inward |
| None | `NONE` | No hollowing |

## When to Use Surface Shell

### Ideal Use Cases

- **Display models** - statues, figures, decorative items
- **Painted models** - surface texture matters for paint adhesion
- **Detailed sculpts** - fine surface features must be preserved
- **Large format prints** - where detail is visible at full scale

### When Voxel May Be Better

- **Functional parts** - surface detail doesn't matter
- **Very complex internal geometry** - boolean may fail
- **Memory constrained** - voxel uses less memory
- **Need specific wall features** - voxel allows internal structure

## Wall Thickness Considerations

With surface shell hollowing:

1. **Minimum practical:** 3-5mm for structural integrity
2. **With integrated pins:** Must be ≥ pin_diameter + 2mm
3. **Maximum useful:** ~20mm (diminishing returns on material savings)

```python
# Example: 5mm pins require 7mm walls
engine = PlanarSegmentationEngine(
    hollowing_strategy=HollowingStrategy.SURFACE_SHELL,
    wall_thickness_mm=5.0,      # Requested
    pin_diameter_mm=5.0,        # 5mm integrated pins
)
# Engine auto-adjusts: "Wall thickness (5.0mm) too thin for 5.0mm pins. Adjusting to 7.0mm"
```

## Limitations

### Self-Intersecting Inner Surface

For highly concave models, the inner offset surface may self-intersect:

```
Original:          Inner offset (problem):
  ____               ____
 /    \             /    \
|      |    →      |  XX  |  ← Overlapping faces
|  __  |           |  XX  |
|_|  |_|           |_|  |_|
```

**Current behavior:** Falls back to voxel method if boolean fails

### Thin Features

Very thin features (< 2× wall thickness) may become solid or disappear:

```
Feature < 2×wall:    Result:
    |                  |
    |        →         |   ← No hollow interior
    |                  |
```

## Performance

| Mesh Size | Surface Shell | Voxel (res=200) |
|-----------|---------------|-----------------|
| 100K faces | ~0.5s | ~3s |
| 500K faces | ~1.5s | ~5s |
| 1M faces | ~3s | ~8s |

Surface shell is typically **faster** than voxel because:
- No voxelization step
- No marching cubes reconstruction
- Inner simplification is fast
- Boolean is optimized in manifold3d

## Testing

```python
# Quick test
from fabrication.segmentation.hollowing.sdf_hollower import SdfHollower, HollowingConfig
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper

mesh = MeshWrapper(trimesh.load("model.3mf"))
config = HollowingConfig(wall_thickness_mm=5.0)
hollower = SdfHollower(config)

result = hollower.hollow(mesh, strategy="surface_shell")
print(f"Faces: {mesh.face_count} → {result.mesh.face_count}")
print(f"Material savings: {result.material_savings_percent:.1f}%")
```

## Key Files

| File | Purpose |
|------|---------|
| `hollowing/sdf_hollower.py:129-215` | `_hollow_surface_shell()` implementation |
| `schemas.py:21-27` | `HollowingStrategy` enum |
| `engine/planar_engine.py:138-165` | Strategy selection in segment() |

## Troubleshooting

### "Surface shell boolean failed"

**Cause:** Boolean subtraction produced invalid geometry
**Solution:** Falls back to voxel method automatically

### High face count output

**Expected:** Surface shell produces ~110% of original faces (outer + simplified inner)
**If much higher:** Check that inner simplification is working

### Incorrect wall thickness

**Check:** Wall may be auto-adjusted for integrated pins
**Log message:** "Wall thickness (X.Xmm) too thin for X.Xmm pins. Adjusting to X.Xmm"
