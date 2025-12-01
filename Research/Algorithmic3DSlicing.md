# Algorithmic 3D Model Splitting System: Technical Design Guide

**A Python-based CLI tool for partitioning large STL/3MF files into printable pieces can be built using trimesh as the core library, Manifold3D for Boolean operations, and a BSP-based splitting algorithm derived from the SIGGRAPH "Chopper" paper.** This guide provides complete technical specifications for implementing such a system on macOS Apple Silicon, with emphasis on hollowing, overhang-constrained cutting, and automatic joint generation.

The key innovation required is combining trimesh's mesh slicing with an overhang-aware objective function that ensures all resulting pieces satisfy the ≤30° constraint. No complete open-source implementation currently exists—this represents a significant development opportunity.

---

## Recommended library stack balances robustness with Apple Silicon optimization

After evaluating 10+ mesh processing libraries, **trimesh** emerges as the clear primary choice for this project. It offers the best combination of active maintenance (v4.10.0, December 2024), native ARM64 support via `pip install trimesh[easy]`, comprehensive mesh operations, and integration with specialized backends for demanding operations.

| Library | Role | Installation | Why Selected |
|---------|------|--------------|--------------|
| **trimesh** | Core mesh I/O, slicing, analysis | `pip install trimesh[easy]` | Most versatile, excellent Apple Silicon support, used by Cura |
| **Manifold3D** | Boolean operations | `pip install manifold3d` | Only library with *guaranteed manifold output* |
| **pymeshlab** | Mesh repair, decimation | `pip install pymeshlab` | 200+ MeshLab filters, ARM64 wheels since v2025.7 |
| **lib3mf** | Native 3MF read/write | `pip install lib3mf` | Official 3MF consortium library, universal binary |
| **MeshLib** | Performance-critical operations | `pip install meshlib` | **10x faster** Boolean operations than competitors |

**Libraries to avoid:** PyMesh should not be used despite its powerful feature set—it has no pip wheels, requires manual C++ compilation, and is effectively unmaintained. CGAL Python bindings require complex installation and are overkill for this application.

The splitting operation pipeline flows through these libraries: trimesh loads the mesh and performs `slice_mesh_plane()` cuts, Manifold3D handles Boolean subtractions for connector generation, and pymeshlab repairs any resulting non-manifold geometry before export via lib3mf.

---

## Hollowing algorithm uses signed distance fields with marching cubes reconstruction

The most robust hollowing approach combines **signed distance field (SDF) computation** with **marching cubes mesh reconstruction**. This method handles complex geometry far better than simple vertex-normal offsets, which create self-intersections at concave features.

```python
def hollow_mesh(mesh, wall_thickness, voxel_size=0.05):
    """
    Create hollow shell using SDF-based approach.
    
    Args:
        mesh: trimesh.Trimesh (must be watertight)
        wall_thickness: Shell thickness in mm (recommend 1.2-2.0mm for FDM)
        voxel_size: Resolution in mm (smaller = more detail, more memory)
    """
    import numpy as np
    from skimage.measure import marching_cubes
    
    # Validate input
    if not mesh.is_watertight:
        mesh.fill_holes()
        mesh.fix_normals()
    
    # Compute 3D SDF grid
    bounds = mesh.bounds
    padding = wall_thickness * 3
    grid_dims = ((bounds[1] - bounds[0] + 2*padding) / voxel_size).astype(int)
    
    # Query points for SDF
    x = np.linspace(bounds[0,0]-padding, bounds[1,0]+padding, grid_dims[0])
    y = np.linspace(bounds[0,1]-padding, bounds[1,1]+padding, grid_dims[1])
    z = np.linspace(bounds[0,2]-padding, bounds[1,2]+padding, grid_dims[2])
    query_points = np.stack(np.meshgrid(x, y, z, indexing='ij'), -1).reshape(-1, 3)
    
    # Compute signed distances (negative inside mesh)
    sdf = mesh.nearest.signed_distance(query_points).reshape(grid_dims)
    
    # Create shell: exterior AND NOT eroded_interior
    shell_sdf = np.maximum(sdf, -(sdf + wall_thickness))
    
    # Extract mesh via marching cubes
    verts, faces, _, _ = marching_cubes(shell_sdf, level=0, spacing=(voxel_size,)*3)
    verts += bounds[0] - padding  # Transform to original coordinates
    
    return trimesh.Trimesh(vertices=verts, faces=faces)
```

