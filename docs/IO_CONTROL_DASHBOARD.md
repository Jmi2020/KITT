# KITTY I/O Control Dashboard

## Overview

The I/O Control Dashboard provides a unified interface (TUI + Web) for managing all external device integrations and feature flags in KITTY. It features:

- **Smart Dependency Validation** - Automatically checks prerequisites before enabling features
- **Intelligent Restart Handling** - Only restarts what's necessary (service, stack, or hot-reload)
- **Hot-Reload Support** - Runtime flags update instantly via Redis (no restart needed)
- **Centralized Control** - Single place to manage cameras, printers, storage, and all Phase 4 features

## Quick Start

### TUI (Terminal Interface)

```bash
# Launch the dashboard
python /home/user/KITT/ops/scripts/kitty-io-control.py

# Or from anywhere
cd /home/user/KITT && ./ops/scripts/kitty-io-control.py
```

**Keyboard Shortcuts:**
- `q` - Quit
- `r` - Refresh state from current config
- `s` - Save and apply all changes
- `h` - Show help
- `Space` - Toggle checkbox
- `Tab` - Navigate between features
- `Enter` - Activate button

### Web API

```bash
# Get all features with current state
curl http://localhost:8080/api/io-control/features

# Get dashboard state grouped by category
curl http://localhost:8080/api/io-control/state

# Enable a feature
curl -X POST http://localhost:8080/api/io-control/features/camera_capture \
  -H "Content-Type: application/json" \
  -d '{"feature_id": "camera_capture", "value": true, "persist": true}'

# Bulk update multiple features
curl -X POST http://localhost:8080/api/io-control/features/bulk-update \
  -H "Content-Type: application/json" \
  -d '{"changes": {"camera_capture": true, "raspberry_pi_cameras": true}, "persist": true}'

# Validate current state
curl http://localhost:8080/api/io-control/validate
```

## Architecture

### Components

1. **Feature Registry** (`common/io_control/feature_registry.py`)
   - Central registry of all features with metadata
   - Dependency tracking (requires, enables, conflicts_with)
   - Restart scope definitions (none, service, stack, llamacpp)

2. **State Manager** (`common/io_control/state_manager.py`)
   - Reads state from Redis (hot-reload) and Settings (.env)
   - Writes to both Redis and .env for persistence
   - Triggers Docker/llama.cpp restarts when needed

3. **TUI Dashboard** (`ops/scripts/kitty-io-control.py`)
   - Interactive terminal interface using textual
   - Real-time validation and dependency checking
   - Bulk save & apply with atomic updates

4. **Web API** (`services/gateway/src/gateway/routes/io_control.py`)
   - REST endpoints for programmatic control
   - Same validation logic as TUI
   - Exposed at http://localhost:8080/api/io-control/*

### Data Flow

```
User Action (TUI/Web)
     ↓
State Manager
     ├─→ Redis (hot-reload flags)
     ├─→ .env file (persistence)
     └─→ Trigger restart (if needed)
           ├─→ Docker service restart
           ├─→ llama.cpp restart
           └─→ Full stack restart
```

## Feature Categories

### 1. Print Monitoring
- **Print Outcome Tracking** - Store results in database with visual evidence
  - Hot-reload: Yes
  - Requires: PostgreSQL database

### 2. Camera
- **Camera Capture (Master)** - Enable all camera snapshot features
  - Hot-reload: Yes
  - Enables: bamboo_camera, raspberry_pi_cameras

- **Bamboo Labs Camera** - Capture from H2D built-in camera via MQTT
  - Hot-reload: Yes
  - Requires: camera_capture, mqtt_broker
  - Setup: Get access code from printer WiFi settings

- **Raspberry Pi Cameras** - Capture from Pi cameras via HTTP
  - Hot-reload: Yes
  - Requires: camera_capture
  - Setup: Install mjpg-streamer or picamera2 on Raspberry Pi

### 3. Storage
- **MinIO Snapshot Upload** - Upload snapshots to S3-compatible storage
  - Hot-reload: Yes
  - Requires: camera_capture
  - Setup: Configure MINIO_ACCESS_KEY and MINIO_SECRET_KEY

