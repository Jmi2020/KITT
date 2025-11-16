# KITT Printer Drivers

Automated printer control for multi-printer fabrication workflows.

## Overview

KITT supports automated print execution through printer drivers that provide unified control across different printer types:

- **Bamboo H2D** → MQTT protocol
- **Elegoo Giga** → Moonraker/Klipper REST API
- **Snapmaker Artisan** → Moonraker/Klipper REST API

All drivers implement a common `PrinterDriver` interface, enabling consistent control regardless of printer type.

## Architecture

```
┌─────────────────┐
│ PrintExecutor   │  ← Orchestrates print workflow
└────────┬────────┘
         │
    ┌────┴─────┬──────────┬────────────┐
    │          │          │            │
┌───▼───┐  ┌──▼───┐  ┌───▼────┐  ┌────▼────┐
│ Base  │  │ Moon │  │ Bamboo │  │ Future  │
│ Driver│  │raker │  │  MQTT  │  │ Drivers │
└───────┘  └──────┘  └────────┘  └─────────┘
              │          │
         ┌────▼──┐  ┌────▼────┐
         │Elegoo │  │ Bamboo  │
         │ Giga  │  │   H2D   │
         └───────┘  └─────────┘
         │Snapmaker│
         │Artisan  │
         └─────────┘
```

## Printer Drivers

### 1. MoonrakerDriver (Klipper-based printers)

**Supported Printers:**
- Elegoo OrangeStorm Giga
- Snapmaker Artisan
- Any Klipper printer with Moonraker API

**Protocol:** REST API (HTTP/HTTPS)

**Configuration:**
```yaml
elegoo_giga:
  driver: "moonraker"
  config:
    base_url: "http://elegoo-giga.local:7125"
    api_key: null  # Optional
    timeout: 30
```

**Features:**
- ✅ Real-time status querying
- ✅ G-code file upload
- ✅ Print start/pause/resume/cancel
- ✅ Temperature control
- ✅ Axis homing
- ✅ Progress tracking

**API Endpoints Used:**
- `GET /server/info` - Server information
- `GET /printer/objects/query` - Printer status
- `POST /server/files/upload` - Upload G-code
- `POST /printer/print/start` - Start print
- `POST /printer/print/pause` - Pause print
- `POST /printer/print/resume` - Resume print
- `POST /printer/print/cancel` - Cancel print
- `POST /printer/gcode/script` - Execute G-code

**Documentation:** https://moonraker.readthedocs.io/en/latest/web_api/

---

### 2. BambuMqttDriver (Bamboo Labs printers)

**Supported Printers:**
- Bamboo Labs H2D
- Other Bamboo Labs printers with MQTT API

**Protocol:** MQTT (pub/sub messaging)

**Configuration:**
```yaml
bamboo_h2d:
  driver: "bamboo_mqtt"
  config:
    mqtt_broker: "bamboo-h2d.local"
    mqtt_port: 1883
    device_id: "01S00XXXXXXXXX"  # From printer screen
    access_code: "12345678"  # 8-digit code from printer
    username: "bblp"
```

**Features:**
- ✅ Real-time status via MQTT subscriptions
- ✅ Print control via MQTT publish
- ✅ Multi-material support (AMS)
- ✅ Layer-by-layer progress
- ✅ Built-in camera integration
- ✅ Temperature monitoring

**MQTT Topics:**
- `device/{device_id}/report` - Status updates from printer (subscribe)
- `device/{device_id}/request` - Commands to printer (publish)

**Getting Credentials:**
1. **Device ID**: Settings → About → Serial Number
2. **Access Code**: Settings → Network → LAN Mode → Access Code

**Documentation:** https://github.com/bambulab/BambuStudio/wiki/MQTT-API

---

## PrinterDriver Interface

All drivers implement these methods:

```python
class PrinterDriver(ABC):
    # Connection
    async def connect() -> bool
    async def disconnect() -> None
    async def is_connected() -> bool

    # Status
    async def get_status() -> PrinterStatus
    async def get_capabilities() -> PrinterCapabilities

    # Print Control
    async def upload_gcode(gcode_path: str) -> str
    async def start_print(filename: str) -> bool
    async def pause_print() -> bool
    async def resume_print() -> bool
    async def cancel_print() -> bool

    # Temperature Control
    async def set_bed_temperature(temp_celsius: float) -> bool
    async def set_nozzle_temperature(temp_celsius: float) -> bool

    # Utility
    async def home_axes(x: bool, y: bool, z: bool) -> bool
```

