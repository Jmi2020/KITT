# Vision Service Dashboard - User Guide

## Overview

The **Vision Service Dashboard** provides unified camera monitoring and snapshot capture capabilities across all 3D printers in the KITT system. This dashboard enables operators to view live camera feeds, capture snapshots manually, test camera connectivity, and browse recent snapshot galleries from print jobs.

**Status**: ✅ **Production Ready** (P2 #13 Implementation Complete)

**Access**: http://localhost:4173/?view=cameras

---

## Features

### 1. Multi-Camera Status Monitoring

**Camera Grid** displays status for all configured printers:
- **Bamboo Labs H2D**: Built-in camera via MQTT
- **Snapmaker Artisan**: Raspberry Pi camera via HTTP
- **Elegoo Orangestorm Giga**: Raspberry Pi camera via HTTP

Each camera card shows:
- **Printer Name**: Human-readable printer identifier
- **Camera Type Badge**:
  - 📡 Bamboo MQTT (built-in camera)
  - 🥧 Raspberry Pi (external camera module)
- **Connection Status**:
  - 🟢 Online: Camera responding
  - 🔴 Offline: Camera unreachable
  - ⚪ Unknown: Status not yet checked
- **Last Snapshot Preview**: Most recent captured image
- **Camera Endpoint**: HTTP URL for Pi cameras
- **Last Snapshot Time**: Timestamp of most recent capture

### 2. Live Feed Viewing

**Live View** feature for Raspberry Pi cameras:
- Click **"👁️ Live View"** to toggle live feed
- Embedded iframe streams from camera HTTP endpoint
- Automatic fallback to snapshot URL if stream unavailable
- External link provided for direct camera access

**Note**: Bamboo Labs cameras use MQTT and don't support HTTP streaming. Use Bamboo Studio or Handy app for live view.

### 3. Manual Snapshot Capture

**Capture Controls** on each camera card:
- **"📸 Capture Snapshot"** button triggers manual snapshot
- Captures image from camera and uploads to MinIO
- Generates unique job_id for manual captures (`manual_<timestamp>`)
- Returns MinIO URL for stored snapshot
- Updates camera status and preview after capture
- Shows capture progress with "⏳ Capturing..." indicator

### 4. Camera Connection Testing

**Test Connection** feature:
- Click **"🔍 Test Connection"** to verify camera availability
- Measures round-trip latency in milliseconds
- Confirms camera can capture and return images
- Displays success/failure with error details
- Useful for troubleshooting camera setup

### 5. Recent Snapshot Galleries

**Snapshot Gallery** section shows recent print jobs:
- Groups snapshots by job_id
- Displays all milestones:
  - **initial**: First snapshot after print start
  - **progress_N**: Periodic snapshots during print (every 5 minutes)
  - **final**: Snapshot after print completion
- Thumbnail grid with milestone badges
- Timestamps for each snapshot
- Linked to print outcomes (integrated with Print Intelligence Dashboard)

### 6. Real-Time Status Updates

**Auto-Refresh** functionality:
- Camera status refreshes every 30 seconds
- Manual refresh via browser reload
- Recent snapshots reload after capture
- Graceful degradation if backend unavailable

---

## Camera Architecture

### Bamboo Labs H2D (Built-in Camera)

**Camera Type**: Bamboo Labs integrated camera
**Access Method**: MQTT protocol
**Resolution**: HD (1280x720 or 1920x1080)
**Capabilities**:
- Snapshot on demand via MQTT command
- Timelapse video generation
- Live stream (via Bamboo Studio/Handy app)

**MQTT Topics**:
```
device/{serial}/request   # Send snapshot request
device/{serial}/report     # Receive snapshot data (ipcam.img field)
```

**Status**: Framework implemented, full MQTT integration pending

### Snapmaker Artisan (Raspberry Pi Camera)

**Camera Type**: Raspberry Pi Camera Module
**Access Method**: HTTP endpoint
**Default URL**: `http://snapmaker-pi.local:8080/snapshot.jpg`
**Resolution**: Configurable (recommend 1080p)
**Capabilities**:
- HTTP snapshot endpoint
- MJPEG live stream (port 8080)
- Motion detection (optional)

**Setup Requirements**:
1. Raspberry Pi with Camera Module connected
2. Camera streaming software (mjpg-streamer or motion)
3. Network accessibility from KITT system
4. Feature flag: `ENABLE_RASPBERRY_PI_CAMERAS=true`

### Elegoo Orangestorm Giga (Raspberry Pi Camera)

**Camera Type**: Raspberry Pi Camera Module (to be installed)
**Access Method**: HTTP endpoint
**Default URL**: `http://elegoo-pi.local:8080/snapshot.jpg`
**Resolution**: Configurable
**Capabilities**:
- Same as Snapmaker configuration
- HTTP snapshot endpoint
- MJPEG live stream

**Setup Requirements**:
- Same as Snapmaker Artisan
- Raspberry Pi mounted near printer
- Camera positioned to view build plate

---

## API Integration

The dashboard consumes the following fabrication service endpoints:

### GET /api/fabrication/cameras/status

Get status of all configured printer cameras.

**Response**:
```json
[
  {
    "printer_id": "bamboo_h2d",
    "camera_type": "bamboo_mqtt",
    "camera_url": null,
    "status": "unknown",
    "last_snapshot_url": "minio://prints/job123/final_20251116_120000.jpg",
    "last_snapshot_time": "2025-11-16T12:00:00Z"
  },
  {
    "printer_id": "snapmaker_artisan",
    "camera_type": "raspberry_pi_http",
    "camera_url": "http://snapmaker-pi.local:8080/snapshot.jpg",
    "status": "online",
    "last_snapshot_url": "minio://prints/job456/progress_20251116_120500.jpg",
    "last_snapshot_time": "2025-11-16T12:05:00Z"
  },
  {
    "printer_id": "elegoo_giga",
    "camera_type": "raspberry_pi_http",
    "camera_url": "http://elegoo-pi.local:8080/snapshot.jpg",
    "status": "offline",
    "last_snapshot_url": null,
    "last_snapshot_time": null
  }
]
```

### POST /api/fabrication/cameras/{printer_id}/snapshot

Capture snapshot from specific printer camera.

**Request Body**:
```json
{
  "job_id": "manual_1700000000000",
  "milestone": "manual"
}
```

**Response**:
```json
{
  "success": true,
  "url": "minio://prints/manual_1700000000000/manual_20251116_120000.jpg",
  "error": null,
  "milestone": "manual",
  "timestamp": "2025-11-16T12:00:00Z"
}
```

### GET /api/fabrication/cameras/{printer_id}/test

Test camera connection and measure latency.

**Response**:
```json
{
  "success": true,
  "latency_ms": 235.67,
  "error": null
}
```

### GET /api/fabrication/cameras/snapshots/recent

Get recent snapshot galleries grouped by print job.

**Query Parameters**:
- `limit` (optional): Maximum number of job galleries (default: 10, max: 100)

**Response**:
```json
[
  {
    "job_id": "print_20251116_001",
    "printer_id": "bamboo_h2d",
    "snapshots": [
      {
        "milestone": "initial",
        "url": "minio://prints/print_20251116_001/start_20251116_080000.jpg",
        "timestamp": "2025-11-16T08:00:00Z"
      },
      {
        "milestone": "progress_1",
        "url": "minio://prints/print_20251116_001/progress_20251116_080500.jpg",
        "timestamp": "2025-11-16T08:05:00Z"
      },
      {
        "milestone": "final",
        "url": "minio://prints/print_20251116_001/complete_20251116_120000.jpg",
        "timestamp": "2025-11-16T12:00:00Z"
      }
    ]
  }
]
```

---

## Usage Workflows

### Workflow 1: Monitor Camera Status

1. Navigate to Vision Service dashboard
2. Review camera status badges for all printers
3. Check last snapshot times to verify recent activity
4. Preview most recent snapshots in camera cards
5. Identify offline cameras for troubleshooting

### Workflow 2: Capture Manual Snapshot

1. Select printer camera to capture from
2. Click **"📸 Capture Snapshot"** button
3. Wait for capture confirmation (⏳ indicator shows progress)
4. Review snapshot URL in alert message
5. Check camera preview updated with new snapshot
6. Find snapshot in Recent Snapshots section

### Workflow 3: Test Camera Connection

1. Select camera to test
2. Click **"🔍 Test Connection"** button
3. Review test results:
   - ✅ Success: Camera online, latency shown
   - ❌ Failure: Error message with details
4. Use latency measurement to diagnose network issues
5. Retry after resolving connectivity problems

### Workflow 4: View Live Camera Feed

1. Select Raspberry Pi camera (Snapmaker or Elegoo)
2. Click **"👁️ Live View"** to toggle live feed
3. View embedded MJPEG stream in iframe
4. If stream doesn't load, click external camera URL link
5. Click **"👁️ Hide Live View"** to collapse

**Note**: Bamboo Labs cameras require Bamboo Studio or Handy app for live viewing.

### Workflow 5: Browse Recent Snapshots

1. Scroll to **Recent Snapshots** section
2. Review print jobs with captured images
3. Identify milestone badges (initial, progress_N, final)
4. Click thumbnails to view full-size snapshots
5. Cross-reference job_id with Print Intelligence Dashboard

---

## Configuration

### Feature Flags

**Camera Capture Master Switch**:
```bash
ENABLE_CAMERA_CAPTURE=false  # Set to true to enable all camera features
```

**Bamboo Labs Camera**:
```bash
ENABLE_BAMBOO_CAMERA=false   # Enable Bamboo Labs MQTT snapshots
```

**Raspberry Pi Cameras**:
```bash
ENABLE_RASPBERRY_PI_CAMERAS=false  # Enable Snapmaker/Elegoo HTTP snapshots
```

**Camera Endpoints** (Raspberry Pi):
```bash
SNAPMAKER_CAMERA_URL=http://snapmaker-pi.local:8080/snapshot.jpg
ELEGOO_CAMERA_URL=http://elegoo-pi.local:8080/snapshot.jpg
```

**Snapshot Settings**:
```bash
CAMERA_SNAPSHOT_INTERVAL_MINUTES=5       # Progress snapshot interval
CAMERA_FIRST_LAYER_SNAPSHOT_DELAY=5      # Delay after start for first layer
```

**MinIO Upload**:
```bash
ENABLE_MINIO_SNAPSHOT_UPLOAD=false  # Set to true for actual uploads (vs. mock URLs)
```

### Development Mode

With cameras disabled (`ENABLE_CAMERA_CAPTURE=false`):
- Dashboard loads with mock camera data
- Snapshot capture returns mock URLs immediately
- No actual camera connections attempted
- Useful for testing UI without hardware

---

## Raspberry Pi Camera Setup

### Hardware Requirements

- **Raspberry Pi**: Model 3B+, 4, or Zero 2 W
- **Camera Module**: Pi Camera Module v2 or v3 (recommend v3 for better quality)
- **Power Supply**: 5V 3A (Pi 4) or 5V 2.5A (Pi 3)
- **Network**: Ethernet or WiFi connection to local network
- **Mount**: 3D-printed mount to position camera above build plate

### Software Setup (mjpg-streamer)

**1. Install Dependencies**:
```bash
sudo apt update
sudo apt install cmake libjpeg-dev gcc g++ git
```

**2. Clone and Build mjpg-streamer**:
```bash
git clone https://github.com/jacksonliam/mjpg-streamer.git
cd mjpg-streamer/mjpg-streamer-experimental
make
sudo make install
```

**3. Create Startup Script** (`/home/pi/start_camera.sh`):
```bash
#!/bin/bash
mjpg_streamer -i "input_raspicam.so -fps 10 -q 85 -x 1920 -y 1080" \
              -o "output_http.so -p 8080 -w /usr/local/share/mjpg-streamer/www"
```

**4. Make Executable**:
```bash
chmod +x /home/pi/start_camera.sh
```

**5. Create Systemd Service** (`/etc/systemd/system/camera.service`):
```ini
[Unit]
Description=Camera Streaming Service
After=network.target

[Service]
ExecStart=/home/pi/start_camera.sh
WorkingDirectory=/home/pi
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

**6. Enable and Start Service**:
```bash
sudo systemctl enable camera.service
sudo systemctl start camera.service
```

**7. Test Camera**:
```bash
curl http://localhost:8080/snapshot.jpg -o test.jpg
```

**8. Configure Hostname** (optional):
```bash
sudo raspi-config
# Network Options -> Hostname -> snapmaker-pi (or elegoo-pi)
```

**9. Set Static IP** (recommended for reliability):
Edit `/etc/dhcpcd.conf`:
```
interface wlan0
static ip_address=192.168.1.151/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

### Verification

Test camera from KITT system:
```bash
# From KITT host machine
curl http://snapmaker-pi.local:8080/snapshot.jpg -o snapshot.jpg

# Or using IP address
curl http://192.168.1.151:8080/snapshot.jpg -o snapshot.jpg
```

---

## Troubleshooting

### Issue: Dashboard shows "Using mock camera data"

**Cause**: Backend fabrication service not running or API unreachable

**Solution**:
1. Check if fabrication service is running:
   ```bash
   docker compose -f infra/compose/docker-compose.yml ps fabrication
   ```
2. Verify API endpoint:
   ```bash
   curl http://localhost:8080/api/fabrication/cameras/status | jq
   ```
3. Check service logs:
   ```bash
   docker compose -f infra/compose/docker-compose.yml logs fabrication
   ```

### Issue: Camera shows status "Offline"

**Cause**: Camera endpoint unreachable or camera not configured

**Solution**:
1. **For Raspberry Pi cameras**:
   ```bash
   # Test camera endpoint directly
   curl http://snapmaker-pi.local:8080/snapshot.jpg -o test.jpg

   # Check if Pi is online
   ping snapmaker-pi.local

   # Verify mjpg-streamer is running on Pi
   ssh pi@snapmaker-pi.local
   systemctl status camera.service
   ```

2. **For Bamboo Labs camera**:
   - Verify Bamboo Labs printer is online
   - Check MQTT broker connectivity
   - Enable `ENABLE_BAMBOO_CAMERA=true` in .env
   - Ensure MQTT client configured in fabrication service

3. **Check feature flags**:
   ```bash
   # Verify camera features are enabled
   grep ENABLE_CAMERA .env

   # Should show:
   # ENABLE_CAMERA_CAPTURE=true
   # ENABLE_RASPBERRY_PI_CAMERAS=true  (for Pi cameras)
   # ENABLE_BAMBOO_CAMERA=true         (for Bamboo)
   ```

### Issue: Snapshot capture fails with 503 error

**Cause**: Camera capture service not initialized in backend

**Solution**:
1. Restart fabrication service:
   ```bash
   docker compose -f infra/compose/docker-compose.yml restart fabrication
   ```
2. Check service logs for initialization errors:
   ```bash
   docker compose -f infra/compose/docker-compose.yml logs fabrication | grep camera
   ```
3. Verify camera endpoints in config:
   ```bash
   curl http://localhost:8080/api/fabrication/cameras/status | jq
   ```

### Issue: Live view iframe shows blank/error

**Cause**: Camera HTTP stream not accessible or CORS issue

**Solution**:
1. Test stream URL directly in browser:
   ```
   http://snapmaker-pi.local:8080/
   ```
2. Check if mjpg-streamer web interface loads
3. Verify camera service is running on Pi:
   ```bash
   ssh pi@snapmaker-pi.local
   systemctl status camera.service
   journalctl -u camera.service -n 50
   ```
4. Try external link provided below iframe
5. Check browser console for CORS errors

### Issue: Snapshots not appearing in gallery

**Cause**: No print outcomes with snapshots in database

**Solution**:
1. Verify print outcomes exist:
   ```bash
   curl http://localhost:8080/api/fabrication/outcomes | jq '.[].snapshot_urls'
   ```
2. Ensure print outcome tracking enabled:
   ```bash
   grep ENABLE_PRINT_OUTCOME_TRACKING .env
   ```
3. Capture manual snapshot to test gallery:
   - Use "📸 Capture Snapshot" button
   - Check if snapshot appears in gallery after reload

### Issue: MinIO URLs return 404

**Cause**: MinIO upload disabled or MinIO service not running

**Solution**:
1. Check MinIO service:
   ```bash
   docker compose -f infra/compose/docker-compose.yml ps minio
   ```
2. Enable MinIO upload:
   ```bash
   # In .env
   ENABLE_MINIO_SNAPSHOT_UPLOAD=true
   ```
3. Verify MinIO bucket exists:
   ```bash
   # Using MinIO CLI (mc)
   mc ls myminio/prints
   ```
4. For development, mock URLs are acceptable:
   ```bash
   ENABLE_MINIO_SNAPSHOT_UPLOAD=false  # Uses mock URLs
   ```

---

## Integration with Other Features

### Print Intelligence Dashboard

- Snapshot URLs stored in print outcomes
- Visual evidence linked to quality reviews
- Human feedback references snapshot milestones
- Cross-reference job_id between dashboards

### I/O Control Dashboard

- Feature flags control camera features
- Camera capture can be toggled via I/O Control
- MQTT broker shared for Bamboo Labs integration

### Autonomous Print Monitoring (Future)

- Snapshots feed into failure detection models
- Visual defects classified from camera images
- Anomaly detection triggers snapshot capture
- Auto-stop prints based on CV analysis

---

## Roadmap

### Phase 4 (Current - Complete)

- ✅ Camera status monitoring
- ✅ Manual snapshot capture
- ✅ Connection testing
- ✅ Recent snapshot galleries
- ✅ Live feed viewing (Pi cameras)
- ✅ Multi-camera support (Bamboo + Pi)

### Phase 5 (Planned)

- [ ] **Automatic Print Monitoring**: Snapshots captured at milestones (start, first layer, progress, complete)
- [ ] **Snapshot Comparison**: Side-by-side view of progress snapshots
- [ ] **Timelapse Video Generation**: Compile snapshots into timelapse
- [ ] **Snapshot Annotations**: Mark defects on snapshots
- [ ] **Camera Calibration**: Adjust camera settings (exposure, focus, resolution)
- [ ] **Multi-Angle Cameras**: Support for multiple cameras per printer

### Phase 6 (Future)

- [ ] **Computer Vision Integration**: Automated failure detection from snapshots
- [ ] **Anomaly Alerts**: Real-time notifications on visual defects
- [ ] **Print Quality Scoring**: CV-based quality assessment
- [ ] **Auto-Stop on Failure**: Pause prints when defects detected
- [ ] **Knowledge Base Integration**: Visual failure patterns in KB

---

## Related Documentation

- **Camera Capture Backend**: `services/fabrication/src/fabrication/monitoring/camera_capture.py`
- **CV Print Monitoring Design**: `docs/CV_PRINT_MONITORING_DESIGN.md`
- **API Contracts**: `services/fabrication/src/fabrication/app.py` (lines 1208-1469)
- **Print Intelligence Dashboard**: `docs/PRINT_INTELLIGENCE_DASHBOARD.md`
- **Feature Flags Guide**: `docs/PHASE4_FEATURE_FLAGS_GUIDE.md`
- **I/O Control Dashboard**: `docs/IO_CONTROL_DASHBOARD.md`

---

## Support

For questions or issues:
1. Check logs: `docker compose logs fabrication`
2. Test camera endpoints: `curl http://<camera-url>/snapshot.jpg`
3. Review API docs: `http://localhost:8080/docs`
4. File issue: https://github.com/Jmi2020/KITT/issues

---

**Vision Service Dashboard**: Production ready for all 3D printer camera monitoring and snapshot capture! 📹