**Wall thickness guidelines by printing technology:**
- **FDM**: 1.2–2.0mm minimum (3× nozzle diameter), 0.4mm nozzle needs ≥1.2mm walls
- **SLA/DLP**: 0.8–2.0mm, thinner possible but fragile
- **Large format (OrangeStorm Giga)**: 2.0–3.0mm for structural rigidity

For production use, **MeshLib** provides optimized `offsetMesh()` that runs significantly faster:

```python
from meshlib import mrmeshpy

mesh = mrmeshpy.loadMesh("model.stl")
params = mrmeshpy.OffsetParameters()
params.voxelSize = 0.04
params.type = mrmeshpy.OffsetParametersType.Shell
hollow_mesh = mrmeshpy.offsetMesh(mesh, -wall_thickness, params)
```

---

## BSP-based Chopper algorithm provides optimal splitting strategy

The **Chopper algorithm** (Luo et al., SIGGRAPH 2012) remains the gold standard for automatic mesh partitioning. It uses **beam search over binary space partitioning (BSP) trees** to find optimal cut planes that minimize parts while satisfying build volume constraints.

### Core algorithm pseudocode

```python
def overhang_aware_split(mesh, build_volume, max_overhang=30, beam_width=4):
    """
    Split mesh into printable parts using beam search BSP.
    
    Key modification: Add overhang penalty to objective function
    to ensure all pieces satisfy ≤30° constraint.
    """
    current_trees = [EmptyBSPTree()]
    
    while any_part_exceeds_volume(current_trees, mesh, build_volume):
        candidates = []
        
        for tree in current_trees:
            largest_part = get_largest_part(mesh, tree)
            if fits_in_volume(largest_part, build_volume):
                continue
                
            # Sample 129 plane normals (subdivided octahedron)
            for normal in sample_uniform_normals(129):
                for offset in sample_offsets(largest_part.bounds, normal):
                    plane = (normal, offset)
                    
                    # Cut and evaluate
                    part_a, part_b = cut_mesh(largest_part, plane)
                    
                    # Find optimal orientation for each piece
                    orient_a = optimize_orientation(part_a, max_overhang)
                    orient_b = optimize_orientation(part_b, max_overhang)
                    
                    # Skip if either piece cannot satisfy overhang constraint
                    if orient_a is None or orient_b is None:
                        continue
                    
                    # Compute composite score
                    score = (
                        WEIGHT_PARTS * count_parts(tree, plane) +
                        WEIGHT_OVERHANG * (overhang_area(part_a, orient_a) + 
                                           overhang_area(part_b, orient_b)) +
                        WEIGHT_SEAM * seam_length(plane, largest_part) +
                        WEIGHT_CONNECTOR * connector_feasibility(plane) +
                        WEIGHT_UTILIZATION * (1 - utilization(part_a, build_volume))
                    )
                    
                    candidates.append((tree.add_cut(plane), score, orient_a, orient_b))
        
        # Keep top beam_width candidates
        current_trees = sorted(candidates, key=lambda x: x[1])[:beam_width]
    
    return best_tree(current_trees)
```

### Mathematical constraint for 30° overhang

For a face with normal vector **n_f** and build direction **d** = [0, 0, 1] (Z-up), the overhang angle constraint requires:

```
n_f · d ≥ cos(90° - 30°) = cos(60°) = 0.5

Equivalently: n_z ≥ 0.5 for all face normals after optimal orientation
```

The **orientation optimization** subroutine searches over ~26 candidate directions (6 principal axes + 12 edge midpoints + 8 corners) to find one where total overhang area is minimized or zero.

### Planar cutting with trimesh

```python
import trimesh
from trimesh.intersections import slice_mesh_plane

def cut_and_cap(mesh, plane_normal, plane_origin):
    """Cut mesh along plane, returning both halves with capped surfaces."""
    
    # Get both sides
    positive_side = slice_mesh_plane(
        mesh, 
        plane_normal=plane_normal, 
        plane_origin=plane_origin,
        cap=True  # Close the cut surface
    )
    
    negative_side = slice_mesh_plane(
        mesh,
        plane_normal=-np.array(plane_normal),  # Flip normal
        plane_origin=plane_origin,
        cap=True
    )
    
    return positive_side, negative_side
```

---

## Joint generation requires tolerance-aware parametric design

Automatic connector generation adds mechanical interlocking features to cut surfaces. The three primary joint types each suit different geometries:

