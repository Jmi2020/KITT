# Network Discovery Service Testing Guide

This guide walks through testing the discovery service locally and in Docker.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local testing)
- Network with discoverable devices (or mock mode)

## Setup

### 1. Configure Environment

```bash
# Copy example env file (if not already done)
cp .env.example .env

# Edit .env with discovery settings
nano .env
```

**Discovery variables:**
```bash
# Network Discovery Service
DISCOVERY_PORT=8500
DISCOVERY_SCAN_INTERVAL_MINUTES=15
DISCOVERY_ENABLE_PERIODIC_SCANS=true

# Scanner Settings
DISCOVERY_ENABLE_MDNS=true
DISCOVERY_ENABLE_SSDP=true
DISCOVERY_ENABLE_BAMBOO_UDP=true
DISCOVERY_ENABLE_SNAPMAKER_UDP=true
DISCOVERY_ENABLE_NETWORK_SCAN=false  # Requires nmap, disabled by default
```

### 2. Apply Database Migrations

The discovery service requires PostgreSQL tables for device registry:

```bash
# From repo root
alembic -c services/common/alembic.ini revision --autogenerate -m "Add discovery tables"
alembic -c services/common/alembic.ini upgrade head
```

## Docker Compose Testing

### Validate Configuration

```bash
cd infra/compose

# Check docker-compose.yml syntax
docker compose config --quiet
echo $?  # Should print 0 (success)

# View resolved configuration
docker compose config | grep -A 20 discovery:
```

### Build Discovery Service

```bash
# Build just the discovery service
docker compose build discovery

# Check build success
docker images | grep discovery
```

### Start Dependencies First

```bash
# Start infrastructure services
docker compose up -d postgres mosquitto

# Wait 10 seconds for startup
sleep 10

# Check services are running
docker compose ps postgres mosquitto
```

### Start Discovery Service

```bash
# Start discovery service
docker compose up -d discovery

# Wait for health check
sleep 15

# Check service is healthy
docker compose ps discovery
# STATUS should show "healthy" after start_period

# View logs
docker compose logs -f discovery
# Press Ctrl+C to stop following
```

### Test Health Endpoint

```bash
# Test from host
curl http://localhost:8500/healthz

# Expected response:
# {"status":"ok"}

# Test from inside Docker network
docker compose exec discovery curl http://localhost:8500/healthz
```

### Start Full Stack

```bash
# Start all services including brain and gateway
cd infra/compose
docker compose up -d

# Wait for all services to start
sleep 30

# Check all services
docker compose ps

# All services should be "running" or "healthy"
```

## API Endpoint Testing

### 1. Test Device Listing (Initial - Empty)

```bash
# Via gateway
curl http://localhost:8080/api/discovery/devices

# Via discovery service directly
curl http://localhost:8500/api/discovery/devices

# Expected response (empty initially):
# {
#   "devices": [],
#   "total": 0,
#   "filters_applied": {}
# }
```

### 2. Trigger Network Scan

```bash
# Trigger full discovery scan
curl -X POST http://localhost:8500/api/discovery/scan \
  -H 'Content-Type: application/json' \
  -d '{
    "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp"],
    "timeout_seconds": 30
  }'

# Expected response:
# {
#   "scan_id": "uuid",
#   "status": "running",
#   "started_at": "2025-11-11T12:00:00Z",
#   "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp"],
#   "devices_found": 0
# }

# Save scan_id for status check
SCAN_ID="<uuid from response>"
```

### 3. Check Scan Status

```bash
# Wait 30 seconds for scan to complete
sleep 30

# Check scan status
curl http://localhost:8500/api/discovery/scan/$SCAN_ID

# Expected response:
# {
#   "scan_id": "uuid",
#   "status": "completed",
#   "started_at": "2025-11-11T12:00:00Z",
#   "completed_at": "2025-11-11T12:00:30Z",
#   "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp"],
#   "devices_found": 5,
#   "errors": []
# }
```

### 4. List Discovered Devices

```bash
# List all devices
curl http://localhost:8500/api/discovery/devices

# Expected response:
# {
#   "devices": [
#     {
#       "id": "uuid",
#       "ip_address": "192.168.1.100",
#       "hostname": "bamboo-h2d",
#       "device_type": "printer_3d",
#       "manufacturer": "Bamboo Labs",
#       "model": "X1 Carbon",
#       "serial_number": "01P45165616",
#       "last_seen": "2025-11-11T12:00:30Z",
#       "approved": false,
#       "is_online": true,
#       "confidence_score": 0.95,
#       ...
#     },
#     ...
#   ],
#   "total": 5
# }
```

### 5. Filter Devices

