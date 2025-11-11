# Network Discovery Service

## Overview

The Network Discovery Service enables KITTY to automatically discover IoT devices on the local network, including 3D printers, Raspberry Pi devices, ESP32 microcontrollers, and other controllable devices. It provides periodic scanning, device categorization, and a user-approval workflow before integration.

## Features

- **Multiple Discovery Methods**:
  - mDNS/Bonjour (Zeroconf)
  - SSDP/UPnP
  - Manufacturer-specific UDP (Bamboo Labs, Snapmaker)
  - Network scanning (nmap)

- **Device Categorization**:
  - 3D printers (Bamboo Labs, Elegoo, Prusa, etc.)
  - CNC mills and laser engravers (Snapmaker)
  - Raspberry Pi and other SBCs
  - ESP32/ESP8266 microcontrollers
  - Smart home devices

- **User Approval Workflow**:
  - Devices are reported but not auto-configured
  - User must explicitly approve devices for integration
  - Optional notes for approved devices

- **Hybrid Scanning**:
  - Periodic background scans (default: every 15 minutes)
  - On-demand manual scans
  - Real-time updates via mDNS service browser

## Architecture

```
services/discovery/
├── src/discovery/
│   ├── scanners/          # Discovery scanner implementations
│   │   ├── base.py        # Abstract scanner interface
│   │   ├── mdns_scanner.py
│   │   ├── ssdp_scanner.py
│   │   ├── bamboo_scanner.py
│   │   └── snapmaker_scanner.py
│   ├── registry/          # Device storage and categorization
│   │   ├── device_store.py
│   │   └── categorizer.py
│   ├── scheduler/         # Periodic scan scheduling
│   │   └── scan_scheduler.py
│   ├── models.py          # Pydantic and SQLAlchemy models
│   └── app.py             # FastAPI service
├── requirements.txt
└── Dockerfile
```

## Database Schema

### `discovered_devices` Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Device unique identifier |
| discovered_at | DateTime | First discovery timestamp |
| last_seen | DateTime | Most recent discovery |
| discovery_method | String | How device was found (mdns, ssdp, etc.) |
| ip_address | String | Device IP address |
| mac_address | String | MAC address (if known) |
| hostname | String | Device hostname |
| device_type | String | Category (printer_3d, raspberry_pi, etc.) |
| manufacturer | String | Manufacturer name |
| model | String | Model name |
| serial_number | String | Serial number (if available) |
| firmware_version | String | Firmware version |
| services | JSON | List of discovered services |
| capabilities | JSON | Device-specific capabilities |
| approved | Boolean | User approval status |
| approved_at | DateTime | Approval timestamp |
| approved_by | String | User who approved |
| notes | Text | User notes |
| is_online | Boolean | Current online status |
| confidence_score | Float | Classification confidence (0.0-1.0) |

### `discovery_scans` Table

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Scan unique identifier |
| started_at | DateTime | Scan start time |
| completed_at | DateTime | Scan completion time |
| status | String | running, completed, failed |
| methods | JSON | Discovery methods used |
| devices_found | Integer | Number of devices discovered |
| errors | JSON | List of error messages |
| triggered_by | String | user_id or "scheduler" |

## API Endpoints

### Discovery Control

**POST /api/discovery/scan**
```json
// Request
{
  "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp"],
  "timeout_seconds": 30
}

// Response
{
  "scan_id": "uuid",
  "status": "running",
  "started_at": "2025-11-11T12:00:00Z",
  "methods": ["mdns", "ssdp", "bamboo_udp"]
}
```

**GET /api/discovery/scan/{scan_id}**
```json
// Response
{
  "scan_id": "uuid",
  "status": "completed",
  "started_at": "2025-11-11T12:00:00Z",
  "completed_at": "2025-11-11T12:00:30Z",
  "methods": ["mdns", "ssdp"],
  "devices_found": 5,
  "errors": []
}
```

### Device Registry

**GET /api/discovery/devices**
```
Query params:
- device_type (optional)
- approved (optional)
- is_online (optional)
- manufacturer (optional)
- limit (default: 100)
- offset (default: 0)
```

**GET /api/discovery/devices/{device_id}**

**GET /api/discovery/search?q={query}&limit=50**

**GET /api/discovery/printers**

**POST /api/discovery/devices/{device_id}/approve**
```json
// Request
{
  "notes": "Bamboo Labs H2D - Main workshop printer"
}

// Response
{
  "id": "uuid",
  "approved": true,
  "approved_at": "2025-11-11T12:00:00Z",
  "approved_by": "admin"
}
```

**DELETE /api/discovery/devices/{device_id}**

## ReAct Agent Tools (MCP)

### discovery.scan_network
Trigger network discovery scan to find IoT devices.

**Parameters:**
- `methods` (optional): Array of discovery methods
- `timeout_seconds` (optional): Scan timeout (default: 30)

**Example:**
```
User: "KITTY, scan the network for devices"
KITTY: [Calls discovery.scan_network]
KITTY: "Network discovery scan started. Found 8 devices:
  - Bamboo Labs X1 Carbon (192.168.1.100)
  - Elegoo Neptune 4 Pro (192.168.1.200)
  - raspberrypi-office (192.168.1.150)
  ..."
```

### discovery.list_devices
List all discovered devices with optional filtering.

**Parameters:**
- `device_type` (optional): Filter by type
- `approved` (optional): Filter by approval status
- `is_online` (optional): Filter by online status
- `limit` (optional): Max results

**Example:**
```
User: "Show me all discovered printers"
KITTY: [Calls discovery.list_devices with device_type="printer_3d"]
```

### discovery.find_printers
Find all 3D printers, CNC mills, and laser engravers.

