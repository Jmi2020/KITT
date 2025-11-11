# Multi-Printer Control Feature

## Quick Links

- **[Specification](spec.md)** - Detailed feature requirements and user stories
- **[Implementation Plan](plan.md)** - Technical architecture and code examples
- **[Research](../../Research/3dPrinterControl.md)** - Printer API integration research

## Overview

This feature provides intelligent multi-printer control through TWO WORKFLOWS:

### Phase 1: Manual Workflow (✅ IMPLEMENTED - DEFAULT)
KITTY analyzes model dimensions, checks printer availability, opens appropriate slicer app. **User completes slicing and printing manually.**

### Phase 2: Automatic Workflow (📋 PLANNED)
KITTY asks for target height, scales model, validates orientation/supports via vision, then opens slicer with recommendations.

## Supported Printers

| Printer | Type | Build Volume | Best For | Protocol | Status Check |
|---------|------|--------------|----------|----------|--------------|
| **Bamboo Labs H2D** | FDM | 250×250×250mm | Excellent quality | MQTT (local) | ✅ MQTT subscription |
| **Elegoo OrangeStorm Giga** | FDM (Klipper) | 800×800×1000mm | Large/fast prints | Moonraker HTTP | ✅ HTTP polling |
| **Snapmaker Artisan Pro** | 3-in-1 | 400×400×400mm | CNC/laser/3D | SACP (TCP) | ⏳ Phase 2 |

## Quality-First Printer Selection

**Priority hierarchy** (prefers Bamboo for superior print quality):

```
CNC or Laser job           →  Snapmaker Artisan (only multi-mode printer)

3D Print ≤250mm + Bamboo idle  →  Bamboo H2D (BEST QUALITY)
3D Print ≤250mm + Bamboo busy  →  Elegoo Giga (fallback)
3D Print >250mm and ≤800mm     →  Elegoo Giga (only option)
3D Print >800mm                →  Error: too large
```

## Usage Examples (Phase 1 - Manual Workflow)

### 1. Open STL in Slicer (Automatic Printer Selection)

```python
# ReAct agent automatically selects printer based on model size and availability
{
  "tool": "fabrication.open_in_slicer",
  "args": {
    "stl_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
    "print_mode": "3d_print"
  }
}

# Response:
✓ Opened /Users/Shared/KITTY/artifacts/cad/bracket.stl in BambuStudio

Printer: bamboo_h2d
Model size: 150.0mm (max dimension)
Reasoning: Model fits Bamboo H2D (150mm ≤ 250mm). Bamboo is idle. Using Bamboo for excellent print quality.

Please complete slicing and printing in the BambuStudio application.
```

### 2. Force Specific Printer

```python
{
  "tool": "fabrication.open_in_slicer",
  "args": {
    "stl_path": "/Users/Shared/KITTY/artifacts/cad/large_enclosure.stl",
    "force_printer": "elegoo_giga"  # Override automatic selection
  }
}

# Opens ElegySlicer with the large enclosure STL
```

### 3. CNC Job

```python
{
  "tool": "fabrication.open_in_slicer",
  "args": {
    "stl_path": "/Users/Shared/KITTY/artifacts/cam/aluminum_plate.stl",
    "print_mode": "cnc"
  }
}

# Opens Luban (Snapmaker) with CNC mode
```

### 4. Analyze Model Before Opening

```python
# Preview dimensions and printer recommendation without launching slicer
{
  "tool": "fabrication.analyze_model",
  "args": {
    "stl_path": "/Users/Shared/KITTY/artifacts/cad/test.stl"
  }
}

# Response:
Model Analysis: /Users/Shared/KITTY/artifacts/cad/test.stl

Dimensions:
  Width:  150.0mm
  Depth:  80.0mm
  Height: 45.0mm
  Max:    150.0mm
  Volume: 540000mm³

Recommended Printer: bamboo_h2d (BambuStudio)
Status: ✓ Available
Reasoning: Model fits Bamboo H2D (150mm ≤ 250mm). Bamboo is idle...
```

