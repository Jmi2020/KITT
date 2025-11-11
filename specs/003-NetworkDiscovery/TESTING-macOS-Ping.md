# Network Discovery Testing Guide - macOS/Docker Desktop with Ping Sweep

This guide provides step-by-step testing procedures for KITTY's network discovery service, specifically optimized for macOS/Docker Desktop environments with ICMP ping sweep support.

## Prerequisites

### Required
- macOS 14+ with Docker Desktop (Apple Silicon or Intel)
- Network access to target devices (printers, Raspberry Pi, ESP32, etc.)
- Know your network CIDR (e.g., `192.168.1.0/24`)

### Optional
- `jq` for JSON parsing: `brew install jq`
- `curl` for API testing (pre-installed on macOS)

## Quick Start

### 1. Configuration Setup

**Edit your `.env` file:**
```bash
cd /path/to/KITT

# Copy example if .env doesn't exist
cp .env.example .env

# Edit the following discovery settings:
```

**Minimal Configuration:**
```env
# Enable network discovery
DISCOVERY_ENABLE_PERIODIC_SCANS=true
DISCOVERY_ENABLE_NETWORK_SCAN=true

# Configure your network subnet(s)
# Find your subnet with: ipconfig getifaddr en0
DISCOVERY_SUBNETS=["192.168.1.0/24"]

# Scan intervals (adjust as needed)
DISCOVERY_SCAN_INTERVAL_MINUTES=15        # Fast scans
DISCOVERY_PING_SWEEP_INTERVAL_MINUTES=60  # Ping sweeps

# Enable/disable specific scanners
DISCOVERY_ENABLE_MDNS=true
DISCOVERY_ENABLE_SSDP=true
DISCOVERY_ENABLE_BAMBOO_UDP=true
DISCOVERY_ENABLE_SNAPMAKER_UDP=true
```

### 2. Find Your Network Subnet

```bash
# Get your Mac's IP address
ipconfig getifaddr en0
# Example output: 192.168.1.42

# Your subnet is likely: 192.168.1.0/24
# Or check router settings for DHCP range
```

### 3. Start Discovery Service

```bash
cd infra/compose

# Rebuild discovery service with new dependencies
docker-compose build discovery

# Start discovery service
docker-compose up -d discovery

# Verify service is running
docker-compose ps discovery
```

**Expected Output:**
```
NAME                COMMAND                  SERVICE      STATUS
discovery-1         "python app.py"          discovery    Up (healthy)
```

## Verification Tests

### Test 1: Health Check

```bash
curl http://localhost:8500/healthz
```

**Expected:**
```json
{"status": "ok"}
```

### Test 2: View Service Logs

```bash
# Follow logs in real-time
docker-compose logs -f discovery

# Look for these key messages:
# - "Enabled scanners: ['mdns', 'ssdp', 'bamboo_udp', 'snapmaker_udp', 'network_scan']"
# - "Ping sweep subnets: ['192.168.1.0/24']"
# - "Starting periodic discovery scan"
# - "Starting periodic ping sweep (1 subnets)"
# - "Ping sweep will scan 254 hosts across 1 subnets"
# - "Ping sweep completed: X devices found, 0 errors"
```

### Test 3: List All Discovered Devices

```bash
curl http://localhost:8500/api/discovery/devices | jq
```

**Expected Response:**
```json
{
  "devices": [
    {
      "id": "uuid-here",
      "discovered_at": "2025-11-11T12:00:00",
      "last_seen": "2025-11-11T12:15:00",
      "discovery_method": "network_scan",
      "ip_address": "192.168.1.100",
      "mac_address": null,
      "hostname": null,
      "device_type": "unknown",
      "manufacturer": null,
      "model": null,
      "capabilities": {
        "latency_ms": 2.34,
        "packet_loss": 0.0,
        "jitter_ms": 0.12
      },
      "confidence_score": 0.3,
      "is_online": true,
      "approved": false
    }
  ],
  "total": 12,
  "filters_applied": {}
}
```

