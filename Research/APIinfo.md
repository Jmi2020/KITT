# AI Lab Integration API Reference Guide

## Executive Overview

This document provides comprehensive API documentation, authentication requirements, configuration schemas, notable quirks, and sample payloads for 18 critical system integrations in your Mac Studio M3 Ultra warehouse AI setup with Home Lab infrastructure.

---

## 1. FastAPI Brain/Gateway

### Preferred Authentication
- **OAuth2 with JWT Tokens** (recommended for production)
- **Bearer token scheme**: `Authorization: Bearer <token>`
- **Token structure**: JWT with HS256 algorithm by default
- **Environment variables**: `SECRET_KEY` (min 32 chars), `ACCESS_TOKEN_EXPIRE_MINUTES`

### Function-Calling Payload Schema

```json
{
  "model": "gpt-4-turbo",
  "messages": [
    {
      "role": "user",
      "content": "What's the weather?"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Get weather for a location",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {
              "type": "string",
              "description": "City name"
            }
          },
          "required": ["location"]
        }
      }
    }
  ]
}
```

### Deployment Patterns

| Pattern | Use Case | Notes |
|---------|----------|-------|
| **ASGI (Uvicorn)** | Production, concurrent requests | Native FastAPI support, recommended |
| **WSGI (Gunicorn)** | Shared hosting, legacy systems | Requires `a2wsgi` middleware wrapper |
| **Workers** | Multi-core systems | Use `uvicorn --workers 4` for M3 Ultra |

### Notable Quirks
- JWT tokens require explicit expiration handling; set `ACCESS_TOKEN_EXPIRE_MINUTES` appropriately
- Dependency injection for security; always use `Depends()` for endpoint protection
- Automatic OpenAPI docs at `/docs` and `/redoc`

### Sample FastAPI Setup

```python
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta
import jwt

SECRET_KEY = "your-secret-key-min-32-chars" * 2
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return username

@app.post("/token")
async def login(username: str, password: str):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}
```

---

## 2. MQTT (Mosquitto) + Topic Schema

### Broker Configuration

**mosquitto.conf**:
```
port 1883
protocol mqtt
allow_anonymous true
max_connections -1
max_queued_messages 1000
message_size_limit 0
persistence true
persistence_location /var/lib/mosquitto/
autosave_interval 3600
```

### QoS Expectations
- **QoS 0 (At most once)**: No guarantee, overhead-free (device status)
- **QoS 1 (At least once)**: Guaranteed, duplicate possible (sensor readings)
- **QoS 2 (Exactly once)**: Guaranteed, no duplicates, highest overhead (critical commands)

### Retained Message Policies
- Stored one per topic
- Delete by publishing zero-byte payload with retain flag
- Useful for "last known good" state
- Format: `topic: message, topic: empty_payload`

### Topic Schema Example

```
warehouse/
â”œâ”€â”€ climate/
â”‚   â”œâ”€â”€ temp (retained, QoS 1)
â”‚   â”œâ”€â”€ humidity (retained, QoS 1)
â”‚   â””â”€â”€ air_quality (retained, QoS 1)
â”œâ”€â”€ printers/
â”‚   â”œâ”€â”€ h2d/status (retained, QoS 1)
â”‚   â”œâ”€â”€ giga/job_progress (QoS 1)
â”‚   â””â”€â”€ artisan/laser_status (retained, QoS 1)
â”œâ”€â”€ access/
â”‚   â”œâ”€â”€ door_unlock_request (QoS 2)
â”‚   â”œâ”€â”€ entry_log (QoS 1)
â”‚   â””â”€â”€ zone_occupancy (retained, QoS 1)
â””â”€â”€ power/
    â”œâ”€â”€ unifi_uptime (retained, QoS 1)
    â”œâ”€â”€ flow_ultra_soc (retained, QoS 1)
    â””â”€â”€ delta_pro_battery (retained, QoS 1)
```

### Bridge Configuration

```
connection bridge_to_remote
address remote.broker.example.com
remote_username user
remote_password pass
topic warehouse/# out
topic remote/# in
cleansession true
clientid mosquitto-bridge
start_type automatic
restart_timeout 30
```

---