**Dovetail joints** work best for large flat cuts:
- Recommended angle: **15°** (printable without modification)
- Clearance: **0.1mm** per side for standard FDM
- Minimum 2 connectors per cut to prevent rotation

**Dowel pin holes** provide simple alignment:
- Standard sizes: 2mm, 3mm, 4mm diameter
- Hole clearance: hole_diameter = pin_diameter + **0.3mm** for slip fit
- Use **2+ dowels** offset from centerline for torque resistance

**Hollow pyramid joints** (from Split3r) print support-free:
- Male pyramid on positive-Z side, female socket on negative side
- Wall thickness 1.5mm, 15° taper angle
- Self-aligning and support-free on both halves

### Joint placement algorithm

```python
def place_connectors(cut_boundary, joint_type, joint_params):
    """Automatically distribute connectors across cut surface."""
    
    cut_area = cut_boundary.area
    min_connectors = 2
    area_per_connector = 400  # mm², tune based on part size
    
    num_connectors = max(min_connectors, int(cut_area / area_per_connector))
    
    # Use Poisson disk sampling for even distribution
    positions = poisson_disk_sample(
        boundary=cut_boundary,
        num_points=num_connectors,
        min_distance=joint_params['size'] * 2,
        edge_margin=joint_params['size']
    )
    
    # Generate geometry
    male_joints = []
    female_joints = []
    
    for pos in positions:
        male = create_joint_geometry(pos, joint_params, is_male=True)
        female = create_joint_geometry(pos, joint_params, is_male=False)
        
        # Apply tolerance to female (larger hole)
        female = offset_geometry(female, joint_params['clearance'])
        
        male_joints.append(male)
        female_joints.append(female)
    
    return male_joints, female_joints
```

**Tolerance values for FDM printing:**

| Fit Type | Clearance | Use Case |
|----------|-----------|----------|
| Press/interference | 0.0 to -0.1mm | Permanent assembly |
| Tight/snug | 0.1–0.15mm | Requires force to insert |
| Slip fit | 0.2mm | Easy assembly without wobble |
| Loose | 0.3–0.5mm | Free movement |

---

## 3MF format is strongly preferred over STL for split models

**3MF's native multi-component support** makes it ideal for split models—all parts can be stored in a single file with relationships and metadata preserved. STL has no mechanism for this; each part requires a separate file.

| Feature | STL | 3MF |
|---------|-----|-----|
| Multi-part in single file | ❌ | ✅ |
| Unit information | ❌ | ✅ (millimeters enforced) |
| Part relationships | ❌ | ✅ |
| Color/materials | ❌ | ✅ |
| Slicer settings | ❌ | ✅ (extension) |
| Typical file size | Large | **70% smaller** (compressed) |

### lib3mf integration

```python
import lib3mf
from lib3mf import get_wrapper

def save_split_parts_3mf(parts, output_path, assembly_info):
    """Save all split parts to single 3MF file with metadata."""
    
    wrapper = get_wrapper()
    model = wrapper.CreateModel()
    
    # Add metadata
    model.SetMetaDataGroup("assembly_info")
    model.AddMetaData("assembly_order", str(assembly_info['order']))
    
    for i, part in enumerate(parts):
        mesh_obj = model.AddMeshObject()
        mesh_obj.SetName(f"part_{i:03d}")
        
        # Add vertices
        for v in part.vertices:
            pos = lib3mf.Position()
            pos.Coordinates = [float(v[0]), float(v[1]), float(v[2])]
            mesh_obj.AddVertex(pos)
        
        # Add triangles
        for f in part.faces:
            tri = lib3mf.Triangle()
            tri.Indices = [int(f[0]), int(f[1]), int(f[2])]
            mesh_obj.AddTriangle(tri)
        
        # Add to build
        build_item = model.AddBuildItem(mesh_obj, wrapper.GetIdentityTransform())
    
    writer = model.QueryWriter("3mf")
    writer.WriteToFile(output_path)
```

---

## CLI architecture uses Typer with YAML configuration

The recommended CLI framework is **Typer** (built on Click) with **Rich** for progress visualization. This combination provides automatic help generation, type validation, and excellent visual feedback for long-running mesh operations.

### Command interface design

