# Network Discovery Service Specification

## Overview

The Network Discovery Service enables KITTY to automatically discover IoT devices on the local network, collect their IP addresses and metadata, categorize them by type (printers, Raspberry Pi, ESP32, etc.), and maintain a device registry for connection and control purposes.

## Goals

1. **Automatic Device Discovery**: Scan local network using multiple protocols (mDNS, SSDP, manufacturer-specific)
2. **Device Categorization**: Identify device types (3D printers, SBCs, microcontrollers, smart home devices)
3. **IP Address Collection**: Maintain current IP addresses for DHCP-assigned devices
4. **User Approval Workflow**: Report findings without auto-configuring services
5. **Hybrid Scanning**: Support both periodic background scans and on-demand discovery
6. **IoT Focus**: Prioritize fabrication equipment, Raspberry Pi, ESP32, and controllable devices

## Non-Goals

- Automatic service configuration (requires user approval)
- Deep device interrogation requiring credentials
- Network security scanning or vulnerability assessment
- Non-IoT device tracking (phones, laptops, etc.)

## Architecture

### Service Design

**Dedicated discovery service** at port 8500 with modular scanner architecture:

```
services/discovery/
├── src/discovery/
│   ├── scanners/
│   │   ├── mdns_scanner.py       # Bonjour/mDNS (zeroconf)
│   │   ├── ssdp_scanner.py       # UPnP/SSDP (smart devices)
│   │   ├── bamboo_scanner.py     # Bamboo Labs UDP (port 2021)
│   │   ├── snapmaker_scanner.py  # Snapmaker UDP (port 20054)
│   │   ├── network_scanner.py    # Generic ARP/nmap fallback
│   │   └── base.py               # Abstract scanner interface
│   ├── registry/
│   │   ├── device_store.py       # PostgreSQL device registry
│   │   └── categorizer.py        # Device type classification
│   ├── scheduler/
│   │   └── scan_scheduler.py     # APScheduler periodic scans
│   ├── app.py                    # FastAPI service
│   └── models.py                 # Pydantic models
├── requirements.txt
└── Dockerfile
```

### Discovery Methods

#### 1. mDNS/Bonjour Discovery (zeroconf)
**Purpose**: Discover devices advertising services via Bonjour
**Targets**:
- `_http._tcp.local.` - Web interfaces
- `_printer._tcp.local.` - Network printers
- `_ipp._tcp.local.` - IPP printers
- `_octoprint._tcp.local.` - OctoPrint instances
- `_moonraker._tcp.local.` - Klipper Moonraker
- `_ssh._tcp.local.` - SSH servers (Raspberry Pi)

**Library**: `zeroconf` (Python pure implementation)

#### 2. SSDP/UPnP Discovery (ssdpy)
**Purpose**: Discover UPnP-enabled smart home devices
**Targets**:
- Generic UPnP devices
- Smart plugs, cameras, thermostats
- Some 3D printers with web interfaces

**Library**: `ssdpy` (lightweight SSDP client)

#### 3. Manufacturer-Specific Discovery

**Bamboo Labs Printers**:
- UDP broadcast on port 2021
- Response contains printer model, serial, IP, status
- Command: `M990` (device info request)

**Snapmaker Printers**:
- UDP broadcast on port 20054
- Discovery protocol: JSON-based
- Response includes model, serial, capabilities

#### 4. Network Scanning (Fallback)
**Purpose**: Discover devices not advertising via protocols
**Method**: ARP scan + port fingerprinting
**Library**: `python-nmap` or `scapy`

**Target ports**:
- 22 (SSH - Raspberry Pi)
- 80/443 (HTTP/HTTPS - web interfaces)
- 7125 (Moonraker)
- 5000 (OctoPrint)
- 8888 (Snapmaker)
- 9100 (Raw printing)

## Data Model

### Device Registry Schema