## 3. Home Assistant REST/WebSocket Services

### Authentication
- **Long-lived access token**: `Authorization: Bearer <TOKEN>`
- Generate at: `http://homeassistant:8123/profile/security`
- Token format: 40-character alphanumeric string

### Service Call Formats

**REST POST Format**:
```bash
POST /api/services/light/turn_on
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "entity_id": "light.living_room",
  "brightness": 255,
  "color_temp": 3000
}
```

**Response**:
```json
{
  "context": {
    "id": "01ARZ3NDEKTSV4RRFFQ6P5Q1",
    "parent_id": null,
    "user_id": "123"
  },
  "service_data": {}
}
```

### Common Service Calls

| Service | Endpoint | Payload |
|---------|----------|---------|
| Turn On Light | `/api/services/light/turn_on` | `{"entity_id": "light.NAME"}` |
| Lock Door | `/api/services/lock/lock` | `{"entity_id": "lock.NAME"}` |
| Scene Activate | `/api/services/scene/turn_on` | `{"entity_id": "scene.NAME"}` |
| Climate Set Temp | `/api/services/climate/set_temperature` | `{"entity_id": "climate.NAME", "temperature": 72}` |

### MQTT Bridge Setup

**configuration.yaml**:
```yaml
mqtt:
  broker: localhost
  port: 1883
  discovery: true
  discovery_prefix: homeassistant

homeassistant:
  customize:
    automation.warehouse_automation:
      friendly_name: "Warehouse Automation"
```

### WebSocket Connection
```javascript
const ws = new WebSocket("ws://homeassistant:8123/api/websocket");
ws.send(JSON.stringify({
  type: "auth",
  access_token: "TOKEN"
}));
```

---

## 4. OctoPrint/Klipper APIs per Printer

### OctoPrint API Authentication
- **API Key method**: `X-Api-Key: <KEY>` header
- **Bearer token**: `Authorization: Bearer <token>` (newer versions)
- Key rotation: POST `/api/plugin/appkeys` with `{"command": "revoke", "app": "myapp"}`

### Job Control Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/files?recursive=true` | GET | List all files |
| `/api/files/local/<path>` | POST | Upload file |
| `/api/job` | GET | Current job status |
| `/api/job` | POST | Start/pause/cancel job |
| `/api/printer` | GET | Printer state |
| `/api/plugin/eventmanager/fire` | POST | Fire custom event |

### Job Control Payload

```json
{
  "command": "start"
}
```

Pause/Resume/Cancel:
```json
{
  "command": "pause",
  "action": "pause"
}
```

### Plugin Hook System

**cv_alert_hook**:
```python
def process_cv_alert(*args, **kwargs):
    alert_data = kwargs.get("alert")
    alert_type = alert_data.get("type")  # "layer_skip", "adhesion_fail", etc.
    confidence = alert_data.get("confidence")
    return True  # Accept alert

__plugin_hooks__ = {
    "octoprint.plugin.cv_alert": process_cv_alert
}
```

### Moonraker (Klipper) Endpoints

**JSON-RPC Format**:
```json
{
  "jsonrpc": "2.0",
  "method": "printer.objects.query",
  "params": {
    "objects": {
      "toolhead": ["position", "status"],
      "gcode_move": null
    }
  },
  "id": 1
}
```

**Query Printer Objects**:
```bash
POST /printer/objects/query
Content-Type: application/json

{
  "objects": {
    "print_stats": ["state", "filename"],
    "toolhead": ["position", "homed_axes"]
  }
}
```

### Printer States (Klipper)

| State | Meaning |
|-------|---------|
| `startup` | Initializing |
| `ready` | Online and ready |
| `error` | Fatal error |
| `shutdown` | Emergency stop or critical error |

---

## 5. UniFi Protect Cameras

### RTSP Stream Access

**Gateway-hosted RTSP**:
```
rtsps://192.168.1.1:7447/rtsps?camera=<camera-uuid>&enableSrtp
```

**Configuration**:
- Port: 7447 (RTSPS) or 7445 (RTMP)
- Audio: Supported via stream
- Bitrate: 2-6 Mbps depending on resolution

### HTTP Snapshot API

**Authentication**: Cookie-based (login required)