### 5. Check Printer Status

```python
{
  "tool": "fabrication.printer_status",
  "args": {}
}

# Response:
Printer Status:

  ✓ bamboo_h2d: idle 💤
  ✓ elegoo_giga: printing 🔨
      Job: calibration_cube.gcode
      Progress: 45%
  ✓ snapmaker_artisan: idle 💤
```

## Configuration

### Printer Configuration File: `config/printers.yaml`

```yaml
printers:
  bamboo_h2d:
    type: bamboo_h2d
    ip: 192.168.1.100
    serial: "01P45165616"
    access_code: "YOUR_16_CHAR_CODE"
    mqtt_host: 192.168.1.100  # Local MQTT
    mqtt_port: 1883

  elegoo_giga:
    type: elegoo_giga
    ip: 192.168.1.200
    port: 7125  # Moonraker default

  snapmaker_artisan:
    type: snapmaker_artisan
    ip: 192.168.1.150
    port: 8888  # SACP default
    token: ""   # Optional
```

### Environment Variables (`.env`)

```bash
# Fabrication Service
FABRICATION_BASE=http://fabrication:8300
PRINTER_CONFIG=config/printers.yaml

# Bamboo Labs
BAMBOO_IP=192.168.1.100
BAMBOO_SERIAL=01P45165616
BAMBOO_ACCESS_CODE=your_16_char_code

# Elegoo Giga
ELEGOO_IP=192.168.1.200
ELEGOO_MOONRAKER_PORT=7125

# Snapmaker
SNAPMAKER_IP=192.168.1.150
SNAPMAKER_PORT=8888
```

## Setup Instructions

### 1. Find Bamboo Labs Access Code

1. On printer display: Settings → Network → WiFi Settings
2. Look for "Access Code" (16 alphanumeric characters)
3. OR enable LAN-only mode for local MQTT without cloud

### 2. Configure Elegoo Giga (Klipper)

1. SSH into printer: `ssh mks@192.168.1.200` (password: makerbase)
2. Verify Moonraker running: `curl http://192.168.1.200:7125/server/info`
3. Note: No authentication required (local network only)

### 3. Discover Snapmaker

1. Use UDP discovery script (port 20054)
2. OR find IP in router DHCP leases
3. Test SACP: `nc 192.168.1.150 8888` (should accept connection)

### 4. Update Configuration

```bash
# Copy example config
cp config/printers.yaml.example config/printers.yaml

# Edit with your printer IPs and credentials
nano config/printers.yaml
```

### 5. Test Connectivity

```bash
# Test all printers
curl http://localhost:8080/api/fabrication/printers

# Test specific printer
curl http://localhost:8080/api/fabrication/printers/bamboo_h2d/status
```

## Architecture

### Phase 1: Manual Workflow (Current)

```
User Intent
    ↓
Brain Service (ReAct Agent)
    ↓
Broker MCP Server (fabrication.open_in_slicer tool)
    ↓
Gateway (:8080) → /api/fabrication/open_in_slicer
    ↓
Fabrication Service (:8300)
    ├→ STL Analyzer (trimesh) → Extract dimensions
    ├→ Status Checker → Query printer availability
    │   ├→ Bamboo H2D (MQTT subscription, 30s cache)
    │   └→ Elegoo Giga (HTTP polling, 30s cache)
    ├→ Printer Selector → Quality-first selection logic
    └→ Slicer Launcher → macOS 'open -a' command
            ↓
    ┌─────────────┬──────────────┬────────────┐
    │ BambuStudio│ ElegySlicer  │   Luban    │
    └─────────────┴──────────────┴────────────┘
         (User completes slicing and printing)
```

## Files Added/Modified (Phase 1)

