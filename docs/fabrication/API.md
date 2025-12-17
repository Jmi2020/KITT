# Fabrication API Reference

Complete API documentation for the KITTY Fabrication service.

**Base URL**: `http://localhost:8300` (or `http://fabrication:8300` from Docker)

## Table of Contents

- [Segmentation API](#segmentation-api)
- [Slicer API](#slicer-api)
- [Printer APIs](#printer-apis)

---

## Segmentation API

### Check Segmentation

Check if a model needs segmentation based on printer build volume.

```http
POST /api/segmentation/check
Content-Type: application/json
```

**Request Body:**
```json
{
  "stl_path": "/path/to/model.3mf",
  "printer_id": "bambu_h2d"
}
```

**Response:**
```json
{
  "needs_segmentation": true,
  "model_dimensions_mm": [300, 200, 150],
  "build_volume_mm": [256, 256, 256],
  "exceeds_by_mm": [44, 0, 0],
  "recommended_cuts": 2
}
```

### Segment Mesh

Segment a large model into printable parts.

```http
POST /api/segmentation/segment
Content-Type: application/json
```

**Request Body:**
```json
{
  "stl_path": "/path/to/model.3mf",
  "printer_id": "bambu_h2d",
  "wall_thickness_mm": 2.0,
  "enable_hollowing": true,
  "hollowing_strategy": "hollow_then_segment",
  "joint_type": "dowel",
  "joint_tolerance_mm": 0.3,
  "max_parts": 10
}
```

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stl_path` | string | required | Path to input 3MF or STL file |
| `printer_id` | string | optional | Target printer for build volume |
| `wall_thickness_mm` | float | 2.0 | Shell thickness for hollowing |
| `enable_hollowing` | bool | true | Whether to hollow the mesh |
| `hollowing_strategy` | string | "hollow_then_segment" | When to hollow: "hollow_then_segment", "segment_then_hollow", "none" |
| `joint_type` | string | "dowel" | Joint type: "dowel", "integrated", "dovetail", "pyramid", "none" |
| `joint_tolerance_mm` | float | 0.3 | Clearance for joints |
| `max_parts` | int | 10 | Maximum number of parts |

**Response:**
```json
{
  "success": true,
  "needs_segmentation": true,
  "num_parts": 4,
  "parts": [
    {
      "id": "part_001",
      "path": "/artifacts/3mf/model_segmented/part_001.3mf",
      "dimensions_mm": [200, 200, 150]
    }
  ],
  "combined_3mf_path": "/artifacts/3mf/model_segmented/combined.3mf",
  "combined_3mf_uri": "minio://artifacts/model_segmented/combined.3mf",
  "hardware_required": {
    "dowels_6mm": 8
  },
  "assembly_notes": "Align parts using dowel holes. Apply glue to flat surfaces."
}
```

### List Printers

Get available printers with build volumes.

```http
GET /api/segmentation/printers
```

**Response:**
```json
[
  {
    "id": "bambu_h2d",
    "name": "Bambu H2D",
    "build_volume": [256, 256, 256],
    "is_online": true,
    "is_printing": false
  },
  {
    "id": "elegoo_giga",
    "name": "Elegoo Giga",
    "build_volume": [600, 600, 600],
    "is_online": true,
    "is_printing": true,
    "progress_percent": 45
  }
]
```

---

## Slicer API

### Get Slicer Status

Check if the slicer engine is available.

```http
GET /api/slicer/status
```

**Response:**
```json
{
  "available": true,
  "bin_path": "/usr/bin/CuraEngine",
  "profiles_loaded": {
    "printers": 3,
    "materials": 5,
    "qualities": 3
  },
  "message": "CuraEngine ready"
}
```

### Start Slicing Job

Start an async slicing job.

```http
POST /api/slicer/slice
Content-Type: application/json
```

**Request Body:**
```json
{
  "input_path": "/artifacts/3mf/model.3mf",
  "config": {
    "printer_id": "bambu_h2d",
    "material_id": "pla_generic",
    "quality": "normal",
    "support_type": "tree",
    "infill_percent": 20
  },
  "upload_to_printer": false
}
```

**Config Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `printer_id` | string | required | Target printer ID |
| `material_id` | string | "pla_generic" | Material profile |
| `quality` | string | "normal" | Quality preset: "draft", "normal", "fine" |
| `support_type` | string | "tree" | Support type: "none", "normal", "tree" |
| `infill_percent` | int | 20 | Infill percentage (0-100) |
| `layer_height_mm` | float | null | Override layer height |
| `nozzle_temp_c` | int | null | Override nozzle temp |
| `bed_temp_c` | int | null | Override bed temp |

**Response:**
```json
{
  "job_id": "slice_abc123",
  "status": "pending",
  "status_url": "/api/slicer/jobs/slice_abc123"
}
```

### Get Job Status

Poll slicing job progress.

```http
GET /api/slicer/jobs/{job_id}
```

**Response (In Progress):**
```json
{
  "job_id": "slice_abc123",
  "status": "running",
  "progress": 0.45,
  "input_path": "/artifacts/3mf/model.3mf",
  "config": {
    "printer_id": "bambu_h2d",
    "quality": "normal"
  }
}
```

**Response (Completed):**
```json
{
  "job_id": "slice_abc123",
  "status": "completed",
  "progress": 1.0,
  "input_path": "/artifacts/3mf/model.3mf",
  "config": {...},
  "gcode_path": "/artifacts/gcode/model.gcode",
  "estimated_print_time_seconds": 2700,
  "estimated_filament_grams": 45.2,
  "layer_count": 180,
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:31:45Z"
}
```

### Download G-code

Download the generated G-code file.

```http
GET /api/slicer/jobs/{job_id}/download
```

**Response:** Binary G-code file

### Upload to Printer

Upload G-code to a printer.

```http
POST /api/slicer/jobs/{job_id}/upload?printer_id=elegoo_giga
```

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `printer_id` | string | from job | Target printer (optional override) |

**Response:**
```json
{
  "success": true,
  "job_id": "slice_abc123",
  "printer_id": "elegoo_giga",
  "gcode_path": "/artifacts/gcode/model.gcode",
  "message": "Upload complete"
}
```

### List Profiles

Get all available slicer profiles.

```http
GET /api/slicer/profiles
```

**Response:**
```json
{
  "printers": [
    {
      "id": "bambu_h2d",
      "name": "Bambu H2D",
      "build_volume": [256, 256, 256],
      "nozzle_diameter": 0.4,
      "max_bed_temp": 110,
      "max_nozzle_temp": 300
    }
  ],
  "materials": [
    {
      "id": "pla_generic",
      "name": "Generic PLA",
      "type": "PLA",
      "default_nozzle_temp": 210,
      "default_bed_temp": 60
    }
  ],
  "qualities": [
    {
      "id": "draft",
      "name": "Draft",
      "layer_height": 0.3
    },
    {
      "id": "normal",
      "name": "Normal",
      "layer_height": 0.2
    },
    {
      "id": "fine",
      "name": "Fine",
      "layer_height": 0.12
    }
  ]
}
```

---

## Printer APIs

### Bambu API

```http
GET /api/bambu/printers
GET /api/bambu/printers/{printer_id}/status
POST /api/bambu/printers/{printer_id}/print
POST /api/bambu/printers/{printer_id}/pause
POST /api/bambu/printers/{printer_id}/resume
POST /api/bambu/printers/{printer_id}/stop
```

### Elegoo API (Moonraker)

```http
GET /api/elegoo/status
POST /api/elegoo/gcode
GET /api/elegoo/temperature
POST /api/elegoo/temperature/set
```

---

## MCP Tools

For voice integration, the following MCP tools are available:

| Tool | Description |
|------|-------------|
| `segment_mesh` | Segment large models into parts |
| `check_segmentation` | Check if model needs segmentation |
| `list_printers` | List available printers |
| `slice_model` | Start async slicing job |
| `check_slicing_status` | Poll slicing progress |
| `send_to_printer` | Upload G-code and start print |

See the MCP server documentation for tool schemas and usage.

---

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found (job, file, printer) |
| 503 | Service unavailable (slicer not configured) |
| 500 | Internal server error |

**Common Errors:**

```json
{
  "detail": "Input file not found: /path/to/file.stl"
}
```

```json
{
  "detail": "Unknown printer: invalid_id. Available: ['bambu_h2d', 'elegoo_giga']"
}
```

```json
{
  "detail": "Job not complete. Current status: running"
}
```