```bash
# List only printers
curl http://localhost:8500/api/discovery/printers

# List only unapproved devices
curl "http://localhost:8500/api/discovery/devices?approved=false"

# List only online devices
curl "http://localhost:8500/api/discovery/devices?is_online=true"

# List by device type
curl "http://localhost:8500/api/discovery/devices?device_type=printer_3d"

# List by manufacturer
curl "http://localhost:8500/api/discovery/devices?manufacturer=bamboo"
```

### 6. Search Devices

```bash
# Search by hostname/IP/model
curl "http://localhost:8500/api/discovery/search?q=bamboo"

# Search by IP address
curl "http://localhost:8500/api/discovery/search?q=192.168.1.100"

# Expected response:
# {
#   "devices": [
#     {...}  // Matching devices
#   ],
#   "total": 1,
#   "filters_applied": {"query": "bamboo"}
# }
```

### 7. Get Device Details

```bash
# Get specific device by ID
DEVICE_ID="<uuid from device list>"
curl http://localhost:8500/api/discovery/devices/$DEVICE_ID

# Expected response:
# {
#   "id": "uuid",
#   "ip_address": "192.168.1.100",
#   "mac_address": "00:11:22:33:44:55",
#   "hostname": "bamboo-h2d",
#   "device_type": "printer_3d",
#   "manufacturer": "Bamboo Labs",
#   "model": "X1 Carbon",
#   "serial_number": "01P45165616",
#   "services": [
#     {"protocol": "mqtt", "port": 1883, "name": "Device Control"}
#   ],
#   "capabilities": {
#     "print_volume": {"x": 256, "y": 256, "z": 256},
#     "multi_material": true
#   },
#   "approved": false,
#   "is_online": true,
#   "confidence_score": 0.95
# }
```

### 8. Approve Device

```bash
# Approve device for integration
curl -X POST http://localhost:8500/api/discovery/devices/$DEVICE_ID/approve \
  -H 'Content-Type: application/json' \
  -d '{
    "notes": "Bamboo Labs H2D - Main workshop printer"
  }'

# Expected response:
# {
#   "id": "uuid",
#   "approved": true,
#   "approved_at": "2025-11-11T12:05:00Z",
#   "approved_by": "admin"
# }
```

### 9. Delete Device

```bash
# Remove device from registry
curl -X DELETE http://localhost:8500/api/discovery/devices/$DEVICE_ID

# Expected response:
# {
#   "success": true,
#   "message": "Device removed from registry"
# }
```

## Integration Testing

### Test via ReAct Agent (Full E2E)

**Prerequisites:** Brain service must be running with ReAct agent enabled.

```bash
# Start full stack
cd infra/compose
docker compose up -d

# Wait for brain to be ready
sleep 30

# Test via brain API
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Scan the network for devices",
    "user_id": "test-user",
    "conversation_id": "test-conv"
  }'

# Expected: Brain calls discovery.scan_network tool
# Response includes scan results
```

### Test Discovery Tool Calling

```bash
# Ask brain to list printers
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What printers are on the network?",
    "user_id": "test-user",
    "conversation_id": "test-conv"
  }'

# Expected: Brain calls discovery.find_printers tool
# Response includes printer list

# Ask brain to approve a device
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Approve the Bamboo Labs printer at 192.168.1.100",
    "user_id": "test-user",
    "conversation_id": "test-conv"
  }'

# Expected: Brain calls discovery.approve_device tool
# Response confirms approval
```

## Periodic Scanning

### Monitor Periodic Scans

```bash
# View discovery logs to see periodic scans
docker compose logs -f discovery

# You should see logs every 15 minutes:
# "Starting periodic discovery scan"
# "Periodic scan completed: X devices found, Y errors"

# Check scan history
curl http://localhost:8500/api/discovery/scans
```

### Adjust Scan Interval

```bash
# In .env, change scan interval
DISCOVERY_SCAN_INTERVAL_MINUTES=5

# Restart discovery service
docker compose restart discovery

# Scans will now run every 5 minutes
```

### Disable Periodic Scans

```bash
# In .env
DISCOVERY_ENABLE_PERIODIC_SCANS=false

# Restart discovery service
docker compose restart discovery

# Only manual scans will run now
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs discovery

# Common issues:
# - Port 8500 already in use: Change DISCOVERY_PORT in .env
# - PostgreSQL connection failed: Ensure postgres service is running
# - Missing tables: Run Alembic migrations
```

### Health Check Failing

```bash
# Check if service is listening
docker compose exec discovery curl http://localhost:8500/healthz

# If curl fails:
# 1. Check app.py has @app.get("/healthz") endpoint
# 2. Check uvicorn is running: docker compose exec discovery ps aux | grep uvicorn
# 3. Check logs: docker compose logs discovery
```

