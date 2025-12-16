upi# Segmentation Tool - Complete Reference

> **Purpose**: This document provides complete context for the KITTY fabrication segmentation system, enabling continued development without prior session context.

## Overview

The segmentation tool in `services/fabrication/src/fabrication/segmentation/` breaks large 3D models into printable parts that fit within printer build volumes. It's a sophisticated multi-phase mesh splitting engine with:

- **Unified mesh abstraction** bridging trimesh, MeshLib, and Manifold3D
- **Pluggable segmentation engines** with abstract base class
- **Configurable strategies** for hollowing, cutting, and joints
- **Progressive enhancement** via phased feature rollout

---

## Architecture

### Directory Structure

```
services/fabrication/src/fabrication/segmentation/
├── __init__.py                    # Package exports
├── schemas.py                     # Pydantic data models
├── engine/
│   ├── __init__.py               # Engine exports
│   ├── base.py                   # Abstract SegmentationEngine + scoring
│   ├── planar_engine.py          # MVP implementation (Phase 1)
│   └── beam_search.py            # Phase 2 optimization
├── geometry/
│   ├── __init__.py               # Geometry exports
│   ├── mesh_wrapper.py           # Unified mesh abstraction
│   └── plane.py                  # Cutting plane representation
├── joints/
│   ├── __init__.py               # Joint exports
│   ├── base.py                   # Abstract JointFactory
│   ├── dowel.py                  # External hardware pins
│   └── integrated.py             # Printed pins (no hardware)
├── hollowing/
│   ├── __init__.py               # Hollowing exports
│   └── sdf_hollower.py           # Voxel-based mesh hollowing
└── output/
    ├── __init__.py               # Output exports
    └── threemf_writer.py         # 3MF assembly export
```

### API Routes

Located in `services/fabrication/src/fabrication/routes/segmentation.py`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/segmentation/check` | POST | Analyze if mesh needs segmentation |
| `/api/segmentation/segment` | POST | Synchronous segmentation |
| `/api/segmentation/segment/async` | POST | Background job |
| `/api/segmentation/jobs/{job_id}` | GET | Poll async job status |
| `/api/segmentation/printers` | GET | List printer configurations |

---

## Data Models (schemas.py)

### Core Enums

```python
class JointType(Enum):
    DOWEL = "dowel"              # External cylindrical pins
    INTEGRATED = "integrated"    # Printed pins (no hardware needed)
    DOVETAIL = "dovetail"        # Phase 2 (NOT IMPLEMENTED)
    PYRAMID = "pyramid"          # Phase 2 (NOT IMPLEMENTED)
    NONE = "none"                # Glue only

class HollowingStrategy(Enum):
    HOLLOW_THEN_SEGMENT = "hollow_then_segment"  # Default - hollow first
    SEGMENT_THEN_HOLLOW = "segment_then_hollow"  # Hollow each piece
    SURFACE_SHELL = "surface_shell"              # Preserve surface detail
    NONE = "none"                                 # No hollowing