**Example:**
```
User: "What printers are on the network?"
KITTY: [Calls discovery.find_printers]
```

### discovery.approve_device
Approve a discovered device for integration.

**Parameters:**
- `device_id` (required): Device UUID
- `notes` (optional): Approval notes

**Example:**
```
User: "Approve the Bamboo Labs printer"
KITTY: [Calls discovery.approve_device with device_id and notes]
```

## Configuration

### Environment Variables

```bash
# Discovery Service
DISCOVERY_PORT=8500
DISCOVERY_SCAN_INTERVAL_MINUTES=15
DISCOVERY_ENABLE_PERIODIC_SCANS=true

# PostgreSQL (for device registry)
POSTGRES_URL=postgresql+asyncpg://kitty:changeme@postgres:5432/kitty

# Network Configuration (auto-detected if not set)
DISCOVERY_NETWORK_SUBNET=192.168.1.0/24
DISCOVERY_TIMEOUT_SECONDS=30

# Scanner Enablement
DISCOVERY_ENABLE_MDNS=true
DISCOVERY_ENABLE_SSDP=true
DISCOVERY_ENABLE_BAMBOO_UDP=true
DISCOVERY_ENABLE_SNAPMAKER_UDP=true
DISCOVERY_ENABLE_NETWORK_SCAN=true
```

### Docker Compose

The discovery service is integrated into the KITTY stack:

```yaml
discovery:
  build:
    context: ../..
    dockerfile: services/discovery/Dockerfile
  ports:
    - "8500:8500"
  depends_on:
    - postgres
    - mosquitto
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8500/healthz"]
```

## User Workflow

### 1. Initial Discovery

```bash
# Trigger first scan
curl -X POST http://localhost:8500/api/discovery/scan \
  -H 'Content-Type: application/json' \
  -d '{"timeout_seconds": 30}'
```

Or via ReAct agent:
```
User: "KITTY, scan the network for devices"
```

### 2. View Discovered Devices

```bash
# List all devices
curl http://localhost:8500/api/discovery/devices

# List only printers
curl http://localhost:8500/api/discovery/printers

# List unapproved devices
curl http://localhost:8500/api/discovery/devices?approved=false
```

Or via ReAct agent:
```
User: "What devices did you find?"
User: "Show me the printers"
```

### 3. Approve Devices

```bash
# Approve specific device
curl -X POST http://localhost:8500/api/discovery/devices/{device_id}/approve \
  -H 'Content-Type: application/json' \
  -d '{"notes": "Bamboo Labs H2D - Main printer"}'
```

Or via ReAct agent:
```
User: "Approve the Bamboo Labs printer at 192.168.1.100"
```

### 4. Integration with Other Services

Once approved, devices are available to other services:

```python
# Fabrication service queries discovery for printer IPs
async def get_printer_ip(printer_id: str) -> str:
    response = await httpx.get(
        f"{DISCOVERY_BASE}/api/discovery/search",
        params={"q": printer_id, "approved": True}
    )
    devices = response.json()["devices"]
    if devices:
        return devices[0]["ip_address"]
```

## Device Type Classification

The discovery service uses multiple heuristics to classify devices:

### Port-Based Classification

| Port | Device Type | Confidence |
|------|-------------|------------|
| 5000 | OctoPrint | 0.85 |
| 7125 | Klipper (3D Printer) | 0.85 |
| 8123 | Home Assistant | 0.90 |
| 8888 | Snapmaker (CNC) | 0.70 |

### Hostname-Based Classification

| Pattern | Device Type | Manufacturer |
|---------|-------------|--------------|
| bamboo* | 3D Printer | Bamboo Labs |
| elegoo* | 3D Printer | Elegoo |
| raspberrypi* | Raspberry Pi | Raspberry Pi Foundation |
| esp32* | ESP32 | Espressif |

### MAC Address (OUI) Classification

| Vendor | Device Type | Confidence |
|--------|-------------|------------|
| Espressif | ESP32 | 0.70 |
| Raspberry Pi Foundation | Raspberry Pi | 0.85 |

### Combined Classification

The categorizer uses all available information and selects the result with the highest confidence score.

## Periodic Scanning

The discovery service runs background scans every 15 minutes (configurable) using fast methods:
- mDNS (5 seconds)
- SSDP (3 seconds)
- Bamboo UDP (2 seconds)
- Snapmaker UDP (2 seconds)

**Total scan time:** ~12 seconds

This keeps the device registry up-to-date with:
- Current IP addresses (DHCP changes)
- Online/offline status
- New devices coming online

## Performance Benchmarks

| Operation | Target | Typical |
|-----------|--------|---------|
| Health check | <100ms | 20ms |
| Periodic scan (all fast methods) | <15s | 12s |
| Full scan (including nmap) | <60s | 45s |
| Device list query | <200ms | 50ms |
| Device approval | <100ms | 30ms |

## Success Criteria

- ✅ Discover all printers on network (Bamboo, Elegoo, Snapmaker)
- ✅ Identify Raspberry Pi devices
- ✅ Detect ESP32/ESP8266 via MAC OUI lookup
- ✅ Track IP address changes for DHCP devices
- ✅ Support user approval workflow
- ✅ Periodic background scans complete in <15 seconds
- ✅ Full on-demand scans complete in <60 seconds
- ✅ ReAct agent can discover and list devices via MCP tools
- ✅ Fabrication service can query for printer IPs dynamically

## Future Enhancements (Phase 2)

- Deep device interrogation with credentials
- Automatic service configuration after approval
- Device health monitoring
- Generic IoT control interface
- Network topology mapping
- MAC address persistent tracking
- SNMP support
- IPv6 support