```python
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from pathlib import Path
from typing import Optional
import yaml

app = typer.Typer(help="KITTY Mesh Splitting System")

@app.command()
def split(
    input_file: Path = typer.Argument(..., help="Input STL or 3MF file"),
    output_dir: Path = typer.Option("./output", "-o", help="Output directory"),
    printer: str = typer.Option("bambu_x1", "-p", help="Printer profile name"),
    wall_thickness: float = typer.Option(1.5, "-w", help="Wall thickness in mm"),
    max_overhang: float = typer.Option(30.0, help="Maximum overhang angle"),
    hollow: bool = typer.Option(True, help="Hollow the model"),
    connector_type: str = typer.Option("dovetail", help="Joint type: dovetail, dowel, pyramid"),
    parallel: int = typer.Option(-1, "-j", help="Parallel jobs (-1=auto)"),
    config: Optional[Path] = typer.Option(None, "-c", help="YAML config file"),
):
    """Split a 3D model into printable pieces."""
    
    # Load printer profile
    profiles = load_printer_profiles(config)
    build_volume = profiles[printer]['build_volume']
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        
        task = progress.add_task("Loading mesh...", total=None)
        mesh = trimesh.load(input_file)
        
        if hollow:
            progress.update(task, description="Hollowing mesh...")
            mesh = hollow_mesh(mesh, wall_thickness)
        
        progress.update(task, description="Computing split planes...")
        parts = overhang_aware_split(mesh, build_volume, max_overhang)
        
        progress.update(task, description="Generating connectors...")
        parts = add_connectors(parts, connector_type)
        
        progress.update(task, description="Saving parts...")
        save_parts(parts, output_dir, format='3mf')
        
        generate_manifest(parts, output_dir)

if __name__ == "__main__":
    app()
```

### Printer profile configuration (YAML)

```yaml
# printers.yaml
printers:
  bambu_x1:
    name: "Bambu Lab X1 Carbon"
    build_volume: [256, 256, 256]
    effective_volume: [238, 228, 250]  # Minus cutter exclusion
    nozzle_diameter: 0.4
    
  elegoo_giga:
    name: "Elegoo OrangeStorm Giga"  
    build_volume: [800, 800, 1000]
    effective_volume: [800, 800, 1000]
    nozzle_diameter: 0.4
    
  snapmaker_artisan:
    name: "Snapmaker Artisan"
    build_volume: [400, 400, 400]
    effective_volume: [400, 400, 400]
    nozzle_diameter: 0.4

defaults:
  output_format: "3mf"
  connector_type: "dovetail"
  wall_thickness: 1.5
  connector_clearance: 0.15
```

### Assembly manifest output (JSON)

```json
{
  "source_file": "large_statue.stl",
  "created": "2025-12-01T10:30:00Z",
  "build_volume": [256, 256, 256],
  "total_parts": 6,
  "parts": [
    {
      "id": 1,
      "filename": "large_statue_part001.3mf",
      "dimensions": [245, 180, 256],
      "orientation": [0, 0, 0],
      "connects_to": [2, 3],
      "connector_type": "dovetail"
    }
  ],
  "assembly_order": [1, 2, 3, 4, 5, 6],
  "estimated_print_time_hours": 18.5
}
```

---

## Memory management handles 100MB+ files through chunking and memory mapping

Large STL files require careful memory management. A **100MB binary STL** contains approximately **2 million triangles** and expands to **~144MB in numpy arrays**. Two strategies address this:

### Memory-mapped file loading

```python
import mmap
import numpy as np

def load_stl_mmap(filepath):
    """Memory-map large binary STL for efficient access."""
    with open(filepath, 'rb') as f:
        f.seek(80)  # Skip header
        num_triangles = np.frombuffer(f.read(4), dtype=np.uint32)[0]
        
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        
        # View data without copying (each triangle = 50 bytes)
        triangles = np.frombuffer(
            mm[84:84 + num_triangles * 50],
            dtype=[('normal', '<f4', 3), ('vertices', '<f4', (3, 3)), ('attr', '<u2')]
        )
    return triangles, num_triangles
```

### Parallel processing with joblib

For CPU-intensive operations like plane intersection testing, **joblib** provides efficient parallelization that works around Python's GIL:

```python
from joblib import Parallel, delayed

def parallel_overhang_analysis(mesh, orientations, n_jobs=-1):
    """Evaluate overhang area for multiple orientations in parallel."""
    
    def analyze_single(orientation):
        rotated = mesh.copy()
        rotated.apply_transform(orientation_matrix(orientation))
        
        overhang_area = 0
        for face_idx, normal in enumerate(rotated.face_normals):
            if normal[2] < 0.5:  # Fails 30° constraint
                overhang_area += rotated.area_faces[face_idx]
        return overhang_area
    
    results = Parallel(n_jobs=n_jobs, backend='loky', verbose=10)(
        delayed(analyze_single)(orient) for orient in orientations
    )
    
    return results
```