```bash
# Login first
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"ubnt","password":"<recovery-code>"}' \
  https://192.168.1.1/api/auth/login \
  -c cookies.txt

# Get snapshot
curl -H "Accept: image/jpeg" \
  https://192.168.1.1/api/cameras/<camera-uuid>/snapshot \
  -b cookies.txt -o snapshot.jpg
```

### Webhook Configuration

**Alarm Manager Trigger**:
```
https://192.168.1.1/proxy/protect/api/cameras/<id>/events
```

**Rate Limits**:
- Snapshots: 1 per second per camera
- RTSP connections: 5 concurrent max
- API calls: 30 req/min per camera

### Notable Quirks
- No direct camera snapshot URL; must proxy through gateway
- RTSP requires SRTP (Secure Real-time Transport Protocol)
- Anonymous snapshots require explicit enablement per camera
- Video quality capped at 1fps for snapshot API

---

## 6. UniFi Access Control API

### Identity Lookup

**Endpoint**: `https://identity.ui.com/api/v1/users`

```bash
GET /api/v1/users?filter={"email":"user@example.com"}
Authorization: Bearer <token>

Response:
{
  "data": [
    {
      "id": "user-123",
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      "role": "user"
    }
  ]
}
```

### Door Unlock Flow

**Step 1: Request Unlock**
```bash
POST /api/v1/doors/<door-id>/unlock
Authorization: Bearer <token>
Content-Type: application/json

{
  "user_id": "user-123",
  "unlock_method": "mobile_button"
}
```

**Step 2: Verify Unlock Status**
```bash
GET /api/v1/doors/<door-id>/last-unlock
Authorization: Bearer <token>

Response:
{
  "status": "success",
  "timestamp": "2025-11-04T21:15:00Z",
  "method": "mobile_button",
  "user": "user-123"
}
```

### Zone Presence Data

```bash
GET /api/v1/zones/<zone-id>/occupancy
Authorization: Bearer <token>

Response:
{
  "zone_id": "zone-123",
  "occupied": true,
  "presence_count": 5,
  "last_update": "2025-11-04T21:15:30Z",
  "devices": [
    {
      "device_id": "d-456",
      "type": "reader",
      "status": "active"
    }
  ]
}
```

### Unlock Methods Supported
- Mobile button
- Mobile tap (NFC)
- NFC card
- PIN
- Face unlock
- QR code (visitors)
- License plate recognition

---

## 7. Tailscale Admin/API

### ACL Management

**ACL Policy Format**:
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:members"],
      "dst": ["autogroup:self:*"]
    },
    {
      "action": "accept",
      "src": ["tag:server"],
      "dst": ["tag:client:*"]
    }
  ],
  "tagOwners": {
    "tag:server": ["autogroup:owners"],
    "tag:device": ["autogroup:owners"]
  },
  "groups": {
    "group:admins": ["user@example.com"]
  }
}
```

### Device Tagging

**CLI Commands**:
```bash
# Tag device (requires admin approval)
tailscale tag -t tag:device <hostname>

# Disable key expiry for tagged devices (automatic in v1.26+)
# Tagged devices no longer require key renewal
```

### Exit Node Configuration

**Allow Exit Node Usage**:
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:members"],
      "dst": ["autogroup:internet:*"]
    }
  ]
}
```

**Enable on Device**:
```bash
tailscale up --advertise-exit-node
```

**Use Exit Node**:
```bash
tailscale set --exit-node=<device-ip>
tailscale set --exit-node=<device-ip> --exit-node-allow-lan-access
```

### API Endpoints

**List Devices**:
```bash
curl https://api.tailscale.com/api/v2/tailnet/-/devices \
  -H "Authorization: Bearer <TAILSCALE_API_TOKEN>"
```

**Update Device Tags**:
```bash
curl -X PATCH \
  https://api.tailscale.com/api/v2/device/<device-id> \
  -H "Authorization: Bearer <TAILSCALE_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"tags":["tag:device","tag:ml"]}'
```

---

## 8. Ollama & MLX Runtime APIs

### Model Load/Unload Commands