```python
class DiscoveredDevice(Base):
    __tablename__ = "discovered_devices"

    id = Column(UUID, primary_key=True, default=uuid4)

    # Discovery metadata
    discovered_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    discovery_method = Column(String)  # mdns, ssdp, bamboo_udp, nmap

    # Network information
    ip_address = Column(String, nullable=False)
    mac_address = Column(String)
    hostname = Column(String)

    # Device identification
    device_type = Column(String)  # printer, raspberry_pi, esp32, smart_device, unknown
    manufacturer = Column(String)  # bamboo_labs, elegoo, snapmaker, raspberry_pi, espressif
    model = Column(String)
    serial_number = Column(String)
    firmware_version = Column(String)

    # Service information
    services = Column(JSON)  # List of discovered services [{protocol, port, name}]
    capabilities = Column(JSON)  # Device-specific capabilities

    # User approval
    approved = Column(Boolean, default=False)
    approved_at = Column(DateTime)
    approved_by = Column(String)
    notes = Column(Text)

    # Status
    is_online = Column(Boolean, default=True)
    confidence_score = Column(Float)  # 0.0-1.0 (how certain we are about device type)
```

### Device Types

```python
class DeviceType(str, Enum):
    PRINTER_3D = "printer_3d"
    PRINTER_LASER = "printer_laser"
    PRINTER_CNC = "printer_cnc"
    RASPBERRY_PI = "raspberry_pi"
    ESP32 = "esp32"
    ESP8266 = "esp8266"
    ARDUINO = "arduino"
    SMART_PLUG = "smart_plug"
    SMART_CAMERA = "smart_camera"
    SMART_SENSOR = "smart_sensor"
    OCTOPRINT = "octoprint"
    HOMEASSISTANT = "homeassistant"
    UNKNOWN = "unknown"
```

### Categorization Logic

**Port-based identification**:
- Port 7125 + HTTP → `printer_3d` (Moonraker)
- Port 5000 + HTTP → `octoprint`
- Port 8123 + HTTP → `homeassistant`
- Port 8888 + HTTP → `printer_cnc` (Snapmaker)
- Port 22 + "Raspberry Pi" in banner → `raspberry_pi`

**Service-based identification** (mDNS):
- `_octoprint._tcp` → `octoprint`
- `_moonraker._tcp` → `printer_3d`
- `_printer._tcp` → `printer_3d`
- `_ssh._tcp` + Raspberry Pi OS → `raspberry_pi`

**Manufacturer-specific**:
- Bamboo UDP response → `printer_3d` + `manufacturer=bamboo_labs`
- Snapmaker UDP response → `printer_cnc` + `manufacturer=snapmaker`
- MAC address OUI lookup (Espressif → ESP32/ESP8266)

## API Endpoints

### Discovery Control

```python
# Trigger full network scan
POST /api/discovery/scan
Request: {
    "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp", "nmap"],  # optional
    "timeout_seconds": 30  # optional
}
Response: {
    "scan_id": "uuid",
    "started_at": "2025-11-11T12:00:00Z",
    "methods": ["mdns", "ssdp", "bamboo_udp"],
    "status": "running"
}

# Get scan status
GET /api/discovery/scan/{scan_id}
Response: {
    "scan_id": "uuid",
    "status": "completed",  # running, completed, failed
    "started_at": "...",
    "completed_at": "...",
    "devices_found": 12,
    "methods_completed": ["mdns", "ssdp"]
}
```

### Device Registry

```python
# List all discovered devices
GET /api/discovery/devices
Query params:
    - device_type: str (optional filter)
    - approved: bool (optional filter)
    - is_online: bool (optional filter)
Response: {
    "devices": [
        {
            "id": "uuid",
            "ip_address": "192.168.1.100",
            "hostname": "bamboo-h2d",
            "device_type": "printer_3d",
            "manufacturer": "bamboo_labs",
            "model": "X1 Carbon",
            "serial_number": "01P45165616",
            "services": [
                {"protocol": "mqtt", "port": 1883, "name": "Device Control"}
            ],
            "last_seen": "2025-11-11T12:00:00Z",
            "approved": false,
            "confidence_score": 0.95
        }
    ],
    "total": 12,
    "filters_applied": {"device_type": "printer_3d"}
}

# Get device details
GET /api/discovery/devices/{device_id}
Response: {
    "id": "uuid",
    "ip_address": "192.168.1.100",
    "mac_address": "00:11:22:33:44:55",
    "hostname": "bamboo-h2d",
    "device_type": "printer_3d",
    "manufacturer": "bamboo_labs",
    "model": "X1 Carbon",
    "serial_number": "01P45165616",
    "firmware_version": "1.5.0",
    "services": [...],
    "capabilities": {
        "print_volume": {"x": 256, "y": 256, "z": 256},
        "multi_material": true
    },
    "discovered_at": "...",
    "last_seen": "...",
    "discovery_method": "bamboo_udp",
    "approved": false,
    "notes": null,
    "confidence_score": 0.95
}

# Approve device for integration
POST /api/discovery/devices/{device_id}/approve
Request: {
    "notes": "Bamboo Labs H2D - Main workshop printer"
}
Response: {
    "id": "uuid",
    "approved": true,
    "approved_at": "2025-11-11T12:00:00Z",
    "approved_by": "admin"
}

# Delete device from registry
DELETE /api/discovery/devices/{device_id}
Response: {
    "success": true,
    "message": "Device removed from registry"
}
```

