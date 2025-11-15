# KITTY Design Principle: Everything Has a Switch

**Date Added:** 2025-11-14
**Category:** Core Design Philosophy
**Phase:** 4 - Fabrication Intelligence
**Status:** Implemented

## Principle

Every external device integration, feature, and capability in KITTY can be individually enabled or disabled through the I/O Control Dashboard.

## Why This Matters

KITTY manages physical fabrication equipment (printers, cameras, storage systems). Unlike pure software systems, hardware integration requires:

- **Safe development** - Ability to test workflows without physical devices
- **Incremental deployment** - Enable one device at a time in production
- **Component-level debugging** - Isolate issues by toggling individual features
- **Graceful degradation** - System continues operating when optional features are disabled

## How It Works

### Dual-Layer State Management

1. **Redis** - Hot-reload flags for runtime changes (no restart needed)
2. **.env** - Persistent configuration (survives restarts)

### Smart Restart Logic

- **Hot-reload (no restart)**: Camera capture, outcome tracking, MinIO uploads, MQTT notifications
- **Service restart**: Printer configuration, discovery settings → Restart specific Docker service
- **Stack restart**: Critical infrastructure changes → Full docker-compose restart
- **llama.cpp restart**: Model or inference settings → Restart inference servers

### Dependency Validation

Features declare their requirements:
```python
bamboo_camera:
  requires: ["camera_capture", "mqtt_broker"]
  enables: []
  conflicts_with: []
```

Dashboard automatically:
- Prevents enabling features without prerequisites
- Blocks disabling features that others depend on
- Shows clear error messages explaining dependencies

## Examples

### Phase 4 Features (All Have Switches)

**Print Monitoring:**
- `ENABLE_PRINT_OUTCOME_TRACKING` - Database storage of print results

**Camera Integration:**
- `ENABLE_CAMERA_CAPTURE` - Master switch for all cameras
- `ENABLE_BAMBOO_CAMERA` - Bamboo Labs H2D built-in camera via MQTT
- `ENABLE_RASPBERRY_PI_CAMERAS` - Snapmaker/Elegoo Pi cameras via HTTP

**Storage:**
- `ENABLE_MINIO_SNAPSHOT_UPLOAD` - Upload snapshots to S3-compatible storage

**Communication:**
- `ENABLE_HUMAN_FEEDBACK_REQUESTS` - MQTT notifications for print review

**Intelligence:**
- `ENABLE_PRINT_INTELLIGENCE` - Success prediction and recommendations

## Control Interfaces

### 1. TUI (Terminal UI)

```bash
python /home/user/KITT/ops/scripts/kitty-io-control.py
```

Features:
- Interactive checkboxes for all features
- Visual dependency indicators (⚠ = missing deps)
- Restart requirement indicators (🔄 = restart, 🧠 = llama.cpp)
- Real-time validation
- Bulk save & apply

### 2. Web API

```bash
# Get all features with current state
curl http://localhost:8080/api/io-control/features

# Enable camera capture
curl -X POST http://localhost:8080/api/io-control/features/camera_capture \
  -d '{"feature_id": "camera_capture", "value": true}'

# Bulk update
curl -X POST http://localhost:8080/api/io-control/features/bulk-update \
  -d '{"changes": {"camera_capture": true, "raspberry_pi_cameras": true}}'
```

## Common Workflows

### Development Without Hardware

```
All features disabled (default)
↓
System works with mock data
↓
No cameras, MinIO, or physical printers needed
↓
Complete workflow testable
```

### Incremental Production Deployment

```
Week 1: Enable print outcome tracking (database only)
Week 2: Add Snapmaker Pi camera (one camera)
Week 3: Test thoroughly, add Bamboo Labs camera
Week 4: Enable MinIO storage (persistent snapshots)
Week 5: Collect 30+ outcomes with human feedback
Week 6: Enable print intelligence (predictions)
```

### Component-Level Troubleshooting

```
Issue: Print monitoring not working
↓
Disable all camera features
↓
Test outcome tracking alone (works)
↓
Enable camera_capture (works)
↓
Enable raspberry_pi_cameras (fails)
↓
Found the issue: Snapmaker Pi camera offline
```