```

### Key Data Classes

**SegmentationConfig** - Main configuration:
- Build volume constraints (default: 300×320×325mm for Bambu H2D)
- Hollowing: `wall_thickness_mm`, `enable_hollowing`, `hollowing_strategy`, `hollowing_resolution`
- Joints: `joint_type`, `joint_tolerance_mm`, dowel/pin dimensions
- Algorithm: `max_parts` (0=auto), `overhang_threshold_deg`
- Oblique cuts: `enable_oblique_cuts`, `oblique_fallback_threshold`
- Beam search: `enable_beam_search`, `beam_width`, `beam_max_depth`

**CuttingPlane** - Cut representation:
- `origin`: (x, y, z) point on plane
- `normal`: direction vector
- `plane_type`: "vertical_x", "vertical_y", "horizontal", "oblique"
- `seam_area`: calculated intersection area

**JointLocation** - Joint position:
- `position`: (x, y, z) in 3D space
- `diameter_mm`, `depth_mm` (negative for protrusions)
- `part_index`, `normal` (orientation)

**SegmentedPart** - Output part:
- `index`, `name`, `dimensions_mm`, `volume_cm3`
- `file_path`, `minio_uri`
- `joints`: list of JointLocation
- `requires_supports`: bool

**SegmentationResult** - Complete output:
- `success`, `needs_segmentation`, `num_parts`
- `parts`: list of SegmentedPart
- `cut_planes`: list of CuttingPlane
- `combined_3mf_path`, `combined_3mf_uri`
- `hardware_required`: dict (dowels, adhesive quantities)
- `assembly_notes`: step-by-step instructions

---

## Segmentation Engine

### Class Hierarchy

```
SegmentationEngine (abstract) - engine/base.py
├── PlanarSegmentationEngine (MVP) - engine/planar_engine.py
└── BeamSearchSegmenter (Phase 2) - engine/beam_search.py
```

### Internal State Classes (engine/base.py)

**CutCandidate** - Candidate cutting plane with scoring:
```python
@dataclass
class CutCandidate:
    plane: CuttingPlane
    score: float
    resulting_parts: int
    max_overhang_ratio: float = 0.0
    seam_visibility: float = 0.0
    balance_score: float = 0.0
```

**SegmentationState** - Tracks segmentation progress:
```python
@dataclass
class SegmentationState:
    parts: List[MeshWrapper]           # Current mesh parts
    cut_planes: List[CuttingPlane]     # Applied cuts
    iteration: int = 0
    parts_exceeding_volume: int = 0

    def all_parts_fit(build_volume) -> bool
    def count_exceeding(build_volume) -> int
```

**SegmentationJobStatus** - Async job tracking (routes/segmentation.py):
```python
class SegmentationJobStatus(BaseModel):
    job_id: str
    status: str          # pending, running, completed, failed
    progress: float      # 0.0 to 1.0
    result: Optional[SegmentMeshResponse]
    error: Optional[str]
```

### Phase 1A: Greedy Iterative Segmentation

**Algorithm Flow** (in `planar_engine.py`):
1. Check if mesh fits build volume
2. If not, find mesh that exceeds limits most
3. Find best cut using multi-factor scoring
4. Execute cut (boolean subtraction via Manifold3D)
5. Track seam relationships for joint generation
6. Repeat until all parts fit or max_parts reached

**Cut Scoring Formula**:
```
score = fit_score × 0.35
      + utilization_score × 0.20
      + balance × 0.10
      + overhang_score × 0.20
      + visibility_score × 0.15
```

### Phase 1A: Overhang-Aware Scoring

Located in `engine/base.py:228-331`:
- Tests 6 cardinal orientations: Z-up, Z-down, Y-up, Y-down, X-up, X-down
- Returns minimum (best) overhang ratio per part
- Configurable threshold: 30° (strict/clean), 45° (standard FDM)
- Score conversion: `overhang_score = 1.0 - max(ratio_pos, ratio_neg)`

### Phase 1B: Seam Visibility Scoring

Located in `engine/base.py:333-380`:

Heuristic positioning preference:
| Position | Visibility Score | Rating |
|----------|------------------|--------|
| Bottom (low Z) | 0.9 | Very hidden |
| Back (low Y) | 0.7-0.8 | Moderately hidden |
| Side (X axis) | 0.5 | Moderately visible |
| Front (high Y) | 0.2-0.3 | Visible |
| Top (high Z) | 0.2-0.3 | Visible |

**Formulas**:
```python
# Z-axis cuts:
visibility = 0.9 - 0.7 × normalized_position

# Y-axis cuts:
visibility = 0.8 - 0.6 × normalized_position