### Filtering and Search

```python
# Search devices by various criteria
GET /api/discovery/search
Query params:
    - q: str (search hostname, model, manufacturer)
    - ip: str (IP address or subnet like 192.168.1.0/24)
    - device_type: str
    - manufacturer: str
Response: {
    "devices": [...],
    "total": 5,
    "query": "bamboo"
}

# Get printers only
GET /api/discovery/printers
Response: {
    "printers": [
        {
            "id": "uuid",
            "ip_address": "192.168.1.100",
            "device_type": "printer_3d",
            "manufacturer": "bamboo_labs",
            "model": "X1 Carbon",
            "approved": false
        }
    ],
    "total": 3
}
```

## ReAct Agent Tools (MCP)

### Tool Definitions

```yaml
discovery.scan_network:
  server: broker
  description: "Trigger network discovery scan to find IoT devices (printers, Raspberry Pi, ESP32)"
  hazard_class: none
  requires_confirmation: false
  budget_tier: free
  enabled: true
  parameters:
    methods: ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp", "nmap"]  # optional
    timeout_seconds: 30  # optional

discovery.list_devices:
  server: broker
  description: "List all discovered devices with optional filtering by type or approval status"
  hazard_class: none
  requires_confirmation: false
  budget_tier: free
  enabled: true
  parameters:
    device_type: str  # optional: "printer_3d", "raspberry_pi", "esp32", etc.
    approved: bool    # optional: true, false
    is_online: bool   # optional: true, false

discovery.find_printers:
  server: broker
  description: "Find all 3D printers, CNC mills, and laser engravers on the network"
  hazard_class: none
  requires_confirmation: false
  budget_tier: free
  enabled: true

discovery.approve_device:
  server: broker
  description: "Approve a discovered device for integration and control"
  hazard_class: low
  requires_confirmation: true
  confirmation_phrase: "Confirm: approve"
  budget_tier: free
  enabled: true
  parameters:
    device_id: str  # required
    notes: str      # optional
```

## Scanning Strategy

### Periodic Background Scans

**Frequency**: Every 15 minutes (configurable via `DISCOVERY_SCAN_INTERVAL_MINUTES`)

**Methods**: Fast scans only (mDNS, SSDP, manufacturer-specific UDP)

**Purpose**:
- Update IP addresses for known devices (DHCP changes)
- Detect new devices coming online
- Mark devices as offline if unreachable

**Performance**:
- mDNS: ~5 seconds
- SSDP: ~3 seconds
- Bamboo UDP: ~2 seconds
- Snapmaker UDP: ~2 seconds
- Total: ~12 seconds per scan

### On-Demand Full Scans

**Trigger**: ReAct agent tool call or API request

**Methods**: All methods including network scanning (nmap)

**Purpose**:
- Initial device discovery
- User-requested comprehensive scan
- Troubleshooting connectivity issues

**Performance**:
- Full scan: 30-60 seconds (depends on network size)

### Incremental Updates

**Continuous monitoring** via mDNS service browser:
- Subscribe to mDNS service announcements
- Real-time updates when devices advertise
- Zero overhead when network is stable

## Configuration

### Environment Variables

