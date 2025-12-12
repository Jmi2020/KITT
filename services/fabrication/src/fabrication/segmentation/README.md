# Mesh Segmentation Module

Technical documentation for the mesh segmentation system.

## Overview

The segmentation system automatically divides oversized 3D models into printable parts that fit within a target printer's build volume. It features:

- **Smart Cut Placement**: Multi-factor scoring for optimal cuts (fit, overhang, visibility)
- **Surface-Preserving Hollowing**: Reduce material while keeping original surface detail
- **Integrated Joints**: Printed pins/holes for easy assembly alignment
- **Multiple Search Algorithms**: Greedy (fast) or beam search (optimal)

## Architecture

```
segmentation/
├── __init__.py              # Public exports
├── schemas.py               # Pydantic/dataclass models
├── engine/
│   ├── base.py              # Abstract SegmentationEngine + scoring methods
│   ├── planar_engine.py     # Main segmentation algorithm
│   └── beam_search.py       # Beam search for optimal cut sequences
├── geometry/
│   ├── mesh_wrapper.py      # MeshWrapper: unified mesh interface
│   └── plane.py             # CuttingPlane representation
├── hollowing/
│   └── sdf_hollower.py      # Voxel + surface shell hollowing
├── joints/
│   ├── base.py              # JointFactory interface
│   ├── dowel.py             # Dowel hole joints
│   └── integrated.py        # Printed pin/hole joints
└── output/
    └── threemf_writer.py    # 3MF export with metadata
```

## Quick Start

```python
from fabrication.segmentation.engine.planar_engine import PlanarSegmentationEngine
from fabrication.segmentation.geometry.mesh_wrapper import MeshWrapper
from fabrication.segmentation.schemas import HollowingStrategy, JointType

# Load mesh
mesh = MeshWrapper(trimesh.load("model.3mf"))

# Configure and run segmentation
engine = PlanarSegmentationEngine(
    build_volume=(300.0, 320.0, 325.0),  # Bambu H2D
    wall_thickness_mm=5.0,
    hollowing_strategy=HollowingStrategy.SURFACE_SHELL,
    joint_type=JointType.INTEGRATED,
)

result = engine.segment(mesh, output_dir="/output/path")
print(f"Created {result.num_parts} parts")
```

## Cut Scoring System

The engine scores each potential cut using a weighted formula:

```
score = fit×0.35 + utilization×0.20 + balance×0.10 + overhang×0.20 + visibility×0.15
```

| Factor | Weight | Description |
|--------|--------|-------------|
| **Fit** | 35% | Do resulting parts fit in build volume? |
| **Utilization** | 20% | How efficiently do parts use build volume? |
| **Balance** | 10% | Are parts roughly equal in size? |
| **Overhang** | 20% | Can parts print with minimal supports? (Phase 1A) |
| **Visibility** | 15% | Is the seam hidden from view? (Phase 1B) |

### Phase 1A: Overhang-Aware Scoring

Each cut candidate is evaluated for printability:
- Tests 6 print orientations (Z-up/down, Y-up/down, X-up/down)
- Returns minimum overhang ratio across orientations
- Configurable threshold (default 30° from vertical)

```python
engine = PlanarSegmentationEngine(
    overhang_threshold_deg=30.0,  # Strict (cleaner surfaces)
    # overhang_threshold_deg=45.0,  # Standard FDM threshold
)
```

### Phase 1B: Seam Visibility Scoring

Prefers cuts on less visible surfaces:
- **Bottom cuts (low Z)**: visibility score = 0.9 (hidden)
- **Back cuts (min Y)**: visibility score = 0.7
- **Front/top cuts**: visibility score = 0.3 (visible)

### Phase 1C: Oblique Cutting Planes

When axis-aligned cuts score poorly, the engine can try oblique cuts:

```python
engine = PlanarSegmentationEngine(
    enable_oblique_cuts=True,           # Enable PCA-based oblique cuts
    oblique_fallback_threshold=0.5,     # Use when axis-aligned < 0.5
)
```

Uses Principal Component Analysis (PCA) to find mesh orientation axes.

## Search Algorithms

### Greedy (Default)

Fast iterative approach - finds and applies the single best cut at each step.

### Beam Search (Phase 2)

Explores multiple cut sequences in parallel for potentially better results:

```python
engine = PlanarSegmentationEngine(
    enable_beam_search=True,
    beam_width=3,              # Parallel paths to explore
    beam_timeout_seconds=60.0, # Max search time
)
```