### Test 4: List Only Printers

```bash
curl http://localhost:8500/api/discovery/printers | jq
```

**Expected:**
- Devices with `device_type` of `printer_3d`, `printer_cnc`, or `printer_laser`
- Higher confidence scores for devices discovered via Bamboo/Snapmaker UDP

### Test 5: Search for Specific Device

```bash
# Search by IP
curl "http://localhost:8500/api/discovery/search?q=192.168.1.100" | jq

# Search by hostname (if discovered)
curl "http://localhost:8500/api/discovery/search?q=bambu" | jq
```

### Test 6: Trigger Manual Scan

```bash
# Run all scanners with 60s timeout
curl -X POST http://localhost:8500/api/discovery/scan \
  -H "Content-Type: application/json" \
  -d '{
    "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp", "network_scan"],
    "timeout_seconds": 60
  }' | jq

# Save scan_id from response
SCAN_ID="uuid-from-response"

# Check scan status
curl "http://localhost:8500/api/discovery/scan/$SCAN_ID" | jq
```

**Expected Response:**
```json
{
  "scan_id": "uuid-here",
  "status": "running",
  "started_at": "2025-11-11T12:00:00",
  "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp", "network_scan"],
  "devices_found": 0
}
```

Wait 30-60 seconds, then check again:
```json
{
  "scan_id": "uuid-here",
  "status": "completed",
  "started_at": "2025-11-11T12:00:00",
  "completed_at": "2025-11-11T12:01:00",
  "methods": ["mdns", "ssdp", "bamboo_udp", "snapmaker_udp", "network_scan"],
  "devices_found": 15,
  "errors": []
}
```

## Advanced Testing

### Test 7: Verify Ping Sweep Performance

```bash
# Enable detailed logging
docker-compose logs -f discovery | grep -E "(Ping sweep|multiping)"

# Look for:
# - "Expanded 192.168.1.0/24 to 254 hosts"
# - "Ping sweep will scan 254 hosts across 1 subnets"
# - Scan completion time (should be < 5 minutes for /24)
```

### Test 8: Test Multiple Subnets

**Edit `.env`:**
```env
DISCOVERY_SUBNETS=["192.168.1.0/24","10.0.0.0/24"]
```

**Restart:**
```bash
docker-compose restart discovery
```

**Verify in logs:**
```
Ping sweep subnets: ['192.168.1.0/24', '10.0.0.0/24']
Starting periodic ping sweep (2 subnets)
Ping sweep will scan 508 hosts across 2 subnets
```

### Test 9: Verify NET_RAW Capability

```bash
# Check container capabilities
docker inspect $(docker ps -qf name=discovery) \
  | jq '.[0].HostConfig.CapAdd'

# Expected output:
# [
#   "NET_ADMIN",
#   "NET_RAW"
# ]
```

If missing, verify `infra/compose/docker-compose.yml` has:
```yaml
discovery:
  cap_add:
    - NET_ADMIN
    - NET_RAW
```

### Test 10: Test Scanner Enable/Disable

**Disable ping sweep:**
```env
DISCOVERY_ENABLE_NETWORK_SCAN=false
```

**Restart and verify:**
```bash
docker-compose restart discovery
docker-compose logs discovery | grep "Enabled scanners"

# Should NOT include 'network_scan':
# Enabled scanners: ['mdns', 'ssdp', 'bamboo_udp', 'snapmaker_udp']
```

## Troubleshooting

### Issue: No Devices Found

**Check 1: Verify subnet configuration**
```bash
# Get your Mac's IP
ipconfig getifaddr en0

# If output is 192.168.1.42, your subnet should be:
DISCOVERY_SUBNETS=["192.168.1.0/24"]
```

**Check 2: Verify firewall allows ICMP**
```bash
# From Mac host, test ping manually
ping -c 1 192.168.1.100

# If this fails, device may block ICMP or be offline
```

**Check 3: Check discovery service logs**
```bash
docker-compose logs discovery | grep -i error
```