### New Files (Core Components)
- `services/fabrication/src/fabrication/analysis/stl_analyzer.py` - STL dimension analysis with trimesh
- `services/fabrication/src/fabrication/status/printer_status.py` - Printer availability checking (MQTT + HTTP)
- `services/fabrication/src/fabrication/selector/printer_selector.py` - Quality-first printer selection
- `services/fabrication/src/fabrication/launcher/slicer_launcher.py` - macOS slicer app launching

### New Files (API Layer)
- `services/fabrication/src/fabrication/app.py` - FastAPI application with 3 endpoints
- `services/gateway/src/gateway/routes/fabrication.py` - Gateway proxy routes

### New Files (Configuration)
- `config/printers.yaml.example` - Printer network configuration template

### Modified Files
- `.env.example` - Added fabrication service environment variables
- `services/common/src/common/config.py` - Added printer configuration settings
- `services/fabrication/pyproject.toml` - Added trimesh, paho-mqtt dependencies
- `services/gateway/src/gateway/app.py` - Registered fabrication router
- `services/mcp/src/mcp/servers/broker_server.py` - Added fabrication tools
- `config/tool_registry.yaml` - Fabrication tools already defined

## Testing Strategy

### Unit Tests
```bash
# Test printer selection logic
pytest tests/unit/fabrication/test_selector.py -v

# Test driver interfaces
pytest tests/unit/fabrication/test_drivers.py -v
```

### Integration Tests
```bash
# Test with mock printers
pytest tests/integration/fabrication/test_multi_printer.py -v

# Test full workflow
pytest tests/integration/test_cad_to_print.py -v
```

### Manual Testing
```bash
# Queue print to Bamboo
curl -X POST http://localhost:8080/api/fabrication/queue \
  -H 'Content-Type: application/json' \
  -d '{
    "artifact_path": "/Users/Shared/KITTY/artifacts/cad/test.stl",
    "print_mode": "3d_print"
  }'

# Check status
curl http://localhost:8080/api/fabrication/printers/bamboo_h2d/status

# Pause print
curl -X POST http://localhost:8080/api/fabrication/printers/bamboo_h2d/pause
```

## Troubleshooting

### Bamboo Labs Issues

**Problem**: MQTT connection refused
- **Solution**: Check access code is correct (16 chars)
- **Solution**: Verify printer is in LAN-only mode or cloud credentials valid
- **Solution**: Test MQTT broker: `mosquitto_sub -h 192.168.1.100 -p 1883 -u bblp -P YOUR_CODE -t '#'`

**Problem**: FTPS upload fails
- **Solution**: Check port 990 is open
- **Solution**: Verify implicit TLS mode (not explicit STARTTLS)
- **Solution**: Test: `curl -k --ftp-ssl-reqd ftp://bblp:YOUR_CODE@192.168.1.100:990/`

### Elegoo Giga Issues

**Problem**: Moonraker not responding
- **Solution**: SSH into printer, check service: `systemctl status moonraker`
- **Solution**: Restart Moonraker: `systemctl restart moonraker`
- **Solution**: Check Fluidd accessible at `http://192.168.1.200/`

**Problem**: File upload fails
- **Solution**: Check disk space: `df -h`
- **Solution**: Verify file permissions in virtual_sdcard directory

### Snapmaker Issues

**Problem**: SACP connection timeout
- **Solution**: Check printer is on same subnet (192.168.1.x)
- **Solution**: Verify port 8888 not blocked by firewall
- **Solution**: Test with UDP discovery script first

**Problem**: Authentication fails
- **Solution**: Leave token empty unless explicitly set
- **Solution**: Check SACP version matches (use Wireshark to inspect)

### General Issues

**Problem**: Printer shows offline
- **Solution**: Ping printer: `ping 192.168.1.100`
- **Solution**: Check printer power and WiFi connection
- **Solution**: Verify static IP assignment in router