### 4. Communication
- **MQTT Broker** - Message broker for device communication
  - Restart: Service (restarts services that use MQTT)
  - Required by: bamboo_camera, human_feedback_requests

- **Human Feedback Requests** - Send MQTT notifications for print review
  - Hot-reload: Yes
  - Requires: mqtt_broker

### 5. Intelligence
- **Print Intelligence** - Success prediction and recommendations
  - Hot-reload: Yes
  - Requires: print_outcome_tracking
  - Validation: Minimum 30 historical outcomes per material/printer

### 6. Printer
- **Bamboo Labs H2D** - High-quality FDM printer (325×320×325mm)
  - Restart: Service (fabrication)
  - Setup: Configure BAMBOO_ACCESS_CODE and BAMBOO_SERIAL

- **Snapmaker Artisan** - 3-in-1 platform: 3D/CNC/Laser (400×400×400mm)
  - Restart: Service (fabrication)

- **Elegoo OrangeStorm Giga** - Large format FDM (800×800×1000mm)
  - Restart: Service (fabrication)

### 7. Discovery
- **Network Discovery** - Auto-discover devices on local network
  - Restart: Service (discovery)

### 8. API Services
External paid services with cost implications:

- **Perplexity API (MCP Tier)** - Search-augmented generation for fresh information
  - Hot-reload: Yes
  - Cost: ~$0.001-0.005/query
  - Setup: Get API key from https://perplexity.ai → Settings → API
  - Env: `PERPLEXITY_API_KEY`

- **OpenAI API (Frontier Tier)** - GPT-4 and GPT-4 Turbo for complex queries
  - Hot-reload: Yes
  - Cost: ~$0.01-0.06/query depending on model
  - Setup: Get API key from https://platform.openai.com/api-keys
  - Env: `OPENAI_API_KEY`

- **Anthropic API (Frontier Tier)** - Claude 3.5 Sonnet for complex reasoning
  - Hot-reload: Yes
  - Cost: ~$0.01-0.08/query depending on model
  - Setup: Get API key from https://console.anthropic.com/settings/keys
  - Env: `ANTHROPIC_API_KEY`

- **Zoo CAD API** - Parametric CAD generation (Text-to-CAD)
  - Hot-reload: Yes
  - Setup: Get API key from https://zoo.dev → Account → API Keys
  - Env: `ZOO_API_KEY`
  - Note: First choice for CAD generation

- **Tripo CAD API** - Image-to-3D and Text-to-3D mesh generation
  - Hot-reload: Yes
  - Setup: Get API key from https://platform.tripo3d.ai/api-keys
  - Env: `TRIPO_API_KEY`
  - Note: Fallback for organic/mesh CAD

### 9. Routing
Intelligence tier selection and function calling controls:

- **Cloud Routing** - Enable cloud API escalation (MCP/Frontier)
  - Hot-reload: Yes
  - Conflicts with: offline_mode
  - Description: Allow using Perplexity/OpenAI/Claude when local model has low confidence
  - Env: `OFFLINE_MODE=false`

- **Offline Mode (Local Only)** - Disable all cloud API calls
  - Hot-reload: Yes
  - Conflicts with: cloud_routing
  - Description: Local-only operation, no external API calls
  - Env: `OFFLINE_MODE=true`
  - Note: Disables Perplexity, OpenAI, Claude, Zoo, Tripo

- **Function Calling** - Allow LLMs to call device control functions
  - Hot-reload: Yes
  - Description: Enable conversational device control (printer commands, CAD generation)
  - Env: `ENABLE_FUNCTION_CALLING=true`

### 10. Autonomous
Goal execution and budget controls:

- **Autonomous Mode** - Enable autonomous goal execution
  - Restart: Service (brain)
  - Description: KITTY will autonomously pursue goals when system is idle
  - Setup: Set AUTONOMOUS_DAILY_BUDGET_USD to limit costs
  - Env: `AUTONOMOUS_ENABLED=false`

- **Autonomous Budget Enforcement** - Daily spending limits
  - Hot-reload: Yes
  - Requires: autonomous_mode
  - Description: Enforce daily budget for autonomous API calls
  - Env: `AUTONOMOUS_DAILY_BUDGET_USD=5.00`

