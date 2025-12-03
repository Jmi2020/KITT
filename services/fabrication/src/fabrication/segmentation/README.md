# Mesh Segmentation Module

Technical documentation for the mesh segmentation system.

## Architecture

```
segmentation/
├── __init__.py              # Public exports
├── schemas.py               # Pydantic/dataclass models
├── engine/
│   ├── base.py              # Abstract SegmentationEngine
│   └── planar_engine.py     # Axis-aligned planar cutting
├── geometry/
│   └── mesh_wrapper.py      # MeshWrapper: unified mesh interface
├── hollowing/
│   └── sdf_hollower.py      # SDF-based mesh hollowing
├── joints/
│   ├── base.py              # JointFactory interface
│   ├── dowel.py             # Dowel hole joints
│   └── integrated.py        # Printed pin/hole joints
└── output/
    └── threemf_writer.py    # 3MF export with metadata
```

## Core Components

### MeshWrapper (`geometry/mesh_wrapper.py`)

Unified interface for mesh operations supporting multiple backends:
- **trimesh**: Primary backend for mesh operations
- **MeshLib (mrmeshpy)**: Optional, used for SDF hollowing when available

Key features:
- Automatic unit detection from 3MF files
- Lazy conversion between backends
- Boolean operations (difference for joint holes)
- Bounding box, volume, dimension calculations

```python
mesh = MeshWrapper("/path/to/model.3mf")
print(f"Dimensions: {mesh.dimensions} mm")
print(f"Volume: {mesh.volume_cm3} cm³")

# Boolean subtraction
mesh_with_holes = mesh.boolean_difference(cylinder_mesh)
```

### PlanarSegmentationEngine (`engine/planar_engine.py`)

Main segmentation algorithm using iterative axis-aligned cuts:

1. **Hollowing** (if enabled): Create shell using SdfHollower
2. **Auto max_parts**: Calculate based on mesh/build volume ratio
3. **Iterative cutting**: Cut largest oversized part until all fit
4. **Joint application**: Add pins/holes to cut seams
5. **Export**: Write parts as 3MF files

```python
config = SegmentationConfig(
    build_volume=(300.0, 320.0, 325.0),  # Bambu H2D
    wall_thickness_mm=10.0,
    hollowing_resolution=1000,
    joint_type=JointType.INTEGRATED,
)

engine = PlanarSegmentationEngine(config)
result = engine.segment(mesh, output_dir="/output/path")
```

### SdfHollower (`hollowing/sdf_hollower.py`)

Voxel-based mesh hollowing:

1. **Voxelize** mesh at specified resolution
2. **Fill interior** using `scipy.ndimage.binary_fill_holes`
3. **Erode** to create wall thickness
4. **Extract shell** as `filled & ~eroded`
5. **Convert back** to mesh via marching cubes

Key config:
- `voxels_per_dim`: Resolution (200=fast, 1000=high quality)
- `wall_thickness_mm`: Target shell thickness

### Joint Factories (`joints/`)

**IntegratedJointFactory**: Creates printed pins on one part, holes on mating part
- Places joints in overlap region of seam contours
- Filters positions too close to edges
- Determines pin/hole assignment based on distance to cut plane

**DowelJointFactory**: Creates matching holes on both parts for external pins

## Data Flow

```
Input 3MF/STL
    ↓
MeshWrapper (load + unit conversion)
    ↓
SdfHollower (optional hollowing)
    ↓
PlanarSegmentationEngine (iterative cutting)
    ↓
JointFactory (add pins/holes)
    ↓
ThreeMFWriter (export parts)
    ↓
Output 3MF files
```

## Configuration

### SegmentationConfig

```python
@dataclass
class SegmentationConfig:
    build_volume: tuple[float, float, float] = (300.0, 320.0, 325.0)
    wall_thickness_mm: float = 10.0
    enable_hollowing: bool = True
    hollowing_strategy: HollowingStrategy = HollowingStrategy.HOLLOW_THEN_SEGMENT
    hollowing_resolution: int = 1000  # voxels per dimension
    joint_type: JointType = JointType.INTEGRATED
    joint_tolerance_mm: float = 0.3
    pin_diameter_mm: float = 8.0
    pin_height_mm: float = 10.0
    max_parts: int = 0  # 0 = auto-calculate
```

### HollowingConfig

```python
@dataclass
class HollowingConfig:
    wall_thickness_mm: float = 2.0
    min_wall_thickness_mm: float = 1.2
    voxel_size_mm: float = 0.5
    voxels_per_dim: int = 200  # overrides voxel_size_mm if > 0
```

## API Integration

Routes are defined in `routes/segmentation.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/segmentation/check` | POST | Check if segmentation needed |
| `/api/segmentation/segment` | POST | Synchronous segmentation |
| `/api/segmentation/segment/async` | POST | Async job for large models |
| `/api/segmentation/jobs/{id}` | GET | Get async job status |
| `/api/segmentation/printers` | GET | List printer configs |

## Performance Considerations

### Memory Usage

| Resolution | Voxels | Memory (1m model) |
|------------|--------|-------------------|
| 200 | 8M | ~100MB |
| 500 | 125M | ~500MB |
| 1000 | 1B | ~1-2GB |

### Processing Time

| Resolution | Hollowing | Cutting (36 parts) |
|------------|-----------|-------------------|
| 200 | ~5s | ~20s |
| 500 | ~20s | ~30s |
| 1000 | ~60-90s | ~40s |

## Dependencies

Required:
- `trimesh`: Mesh loading, boolean operations, marching cubes
- `scipy`: Binary morphology for hollowing
- `numpy`: Array operations

Optional:
- `mrmeshpy` (MeshLib): Faster SDF hollowing via native implementation

## Testing

```bash
PYTHONPATH=services/fabrication/src:services/common/src python3 -m pytest \
  services/fabrication/tests/test_segmentation.py -v
```

## Future Work

- [ ] Dovetail joint implementation
- [ ] Pyramid joint implementation
- [ ] Oblique cutting planes (not just axis-aligned)
- [ ] Material-aware hollowing (variable wall thickness)
- [ ] GPU-accelerated voxelization
