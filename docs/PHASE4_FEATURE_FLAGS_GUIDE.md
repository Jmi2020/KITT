# Phase 4 Print Monitoring Feature Flags Guide

## Overview

Phase 4 Print Monitoring introduces several external device dependencies (cameras, MQTT, MinIO storage). To enable incremental testing and development, all features are controlled by feature flags that can be individually enabled/disabled.

## Quick Start

### Development Mode (All External Deps Disabled)

For local development without hardware:

```bash
# In .env
ENABLE_PRINT_OUTCOME_TRACKING=true       # Database tracking only
ENABLE_CAMERA_CAPTURE=false              # No camera calls
ENABLE_MINIO_SNAPSHOT_UPLOAD=false       # Mock URLs only
ENABLE_HUMAN_FEEDBACK_REQUESTS=true      # MQTT notifications (if broker available)
```

### Testing Camera Integration (Raspberry Pi Only)

To test Raspberry Pi cameras without Bamboo Labs:

```bash
ENABLE_CAMERA_CAPTURE=true
ENABLE_RASPBERRY_PI_CAMERAS=true         # Enable HTTP snapshot capture
ENABLE_BAMBOO_CAMERA=false               # Keep Bamboo disabled
ENABLE_MINIO_SNAPSHOT_UPLOAD=false       # Test with mock URLs first

# Configure camera endpoints
SNAPMAKER_CAMERA_URL=http://snapmaker-pi.local:8080/snapshot.jpg
ELEGOO_CAMERA_URL=http://elegoo-pi.local:8080/snapshot.jpg
```

### Production Mode (All Features Enabled)

When all hardware is installed and tested:

```bash
ENABLE_PRINT_OUTCOME_TRACKING=true
ENABLE_CAMERA_CAPTURE=true
ENABLE_BAMBOO_CAMERA=true
ENABLE_RASPBERRY_PI_CAMERAS=true
ENABLE_MINIO_SNAPSHOT_UPLOAD=true
ENABLE_HUMAN_FEEDBACK_REQUESTS=true
HUMAN_FEEDBACK_AUTO_REQUEST=true
```

## Feature Flag Reference

### Master Switches

#### `ENABLE_PRINT_OUTCOME_TRACKING`
**Default:** `true`

Controls database storage of print outcomes. When disabled:
- `PrintOutcomeTracker.capture_outcome()` returns mock outcome without database insert
- Historical data collection is paused
- Print intelligence cannot accumulate data

**When to disable:** Never in production. Only disable for testing services without database access.

#### `ENABLE_CAMERA_CAPTURE`
**Default:** `false`

Master switch for all camera features. When disabled:
- All snapshot capture calls return mock URLs immediately
- No HTTP requests to Raspberry Pi cameras
- No MQTT requests to Bamboo Labs
- Visual evidence URLs are generated but no actual images captured

**When to enable:** After installing Raspberry Pi cameras or when Bamboo Labs printer is available.

### Camera-Specific Flags

#### `ENABLE_BAMBOO_CAMERA`
**Default:** `false`

Controls Bamboo Labs H2D built-in camera access via MQTT.

**Requirements:**
- `ENABLE_CAMERA_CAPTURE=true`
- MQTT client configured
- Bamboo Labs printer powered on and connected
- Valid access code in `BAMBOO_ACCESS_CODE`

**When disabled:** Bamboo Labs snapshot requests return `None`, falling back to mock URLs.

#### `ENABLE_RASPBERRY_PI_CAMERAS`
**Default:** `false`

Controls Raspberry Pi camera HTTP endpoints for Snapmaker and Elegoo.

**Requirements:**
- `ENABLE_CAMERA_CAPTURE=true`
- Raspberry Pi running with camera server (e.g., `mjpg-streamer`, `picamera2`)
- Valid URLs in `SNAPMAKER_CAMERA_URL` and `ELEGOO_CAMERA_URL`

**When disabled:** HTTP snapshot requests are skipped, mock URLs returned.

### Storage Flags

#### `ENABLE_MINIO_SNAPSHOT_UPLOAD`
**Default:** `false`

Controls actual file upload to MinIO S3-compatible storage.

**Requirements:**
- MinIO server running and accessible
- Valid credentials in `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY`
- Bucket exists: `MINIO_BUCKET` (default: `kitty-artifacts`)

**When disabled:** Snapshot URLs are generated (`minio://prints/job123/start_...jpg`) but no actual upload occurs. Useful for testing workflow without storage dependency.

**When to enable:** After MinIO is configured and tested independently.

### Feedback Flags

#### `ENABLE_HUMAN_FEEDBACK_REQUESTS`
**Default:** `true`

Controls MQTT notifications requesting human review after print completion.