## PrinterStatus Data Model

```python
@dataclass
class PrinterStatus:
    printer_id: str
    state: PrinterState  # offline, idle, printing, paused, complete, error
    is_online: bool
    is_printing: bool

    # Temperatures
    nozzle_temp: Optional[float]
    nozzle_target: Optional[float]
    bed_temp: Optional[float]
    bed_target: Optional[float]

    # Progress (if printing)
    current_file: Optional[str]
    progress_percent: Optional[float]  # 0-100
    print_duration_seconds: Optional[int]
    time_remaining_seconds: Optional[int]
    current_layer: Optional[int]
    total_layers: Optional[int]

    # Error info
    error_message: Optional[str]
    updated_at: datetime
```

## Usage Examples

### Basic Usage

```python
from fabrication.drivers import MoonrakerDriver, BambuMqttDriver

# Initialize Moonraker driver
config = {
    "base_url": "http://elegoo-giga.local:7125",
    "timeout": 30,
}
driver = MoonrakerDriver("elegoo_giga", config)

# Connect to printer
await driver.connect()

# Get status
status = await driver.get_status()
print(f"Printer state: {status.state}")
print(f"Bed temp: {status.bed_temp}°C")

# Upload G-code
filename = await driver.upload_gcode("/path/to/model.gcode")

# Start print
await driver.start_print(filename)

# Monitor progress
while True:
    status = await driver.get_status()
    if status.is_printing:
        print(f"Progress: {status.progress_percent}%")
        await asyncio.sleep(30)
    else:
        break

# Cleanup
await driver.disconnect()
```

### With Bamboo MQTT

```python
from fabrication.drivers import BambuMqttDriver

config = {
    "mqtt_broker": "bamboo-h2d.local",
    "mqtt_port": 1883,
    "device_id": "01S00XXXXXXXXX",
    "access_code": "12345678",
}
driver = BambuMqttDriver("bamboo_h2d", config)

# Connect (starts MQTT loop)
await driver.connect()

# Status updates arrive via MQTT automatically
await asyncio.sleep(2)  # Wait for initial status
status = await driver.get_status()

# Start print (requires file already on printer or accessible path)
await driver.start_print("/path/to/model.gcode")

# MQTT subscriptions provide real-time updates
await driver.disconnect()
```

## Configuration

### Setup printer_config.yaml

```bash
# Copy example configuration
cp services/fabrication/printer_config.example.yaml services/fabrication/printer_config.yaml

# Edit with your printer details
nano services/fabrication/printer_config.yaml
```

### Environment Variables

Printer config can also be set via environment variables:

```bash
# Bamboo H2D
export BAMBOO_H2D_MQTT_BROKER="bamboo-h2d.local"
export BAMBOO_H2D_DEVICE_ID="01S00XXXXXXXXX"
export BAMBOO_H2D_ACCESS_CODE="12345678"

# Elegoo Giga
export ELEGOO_GIGA_MOONRAKER_URL="http://elegoo-giga.local:7125"

# Snapmaker Artisan
export SNAPMAKER_MOONRAKER_URL="http://snapmaker-artisan.local:7125"
```

## Automated Print Workflow

With printer drivers, KITT can now execute fully automated prints:

```
1. Job Submission
   ↓
2. Queue Optimization (P3 #20)
   ↓
3. Job Scheduling (P3 #20)
   ↓
4. G-code Slicing
   ↓
5. Upload G-code (driver.upload_gcode)
   ↓
6. Start Print (driver.start_print)
   ↓
7. Monitor Progress (driver.get_status polling)
   ↓
8. Capture Snapshots (existing camera integration)
   ↓
9. Print Completion Detection
   ↓
10. Record Outcome (existing outcome tracking)
```

## Error Handling

All drivers include comprehensive error handling:

```python
try:
    await driver.upload_gcode("/path/to/model.gcode")
except FileNotFoundError:
    print("G-code file not found")
except ConnectionError:
    print("Failed to upload - check network")
except Exception as e:
    print(f"Unexpected error: {e}")
```

**Common Errors:**
- `ConnectionError` - Network issues, printer offline
- `FileNotFoundError` - G-code file missing
- `ValueError` - Invalid parameters (e.g., printer busy)
- `TimeoutError` - Request timed out

## Troubleshooting

### Moonraker Connection Issues

```bash
# Test Moonraker API directly
curl http://elegoo-giga.local:7125/server/info

# Check Klipper status
curl http://elegoo-giga.local:7125/printer/info

# View Moonraker logs
ssh pi@elegoo-giga.local
tail -f ~/printer_data/logs/moonraker.log
```

### Bamboo MQTT Connection Issues

```bash
# Test MQTT connection with mosquitto
mosquitto_sub -h bamboo-h2d.local -p 1883 \
  -u bblp -P <access_code> \
  -t "device/<device_id>/report" -v

# Check printer network settings
# Settings → Network → LAN Mode (must be enabled)

# Verify device ID and access code
# Settings → About → Serial Number
# Settings → Network → LAN Mode → Access Code
```

### Network Discovery

```bash
# Find printers on network
nmap -p 1883,7125 192.168.1.0/24

# Elegoo Giga - look for port 7125 (Moonraker)
# Bamboo H2D - look for port 1883 (MQTT)

# Use mDNS to discover
avahi-browse -a | grep -i printer
```

## Next Steps

### Phase 2: Print Executor (Planned)

`PrintExecutor` class will orchestrate the full workflow:

```python
class PrintExecutor:
    async def execute_job(job: QueuedPrint):
        # 1. Select driver for assigned printer
        # 2. Connect to printer
        # 3. Upload G-code
        # 4. Start print
        # 5. Monitor progress (poll status)
        # 6. Capture snapshots at milestones
        # 7. Handle errors (retry if configured)
        # 8. Record outcome
        # 9. Notify completion
```

### Phase 3: Integration with Job Scheduler

Link drivers with existing P3 #20 infrastructure:

```python
# After job is scheduled
assignment = await job_scheduler.schedule_next_jobs()

# Execute on printer
for assignment in assignments:
    executor = PrintExecutor(assignment.printer_id)
    await executor.execute_job(assignment.job)
```

## API Reference

See inline docstrings in:
- `services/fabrication/src/fabrication/drivers/base.py`
- `services/fabrication/src/fabrication/drivers/moonraker.py`
- `services/fabrication/src/fabrication/drivers/bamboo_mqtt.py`

## Dependencies

```toml
# Add to services/fabrication/pyproject.toml
[tool.poetry.dependencies]
httpx = "^0.27.0"  # Moonraker HTTP client
paho-mqtt = "^2.1.0"  # Bamboo MQTT client
```

## Testing

```bash
# Install dependencies
cd services/fabrication
poetry install

# Run driver tests (when available)
poetry run pytest tests/drivers/

# Manual testing
poetry run python -m fabrication.drivers.test_moonraker
poetry run python -m fabrication.drivers.test_bamboo
```

## Security Considerations

1. **Credentials Storage**
   - Never commit `printer_config.yaml` with real credentials
   - Use environment variables in production
   - Restrict file permissions: `chmod 600 printer_config.yaml`

2. **Network Security**
   - Printers should be on isolated network/VLAN
   - Use firewall rules to restrict access
   - Consider VPN for remote access

3. **MQTT Security**
   - Bamboo access codes are only 8 digits (not highly secure)
   - Consider MQTT over TLS if supported
   - Rotate access codes periodically

## Resources

- **Moonraker Docs**: https://moonraker.readthedocs.io/
- **Bamboo MQTT Wiki**: https://github.com/bambulab/BambuStudio/wiki/MQTT-API
- **Klipper Docs**: https://www.klipper3d.org/
- **paho-mqtt Docs**: https://eclipse.dev/paho/files/paho.mqtt.python/html/

---

**Status**: ✅ Drivers Implemented | 🚧 Executor Pending | 📋 Integration Planned

**Next**: Implement `PrintExecutor` orchestrator and integrate with job scheduler (P3 #20).
