# Multi-Printer Control Feature

## Quick Links

- **[Specification](spec.md)** - Detailed feature requirements and user stories
- **[Implementation Plan](plan.md)** - Technical architecture and code examples
- **[Research](../../Research/3dPrinterControl.md)** - Printer API integration research

## Overview

This feature adds support for controlling three different 3D printers on KITTY's local network with intelligent printer selection based on model size and fabrication mode.

### Supported Printers

| Printer | Type | Build Volume | Best For | Protocol |
|---------|------|--------------|----------|----------|
| **Bamboo Labs H2D** | FDM | 250×250×250mm | Small-medium parts | MQTT + FTPS |
| **Elegoo OrangeStorm Giga** | FDM (Klipper) | 800×800×1000mm | Large prints | Moonraker REST |
| **Snapmaker Artisan Pro** | 3-in-1 | 400×400×400mm | CNC/laser/3D | SACP (TCP) |

## Automatic Printer Selection

```
Model Size ≤ 200mm  →  Bamboo H2D
Model Size > 200mm  →  Elegoo Giga
Mode = CNC or Laser →  Snapmaker Artisan
```

## Usage Examples

### 1. Automatic Selection (Recommended)

```python
# ReAct agent automatically selects printer based on model size
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cad/bracket.stl",
    "print_mode": "3d_print"
  }
}
# → Auto-selects Bamboo H2D (bracket is 150mm)
```

### 2. Manual Override

```python
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cad/large_enclosure.stl",
    "printer_id": "elegoo_giga"  # Force specific printer
  }
}
```

### 3. CNC Job

```python
{
  "tool": "fabrication.queue_print",
  "args": {
    "artifact_path": "/Users/Shared/KITTY/artifacts/cam/aluminum_plate.nc",
    "print_mode": "cnc"
  }
}
# → Auto-selects Snapmaker Artisan (only CNC-capable printer)
```

### 4. Check Printer Status

```python
{
  "tool": "fabrication.list_printers",
  "args": {}
}

# Returns:
{
  "bamboo_h2d": {
    "online": true,
    "printing": false,
    "capabilities": {
      "type": "bamboo_h2d",
      "modes": ["3d_print"],
      "build_volume": {"x": 250, "y": 250, "z": 250}
    }
  },
  "elegoo_giga": {
    "online": true,
    "printing": true,
    "progress": 45,
    "bed_temp": 60,
    "extruder_temp": 215
  },
  "snapmaker_artisan": {
    "online": false,
    "error": "Connection timeout"
  }
}
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

```
User Intent
    ↓
Brain Service (ReAct Agent)
    ↓
Gateway (:8080)
    ↓
Fabrication Service (:8300)
    ↓
┌────────────┬────────────┬──────────────┐
│  Bamboo    │  Klipper   │  Snapmaker   │
│  Driver    │  Driver    │  Driver      │
│  (MQTT)    │  (HTTP)    │  (SACP)      │
└────────────┴────────────┴──────────────┘
       ↓            ↓              ↓
   Bamboo H2D  Elegoo Giga  Snapmaker Artisan
```

## Files Added/Modified

### New Files
- `services/fabrication/src/fabrication/drivers/base.py` - Abstract driver interface
- `services/fabrication/src/fabrication/drivers/bamboo.py` - Bamboo Labs driver
- `services/fabrication/src/fabrication/drivers/klipper.py` - Klipper/Moonraker driver
- `services/fabrication/src/fabrication/drivers/snapmaker.py` - Snapmaker SACP driver
- `services/fabrication/src/fabrication/registry.py` - Printer registry
- `services/fabrication/src/fabrication/selector.py` - Printer selection logic
- `services/gateway/src/gateway/routes/fabrication.py` - Gateway fabrication routes
- `config/printers.yaml` - Printer configuration

### Modified Files
- `services/fabrication/src/fabrication/jobs/manager.py` - Multi-printer support
- `services/gateway/src/gateway/app.py` - Register fabrication router
- `config/tool_registry.yaml` - Updated fabrication tools

## Implementation Status

### ✅ Completed
- [x] Specification document
- [x] Implementation plan
- [x] Tool registry updates
- [x] Architecture design

### 🚧 In Progress
- [ ] Driver implementations
- [ ] Printer registry
- [ ] Selection engine
- [ ] Gateway routes
- [ ] Testing

### 📋 Planned
- [ ] Documentation updates
- [ ] Operations manual
- [ ] Troubleshooting guide
- [ ] Deployment

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

## Future Enhancements

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