### Issue: Ping Sweep Fails

**Check 1: Verify NET_RAW capability**
```bash
docker-compose logs discovery | grep -i "permission denied"

# If you see permission errors, rebuild:
docker-compose down discovery
docker-compose build discovery
docker-compose up -d discovery
```

**Check 2: Check icmplib installation**
```bash
docker-compose exec discovery python -c "import icmplib; print('OK')"
# Expected: OK
```

### Issue: High CPU During Ping Sweep

This is normal for large subnets. To reduce:

**Option 1: Increase ping interval**
```bash
# Edit scan_scheduler.py line 141:
ping_interval=0.1  # Instead of 0.01 (10x slower)
```

**Option 2: Reduce scan frequency**
```env
DISCOVERY_PING_SWEEP_INTERVAL_MINUTES=120  # Every 2 hours instead of 1
```

**Option 3: Narrow subnet range**
```env
# Instead of scanning entire /24:
DISCOVERY_SUBNETS=["192.168.1.0/28"]  # Only 14 hosts
```

### Issue: mDNS Not Finding Devices

**Expected on macOS/Docker Desktop** - See `Research/KITTY_Network_Discovery_macOS.md` for details.

Multicast mDNS has limitations in Docker Desktop. Rely on:
- ✅ SSDP (active M-SEARCH)
- ✅ Bamboo/Snapmaker UDP (broadcast)
- ✅ ICMP ping sweep (active)

### Issue: Database Connection Errors

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check discovery can connect
docker-compose logs discovery | grep -i "database"

# If migration errors, run migrations:
docker-compose exec discovery alembic upgrade head
```

## Success Criteria

✅ **Service Health:**
- `/healthz` returns `{"status": "ok"}`
- No error logs in `docker-compose logs discovery`

✅ **Fast Scans (every 15 min):**
- Logs show "Starting periodic discovery scan"
- At least 1 device found (your own Mac, router, etc.)

✅ **Ping Sweeps (every 60 min):**
- Logs show "Starting periodic ping sweep"
- Multiple devices found (more than fast scans)
- Completion time < 5 minutes for /24 subnet

✅ **Device Registry:**
- `/api/discovery/devices` returns devices
- Devices have valid IPs matching your network
- `is_online=true` for responsive devices

✅ **Printer Detection:**
- Bamboo/Snapmaker printers found via UDP
- Higher confidence scores (0.7-0.9) for printer-specific discoveries
- Lower confidence (0.3) for ping-only discoveries

## Performance Benchmarks

**Expected Performance (192.168.1.0/24):**
- Fast scan (mDNS + SSDP + UDP): 3-5 seconds
- Ping sweep (254 hosts): 30-60 seconds
- Memory usage: ~50-100 MB
- CPU usage: <5% idle, 10-20% during ping sweep

**Large Subnet (10.0.0.0/16):**
- ⚠️ **Not recommended** - 65,534 hosts will take hours
- Use smaller ranges or disable ping sweep for large networks

## Next Steps

Once discovery is working:

1. **Approve Devices:** Use `/api/discovery/devices/{id}/approve` to mark devices for control
2. **Integrate with Fabrication:** Discovered printers appear in fabrication service
3. **Monitor MQTT:** Device state changes published to `kitty/discovery/devices`
4. **Enable Auto-Configuration:** Future enhancement to auto-configure approved devices

## Reference

- **Research Document:** `Research/KITTY_Network_Discovery_macOS.md`
- **Architecture Spec:** `specs/003-NetworkDiscovery/spec.md`
- **Implementation Plan:** `specs/003-NetworkDiscovery/plan.md`
- **API Documentation:** http://localhost:8500/docs (when service running)

## Support

If you encounter issues not covered here:
1. Check `docker-compose logs discovery` for errors
2. Verify network connectivity: `ping <target_ip>` from host
3. Check firewall settings (System Preferences → Security → Firewall)
4. Review `Research/KITTY_Network_Discovery_macOS.md` for macOS-specific limitations
