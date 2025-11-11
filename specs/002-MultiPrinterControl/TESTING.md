# Multi-Printer Control Testing Guide

This guide walks through testing the Phase 1 implementation locally and in Docker.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local testing)
- Access to printer network (or mock mode)

## Setup

### 1. Configure Environment

```bash
# Copy example env file (if not already done)
cp .env.example .env

# Edit .env with your printer IPs and credentials
nano .env
```

**Required printer variables:**
```bash
# Bamboo Labs H2D
BAMBOO_IP=192.168.1.100              # Your Bamboo IP
BAMBOO_SERIAL=01P45165616            # Your serial number
BAMBOO_ACCESS_CODE=your_16_char_code # Get from printer Settings → Network

# Elegoo Giga
ELEGOO_IP=192.168.1.200              # Your Elegoo IP
ELEGOO_MOONRAKER_PORT=7125           # Default Moonraker port

# Snapmaker (optional for Phase 1)
SNAPMAKER_IP=192.168.1.150
SNAPMAKER_PORT=8888
```

### 2. Copy .env to Compose Directory

```bash
# Docker Compose needs .env in its directory
cp .env infra/compose/.env
```

### 3. Create Printer Configuration (Optional)

```bash
cp config/printers.yaml.example config/printers.yaml
nano config/printers.yaml  # Update with your printer IPs
```

## Docker Compose Testing

### Validate Configuration

```bash
cd infra/compose

# Check docker-compose.yml syntax
docker compose config --quiet
echo $?  # Should print 0 (success)

# View resolved configuration
docker compose config | less
```

### Build Fabrication Service

```bash
# Build just the fabrication service
docker compose build fabrication

# Check build success
docker images | grep fabrication
```

### Start Dependencies First

```bash
# Start infrastructure services
docker compose up -d mosquitto redis

# Wait 10 seconds for startup
sleep 10

# Check services are running
docker compose ps mosquitto redis
```

### Start Fabrication Service

```bash
# Start fabrication service
docker compose up -d fabrication

# Wait for health check
sleep 15

# Check service is healthy
docker compose ps fabrication
# STATUS should show "healthy" after start_period

# View logs
docker compose logs -f fabrication
# Press Ctrl+C to stop following
```

### Test Health Endpoint

```bash
# Test from host
curl http://localhost:8300/healthz

# Expected response:
# {"status":"ok"}

# Test from inside Docker network
docker compose exec fabrication curl http://localhost:8300/healthz
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

### 1. Test Printer Status (No STL Required)

```bash
# Via gateway
curl http://localhost:8080/api/fabrication/printer_status

# Via fabrication service directly
curl http://localhost:8300/api/fabrication/printer_status

# Expected response:
# {
#   "printers": {
#     "bamboo_h2d": {
#       "printer_id": "bamboo_h2d",
#       "is_online": true/false,
#       "is_printing": false,
#       "status": "idle",
#       ...
#     },
#     "elegoo_giga": {...},
#     "snapmaker_artisan": {...}
#   }
# }
```

**Expected outcomes:**
- ✅ If printers are reachable: `is_online: true`
- ✗ If network unreachable: `is_online: false` (service should still respond)
- ✅ Service caches status for 30 seconds

### 2. Test Model Analysis (Requires STL)

Create a test STL or use an existing one:

```bash
# Create test directory
mkdir -p /Users/Shared/KITTY/artifacts/cad/test

# Download a simple STL (or use your own)
curl -o /Users/Shared/KITTY/artifacts/cad/test/cube.stl \
  https://raw.githubusercontent.com/mrdoob/three.js/master/examples/models/stl/ascii/slotted_disk.stl
```

**Test model analysis:**

```bash
curl -X POST http://localhost:8080/api/fabrication/analyze_model \
  -H 'Content-Type: application/json' \
  -d '{
    "stl_path": "/app/artifacts/cad/test/cube.stl",
    "print_mode": "3d_print"
  }'

# Expected response:
# {
#   "dimensions": {
#     "width": 100.0,
#     "depth": 100.0,
#     "height": 50.0,
#     "max_dimension": 100.0,
#     "volume": 500000.0,
#     ...
#   },
#   "recommended_printer": "bamboo_h2d",
#   "slicer_app": "BambuStudio",
#   "reasoning": "Model fits Bamboo H2D (100mm ≤ 250mm)...",
#   "printer_available": true,
#   "model_fits": true
# }
```

**Expected outcomes:**
- ✅ STL file loads successfully
- ✅ Dimensions extracted correctly
- ✅ Printer recommendation matches model size
- ✗ If STL not found: 404 error with helpful message

### 3. Test Slicer Launch (macOS Only)

**NOTE:** This test only works on macOS with slicer apps installed.

```bash
curl -X POST http://localhost:8080/api/fabrication/open_in_slicer \
  -H 'Content-Type: application/json' \
  -d '{
    "stl_path": "/app/artifacts/cad/test/cube.stl",
    "print_mode": "3d_print"
  }'