**Requirements:**
- MQTT broker running and accessible
- UI subscribed to `kitty/fabrication/print/+/review_request`

**When disabled:** `PrintOutcomeTracker.request_human_review()` returns `False` immediately. Outcomes can still be captured, but UI won't receive review prompts.

**When to disable:** During automated testing or when MQTT broker is unavailable.

#### `HUMAN_FEEDBACK_AUTO_REQUEST`
**Default:** `true`

Automatically requests human feedback after every print completion.

**When disabled:** Human feedback must be manually requested via API or CLI. Useful when testing specific prints without notification spam.

### Intelligence Flags

#### `ENABLE_PRINT_INTELLIGENCE`
**Default:** `false`

Controls success prediction and recommendation generation based on historical data.

**Requirements:**
- Minimum historical outcomes: `PRINT_INTELLIGENCE_MIN_SAMPLES` (default: 30)
- PrintIntelligence class implementation (Task 2.4)

**When to enable:** After collecting sufficient historical data from Phase 1 human-in-loop operation.

#### `PRINT_INTELLIGENCE_MIN_SAMPLES`
**Default:** `30`

Minimum number of print outcomes required per material/printer combination before predictions are enabled.

## Configuration Parameters

### Camera Endpoints

#### `SNAPMAKER_CAMERA_URL`
**Default:** `http://snapmaker-pi.local:8080/snapshot.jpg`

HTTP endpoint for Snapmaker Artisan's Raspberry Pi camera.

**Example setups:**
- **mjpg-streamer**: `http://192.168.1.10:8080/?action=snapshot`
- **picamera2 web**: `http://snapmaker-pi.local:8000/snapshot.jpg`
- **Motion**: `http://192.168.1.10:8081/current`

#### `ELEGOO_CAMERA_URL`
**Default:** `http://elegoo-pi.local:8080/snapshot.jpg`

HTTP endpoint for Elegoo Giga's Raspberry Pi camera (to be installed).

### Snapshot Timing

#### `CAMERA_SNAPSHOT_INTERVAL_MINUTES`
**Default:** `5`

Interval between periodic progress snapshots during active prints.

**Recommendations:**
- **Development:** 1-2 minutes (faster feedback)
- **Production:** 5-10 minutes (balance storage vs. monitoring)
- **Long prints (>12h):** 10-15 minutes

#### `CAMERA_FIRST_LAYER_SNAPSHOT_DELAY`
**Default:** `5`

Minutes after print start to capture first layer snapshot (critical for failure detection).

**Recommendations:**
- **Fast printers (Bamboo H2D):** 3-5 minutes
- **Slow printers (Elegoo Giga):** 5-10 minutes
- Adjust based on typical first layer completion time

## Testing Scenarios

### Scenario 1: Test Print Outcome Tracking (No Cameras)

```bash
# .env
ENABLE_PRINT_OUTCOME_TRACKING=true
ENABLE_CAMERA_CAPTURE=false              # Mock URLs
ENABLE_MINIO_SNAPSHOT_UPLOAD=false
ENABLE_HUMAN_FEEDBACK_REQUESTS=false     # No MQTT

# Test code
from fabrication.monitoring import PrintOutcomeTracker, PrintOutcomeData

tracker = PrintOutcomeTracker(db_session, mqtt_client=None)
outcome_data = PrintOutcomeData(
    job_id="test_job_001",
    printer_id="snapmaker_artisan",
    material_id="pla_black_esun",
    started_at=datetime.now(),
    completed_at=datetime.now(),
    actual_duration_hours=2.5,
    actual_cost_usd=1.80,
    material_used_grams=75.0,
    print_settings={"nozzle_temp": 210, "bed_temp": 60},
)

outcome = tracker.capture_outcome(outcome_data)
assert outcome.job_id == "test_job_001"
```

### Scenario 2: Test Camera Capture (HTTP Only)

```bash
# .env
ENABLE_CAMERA_CAPTURE=true
ENABLE_RASPBERRY_PI_CAMERAS=true
ENABLE_BAMBOO_CAMERA=false
ENABLE_MINIO_SNAPSHOT_UPLOAD=false       # Mock URLs initially

# Ensure camera server is running
curl http://snapmaker-pi.local:8080/snapshot.jpg -o test_snapshot.jpg

# Test code
from fabrication.monitoring import CameraCapture

camera = CameraCapture(minio_client=None, mqtt_client=None)
result = await camera.capture_snapshot(
    printer_id="snapmaker_artisan",
    job_id="camera_test_001",
    milestone="start",
)

assert result.success
assert "camera_test_001" in result.url
```

### Scenario 3: Test Full Workflow with MinIO