## Hollowing Strategies

### HOLLOW_THEN_SEGMENT (Default)

Hollow the entire mesh first, then segment. Creates wall panels.

### SEGMENT_THEN_HOLLOW

Segment the solid mesh first, then hollow each piece. Creates hollow boxes.

### SURFACE_SHELL (Best Quality)

Preserves original surface detail while hollowing:

```python
engine = PlanarSegmentationEngine(
    hollowing_strategy=HollowingStrategy.SURFACE_SHELL,
    wall_thickness_mm=5.0,
)
```

**How it works:**
1. Keep original outer surface at full resolution
2. Create inner surface by offsetting vertices along normals
3. Aggressively simplify inner surface (10% of faces - not visible)
4. Boolean subtract inner from outer

**Results (King.3mf example):**
- Original: 578K faces, 84,000 cm³
- Surface shell: 651K faces (578K outer + 58K inner), 13,700 cm³
- Material savings: 83.7%
- Surface detail: 100% preserved

### NONE

No hollowing - segment solid mesh.

## Joint Types

### INTEGRATED (Recommended)

Printed pins on one part, holes on the mating part:
- No external hardware needed
- Self-aligning during assembly
- Configurable pin size

```python
engine = PlanarSegmentationEngine(
    joint_type=JointType.INTEGRATED,
    pin_diameter_mm=5.0,
    pin_height_mm=8.0,
    joint_tolerance_mm=0.25,  # Clearance for fit
)
```

**Note:** Wall thickness must be ≥ pin_diameter + 2mm for structural integrity.

### DOWEL

Creates matching holes on both parts for external dowel pins:
- Requires purchasing dowel pins
- Stronger connection

### NONE

No joints - use adhesive only.

## Configuration Reference

### SegmentationConfig

```python
@dataclass
class SegmentationConfig:
    # Build volume
    build_volume: tuple[float, float, float] = (300.0, 320.0, 325.0)

    # Hollowing
    enable_hollowing: bool = True
    hollowing_strategy: HollowingStrategy = HollowingStrategy.HOLLOW_THEN_SEGMENT
    wall_thickness_mm: float = 10.0
    hollowing_resolution: int = 200  # voxels (for voxel method)
    enable_simplification: bool = True
    simplification_ratio: float = 0.3
    enable_smoothing: bool = False  # Disabled - can cause artifacts

    # Joints
    joint_type: JointType = JointType.INTEGRATED
    joint_tolerance_mm: float = 0.3
    pin_diameter_mm: float = 8.0
    pin_height_mm: float = 10.0

    # Cut optimization (Phase 1)
    overhang_threshold_deg: float = 30.0
    enable_oblique_cuts: bool = False
    oblique_fallback_threshold: float = 0.5

    # Beam search (Phase 2)
    enable_beam_search: bool = False
    beam_width: int = 3
    beam_timeout_seconds: float = 60.0

    # Limits
    max_parts: int = 0  # 0 = auto-calculate
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/segmentation/check` | POST | Check if segmentation needed |
| `/api/segmentation/segment` | POST | Synchronous segmentation |
| `/api/segmentation/segment/async` | POST | Async job for large models |
| `/api/segmentation/jobs/{id}` | GET | Get async job status |
| `/api/segmentation/printers` | GET | List printer configurations |

## Performance

### Hollowing Resolution vs Quality

| Resolution | Time | Quality | Memory |
|------------|------|---------|--------|
| 200 | ~5s | Fast/coarse | ~100MB |
| 500 | ~20s | Medium | ~500MB |
| 1000 | ~60-90s | High | ~1-2GB |

### Surface Shell vs Voxel Hollowing

| Method | Face Count | Surface Detail | Time |
|--------|------------|----------------|------|
| Voxel (res=200) | ~70K | Lost | ~5s |
| Surface Shell | ~650K | Preserved | ~2s |

## Testing

```bash
# Run all segmentation tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/ -v

# Run specific phase tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/test_engine.py::TestOverhangAwareScoring -v

PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/test_engine.py::TestBeamSearchSegmentation -v
```

## Dependencies

**Required:**
- `trimesh`: Mesh loading, boolean operations, marching cubes
- `scipy`: Binary morphology for hollowing
- `numpy`: Array operations
- `manifold3d`: Boolean operations for surface shell + joints

**Optional:**
- `mrmeshpy` (MeshLib): Faster SDF hollowing
- `fast-simplification`: Mesh decimation