**Critical joblib settings for Apple Silicon:**
- Use `backend='loky'` (not `multiprocessing`)—avoids conflicts with Accelerate framework
- Set `max_nbytes='100M'` to memory-map large arrays automatically
- Limit to performance cores: `n_jobs = os.cpu_count() // 2` on M-series chips

---

## FastAPI integration enables web service deployment

For integration into the KITTY fabrication system as a web service, **FastAPI with background tasks** handles long-running mesh operations:

```python
from fastapi import FastAPI, BackgroundTasks, UploadFile, HTTPException
import uuid
from typing import Dict

app = FastAPI(title="KITTY Mesh Splitter")
tasks: Dict[str, dict] = {}

@app.post("/api/split")
async def start_split(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    printer: str = "bambu_x1",
    hollow: bool = True
):
    task_id = str(uuid.uuid4())
    
    # Save uploaded file
    file_path = f"/tmp/{task_id}_{file.filename}"
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)
    
    tasks[task_id] = {"status": "queued", "progress": 0}
    background_tasks.add_task(process_split, task_id, file_path, printer, hollow)
    
    return {"task_id": task_id}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")
    return tasks[task_id]

async def process_split(task_id: str, file_path: str, printer: str, hollow: bool):
    tasks[task_id]["status"] = "processing"
    # ... mesh processing with progress updates ...
    tasks[task_id]["status"] = "completed"
```

For production workloads exceeding a few concurrent users, migrate to **Celery with Redis** for distributed task processing.

---

## Implementation roadmap spans four phases

### Phase 1: Core mesh operations (2-3 weeks)
- Set up development environment with trimesh, Manifold3D, pymeshlab
- Implement mesh loading (STL/3MF) with validation
- Build hollowing pipeline using SDF approach
- Create basic planar cutting with cap generation
- Unit tests for all mesh operations

### Phase 2: Splitting algorithm (3-4 weeks)  
- Implement BSP tree data structure
- Build plane sampling (129 uniform normals)
- Create orientation optimizer with overhang scoring
- Implement beam search with composite objective
- Validate against known test models

### Phase 3: Connectors and output (2 weeks)
- Parametric joint generators (dovetail, dowel, pyramid)
- Automatic joint placement algorithm
- 3MF export with multi-component support
- Assembly manifest generation
- CLI interface with Typer

### Phase 4: Integration and optimization (2 weeks)
- FastAPI service wrapper
- Parallel processing optimization
- Memory management for large files
- Printer profile system
- Documentation and examples

---

## Key repositories and references to leverage

**Essential libraries:**
- `github.com/mikedh/trimesh` — Core mesh operations, excellent documentation
- `github.com/SarahWeiii/CoACD` — State-of-art convex decomposition, better than deprecated V-HACD
- `github.com/ChristophSchranz/Tweaker-3` — Proven orientation optimization used by Cura

**Academic foundations:**
- **Chopper** (SIGGRAPH 2012): https://gfx.cs.princeton.edu/pubs/Luo_2012_CPM/ — Seminal BSP decomposition paper
- **PackMerger** (CGF 2014) — Shell-based packing optimization
- **CoACD** (SIGGRAPH 2022) — Modern collision-aware decomposition

**Production references:**
- PrusaSlicer cut tool source code (C++) — Connector generation logic
- Bambu Studio (fork of PrusaSlicer) — Same foundation
- MeshLib documentation — High-performance offset operations

---

## Conclusion

Building an algorithmic 3D model splitting system requires combining **trimesh for mesh I/O and slicing**, **Manifold3D for robust Booleans**, and a **BSP-based beam search algorithm** with overhang-aware objective functions. The critical innovation is modifying the Chopper algorithm's scoring to penalize cuts that produce parts exceeding the 30° overhang constraint.

The recommended architecture uses **Typer CLI → YAML config → trimesh/Manifold3D processing → lib3mf export**, with joblib parallelization for performance. No complete open-source implementation of automatic overhang-constrained splitting exists—this represents both a technical challenge and an opportunity to contribute a valuable tool to the 3D printing community.

Key technical decisions: prefer 3MF over STL for multi-part output, use SDF-based hollowing over vertex-normal offset, implement hollow pyramid joints for support-free connector printing, and leverage MeshLib's optimized operations for production performance on Apple Silicon.