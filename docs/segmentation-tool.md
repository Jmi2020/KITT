# Mesh Segmentation Tool

Split oversized 3D models into printable parts with automatic hollowing and alignment joints.

## Overview

The Mesh Segmentation Tool takes 3D models (3MF or STL) that are too large for your printer's build volume and automatically:

1. **Detects units** from 3MF files and converts if needed (meters → millimeters)
2. **Hollows the mesh** to save material (configurable wall thickness)
3. **Cuts into parts** that fit your printer's build volume
4. **Adds alignment joints** (integrated pins/holes or dowel holes)
5. **Exports parts** as individual 3MF files + combined assembly

## Quick Start

### Via WebUI

1. Navigate to the **Mesh Segmenter** component
2. Enter the path to your 3MF or STL file
3. Select your target printer (or use auto-detect)
4. Configure options (hollowing, joints, quality)
5. Click **Check Dimensions** to preview
6. Click **Segment Model** to process

### Via CLI

```bash
kitt segment /path/to/model.3mf \
  --printer bamboo_h2d \
  --quality high \
  --joint-type integrated \
  --auto-parts
```

### Via API

```bash
curl -X POST http://localhost:8080/api/segmentation/segment \
  -H "Content-Type: application/json" \
  -d '{
    "mesh_path": "/path/to/model.3mf",
    "printer_id": "bamboo_h2d",
    "enable_hollowing": true,
    "wall_thickness_mm": 10.0,
    "hollowing_resolution": 1000,
    "joint_type": "integrated",
    "max_parts": 0
  }'
```

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `printer_id` | auto | Target printer for build volume constraints |
| `enable_hollowing` | true | Hollow the mesh to save material |
| `wall_thickness_mm` | 10.0 | Shell thickness when hollowing (mm) |
| `hollowing_resolution` | 1000 | Voxels per dimension (200=fast, 500=medium, 1000=high quality) |
| `hollowing_strategy` | hollow_then_segment | When to hollow (see below) |
| `joint_type` | integrated | Type of alignment joints (see below) |
| `joint_tolerance_mm` | 0.3 | Clearance for joint fit |
| `max_parts` | 0 | Maximum parts (0 = auto-calculate based on mesh/build volume) |
| `pin_diameter_mm` | 8.0 | Diameter of integrated pins |
| `pin_height_mm` | 10.0 | Height of pin protrusion |

## Joint Types

### Integrated (Recommended)
- **Description**: Printed pins on one part, matching holes on the mating part
- **Hardware**: None required - everything is printed
- **Pros**: No extra hardware, precise alignment, self-locating
- **Cons**: Requires sufficient wall thickness (≥10mm for 8mm pins)
- **Best for**: Large decorative prints, sculptures, props

### Dowel
- **Description**: Cylindrical holes on both parts for external dowel pins
- **Hardware**: Standard wooden or metal dowel pins (e.g., 4mm × 20mm)
- **Pros**: Works with thinner walls, removable joints
- **Cons**: Requires purchasing dowel pins
- **Best for**: Functional parts, assemblies that may need disassembly

### Dovetail (Future)
- **Description**: Interlocking trapezoidal joints
- **Status**: Planned for Phase 2

### Pyramid (Future)
- **Description**: Self-centering conical joints
- **Status**: Planned for Phase 2

### None
- **Description**: No alignment features
- **Use case**: Manual alignment with glue or when joints would interfere with the design

## Hollowing Strategies

### hollow_then_segment (Default)
1. Creates a hollow shell from the entire mesh first
2. Then cuts the shell into parts
3. **Result**: Wall panels with consistent thickness
4. **Best for**: Large sculptures, decorative items, cost-sensitive prints

### segment_then_hollow
1. Cuts the solid mesh into parts first
2. Then hollows each part individually
3. **Result**: Individual hollow boxes with closed walls
4. **Best for**: Structural parts, items that need internal support

## Quality Settings

| Quality | Resolution | Voxel Size (1m model) | Processing Time | Use Case |
|---------|------------|----------------------|-----------------|----------|
| Fast | 200 | ~5mm | ~10 seconds | Quick previews, iteration |
| Medium | 500 | ~2mm | ~30 seconds | Balanced quality/speed |
| High | 1000 | ~1mm | ~1-2 minutes | Final production, detailed models |

Higher resolution = smoother surfaces, better detail preservation, but longer processing time.

## Output Files

After segmentation, you'll find in the output directory:

```
model_segmented/
├── part_00.3mf          # Individual part files
├── part_01.3mf
├── part_02.3mf
├── ...
└── combined_assembly.3mf # All parts in one file for preview
```

Each part includes:
- The mesh geometry
- Integrated joints (pins or holes)
- Proper orientation for printing

## API Endpoints

### Check if Segmentation Needed
```
POST /api/segmentation/check
```
Returns analysis of whether the model exceeds build volume.

### Segment Mesh (Synchronous)
```
POST /api/segmentation/segment
```
Processes the mesh and returns results immediately. Good for smaller models.

### Segment Mesh (Async)
```
POST /api/segmentation/segment/async
```
Starts a background job for large models. Returns a job ID for status polling.

### Get Job Status
```
GET /api/segmentation/jobs/{job_id}
```
Check progress of an async segmentation job.

### List Printers
```
GET /api/segmentation/printers
```
Returns available printer configurations with build volumes.

## Examples

### Giant Duck (1 meter tall)
```bash
kitt segment /path/to/giant_duck.3mf \
  --printer bamboo_h2d \
  --quality high \
  --joint-type integrated \
  --wall-thickness 10
```

Result: 36 parts, ~1mm voxel resolution, integrated pins for alignment

### Large Cube (1 meter)
```bash
kitt segment /path/to/big_cube.3mf \
  --printer bamboo_h2d \
  --quality medium \
  --auto-parts
```

Result: 56 parts (auto-calculated), medium quality for faster processing

## Troubleshooting

### "Mesh is not watertight"
The tool will attempt automatic repair. If it fails:
- Check your source mesh for holes or non-manifold edges
- Use a mesh repair tool like Meshmixer or MeshLab

### Parts still too large
- Check that the correct printer is selected
- Verify build volume settings in printer config
- The tool accounts for joint clearance (~10mm per axis)

### Pixelated/blocky output
- Increase `hollowing_resolution` to 1000 or higher
- Processing time will increase but output quality improves significantly

### Missing joints on some seams
- Some small seams may not have enough surface area for joints
- The tool filters out positions too close to edges
- Use glue for seams without joints

## Technical Notes

- **Supported formats**: 3MF (preferred), STL
- **Unit detection**: Automatic from 3MF metadata (meter, millimeter, inch)
- **Memory usage**: ~1GB for 1000-voxel resolution on 1m model
- **Dependencies**: trimesh, scipy (ndimage), numpy
- **Optional**: MeshLib (mrmeshpy) for faster SDF hollowing