- **Autonomous Full-Time Mode** - Run workflows 24/7
  - Hot-reload: Yes
  - Requires: autonomous_mode
  - Warning: ⚠️ KITTY will continuously execute goals. May consume budget quickly.
  - Env: `AUTONOMOUS_FULL_TIME_MODE=false`

## Tool Availability System

**NEW**: Pre-query validation ensures KITTY knows which tools are enabled before making LLM calls.

### Overview

The `ToolAvailability` class checks which tools/functions are available based on:
- API keys configured in `.env`
- Feature flags enabled via I/O Control
- Offline mode status
- Hardware configured (printer IPs, camera URLs)

This prevents KITTY from attempting to use disabled tools and provides clear error messages.

### Usage

```python
from common.io_control import get_tool_availability

# Initialize (typically in brain service)
tool_checker = get_tool_availability(redis_client)

# Check if cloud routing is allowed
if not tool_checker.should_allow_cloud_routing():
    # Force local-only model

# Get list of enabled function names
enabled_functions = tool_checker.get_enabled_function_names()
# Returns: ["control_printer", "generate_cad_zoo", "search_web", ...]

# Only provide enabled functions to LLM function_calling schema
function_definitions = [
    func for func in all_functions
    if func["name"] in enabled_functions
]

# Get availability status for all tools
available = tool_checker.get_available_tools()
# Returns: {
#   "perplexity_search": True,
#   "openai_completion": False,  # No API key
#   "printer_control": True,
#   ...
# }

# Get human-readable status message
message = tool_checker.get_unavailable_tools_message()
# Prints helpful hints for enabling disabled tools
```

### Integration Points

1. **Brain Service** - Filter function definitions before LLM calls
2. **Routing Logic** - Check `should_allow_cloud_routing()` before escalation
3. **UI Dashboard** - Display tool availability status
4. **Error Messages** - Show `get_unavailable_tools_message()` when tools unavailable

### Supported Tools

| Tool | Requires | Check Method |
|------|----------|--------------|
| `perplexity_search` | PERPLEXITY_API_KEY | `_check_perplexity()` |
| `openai_completion` | OPENAI_API_KEY | `_check_openai()` |
| `anthropic_completion` | ANTHROPIC_API_KEY | `_check_anthropic()` |
| `zoo_cad_generation` | ZOO_API_KEY, not offline | `_check_zoo_cad()` |
| `tripo_cad_generation` | TRIPO_API_KEY, not offline | `_check_tripo_cad()` |
| `printer_control` | Function calling enabled, printer IPs | `_check_printers()` |
| `camera_capture` | ENABLE_CAMERA_CAPTURE | `_check_camera()` |
| `minio_upload` | ENABLE_MINIO_SNAPSHOT_UPLOAD | `_check_minio()` |
| `cloud_routing` | OFFLINE_MODE=false | `_check_offline_mode()` |
| `autonomous_execution` | AUTONOMOUS_ENABLED | `_check_autonomous()` |

## Smart Restart Logic

The dashboard intelligently determines what needs to restart when features change:

### Hot-Reload (No Restart)
Features checked at runtime, updated via Redis:
- `camera_capture` - Master camera switch
- `bamboo_camera` - Bamboo Labs camera
- `raspberry_pi_cameras` - Pi cameras
- `minio_snapshot_upload` - MinIO uploads
- `human_feedback_requests` - MQTT notifications
- `print_outcome_tracking` - Database tracking
- `print_intelligence` - Success predictions

**How it works:**
```python
# Services check Redis first, fall back to Settings
redis_key = f"feature_flag:ENABLE_CAMERA_CAPTURE"
value = redis.get(redis_key) or settings.enable_camera_capture
```

**No restart needed** - Changes take effect on next request.

### Service Restart
Changes require restarting specific Docker services:
- Printer IP/configuration changes → Restart `fabrication` service
- Discovery settings → Restart `discovery` service
- MQTT broker changes → Restart services that use MQTT

**Command:**
```bash
docker compose -f infra/compose/docker-compose.yml restart fabrication
```

### llama.cpp Restart
Model or inference settings changes:
- `LLAMACPP_PRIMARY_MODEL`, `LLAMACPP_CODER_MODEL`
- `LLAMACPP_CTX`, `LLAMACPP_N_GPU_LAYERS`, `LLAMACPP_THREADS`