# X-axis cuts:
visibility = 0.4 + 0.4 × abs(norm_pos - 0.5)
```

### Phase 1C: Oblique Cutting Planes

Located in `engine/planar_engine.py:521-646`:
- Uses PCA (Principal Component Analysis) on mesh vertices
- Finds natural orientation axes based on variance
- Generates cuts perpendicular to principal axes
- Only used as fallback when axis-aligned score < threshold
- Config: `enable_oblique_cuts=True`, `oblique_fallback_threshold=0.5`

### Phase 2: Beam Search (Optional)

Located in `engine/beam_search.py`:
- Maintains multiple candidate solutions (`beam_width`, default 3)
- Explores cut sequences in parallel instead of greedy single-best
- Scores complete paths rather than individual cuts
- Config: `enable_beam_search=True`, `beam_timeout_seconds=60`

---

## Joint Systems

### Dowel Joints (External Hardware)

Located in `joints/dowel.py`:

```python
@dataclass
class DowelConfig:
    diameter_mm: float = 4.0
    depth_mm: float = 10.0
    hole_clearance_mm: float = 0.2     # Extra clearance for fit
    min_joints_per_seam: int = 2
    max_joints_per_seam: int = 6
    target_joint_density: float = 0.002 # joints per mm² seam
```

**Implementation**:
1. Calculate seam area using mesh cross-section
2. Determine joint count: area × density
3. Find positions via Poisson disk sampling
4. Create cylindrical holes via boolean subtraction
5. Pin side: tight fit (diameter = specified)
6. Socket side: loose fit (diameter + clearance)

### Integrated Joints (Printed Pins)

Located in `joints/integrated.py`:

```python
@dataclass
class IntegratedPinConfig:
    pin_diameter_mm: float = 8.0
    pin_height_mm: float = 10.0       # 2mm anchor + 8mm protrusion
    hole_depth_mm: float = 8.0        # Matches protrusion
    hole_clearance_mm: float = 0.3    # Accounts for layer expansion
    taper_angle_deg: float = 2.0      # Slight taper for insertion
```

**Critical Implementation Details**:

1. **Two-pass geometry application**:
   - First: Union all pins onto one part
   - Second: Subtract holes from mating part
   - Prevents holes from cutting through nearby pins

2. **Position determination**:
   - Find intersection of both parts' seam contours
   - Only place joints where BOTH parts have wall material

3. **Normal direction**:
   - Pin normal points FROM part_a TOWARD part_b
   - Hole normal is opposite (points into part_b)
   - Calculated from part centroids relative to cut plane

4. **Pin placement strategy**:
   - Identifies wall midpoints on cut face
   - Places pins at top/bottom/left/right walls
   - Avoids corners (conflicts with other cuts)

5. **Deduplication**:
   - Removes pin/hole conflicts if too close
   - 15mm minimum spacing between joints

---

## Hollowing System

Located in `hollowing/sdf_hollower.py`:

### Strategies

| Strategy | Method | Use Case | Detail Preservation |
|----------|--------|----------|---------------------|
| `SURFACE_SHELL` | Vertex offset + boolean | **Default** - display models, quality prints | ✅ 100% (preserves all surface triangles) |
| `HOLLOW_THEN_SEGMENT` | Voxel SDF | Functional parts, faster processing | ❌ Loses fine detail |
| `SEGMENT_THEN_HOLLOW` | Voxel SDF per piece | Complex internals | ❌ Loses fine detail |
| `NONE` | Skip hollowing | Small models, already hollow | N/A |

### Surface Shell vs Voxel (from commit 3ee88cc)

Test results with King.3mf (578K original faces):
- **Voxel method**: 70K faces output, 89% material savings, loses surface detail
- **Surface shell**: 1.17M faces output, 84% material savings, **preserves 100% detail**

The surface shell approach:
1. Offsets vertices inward along vertex normals by wall thickness
2. Uses manifold3d boolean subtraction (outer - inner) to create shell
3. Preserves all original surface triangles and texture
4. Falls back to voxel method if boolean operation fails (self-intersecting meshes)

### Key Parameters

```python
wall_thickness_mm: float = 2.0        # Min 1.2mm, max 10.0mm