**Keep Model in Memory**:
```bash
curl http://localhost:11434/api/generate \
  -d '{
    "model": "mistral",
    "prompt": "",
    "keep_alive": -1
  }'
```

**Unload Immediately**:
```bash
curl http://localhost:11434/api/generate \
  -d '{
    "model": "mistral",
    "prompt": "",
    "keep_alive": 0
  }'
```

**Model Parameters**:
```
OLLAMA_MAX_LOADED_MODELS=6  # Default: 3 * GPU count
OLLAMA_NUM_PARALLEL=4       # Max parallel requests per model
OLLAMA_MAX_QUEUE=512        # Max queued requests
```

### Batch Inference

```bash
curl http://localhost:11434/api/generate \
  -d '{
    "model": "mistral:latest",
    "prompt": "What is AI?",
    "stream": false
  }'

Response:
{
  "model": "mistral:latest",
  "created_at": "2025-11-04T21:15:00Z",
  "response": "AI is...",
  "total_duration": 5000000000,
  "load_duration": 2000000000,
  "prompt_eval_count": 8,
  "eval_count": 100,
  "eval_duration": 3000000000
}
```

### Metal Tuning (Apple Silicon)

**M3 Ultra Specific**:
```bash
export METAL_DEVICE_FALLBACK=1
export METAL_FORCE_ASYNCHRONOUS=1
```

**GPU Memory Allocation**:
```
OLLAMA_NUM_GPU=8  # All GPU cores on M3 Ultra
```

### Concurrent Model Loading

**Multiple Models**:
```bash
# Load Mistral
curl -X POST http://localhost:11434/api/generate \
  -d '{"model":"mistral:latest","keep_alive":-1}' &

# Load LLaMA
curl -X POST http://localhost:11434/api/generate \
  -d '{"model":"llama2:latest","keep_alive":-1}' &
```

### Notable Quirks
- Models unload after 5 minutes by default (configurable via `keep_alive`)
- Different endpoints (`/api/generate` vs `/api/chat`) trigger separate model loads
- Concurrent request limit depends on available VRAM
- Memory pressure auto-evicts least recently used models

---

## 9. Whisper.cpp & Piper Speech Pipelines

### Whisper.cpp Streaming Interface

**HTTP Server**:
```bash
./server -m models/ggml-base.bin -p 8000
```

**Streaming Transcription**:
```bash
curl -X POST http://localhost:8000/inference \
  -F "file=@audio.wav" \
  -F "language=en"

Response:
{
  "result": "Hello, how are you?",
  "timestamps": [
    {"word": "Hello", "start": 0.0, "end": 0.5},
    {"word": "how", "start": 0.6, "end": 0.9}
  ]
}
```

### Latency Benchmarks

| Model | Hardware | Latency | Accuracy (WER) |
|-------|----------|---------|----------------|
| tiny | M3 Ultra | 200ms | 12% |
| base | M3 Ultra | 400ms | 6% |
| small | M3 Ultra | 800ms | 4% |
| medium | M3 Ultra | 2000ms | 3% |

**Quantization Impact**:
- INT4: 19% latency reduction, 45% size reduction
- INT8: 12% latency reduction, 25% size reduction

### Piper Speech Synthesis

**Server Setup**:
```bash
piper --model en_US-lessac-medium --output_raw | ffplay -f s16le -ar 22050 -ac 1 -
```

**HTTP TTS Server**:
```python
from flask import Flask, request
import piper

app = Flask(__name__)
piper_voice = piper.load_voice("en_US-lessac-medium")

@app.route("/speak", methods=["POST"])
def speak():
    text = request.json["text"]
    audio = piper.synthesize(text, piper_voice)
    return audio
```

### Voice Selection

**Available Voices**:
```
en_US-lessac-medium       # Clear, friendly
en_US-ljspeech-medium     # Formal, professional
en_US-ryan-medium         # Casual, warm
en_GB-alba-medium         # British English
es_ES-carlfm-x-low        # Spanish (low quality/fast)
```

### Voice Download

```bash
# Automatic on first use
echo "Hello" | piper --model en_US-lessac-medium --output_file out.wav

# Manual download
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
```

---

## 10. Model Context Protocol Endpoints

### MCP Authorization Flow (OAuth 2.1)