**Command:**
```bash
./ops/scripts/restart-llamacpp-dual.sh
```

### Stack Restart
Critical infrastructure changes:
- Database connection strings
- Redis configuration
- Full system reconfiguration

**Command:**
```bash
docker compose -f infra/compose/docker-compose.yml restart
```

## Dependency Validation

The dashboard enforces dependency rules before allowing changes:

### Example 1: Enabling Bamboo Labs Camera

```
User attempts: Enable "Bamboo Labs Camera"
                     ↓
Dashboard checks:
  ✓ Is "Camera Capture (Master)" enabled?
  ✓ Is "MQTT Broker" configured?
                     ↓
All dependencies met → Allow enable
```

If dependencies not met:
```
❌ Cannot enable "Bamboo Labs Camera"
   Requires: Camera Capture (Master)

   [Enable Camera Capture (Master) first]
```

### Example 2: Disabling MQTT Broker

```
User attempts: Disable "MQTT Broker"
                     ↓
Dashboard checks:
  ⚠ Is "Bamboo Labs Camera" enabled?
  ⚠ Is "Human Feedback Requests" enabled?
                     ↓
Dependent features enabled → Block disable
```

Error message:
```
❌ Cannot disable "MQTT Broker"
   Required by: Bamboo Labs Camera, Human Feedback Requests

   [Disable those features first]
```

## Common Workflows

### Workflow 1: Enable Camera Monitoring (Development)

**Goal:** Test print monitoring without physical cameras

```bash
# 1. Launch dashboard
python /home/user/KITT/ops/scripts/kitty-io-control.py

# 2. Enable Print Outcome Tracking
[✓] Print Outcome Tracking

# 3. Keep cameras disabled (mock URLs will be used)
[ ] Camera Capture (Master)

# 4. Save & Apply (s key)
```

**Result:** Workflow works with mock snapshot URLs, no hardware required.

### Workflow 2: Enable Raspberry Pi Camera (Snapmaker)

**Goal:** Test Snapmaker Pi camera for real snapshots

```bash
# 1. Ensure .env has camera URL
SNAPMAKER_CAMERA_URL=http://snapmaker-pi.local:8080/snapshot.jpg

# 2. Launch dashboard
python /home/user/KITT/ops/scripts/kitty-io-control.py

# 3. Enable camera features
[✓] Camera Capture (Master)
[✓] Raspberry Pi Cameras
[ ] Bamboo Labs Camera  # Keep disabled

# 4. Keep MinIO disabled for now (test with mock URLs)
[ ] MinIO Snapshot Upload

# 5. Save & Apply
```

**Result:** Real HTTP snapshots from Snapmaker Pi, stored as mock URLs in database.

### Workflow 3: Enable MinIO Storage

**Goal:** Upload snapshots to MinIO for persistent storage

```bash
# Prerequisites:
# - MinIO server running (docker ps | grep minio)
# - Credentials in .env (MINIO_ACCESS_KEY, MINIO_SECRET_KEY)

# 1. Dashboard should show:
[✓] Camera Capture (Master)  # Already enabled
[✓] Raspberry Pi Cameras      # Already enabled

# 2. Enable MinIO
[✓] MinIO Snapshot Upload

# 3. Save & Apply
```

**Result:** Snapshots uploaded to MinIO, real URLs stored in database.

### Workflow 4: Production Mode (All Enabled)

**Goal:** Full production deployment with all features

```bash
# Prerequisites:
# - All cameras installed and tested
# - MinIO running with valid credentials
# - MQTT broker running
# - 30+ historical print outcomes collected

# Enable everything:
[✓] Print Outcome Tracking
[✓] Camera Capture (Master)
[✓] Bamboo Labs Camera
[✓] Raspberry Pi Cameras
[✓] MinIO Snapshot Upload
[✓] Human Feedback Requests
[✓] Print Intelligence  # After sufficient data

# Save & Apply
```

**Result:** Full production monitoring with success predictions.

## Troubleshooting

### Issue: Changes not taking effect

