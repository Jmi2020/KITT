# Fabrication Service

The KITTY Fabrication service provides 3D printing workflow automation including mesh segmentation, G-code slicing, and printer control.

## Quick Start

### Running Locally

```bash
# Install dependencies
cd services/fabrication
pip install -e .

# Set PYTHONPATH for imports
export PYTHONPATH=services/fabrication/src:services/common/src

# Run the service
python -m uvicorn fabrication.app:app --host 0.0.0.0 --port 8300
```

### Running with Docker

```bash
# Start with Docker Compose
docker-compose -f infra/compose/docker-compose.yml up fabrication

# Or build and run standalone
docker build -t kitt-fabrication services/fabrication
docker run -p 8300:8300 kitt-fabrication
```

### Health Check

```bash
curl http://localhost:8300/health
# {"status": "healthy"}
```

## Architecture

```
services/fabrication/
├── src/fabrication/
│   ├── app.py                 # FastAPI application entry point
│   ├── routes/
│   │   ├── segmentation.py    # Mesh segmentation endpoints
│   │   ├── slicer.py          # G-code slicing endpoints
│   │   ├── bambu.py           # Bambu printer control
│   │   └── elegoo.py          # Elegoo/Moonraker control
│   ├── segmentation/
│   │   ├── engine/            # Segmentation algorithms
│   │   ├── hollowing/         # SDF-based mesh hollowing
│   │   ├── joints/            # Joint generation (dowel, dovetail)
│   │   └── schemas.py         # Pydantic models
│   ├── slicer/
│   │   ├── engine.py          # CuraEngine wrapper
│   │   ├── profiles.py        # Profile management
│   │   └── schemas.py         # Slicing models
│   └── printers/
│       ├── bambu_driver.py    # Bambu MQTT driver
│       └── moonraker.py       # Moonraker HTTP driver
└── tests/
    ├── unit/
    └── integration/
```

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/api/segmentation/check` | POST | Check if model needs segmentation |
| `/api/segmentation/segment` | POST | Segment model into parts |
| `/api/segmentation/printers` | GET | List configured printers |
| `/api/slicer/status` | GET | Check slicer availability |
| `/api/slicer/slice` | POST | Start async slicing job |
| `/api/slicer/jobs/{id}` | GET | Get slicing job status |
| `/api/slicer/jobs/{id}/upload` | POST | Upload G-code to printer |
| `/api/slicer/profiles` | GET | List slicer profiles |

See [API Documentation](../../docs/fabrication/API.md) for complete reference.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FABRICATION_PORT` | 8300 | Service port |
| `CURAENGINE_BIN_PATH` | `/usr/bin/CuraEngine` | CuraEngine binary path |
| `SLICER_PROFILES_DIR` | `config/slicer_profiles` | Profile directory |
| `ARTIFACTS_DIR` | `/tmp/fabrication` | Output directory |
| `BAMBU_PRINTER_IP` | - | Bambu printer IP |
| `BAMBU_ACCESS_CODE` | - | Bambu access code |
| `ELEGOO_MOONRAKER_URL` | - | Moonraker API URL |

### Printer Configuration

Printer profiles are stored in `config/slicer_profiles/printers/`:

```json
{
  "id": "bambu_h2d",
  "name": "Bambu H2D",
  "build_volume": [256, 256, 256],
  "nozzle_diameter": 0.4
}
```

## Development

### Running Tests

```bash
# Unit tests
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/unit/ -v

# Integration tests (requires running service)
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/integration/ -v

# With coverage
PYTHONPATH=services/fabrication/src:services/common/src \
  python3 -m pytest services/fabrication/tests/ --cov=fabrication
```

### Code Quality

```bash
# Lint
ruff check services/fabrication/ --fix

# Format
ruff format services/fabrication/
```

### Adding a New Printer

1. Create printer profile in `config/slicer_profiles/printers/`:
   ```json
   {
     "id": "new_printer",
     "name": "My New Printer",
     "build_volume": [200, 200, 200]
   }
   ```

2. If printer uses Moonraker, add configuration to `.env`:
   ```
   NEW_PRINTER_MOONRAKER_URL=http://192.168.x.x:7125
   ```

3. For custom protocols, implement a driver in `printers/`:
   ```python
   class NewPrinterDriver:
       async def connect(self): ...
       async def upload_gcode(self, path): ...
       async def start_print(self): ...
   ```

4. Register in `app.py` startup.

### Adding a New Joint Type

1. Create joint generator in `segmentation/joints/`:
   ```python
   class NewJointGenerator:
       def generate(self, surface_a, surface_b, tolerance):
           # Return joint geometry
           pass
   ```

2. Register in `segmentation/joints/__init__.py`

3. Add to schema enum in `segmentation/schemas.py`:
   ```python
   class JointType(str, Enum):
       ...
       NEW_JOINT = "new_joint"
   ```

## Dependencies

### System Requirements

- Python 3.11+
- CuraEngine 5.x (for slicing)
- trimesh, numpy, scipy (for segmentation)

### CuraEngine Installation

**Docker (ARM64 compatible):**
CuraEngine is pre-installed in the Docker image.

**macOS:**
```bash
# CuraEngine must be compiled from source for ARM
# See: https://github.com/Ultimaker/CuraEngine
```

**Linux:**
```bash
apt-get install curaengine
```

## Troubleshooting

### CuraEngine Not Found

```
{"available": false, "bin_path": "/usr/bin/CuraEngine"}
```

1. Verify CuraEngine is installed
2. Check `CURAENGINE_BIN_PATH` environment variable
3. Ensure binary is executable

### Segmentation Memory Errors

For large meshes:
1. Reduce mesh complexity before importing
2. Increase Docker memory limit
3. Use `segment_then_hollow` strategy

### Printer Connection Issues

1. Verify network connectivity
2. Check printer credentials in `.env`
3. Review printer-specific logs:
   ```bash
   docker logs kitt-fabrication 2>&1 | grep -i bambu
   ```

## Related Documentation

- [User Workflow Guide](../../docs/fabrication/WORKFLOW.md)
- [API Reference](../../docs/fabrication/API.md)
- [Profile Customization](../../docs/fabrication/PROFILES.md)
- [Troubleshooting](../../docs/fabrication/TROUBLESHOOTING.md)