**Discovery**:
```bash
curl https://mcp-server.example.com/.well-known/oauth-authorization-server

Response:
{
  "authorization_endpoint": "https://mcp-server.example.com/authorize",
  "token_endpoint": "https://mcp-server.example.com/token",
  "registration_endpoint": "https://mcp-server.example.com/register"
}
```

**Dynamic Client Registration**:
```bash
POST /register
Content-Type: application/json

{
  "client_name": "my-mcp-client",
  "redirect_uris": ["http://localhost:3000/callback"]
}

Response:
{
  "client_id": "client-123",
  "client_secret": "secret-456",
  "registration_access_token": "token-789"
}
```

### Authorization Code Flow (PKCE)

```
1. Generate code_verifier & code_challenge
2. Redirect to: /authorize?client_id=X&code_challenge=Y&state=Z
3. User authorizes
4. Redirect back with authorization_code
5. Exchange: POST /token with code, code_verifier, client_id
6. Receive access_token
```

### Tool Registration Process

**Perplexity MCP Schema**:
```json
{
  "tools": [
    {
      "name": "search",
      "description": "Search the web",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query"
          }
        },
        "required": ["query"]
      }
    }
  ]
}
```

**Tool Invocation**:
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "search",
    "arguments": {
      "query": "latest AI news"
    }
  },
  "id": 1
}
```

### Bearer Token Usage

```bash
Authorization: Bearer <access-token>
```

All MCP requests require this header after OAuth flow completes.

---

## 11. Frontier LLM Adapters (GPT-5, Claude Sonnet, Gemini)

### Function-Calling Specs

**Claude Sonnet 4 (claude-sonnet-4-20250514)**:
```json
{
  "tools": [
    {
      "name": "analyze_image",
      "description": "Analyze an image",
      "input_schema": {
        "type": "object",
        "properties": {
          "image_base64": {"type": "string"},
          "analysis_type": {"type": "string", "enum": ["ocr", "object_detection"]}
        }
      }
    }
  ]
}
```

**OpenAI GPT-5 (gpt-5-turbo)**:
```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string"},
            "unit": {"type": "string", "enum": ["C", "F"]}
          }
        }
      }
    }
  ]
}
```

**Google Gemini (gemini-2.0-flash)**:
```json
{
  "tools": [
    {
      "google_search_retrieval": {
        "disable_attribution": false
      }
    }
  ]
}
```

### Rate Limits

| Model | RPM | TPM | Daily |
|-------|-----|-----|-------|
| Claude Sonnet | 40 | 80K | 2M |
| GPT-5 | 3.5K | 200K | 5M |
| Gemini Pro | 60 | 1M | Unlimited |

### Fallback Strategy

```python
def call_with_fallback(prompt, preferred="claude"):
    providers = {
        "claude": call_claude,
        "openai": call_openai,
        "gemini": call_gemini
    }

    for provider_name in [preferred] + [p for p in providers if p != preferred]:
        try:
            return providers[provider_name](prompt)
        except RateLimitError:
            continue

    raise Exception("All providers rate limited")

# Exponential backoff
@backoff.on_exception(backoff.expo, RateLimitError, max_time=30, max_tries=5)
def call_with_retry(prompt):
    return call_with_fallback(prompt)
```

### Retry Logic

**Header Inspection**:
```python
response = client.messages.create(...)
remaining_requests = response.headers.get('x-ratelimit-remaining-requests')
reset_time = response.headers.get('x-ratelimit-reset-requests')
```

---

## 12. Zoo CAD API

### Parametric Request Schema

**Create CAD Model**:
```bash
POST https://api.zoo.dev/projects/<project-id>/models
Authorization: Bearer <api-key>
Content-Type: application/json

{
  "name": "cylinder_part",
  "description": "75mm cylinder with hex end",
  "prompt": "Create a 75mm tall cylinder with M8 hex socket on top",
  "language": "kcl",
  "parameters": {
    "height": 75,
    "diameter": 30
  }
}
```

**Response**:
```json
{
  "id": "model-123",
  "status": "processing",
  "credits_used": 1,
  "kcl_code": "const part = startSketchOnXY(...)",
  "polling_url": "/models/model-123/status"
}
```

### Authentication

**API Key**: Header `Authorization: Bearer <key>`

**Credits**: 40/month free tier, ~1 minute per generation

### Job Status Polling

```bash
GET https://api.zoo.dev/models/model-123/status
Authorization: Bearer <api-key>