## Implementation

### Feature Registry

Centralized registry (`common/io_control/feature_registry.py`) defines all features:

```python
FeatureDefinition(
    id="bamboo_camera",
    name="Bamboo Labs Camera",
    description="Capture snapshots from H2D built-in camera via MQTT",
    category=FeatureCategory.CAMERA,
    env_var="ENABLE_BAMBOO_CAMERA",
    default_value=False,
    restart_scope=RestartScope.NONE,  # Hot-reload
    requires=["camera_capture", "mqtt_broker"],
    validation_message="Requires BAMBOO_ACCESS_CODE in .env",
    setup_instructions="Get code from: Printer Settings → Network → WiFi",
)
```

### State Manager

Manages state with validation (`common/io_control/state_manager.py`):

```python
# Check Redis first (hot-reload), fall back to .env
value = redis.get("feature_flag:ENABLE_CAMERA_CAPTURE") or settings.enable_camera_capture

# Validate before enabling
can_enable, reason = feature_registry.can_enable("bamboo_camera", current_state)
if not can_enable:
    return error(f"Cannot enable: {reason}")

# Update both layers
redis.set("feature_flag:ENABLE_BAMBOO_CAMERA", "true")
update_env_file("ENABLE_BAMBOO_CAMERA", "true")

# Trigger restart if needed (service-level, not full stack)
if feature.restart_scope == RestartScope.SERVICE:
    restart_docker_service("fabrication")
```

### Runtime Checks

Services check flags at runtime:

```python
# In CameraCapture.capture_snapshot()
if not settings.enable_camera_capture:
    LOGGER.debug("Camera capture disabled by feature flag")
    return mock_snapshot_url()  # Works without hardware

# In PrintOutcomeTracker.request_human_review()
if not settings.enable_human_feedback_requests:
    LOGGER.debug("Human feedback disabled by feature flag")
    return False  # Graceful degradation
```

## Benefits Realized

### 1. Testability
- Entire Phase 4 workflow testable without cameras, MinIO, or MQTT
- Unit tests don't require Docker containers
- CI/CD can run full test suite without hardware

### 2. Deployability
- Production rollout can be gradual and safe
- Each feature tested independently before enabling next
- Rollback is simple (toggle off + refresh)

### 3. Debuggability
- Issues isolated to specific components
- No all-or-nothing troubleshooting
- Clear visibility into what's enabled/disabled

### 4. Operations
- No manual .env editing (TUI/API handles it)
- Dependency conflicts caught before applying
- Smart restarts minimize downtime

## Future Application

**This principle applies to all future KITTY features:**

When adding new integrations:
1. Add feature to registry with dependencies
2. Add env var with `ENABLE_` prefix
3. Implement runtime check in service code
4. Update I/O Control Dashboard automatically sees it
5. Document in feature flags guide

**Examples of future features that will have switches:**
- UniFi Access integration (door control)
- CNC machine control
- Laser cutter integration
- Autonomous procurement
- Multi-user support
- Advanced CV failure detection

## Documentation

- **Vision**: `NorthStar/ProjectVision.md` - Principle #6
- **README**: Core Design Philosophy section
- **User Guide**: `docs/IO_CONTROL_DASHBOARD.md`
- **Feature Flags**: `docs/PHASE4_FEATURE_FLAGS_GUIDE.md`
- **Code**: `services/common/src/common/io_control/`

## Related Principles

1. **Bounded Autonomy** - KITTY operates within defined boundaries
2. **Offline-First** - Local inference preferred over cloud
3. **Everything Has a Switch** - All features individually controllable
4. **Smart Restart Logic** - Only restart what's necessary
5. **Graceful Degradation** - System continues when features disabled

## Quotes

> "This makes KITTY testable without hardware, deployable incrementally, and debuggable component-by-component - critical for a system managing physical fabrication equipment."

> "The I/O Control Dashboard ensures you never enable a feature without its prerequisites, and restarts only what's necessary."

---

**Memory Type:** Design Principle
**Importance:** Core
**Applies To:** All future KITTY features
**Maintained By:** Architecture team
**Last Updated:** 2025-11-14