# Surface shell inner surface (not visible - aggressively simplified)
surface_shell_inner_ratio: float = 0.1    # 10% of faces = 90% reduction (default)
surface_shell_inner_min_faces: int = 1000 # Minimum faces for mesh stability

# Voxel method parameters (used for HOLLOW_THEN_SEGMENT, SEGMENT_THEN_HOLLOW)
hollowing_resolution: int = 200       # Voxels per dimension
    # 200 = fast (~5mm voxels for 1m model)
    # 500 = medium (~2mm voxels)
    # 1000+ = high quality (slow)
simplification_ratio: float = 0.3     # Reduce to 30% of faces (voxel only)
enable_smoothing: bool = False        # WARNING: can create "icicles" on voxel output
```

---

## Dependencies

### Core Mesh Processing
- **trimesh**: Primary mesh I/O, analysis, boolean operations
- **manifold3d**: Guaranteed manifold boolean cuts, cylinders
- **mrmeshpy (MeshLib)**: SDF-based hollowing, voxelization
- **numpy**: Numerical computing, linear algebra

### Output & Utilities
- **pyassimp**: 3D model loading (fallback)
- **Shapely**: Polygon operations for joint placement

---

## Configuration Reference

### Full SegmentationConfig

```python
@dataclass
class SegmentationConfig:
    # Build volume (Bambu H2D default)
    build_volume: tuple[float, float, float] = (300.0, 320.0, 325.0)

    # Hollowing
    enable_hollowing: bool = True
    wall_thickness_mm: float = 10.0       # Must be >= pin_diameter for integrated joints
    min_wall_thickness_mm: float = 1.2
    hollowing_strategy: HollowingStrategy = SURFACE_SHELL  # Detail-preserving default
    hollowing_resolution: int = 200
    enable_simplification: bool = True
    simplification_ratio: float = 0.3
    enable_smoothing: bool = False        # Disabled to avoid icicle artifacts
    smooth_iterations: int = 0

    # Joints
    joint_type: JointType = DOWEL         # Default to external hardware
    joint_tolerance_mm: float = 0.3
    dowel_diameter_mm: float = 4.0
    dowel_depth_mm: float = 10.0
    pin_diameter_mm: float = 8.0
    pin_height_mm: float = 10.0

    # Algorithm
    max_parts: int = 0                    # 0 = auto-calculate
    overhang_threshold_deg: float = 30.0  # 30° strict, 45° standard

    # Oblique cuts (Phase 1C)
    enable_oblique_cuts: bool = False
    oblique_fallback_threshold: float = 0.5

    # Beam search (Phase 2)
    enable_beam_search: bool = False
    beam_width: int = 3
    beam_max_depth: int = 10
    beam_timeout_seconds: float = 60.0

    # Output
    output_dir: Optional[str] = None
```

### API Request Defaults (SegmentMeshRequest)

> **Note**: The API request model uses different defaults optimized for typical use cases:

| Field | Config Default | API Default | Reason |
|-------|---------------|-------------|--------|
| `hollowing_strategy` | SURFACE_SHELL | **SURFACE_SHELL** | Detail-preserving (both aligned) |
| `joint_type` | DOWEL | **INTEGRATED** | No-hardware preferred for end users |
| `wall_thickness_mm` | 10.0 | **2.0** | API enforces 1.2-10.0 range |
| `pin_diameter_mm` | 8.0 | **5.0** | Smaller pins for typical prints |
| `pin_height_mm` | 10.0 | **8.0** | Shorter protrusion |
| `enable_smoothing` | False | **True** | Smoother output for general use |
| `smooth_iterations` | 0 | **2** | Light smoothing enabled |
| `hollowing_resolution` | 200 | **1000** | Higher quality for API calls (voxel fallback) |

---

## Tests

### Test Files
- `services/fabrication/tests/conftest.py` - Shared fixtures (mesh generators, temp dirs)
- `services/fabrication/tests/test_engine.py` - Core engine tests
- `services/fabrication/tests/test_schemas.py` - Data model validation
- `services/fabrication/tests/test_geometry.py` - Mesh utilities
- `services/fabrication/tests/test_routes.py` - API endpoints
- `services/fabrication/tests/benchmarks/conftest.py` - Benchmark fixtures
- `services/fabrication/tests/benchmarks/test_performance.py` - Performance
- `services/fabrication/tests/benchmarks/test_cut_quality.py` - Cut quality

### Running Tests
```bash
# All tests
PYTHONPATH=services/fabrication/src:services/common/src python3 -m pytest services/fabrication/tests/ -v