Response:
{
  "status": "complete",
  "model_id": "model-123",
  "geometry": {
    "format": "gltf",
    "url": "https://storage.zoo.dev/model-123.gltf"
  },
  "parameters": {...}
}
```

### Export Formats

| Format | Use Case |
|--------|----------|
| GLTF | Web, real-time rendering |
| STEP | Engineering, CAD software |
| STL | 3D printing |
| KCL | Parametric editing |

### Notable Quirks
- Same prompt may produce different results (non-deterministic)
- Geometry validation may fail (422 error) if model is invalid
- Credits consumed even on failed attempts
- KCL code is fully editable for refinement

---

## 13. Tripo (Cloud) + TripoSR/InstantMesh (Local)

### Tripo Cloud API

**Image to 3D**:
```bash
POST https://api.tripo.ai/v2/openapi/im2tripo
Authorization: Bearer <api-key>
Content-Type: multipart/form-data

file: @image.jpg
model: default
quality: draft
```

**Response**:
```json
{
  "data": {
    "model_url": "https://storage.tripo.ai/model-123.glb",
    "thumbnail": "https://storage.tripo.ai/thumb-123.jpg",
    "status": "completed"
  },
  "req_id": "req-123"
}
```

### TripoSR (Local) Parameters

**Inference**:
```python
from triposr.pipeline import TripoSRPipeline

pipeline = TripoSRPipeline.from_pretrained("stabilityai/TripoSR")
model = pipeline(image)  # Returns mesh in 0.5s on A100

# Save outputs
model.export("output.glb")  # GLTF Binary
model.export("output.obj")  # OBJ with MTL
model.export("output.ply")  # Point Cloud
```

### InstantMesh (Local) Configuration

**Model Variants**:
```
NeRF-base:  Fast, lower quality
NeRF-large: Slower, better detail
Mesh-base:  Fast mesh extraction
Mesh-large: High-quality mesh
```

**Performance**:
```bash
python inference.py \
  --input image.jpg \
  --model mesh-large \
  --output output.glb \
  --device cuda
```

### Output Formats

| Format | Properties |
|--------|-----------|
| GLTF (.glb) | Compressed, web-ready |
| GLTF (.gltf) | JSON + bin, editable |
| OBJ/MTL | Widely compatible |
| PLY | Point cloud format |

### Throttle Limits

**Cloud API**:
- 100 req/min per API key
- 1MB max image size
- 30s timeout per request

**Local (A100 GPU)**:
- TripoSR: ~1 model/sec
- InstantMesh: ~2 models/sec with mesh output

---

## 14. CadQuery/FreeCAD Automation

### CadQuery CLI Usage

**Headless Execution**:
```bash
python -m cadquery.cq_script_runner my_script.py
```

**Script Entry Point**:
```python
import cadquery as cq

# Build directly
result = (
    cq.Workplane("XY")
    .box(10, 20, 5)
    .edges("|Z")
    .chamfer(1)
)

# Export
result.save("part.step")
```

### STEP Export

```python
result.save(
    "assembly.step",
    mode=cq.exporters.assembly.ExportModes.FUSED,
    exportType=cq.exporters.ExportTypes.STEP
)
```

### DXF Export (2D Projection)

```python
# Method 1: Export edges as DXF
edges = result.edges()
cq.exporters.export(edges, "projection.dxf")

# Method 2: Planar section
section = result.section(z=2.5)
cq.exporters.export(section, "cross_section.dxf")
```

### FreeCAD Automation

**Headless Export**:
```bash
freecad --headless model.FCStd --script export_dxf.py
```

**Python Script**:
```python
import FreeCAD as App
import Part

# Load document
doc = App.openDocument("model.FCStd")