**Check:**
1. Was Redis updated? `redis-cli GET feature_flag:ENABLE_CAMERA_CAPTURE`
2. Was .env updated? `grep ENABLE_CAMERA_CAPTURE /home/user/KITT/.env`
3. Did service restart complete? `docker ps` (check uptime)

**Solution:**
```bash
# Force refresh
python /home/user/KITT/ops/scripts/kitty-io-control.py
# Press 'r' to refresh state
```

### Issue: Dependency validation failing

**Symptoms:**
```
❌ Cannot enable "Bamboo Labs Camera"
   Requires: Camera Capture (Master)
```

**Solution:**
Enable dependencies in correct order:
1. Enable "Camera Capture (Master)" first
2. Then enable "Bamboo Labs Camera"

### Issue: Restart failed

**Symptoms:**
```
✓ Feature updated but restart failed (restart manually)
```

**Solution:**
```bash
# Check Docker service status
docker ps

# Manual restart
docker compose -f infra/compose/docker-compose.yml restart fabrication

# Or restart full stack
docker compose -f infra/compose/docker-compose.yml restart
```

### Issue: Hot-reload not working

**Check Redis connection:**
```bash
docker ps | grep redis
redis-cli ping  # Should return PONG
```

**If Redis unavailable:**
- Hot-reload will fall back to .env values
- Changes require service restart
- Dashboard will still work, just no instant updates

## API Reference

### GET /api/io-control/features

List all features with current state.

**Response:**
```json
[
  {
    "id": "camera_capture",
    "name": "Camera Capture (Master)",
    "description": "Enable all camera snapshot features",
    "category": "camera",
    "env_var": "ENABLE_CAMERA_CAPTURE",
    "default_value": false,
    "current_value": true,
    "restart_scope": "none",
    "requires": [],
    "enables": ["bamboo_camera", "raspberry_pi_cameras"],
    "conflicts_with": [],
    "validation_message": "Master switch for all camera features...",
    "can_enable": true,
    "can_disable": true,
    "dependencies_met": true
  }
]
```

### GET /api/io-control/state

Get complete dashboard state grouped by category.

**Response:**
```json
{
  "features_by_category": {
    "camera": [...],
    "storage": [...],
    "communication": [...]
  },
  "current_state": {
    "camera_capture": true,
    "bamboo_camera": false,
    ...
  },
  "restart_pending": false,
  "restart_services": []
}
```

### POST /api/io-control/features/{feature_id}

Update a single feature.

**Request:**
```json
{
  "feature_id": "camera_capture",
  "value": true,
  "persist": true,
  "trigger_restart": true
}
```

**Response:**
```json
{
  "success": true,
  "feature_id": "camera_capture",
  "value": true
}
```

### POST /api/io-control/features/bulk-update

Update multiple features at once.

**Request:**
```json
{
  "changes": {
    "camera_capture": true,
    "raspberry_pi_cameras": true,
    "minio_snapshot_upload": false
  },
  "persist": true
}
```

**Response:**
```json
{
  "success": true,
  "updated_count": 3
}
```

### GET /api/io-control/validate

Validate current state for dependency issues.

**Response:**
```json
{
  "valid": false,
  "issues": [
    {
      "feature_id": "bamboo_camera",
      "feature_name": "Bamboo Labs Camera",
      "issue": "Requires 'Camera Capture (Master)' to be enabled first"
    }
  ]
}
```

### GET /api/io-control/health

Get health status for all enabled features.

**Response:**
```json
[
  {
    "feature_id": "perplexity_api",
    "feature_name": "Perplexity API (MCP Tier)",
    "is_healthy": true,
    "message": "Healthy"
  },
  {
    "feature_id": "openai_api",
    "feature_name": "OpenAI API",
    "is_healthy": false,
    "message": "Health check failed"
  }
]
```

### GET /api/io-control/features/{feature_id}/dependencies

Get missing dependencies and auto-resolved dependencies for a feature.

**Response:**
```json
{
  "feature_id": "bamboo_camera",
  "missing_dependencies": ["camera_capture"],
  "auto_resolved": {
    "camera_capture": true
  }
}
```

### POST /api/io-control/preview

Preview the impact of applying changes before making them.

**Request:**
```json
{
  "changes": {
    "perplexity_api": true,
    "openai_api": true,
    "camera_capture": true
  }
}
```