**Problem**: Model too large for all printers
- **Solution**: Check STL bounding box: `trimesh.load('model.stl').bounds`
- **Solution**: Scale model in CAD software
- **Solution**: Split model into multiple parts

## Performance Benchmarks

| Operation | Target | Typical |
|-----------|--------|---------|
| Printer status query | <2s | 800ms |
| 10MB file upload | <10s | 6s |
| 50MB file upload | <30s | 18s |
| Print start command | <5s | 2s |
| Full workflow (upload + start) | <30s | 15s |

## Security Notes

- All printers on trusted local network (192.168.1.x)
- No internet exposure of printer APIs
- Credentials stored in `.env` (gitignored)
- FTPS uses TLS encryption for Bamboo uploads
- Confirmation phrase required for all print jobs (hazard_class: medium)
- Audit logging to PostgreSQL for compliance

## Implementation Status

### Phase 1: Manual Workflow ✅ COMPLETE (January 2025)

**Core Components:**
- ✅ STL analysis with trimesh (`services/fabrication/src/fabrication/analysis/stl_analyzer.py`)
- ✅ Printer status checking with caching (`services/fabrication/src/fabrication/status/printer_status.py`)
  - ✅ Bamboo H2D: MQTT subscription to status reports (30s cache)
  - ✅ Elegoo Giga: HTTP GET to Moonraker /printer/info (30s cache)
  - ⏳ Snapmaker Artisan: No status check (assumed available)
- ✅ Quality-first printer selection (`services/fabrication/src/fabrication/selector/printer_selector.py`)
- ✅ macOS slicer app launching (`services/fabrication/src/fabrication/launcher/slicer_launcher.py`)

**API Endpoints:**
- ✅ `POST /api/fabrication/open_in_slicer` - Launch slicer with STL
- ✅ `POST /api/fabrication/analyze_model` - Preview dimensions and selection
- ✅ `GET /api/fabrication/printer_status` - Query all printer statuses

**ReAct Agent Integration:**
- ✅ `fabrication.open_in_slicer` tool (broker MCP server)
- ✅ `fabrication.analyze_model` tool (broker MCP server)
- ✅ `fabrication.printer_status` tool (broker MCP server)

**Configuration:**
- ✅ Printer configuration template (`config/printers.yaml.example`)
- ✅ Environment variables in `.env.example`
- ✅ Tool registry definitions (`config/tool_registry.yaml`)

### Phase 2: Automatic Workflow 📋 PLANNED

**Additional Features:**
- [ ] Model scaling to target height
- [ ] Vision server orientation checking
- [ ] Support detection via vision API
- [ ] Training data collection (screen recording + IPC monitoring)
- [ ] `fabrication.prepare_print` tool implementation
- [ ] Snapmaker Artisan status checking

### Phase 3: Advanced Features 💡 FUTURE

1. **Automatic Slicing**: Integrate Orca Slicer CLI for STL → G-code
2. **Queue Management**: Support job queuing when all printers busy
3. **Multi-Material Detection**: Analyze STL for multi-color requirements
4. **Printer Health Monitoring**: Track failure rates, maintenance schedules
5. **Cost Estimation**: Calculate material cost per print
6. **Computer Vision Integration**: Link to existing CV monitor for failure detection
7. **WebSocket Streaming**: Real-time print progress updates

## Support

For issues or questions:
1. Check troubleshooting guide above
2. Review printer API research: `Research/3dPrinterControl.md`
3. Check logs: `docker logs fabrication -f`
4. File GitHub issue with printer type, error message, and logs

## Related Documentation

- **Operations Manual**: `KITTY_OperationsManual.md`
- **API Reference**: `Research/APIinfo.md`
- **Conversation Framework**: `Research/KITTY_Conversation_Framework_Implementation.md`
- **Tool Registry**: `config/tool_registry.yaml`
- **Vision Pipeline**: `Research/VisionPipelineIntegration.md`