# Expected response:
# {
#   "success": true,
#   "printer_id": "bamboo_h2d",
#   "slicer_app": "BambuStudio",
#   "stl_path": "/app/artifacts/cad/test/cube.stl",
#   "reasoning": "Model fits Bamboo H2D...",
#   "model_dimensions": {...},
#   "printer_available": true
# }

# BambuStudio should open with the STL file loaded
```

**Expected outcomes:**
- ✅ On macOS: Slicer app opens with STL
- ✗ In Docker: Error (macOS `open` command not available in container)
- ✗ If slicer not installed: 404 error with download link

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
    "query": "What printers are available?",
    "user_id": "test-user",
    "conversation_id": "test-conv"
  }'

# Expected: Brain calls fabrication.printer_status tool
# Response includes printer status
```

### Test Tool Calling

```bash
# Ask brain to analyze a model
curl -X POST http://localhost:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Analyze the model at /app/artifacts/cad/test/cube.stl",
    "user_id": "test-user",
    "conversation_id": "test-conv"
  }'

# Expected: Brain calls fabrication.analyze_model tool
# Response includes dimensions and printer recommendation
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs fabrication

# Common issues:
# - Port 8300 already in use: Change FABRICATION_PORT in .env
# - Volume mount issues: Check KITTY_ARTIFACTS_DIR exists
# - Dependency issues: Ensure mosquitto and redis are running
```

### Health Check Failing

```bash
# Check if service is listening
docker compose exec fabrication curl http://localhost:8300/healthz

# If curl fails:
# 1. Check app.py has @app.get("/healthz") endpoint
# 2. Check uvicorn is running: ps aux | grep uvicorn
# 3. Check logs: docker compose logs fabrication
```

### Can't Connect to Printers

```bash
# Test network connectivity from container
docker compose exec fabrication ping 192.168.1.100  # Bamboo IP

# If ping fails:
# - Docker network issue: Use host network mode (network_mode: host)
# - Printer on different subnet: Check router settings
# - Firewall blocking: Check Docker firewall rules
```

### STL Analysis Fails

```bash
# Check STL file is accessible
docker compose exec fabrication ls -la /app/artifacts/cad/test/

# If file not found:
# - Check KITTY_ARTIFACTS_DIR in .env
# - Check volume mount in docker-compose.yml
# - Ensure file exists on host: ls -la /Users/Shared/KITTY/artifacts/
```

### Slicer Won't Launch

**In Docker container:** This is expected. Slicer launching only works on macOS host.

**On macOS:**
```bash
# Check slicer is installed
mdfind kMDItemCFBundleIdentifier == 'com.bambulab.bambu-studio'

# If empty: Install BambuStudio from https://bambulab.com/en/download
```

## Performance Benchmarks

Expected latencies (from localhost):

| Endpoint | Target | Typical |
|----------|--------|---------|
| /healthz | <100ms | 20ms |
| /printer_status (cached) | <200ms | 50ms |
| /printer_status (cold) | <2s | 800ms |
| /analyze_model (10MB STL) | <1s | 400ms |
| /analyze_model (100MB STL) | <5s | 2s |
| /open_in_slicer | <2s | 800ms |

## Success Criteria

Phase 1 testing is successful if:

- ✅ All services start without errors
- ✅ Fabrication service health check passes
- ✅ Printer status endpoint returns data (even if printers offline)
- ✅ STL analysis extracts dimensions correctly
- ✅ Printer selection logic matches specification (quality-first)
- ✅ Error handling provides helpful messages
- ✅ ReAct agent can call fabrication tools (if enabled)

## Mock Mode Testing

To test without real printers:

1. Set mock mode environment variables:
```bash
# In .env
FABRICATION_MOCK_MODE=true
```

2. Printer status will return fake data:
```json
{
  "bamboo_h2d": {"is_online": true, "is_printing": false, "status": "idle"},
  "elegoo_giga": {"is_online": true, "is_printing": false, "status": "idle"},
  "snapmaker_artisan": {"is_online": true, "is_printing": false, "status": "idle"}
}
```

**Note:** Mock mode is not yet implemented in Phase 1. PRs welcome!

## Next Steps After Testing

1. **Create real printer config:** Update .env with actual printer IPs
2. **Test with real STL files:** Use models from your CAD workflow
3. **Test slicer launching:** Verify BambuStudio/ElegySlicer/Luban open correctly
4. **Integrate with CAD pipeline:** Test cad.generate_model → fabrication.open_in_slicer workflow
5. **Monitor printer status:** Use /printer_status to track print jobs

## Reporting Issues

When reporting issues, include:

1. **Docker Compose logs:**
```bash
docker compose logs fabrication > fabrication.log
docker compose logs gateway > gateway.log
docker compose logs brain > brain.log
```

2. **Service status:**
```bash
docker compose ps > compose-status.txt
```

3. **Configuration:**
```bash
docker compose config > compose-config.yml
# Redact sensitive data (IP addresses, access codes)
```

4. **Error message:** Full error response from API

5. **Environment:**
- OS: macOS / Linux / Windows
- Docker version: `docker --version`
- Network setup: Same subnet as printers? VPN? NAT?

File issues at: https://github.com/your-org/KITT/issues