# Unit tests only
PYTHONPATH=services/fabrication/src:services/common/src python3 -m pytest services/fabrication/tests/ -v --ignore=services/fabrication/tests/benchmarks

# Benchmarks only
PYTHONPATH=services/fabrication/src:services/common/src python3 -m pytest services/fabrication/tests/benchmarks/ -v
```

---

## Known Limitations & Improvement Opportunities

### Architecture Limitations

1. **Oblique cuts limited** - Only 3 orientations (one per principal axis), may not find optimal diagonal cuts

2. **Joint positioning probabilistic** - Poisson disk sampling gives different results each run; 15mm spacing is hardcoded

3. **Seam visibility assumptions** - Assumes +Y is front, +Z is up; not orientation-agnostic

4. **Phase 2 features experimental** - Beam search disabled by default; dovetail/pyramid joints not implemented

5. **Multi-cut seam tracking approximate** - For heavily subdivided models, joint positions may be suboptimal

6. **No automatic hollowing resolution** - User must choose; no calculation based on model size

7. **Memory constraints** - No streaming for large high-resolution voxelizations

8. **Surface shell hollowing** - Falls back to voxel for self-intersecting/concave models

### Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Greedy segmentation | ✅ Mature | Default algorithm |
| Overhang analysis | ✅ Mature | 6-orientation testing |
| Seam visibility | ✅ Mature | Heuristic-based |
| Dowel joints | ✅ Mature | External hardware |
| Integrated joints | ✅ Mature | Printed pins |
| SDF hollowing | ✅ Mature | Multiple strategies |
| 3MF export | ✅ Mature | Assembly metadata |
| Oblique cuts | ⚠️ Experimental | PCA-based, optional |
| Beam search | ⚠️ Experimental | Multi-path, optional |
| Dovetail joints | ❌ Not implemented | Phase 2 planned |
| Pyramid joints | ❌ Not implemented | Phase 2 planned |

---

## Development Commands

```bash
# Run fabrication service locally
PYTHONPATH=services/fabrication/src:services/common/src python3 -m uvicorn fabrication.app:app --port 8300

# Run tests
PYTHONPATH=services/fabrication/src:services/common/src python3 -m pytest services/fabrication/tests/ -v

# Lint
ruff check services/fabrication/ --fix
ruff format services/fabrication/
```

---

## Quick Reference: Key File Locations

| Purpose | File |
|---------|------|
| Main engine | `segmentation/engine/planar_engine.py` |
| Scoring functions | `segmentation/engine/base.py:228-380` |
| Data models | `segmentation/schemas.py` |
| API routes | `routes/segmentation.py` |
| Dowel joints | `segmentation/joints/dowel.py` |
| Integrated joints | `segmentation/joints/integrated.py` |
| Hollowing | `segmentation/hollowing/sdf_hollower.py` |
| Mesh abstraction | `segmentation/geometry/mesh_wrapper.py` |
| 3MF export | `segmentation/output/threemf_writer.py` |

---

*Document updated: 2025-12-14*
*For KITTY fabrication service segmentation system*