# Export to DXF via Draft
from Draft import _DraftSketcher
Draft.makeDXF(doc.getObject("Body"), "output.dxf")
```

---

## 15. Redis Streams (Semantic/Prompt Cache)

### Stream Schema

```python
redis.xadd(
    "prompts:llm_cache",
    {
        "user_id": "user-123",
        "prompt": "What is AI?",
        "embedding": "vector-base64",
        "response": "AI is...",
        "model": "claude-sonnet",
        "tokens": 450,
        "timestamp": "2025-11-04T21:15:00Z"
    }
)
```

### Semantic Cache Query

```python
from redisearch import Client

# Search similar prompts
results = client.ft("llm_cache_idx").search(
    "@embedding:[VECTOR_SEARCH semanticCacheQuery.embedding]"
)

# Retrieve cached response if similarity > 0.85
for result in results:
    if result.similarity > 0.85:
        return result.response
```

### Eviction Strategy

**Configuration**:
```
maxmemory 2gb
maxmemory-policy allkeys-lfu

# Or with TTL
maxmemory-policy volatile-lfu
```

**Per-Stream TTL**:
```python
redis.xadd(
    "prompts:cache",
    {"prompt": "...", "response": "..."},
    expireat=int(time.time()) + 3600  # 1 hour
)
```

### RedisVL Integration

```python
from redis import Redis
from redis.commands.json.path import Path
from redisearch import Client

r = Redis.from_url("redis://localhost:6379")

# Store with semantic indexing
cache.store(
    prompt="What is AI?",
    response="AI is...",
    metadata={"model": "claude"}
)

# Query by semantic similarity
results = cache.check(
    prompt="Explain artificial intelligence",
    return_fields=["prompt", "response"]
)
```

---

## 16. PostgreSQL Audit/Lineage DB

### Desired Schema

```sql
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    resource_id UUID NOT NULL,
    old_values JSONB,
    new_values JSONB,
    context JSONB,
    INDEX idx_timestamp (timestamp DESC),
    INDEX idx_resource (resource_type, resource_id)
);

CREATE TABLE lineage_graph (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID NOT NULL,
    target_id UUID NOT NULL,
    edge_type VARCHAR(50) NOT NULL,
    attributes JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    INDEX idx_source (source_id),
    INDEX idx_target (target_id)
);
```

### Connection Pooling

**PgBouncer Configuration**:
```ini
[databases]
warehouse_db = host=localhost port=5432 dbname=warehouse

[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
min_pool_size = 10
reserve_pool_size = 5
reserve_pool_timeout = 3
```

**Application Level (Python)**:
```python
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "postgresql://user:pass@pgbouncer:6432/warehouse",
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
    pool_pre_ping=True
)
```

### Docker Setup

**docker-compose.yml**:
```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: warehouse
      POSTGRES_PASSWORD: secret
    volumes:
      - ./init.sql:/docker-entrypoint-initdb.d/
      - db_data:/var/lib/postgresql/data

  pgbouncer:
    image: pgbouncer:1.18
    environment:
      PGBOUNCER_CONFIG: /etc/pgbouncer/pgbouncer.ini
    volumes:
      - ./pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini
```

---

## 17. Prometheus Exporters & Grafana

### Standard Metric Names

```
# Node Exporter
node_cpu_seconds_total{cpu="0",mode="idle"}
node_memory_MemTotal_bytes
node_network_bytes_total{device="eth0",direction="transmit"}
node_disk_io_time_seconds_total{device="sda"}

# Custom Exporter
warehouse_printer_h2d_temperature_celsius
warehouse_printer_h2d_job_progress_percent
warehouse_power_unifi_uptime_hours
warehouse_access_door_state{door="warehouse_main"}

# System
up{job="warehouse_monitoring"}
process_resident_memory_bytes
process_cpu_seconds_total
```

### Scrape Configuration

**prometheus.yml**:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'warehouse'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:9090']
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'warehouse_.*'
        action: keep

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['192.168.1.10:9100']
```

### Grafana Dashboard JSON Import

**Structure**:
```json
{
  "dashboard": {
    "title": "Warehouse AI Lab",
    "panels": [
      {
        "id": 1,
        "title": "CPU Usage",
        "targets": [
          {
            "expr": "rate(node_cpu_seconds_total[5m])"
          }
        ],
        "datasource": "Prometheus"
      }
    ]
  }
}
```