**Response:**
```json
{
  "dependencies": {
    "bamboo_camera": ["camera_capture"]
  },
  "costs": {
    "enabled_paid_services": ["perplexity_api", "openai_api"],
    "estimated_cost_per_query": {
      "min": 0.011,
      "max": 0.065,
      "unit": "USD"
    },
    "estimated_daily_cost_100_queries": {
      "min": 1.10,
      "max": 6.50,
      "unit": "USD"
    }
  },
  "restarts": {
    "scopes": ["none"],
    "services": []
  },
  "conflicts": {},
  "health_warnings": {
    "openai_api": "Health check failed"
  }
}
```

### GET /api/io-control/tool-availability

Get tool availability status based on current I/O control settings.

**Response:**
```json
{
  "available_tools": {
    "perplexity_search": true,
    "openai_completion": false,
    "printer_control": true,
    "camera_capture": true,
    "cloud_routing": false,
    "autonomous_execution": false
  },
  "enabled_functions": [
    "control_printer",
    "get_printer_status",
    "capture_snapshot",
    "search_web"
  ],
  "unavailable_message": "The following tools are currently disabled:\n  - openai_completion: Add OPENAI_API_KEY to .env\n  - cloud_routing: Disable OFFLINE_MODE in I/O Control\n  - autonomous_execution: Enable AUTONOMOUS_ENABLED in I/O Control\n\nEnable tools via: kitty-io-control or Web UI at /api/io-control"
}
```

### GET /api/io-control/presets

List all available presets with cost estimates.

**Response:**
```json
[
  {
    "id": "development",
    "name": "Development Mode",
    "description": "All features mocked, no external dependencies required",
    "features": {
      "perplexity_api": false,
      "openai_api": false,
      "offline_mode": true,
      "camera_capture": false,
      "autonomous_mode": false
    },
    "cost_estimate": {
      "enabled_paid_services": [],
      "estimated_cost_per_query": {
        "min": 0.0,
        "max": 0.0,
        "unit": "USD"
      }
    }
  },
  {
    "id": "production",
    "name": "Production Mode",
    "description": "All real hardware and APIs enabled (requires configuration)",
    "features": {
      "perplexity_api": true,
      "openai_api": true,
      "cloud_routing": true,
      "camera_capture": true,
      "autonomous_mode": true
    },
    "cost_estimate": {
      "enabled_paid_services": ["perplexity_api", "openai_api", "anthropic_api", "zoo_cad_api", "tripo_cad_api"],
      "estimated_cost_per_query": {
        "min": 0.071,
        "max": 0.63,
        "unit": "USD"
      },
      "estimated_daily_cost_100_queries": {
        "min": 7.10,
        "max": 63.00,
        "unit": "USD"
      }
    }
  }
]
```

### GET /api/io-control/presets/{preset_id}

Get details for a specific preset.

**Response:** Same as single preset from list above.

### POST /api/io-control/presets/{preset_id}/apply

Apply a preset configuration.

**Request:**
Query param: `persist=true` (optional)

**Response:**
```json
{
  "success": true,
  "preset_id": "development",
  "preset_name": "Development Mode",
  "updated_count": 15
}
```

## Integration with Phase 4

The I/O Control Dashboard is the recommended way to manage all Phase 4 features:

1. **Start Development** - All features disabled, test with mocks
2. **Enable Outcome Tracking** - Database storage only
3. **Test One Camera** - Snapmaker Pi via HTTP
4. **Add MinIO Storage** - Persistent snapshot storage
5. **Enable All Cameras** - Bamboo Labs via MQTT
6. **Collect Data** - 30+ print outcomes with human feedback
7. **Enable Intelligence** - Success predictions and recommendations

The dashboard ensures you never enable a feature without its prerequisites, and restarts only what's necessary.

## See Also

- **[Phase 4 Feature Flags Guide](PHASE4_FEATURE_FLAGS_GUIDE.md)** - Detailed flag documentation
- **[Computer Vision Print Monitoring](CV_PRINT_MONITORING_DESIGN.md)** - Camera integration design
- **[Phase 4 Progress Summary](PHASE4_PROGRESS_SUMMARY.md)** - Implementation status