```bash
# .env
ENABLE_CAMERA_CAPTURE=true
ENABLE_RASPBERRY_PI_CAMERAS=true
ENABLE_MINIO_SNAPSHOT_UPLOAD=true

# Ensure MinIO is running
docker ps | grep minio

# Test code
from minio import Minio
from fabrication.monitoring import CameraCapture

minio_client = Minio(
    "localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

camera = CameraCapture(minio_client=minio_client)
result = await camera.capture_snapshot(
    printer_id="snapmaker_artisan",
    job_id="full_test_001",
    milestone="start",
)

assert result.success
assert result.url.startswith("minio://")

# Verify upload
objects = list(minio_client.list_objects("prints", prefix="full_test_001/"))
assert len(objects) > 0
```

### Scenario 4: Test Human Feedback Workflow

```bash
# .env
ENABLE_PRINT_OUTCOME_TRACKING=true
ENABLE_HUMAN_FEEDBACK_REQUESTS=true

# Subscribe to MQTT topic
mosquitto_sub -h localhost -t "kitty/fabrication/print/+/review_request" -v

# Test code
tracker = PrintOutcomeTracker(db_session, mqtt_client)
outcome = tracker.capture_outcome(outcome_data)

# Request review (should see MQTT message)
success = tracker.request_human_review("test_job_001")
assert success

# Simulate human feedback
feedback = HumanFeedback(
    success=True,
    quality_scores={"layer_consistency": 9, "surface_finish": 8},
    notes="Perfect print!",
    reviewed_by="jeremiah",
)

outcome = tracker.record_human_feedback("test_job_001", feedback)
assert outcome.human_reviewed
assert outcome.quality_score == Decimal("85.0")  # (9+8)/2 * 10
```

## Troubleshooting

### Camera capture returns mock URLs even when enabled

**Check:**
1. `ENABLE_CAMERA_CAPTURE=true` (master switch)
2. `ENABLE_RASPBERRY_PI_CAMERAS=true` or `ENABLE_BAMBOO_CAMERA=true`
3. Camera endpoint is reachable: `curl $SNAPMAKER_CAMERA_URL`
4. Check logs for "disabled by feature flag" messages

### MQTT notifications not received

**Check:**
1. `ENABLE_HUMAN_FEEDBACK_REQUESTS=true`
2. MQTT broker is running: `docker ps | grep mosquitto`
3. Correct topic: `kitty/fabrication/print/{job_id}/review_request`
4. UI is subscribed to wildcard: `kitty/fabrication/print/+/review_request`

### MinIO upload fails

**Check:**
1. `ENABLE_MINIO_SNAPSHOT_UPLOAD=true`
2. MinIO credentials are valid
3. Bucket exists: `mc ls myminio/prints` (using MinIO client)
4. Network access: `curl http://localhost:9000/minio/health/live`

### Print outcome not stored in database

**Check:**
1. `ENABLE_PRINT_OUTCOME_TRACKING=true`
2. Database migration applied: `alembic upgrade head`
3. Material exists: `SELECT * FROM materials WHERE id = 'pla_black_esun';`
4. Check logs for "disabled by feature flag" or validation errors

## Migration Path

### Phase 1: Development (No Hardware)
All external dependencies disabled, test with mock data:

```bash
ENABLE_CAMERA_CAPTURE=false
ENABLE_MINIO_SNAPSHOT_UPLOAD=false
```

### Phase 2: Camera Integration
Enable cameras incrementally:

```bash
# Week 1: Snapmaker Raspberry Pi only
ENABLE_CAMERA_CAPTURE=true
ENABLE_RASPBERRY_PI_CAMERAS=true
# Test with Snapmaker for 1 week

# Week 2: Add Elegoo Giga Raspberry Pi
# Install Pi camera on Elegoo, test side-by-side

# Week 3: Add Bamboo Labs
ENABLE_BAMBOO_CAMERA=true
# Implement MQTT snapshot capture
```

### Phase 3: Storage Integration
Enable MinIO after camera testing complete:

```bash
ENABLE_MINIO_SNAPSHOT_UPLOAD=true
# Monitor storage growth, verify uploads
```

### Phase 4: Production
All features enabled, collect data for intelligence:

```bash
# Run for 30+ prints to collect baseline data
ENABLE_PRINT_INTELLIGENCE=false  # Still disabled

# After 30+ outcomes per material/printer combo:
ENABLE_PRINT_INTELLIGENCE=true   # Enable predictions
```

## See Also

- `docs/CV_PRINT_MONITORING_DESIGN.md` - Overall architecture
- `specs/004-FabricationIntelligence/spec.md` - Phase 4 specification
- `.env.example` - Complete environment variable reference
- `services/common/src/common/config.py` - Settings class definition