### No Devices Found

```bash
# Test network connectivity from container
docker compose exec discovery ping 192.168.1.1  # Gateway

# If ping fails:
# - Docker network issue: Check network configuration
# - Firewall blocking: Check Docker firewall rules

# Enable more scanners
# In .env:
DISCOVERY_ENABLE_NETWORK_SCAN=true  # Enable nmap scanning

# Restart and scan again
docker compose restart discovery
curl -X POST http://localhost:8500/api/discovery/scan
```

### mDNS Discovery Not Working

```bash
# Check if mDNS is blocked by firewall
# mDNS uses UDP port 5353

# Test from host machine
dns-sd -B _services._dns-sd._udp .

# If no results, mDNS is likely blocked or no devices advertising

# Try manufacturer-specific scanners instead
curl -X POST http://localhost:8500/api/discovery/scan \
  -d '{"methods": ["bamboo_udp", "snapmaker_udp"]}'
```

### Database Connection Errors

```bash
# Check PostgreSQL is running
docker compose ps postgres

# Check connection string in .env
POSTGRES_URL=postgresql+asyncpg://kitty:changeme@postgres:5432/kitty

# Test connection from discovery container
docker compose exec discovery python -c "
from sqlalchemy import create_engine
engine = create_engine('postgresql://kitty:changeme@postgres:5432/kitty')
conn = engine.connect()
print('Connection successful')
"
```

### Classification Confidence Low

If devices are discovered but classified as "unknown" with low confidence:

```bash
# Check device details
curl http://localhost:8500/api/discovery/devices/$DEVICE_ID

# Low confidence reasons:
# - No hostname (only IP address)
# - No mDNS/SSDP advertisement
# - Unknown MAC address vendor
# - Generic service ports only

# Manual classification:
# 1. Note the device's IP, hostname, and services
# 2. Update categorizer.py with new patterns
# 3. Rebuild discovery service
# 4. Rescan network
```

## Performance Benchmarks

Expected latencies (from localhost):

| Endpoint | Target | Typical |
|----------|--------|---------|
| /healthz | <100ms | 20ms |
| /devices (list) | <200ms | 50ms |
| /devices/{id} (get) | <100ms | 30ms |
| /scan (trigger) | <200ms | 80ms |
| Periodic scan (4 methods) | <15s | 12s |
| Full scan with nmap | <60s | 45s |

## Success Criteria

Discovery service testing is successful if:

- ✅ Service starts without errors
- ✅ Health check passes
- ✅ Scan endpoint triggers discovery
- ✅ Devices are discovered and stored in database
- ✅ Device categorization assigns correct types
- ✅ Filtering and search work correctly
- ✅ Device approval workflow functions
- ✅ Periodic scans run automatically (if enabled)
- ✅ ReAct agent can call discovery tools
- ✅ Fabrication service can query for printer IPs

## Mock Mode Testing

To test without real devices on network:

1. **Create mock device data:**
```bash
# Insert test devices directly into database
docker compose exec postgres psql -U kitty -d kitty -c "
INSERT INTO discovered_devices (
  id, ip_address, hostname, device_type, manufacturer, model,
  discovered_at, last_seen, discovery_method, is_online, confidence_score
) VALUES (
  gen_random_uuid(),
  '192.168.1.100',
  'bamboo-h2d-mock',
  'printer_3d',
  'Bamboo Labs',
  'X1 Carbon',
  NOW(),
  NOW(),
  'mock',
  true,
  1.0
);
"
```

2. **Query mock devices:**
```bash
curl http://localhost:8500/api/discovery/devices

# Should return the mock device
```

## Next Steps After Testing

1. **Configure periodic scans:** Adjust interval based on network size
2. **Approve discovered devices:** Use approval workflow for printers
3. **Integrate with fabrication:** Test dynamic IP lookup
4. **Monitor discovery logs:** Track new devices coming online
5. **Set up alerts:** Notify when new devices discovered

## Reporting Issues

When reporting issues, include:

1. **Docker Compose logs:**
```bash
docker compose logs discovery > discovery.log
docker compose logs postgres > postgres.log
```

2. **Service status:**
```bash
docker compose ps > compose-status.txt
```

3. **Network configuration:**
```bash
ip addr show > network-config.txt
# Or on macOS:
ifconfig > network-config.txt
```

4. **Scan results:**
```bash
curl http://localhost:8500/api/discovery/devices > devices.json
```

5. **Error message:** Full error response from API

6. **Environment:**
- OS: macOS / Linux / Windows
- Docker version: `docker --version`
- Network setup: Same subnet as devices? VPN? NAT?
- Firewall: Enabled? Rules?

File issues at: https://github.com/your-org/KITT/issues