```bash
# Discovery Service
DISCOVERY_PORT=8500
DISCOVERY_SCAN_INTERVAL_MINUTES=15
DISCOVERY_ENABLE_PERIODIC_SCANS=true
DISCOVERY_ENABLE_NMAP=true  # Network scanning requires nmap binary

# Network Configuration
DISCOVERY_NETWORK_SUBNET=192.168.1.0/24  # Default auto-detected
DISCOVERY_TIMEOUT_SECONDS=30

# Scanner Enablement
DISCOVERY_ENABLE_MDNS=true
DISCOVERY_ENABLE_SSDP=true
DISCOVERY_ENABLE_BAMBOO_UDP=true
DISCOVERY_ENABLE_SNAPMAKER_UDP=true
DISCOVERY_ENABLE_NETWORK_SCAN=true
```

## Integration with Existing Services

### Fabrication Service Integration

**Problem**: Fabrication service currently requires manual IP configuration in `.env`

**Solution**: Query discovery service for printer IPs

```python
# services/fabrication/src/fabrication/status/printer_status.py
async def get_printer_ip(self, printer_id: str) -> Optional[str]:
    """Query discovery service for current printer IP"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DISCOVERY_BASE}/api/discovery/search",
            params={"q": printer_id, "device_type": "printer_3d", "approved": True}
        )
        if response.status_code == 200:
            data = response.json()
            if data["devices"]:
                return data["devices"][0]["ip_address"]
    return None
```

### Gateway Integration

**New endpoint**: Proxy discovery API for UI access

```python
# services/gateway/src/gateway/routes/discovery.py
from fastapi import APIRouter

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

@router.post("/scan")
async def trigger_scan(request: dict) -> dict:
    """Proxy to discovery service"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{DISCOVERY_BASE}/api/discovery/scan",
            json=request
        )
        return response.json()

@router.get("/devices")
async def list_devices(
    device_type: Optional[str] = None,
    approved: Optional[bool] = None
) -> dict:
    """Proxy device list with filters"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DISCOVERY_BASE}/api/discovery/devices",
            params={"device_type": device_type, "approved": approved}
        )
        return response.json()
```

### Brain Service Integration

Add discovery tools to ReAct agent toolset via broker MCP server.

## User Workflow

### Initial Setup

1. **Trigger first scan**: User asks "KITTY, scan the network for devices"
2. **Discovery runs**: All scanner methods execute (30-60s)
3. **Results displayed**: Brain reports findings with categories
   ```
   Found 12 devices on network:

   3D Printers:
   - Bamboo Labs X1 Carbon (192.168.1.100) - Not approved
   - Elegoo Neptune 4 Pro (192.168.1.200) - Not approved

   Raspberry Pi:
   - raspberrypi-office (192.168.1.150) - Not approved

   ESP32:
   - esp32-sensor-01 (192.168.1.180) - Not approved

   Unknown devices: 8
   ```

4. **User approval**: User approves specific devices
   ```
   User: "Approve the Bamboo Labs printer"
   KITTY: "Device approved. I can now use 192.168.1.100 for the Bamboo Labs H2D."
   ```

### Ongoing Operation

1. **Periodic scans**: Discovery service scans every 15 minutes
2. **IP updates**: If Bamboo H2D moves from `.100` to `.105`, registry auto-updates
3. **New device alerts**: When new device appears, Brain notifies user
4. **Integration**: Fabrication service queries discovery for current printer IPs

## Success Criteria

- ✅ Discover all printers on network (Bamboo, Elegoo, Snapmaker)
- ✅ Identify Raspberry Pi devices by hostname and SSH banner
- ✅ Detect ESP32/ESP8266 via MAC address OUI lookup
- ✅ Track IP address changes for DHCP-assigned devices
- ✅ Support user approval workflow (no auto-configuration)
- ✅ Periodic background scans complete in <15 seconds
- ✅ Full on-demand scans complete in <60 seconds
- ✅ ReAct agent can discover and list devices via MCP tools
- ✅ Fabrication service can query for printer IPs dynamically

## Future Enhancements (Phase 2)

1. **Deep device interrogation**: Query device capabilities with credentials
2. **Automatic service configuration**: Generate printer configs after approval
3. **Device health monitoring**: Track uptime, temperature, error states
4. **Smart device control**: Generic IoT control interface for ESP32/Raspberry Pi
5. **Network topology mapping**: Visualize device locations and relationships
6. **MAC address tracking**: Persistent device identification across IP changes
7. **SNMP support**: Enterprise network device discovery
8. **IPv6 support**: Dual-stack discovery