**Import via UI**:
```
Grafana â†’ Create â†’ Import â†’ Upload JSON â†’ Select Data Source
```

---

## 18. Loki/Tempo Logging & Tracing APIs

### Loki Ingestion Protocol

**HTTP Push API**:
```bash
curl -X POST -H "Content-Type: application/json" \
  http://loki:3100/loki/api/v1/push \
  -d '{
    "streams": [
      {
        "stream": {
          "app": "warehouse",
          "level": "info",
          "host": "mac-studio"
        },
        "values": [
          ["1699000000000000000", "Application started"]
        ]
      }
    ]
  }'
```

### Retention Configuration

**Loki Config**:
```yaml
limits_config:
  retention_period: 30d

  streams:
    - selector: '{job="ai_inference"}'
      retention: 60d

    - selector: '{level="error"}'
      retention: 90d

    - selector: '{level="debug"}'
      retention: 3d
```

### Label Strategy

**Recommended Labels**:
```json
{
  "app": "warehouse",
  "env": "production",
  "service": "ai_inference",
  "level": "error",
  "host": "mac-studio",
  "region": "warehouse"
}
```

### Tempo Distributed Tracing

**OTLP HTTP Export**:
```bash
curl -X POST http://tempo:3200/v1/traces \
  -H "Content-Type: application/protobuf" \
  --data-binary @traces.pb
```

**Trace Query**:
```bash
GET /api/traces/<trace-id>
Response: Trace with all spans
```

**Object Storage Backend** (S3):
```yaml
storage:
  trace:
    backend: s3
    s3:
      bucket: tempo-traces
      endpoint: s3.amazonaws.com
      access_key: AWS_KEY
      secret_key: AWS_SECRET
    block_retention: 30d
```

**Retention Policies**:
```yaml
retention:
  period: 30d

  streams:
    - selector: '{service="ai_inference"}'
      retention: 60d
```

---

## Deployment Topology (Docker Compose)

```yaml
version: '3.8'

services:
  fastapi:
    build: ./fastapi-brain
    ports:
      - "8000:8000"
    environment:
      SECRET_KEY: ${SECRET_KEY}
      MQTT_HOST: mosquitto
      HA_URL: http://homeassistant:8123

  mosquitto:
    image: eclipse-mosquitto:latest
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto.conf:/mosquitto/config/mosquitto.conf
      - mosquitto_data:/mosquitto/data

  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:latest
    ports:
      - "8123:8123"
    volumes:
      - ha_config:/config

  ollama:
    image: ollama/ollama:latest
    runtime: nvidia
    volumes:
      - ollama_models:/root/.ollama

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lfu

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_PASSWORD: ${PG_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana

  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

  tempo:
    image: grafana/tempo:latest
    ports:
      - "3200:3200"

volumes:
  mosquitto_data:
  ha_config:
  ollama_models:
  postgres_data:
  prometheus_data:
  grafana_data:
```

---

## Security Best Practices

1. **Secrets Management**: Use `.env` files or Kubernetes secrets, never hardcode
2. **API Key Rotation**: Implement automated rotation for long-lived keys
3. **Rate Limiting**: Configure per-service to prevent cascading failures
4. **Authentication**: Prefer OAuth2/JWT over API keys where possible
5. **TLS/HTTPS**: All external APIs should use encrypted transport
6. **Network Isolation**: Run internal services on private Docker networks
7. **Audit Logging**: Log all API calls with user context to PostgreSQL
8. **Monitoring**: Alert on rate limit approaches and error spikes

---

## Glossary & Abbreviations

- **MCP**: Model Context Protocol
- **MQTT**: Message Queuing Telemetry Transport
- **RPM**: Requests Per Minute
- **TPM**: Tokens Per Minute
- **QoS**: Quality of Service
- **RTSP**: Real-time Streaming Protocol
- **JWT**: JSON Web Token
- **OAuth2**: Open Authorization 2.0
- **ACL**: Access Control List
- **NFC**: Near-Field Communication
- **TTS**: Text-To-Speech
- **STL**: Stereolithography (3D printing format)
- **GLTF**: Graphics Library Transmission Format
- **WER**: Word Error Rate
