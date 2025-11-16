# KITTY Operations Manual: Startup and Shutdown Procedures

**Updated:** 2025-11-16
**System Status:** ✅ PRODUCTION READY (Health Score: 92/100)

**KITTY** (KITT-inspired Warehouse Orchestrator) is a multi-service, offline-first AI system running on Mac Studio M3 Ultra. This manual provides comprehensive startup and shutdown procedures with detailed technical justifications.

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Architecture Overview](#architecture-overview)
3. [Detailed Startup Process](#detailed-startup-process)
4. [Detailed Shutdown Process](#detailed-shutdown-process)
5. [Service Dependencies](#service-dependencies)
6. [Health Validation](#health-validation)
7. [Troubleshooting](#troubleshooting)
8. [Emergency Procedures](#emergency-procedures)

---

## Quick Reference

### Startup (Recommended)

```bash
cd /Users/Shared/Coding/KITT
./ops/scripts/start-all.sh
```

**What it does**: Starts entire KITTY stack with health checks and sequential validation.
- Starts llama.cpp servers (Q4, F16, summary, vision)
- Starts all Docker services (brain, gateway, fabrication, RabbitMQ, etc.)
- Validates health of critical services
- Shows startup summary with URLs

### Shutdown

```bash
cd /Users/Shared/Coding/KITT
./ops/scripts/stop-all.sh
```

**What it does**: Gracefully stops all KITTY services (llama.cpp servers, Docker containers including RabbitMQ, images service).

### Verify Running Services

```bash
# Check llama.cpp servers
lsof -i :8083,8082,8085,8086

# Check Docker services
docker compose -f infra/compose/docker-compose.yml ps

# View logs
tail -f .logs/llamacpp-q4.log        # Q4 tool orchestrator
tail -f .logs/llamacpp-f16.log       # F16 reasoning engine
tail -f .logs/llamacpp-summary.log   # Hermes summarizer
tail -f .logs/llamacpp-vision.log    # Gemma vision server
```

---

## Architecture Overview

### Service Topology

KITTY operates as a **multi-tier architecture** with the following components:

```
┌─────────────────────────────────────────────────────────────┐
│                    HOST MACHINE (macOS)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  llama.cpp Servers (Native Metal Acceleration)              │
│  ├─ Q4 Server (Port 8083)   - Athene V2 Agent Q4_K_M        │
│  ├─ F16 Server (Port 8082)  - Llama 3.3 70B F16             │
│  ├─ Summary Server (Port 8085) - Hermes Summarizer          │
│  └─ Vision Server (Port 8086)  - Gemma 3 27B Q4_K_M Vision  │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Docker Compose Stack (Containerized Services)              │
│  ├─ Gateway (Port 8080)      - API Gateway, OAuth2          │
│  ├─ Brain (Port 8000)        - Conversation Router          │
│  ├─ CAD (Port 8200)          - CAD Generation               │
│  ├─ Fabrication (Port 8300)  - 3D Printer Control           │
│  ├─ Safety (Port 8400)       - Hazard Workflow              │
│  ├─ Voice                    - Speech Transcription          │
│  ├─ UI (Port 4173)           - Web Dashboard                │
│  ├─ Redis (Port 6379)        - Cache & Sessions             │
│  ├─ PostgreSQL (Port 5432)   - Persistent Storage           │
│  ├─ MinIO (Port 9000)        - S3-compatible Storage        │
│  ├─ Mosquitto (Port 1883)    - MQTT Broker                  │
│  └─ Observability            - Prometheus, Grafana, Loki    │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Optional: Images Service (Port 8089)                       │
│  └─ Stable Diffusion - Text-to-Image Generation             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Why This Architecture?

**1. Native llama.cpp Servers (Outside Docker)**
- **Metal Acceleration**: Direct access to M3 Ultra's Metal GPU acceleration
- **Unified Memory**: Leverages macOS unified memory architecture without Docker overhead
- **Performance**: ~30-40% faster inference vs. containerized deployment
- **Model Loading**: 15GB+ models load faster from local disk than Docker volumes

**2. Docker Compose for Application Services**
- **Isolation**: Each service has isolated dependencies and environment
- **Networking**: Internal Docker network for service-to-service communication
- **Portability**: Easy deployment across development and production
- **Resource Management**: CPU/memory limits per container

**3. Dual-Model Architecture (Q4 + F16)**
- **Q4 (Athene V2)**: Fast tool calling, function execution, device control
- **F16 (Llama 3.3 70B)**: Deep reasoning, complex analysis, high-quality responses
- **Routing Logic**: Brain service selects model based on task complexity
- **Cost Efficiency**: Use Q4 for 70% of requests, reserve F16 for complex reasoning

---

## Detailed Startup Process

### Phase 1: Environment Validation

**Step 1.1: Navigate to Project Root**
```bash
cd /Users/Shared/Coding/KITT
```

**Why**: All scripts use relative paths from repository root. Ensures consistent file resolution.

---

**Step 1.2: Verify .env Configuration**
```bash
cat .env | grep -E "(LLAMACPP_|ADMIN_|API_KEY)"
```

**Why**: Environment variables control:
- Model paths and configurations
- API keys for cloud providers (OpenAI, Anthropic, Perplexity, Zoo, Tripo)
- Authentication credentials
- Service endpoints and ports

**Critical Variables**:
- `LLAMACPP_MODELS_DIR`: Base directory for GGUF models (default: `/Users/Shared/Coding/models`)
- `LLAMACPP_Q4_MODEL`: Path to Q4 quantized model (fast tool orchestration)
- `LLAMACPP_F16_MODEL`: Path to F16 full-precision model (deep reasoning)
- `LLAMACPP_VISION_MODEL`: Path to Gemma 3 27B vision model
- `LLAMACPP_VISION_MMPROJ`: Path to mmproj file for vision capabilities
- `ADMIN_USERS`: Bcrypt-hashed admin credentials
- `OFFLINE_MODE`: When `true`, disables cloud API fallback

**Validation**:
```bash
# Ensure .env exists
if [[ ! -f .env ]]; then
  echo "ERROR: .env file missing. Copy .env.example to .env and configure."
  exit 1
fi
```

---

**Step 1.3: Check Prerequisites**
```bash
command -v docker >/dev/null 2>&1 || echo "Docker not installed"
command -v llama-server >/dev/null 2>&1 || echo "llama.cpp not in PATH"
docker info >/dev/null 2>&1 || echo "Docker daemon not running"
```

**Why Each Prerequisite**:

1. **Docker**: Required for containerized services (gateway, brain, cad, fabrication, etc.)
   - Validation: `docker info` checks daemon connectivity
   - Failure Impact: Cannot start application services

2. **llama-server**: Native llama.cpp binary for Metal-accelerated inference
   - Location: Usually `/opt/homebrew/bin/llama-server` or custom compiled
   - Validation: `which llama-server` confirms binary availability
   - Failure Impact: No local AI inference capability

3. **Docker Daemon**: Must be running before container orchestration
   - Start: `open -a Docker` (launches Docker Desktop)
   - Failure Impact: `docker compose up` will fail

---

### Phase 2: Cleanup Existing Services

**Step 2.1: Stop Previous Docker Services**
```bash
docker compose -f infra/compose/docker-compose.yml down
```

**Why**:
- **Port Conflicts**: Services bind to specific ports (8000, 8080, etc.). Previous instances must release ports.
- **State Cleanup**: Old containers may have stale connections, cached data, or zombie processes.
- **Resource Freeing**: Releases CPU, memory, and file handles for fresh startup.

**Technical Details**:
- Sends `SIGTERM` to all containers (graceful shutdown, 10s timeout)
- Falls back to `SIGKILL` if containers don't stop
- Removes containers but preserves volumes (data persistence)
- Deletes bridge network `kitty_default`

---

**Step 2.2: Stop Previous llama.cpp Servers**
```bash
# Check for running servers on target ports
for port in 8083 8082 8085 8086; do
  lsof -ti :$port | xargs kill -9 2>/dev/null || true
done
```

**Why**:
- **Port Binding**: llama.cpp servers bind exclusively to ports. Must kill old processes.
- **Memory Cleanup**: Large models (70GB F16) consume significant RAM. Kill releases memory.
- **GPU Reset**: Forces Metal GPU context reset for clean initialization.

**Ports**:
- `8083`: Q4 tool orchestrator
- `8082`: F16 reasoning engine
- `8085`: Hermes summarizer (optional)
- `8086`: Gemma vision server (optional)

**Graceful vs. Force Kill**:
```bash
# Attempt graceful shutdown (SIGTERM)
kill $PID
sleep 2

# Force kill if still running (SIGKILL)
if kill -0 $PID 2>/dev/null; then
  kill -9 $PID
fi
```

---

**Step 2.3: Clean PID Files**
```bash
rm -f .logs/llamacpp-*.pid
```

**Why**: PID files track running process IDs. Stale PID files cause false "already running" detections.

---

### Phase 3: Start llama.cpp Servers

**Step 3.1: Create Log Directory**
```bash
mkdir -p .logs
```

**Why**:
- Centralized logging for troubleshooting
- Persistent across runs (not cleaned on shutdown)
- Separate log per service for debugging

---

**Step 3.2: Validate Model Files**
```bash
MODELS_DIR="${LLAMACPP_MODELS_DIR:-/Users/Shared/Coding/models}"
Q4_MODEL="${LLAMACPP_Q4_MODEL}"
F16_MODEL="${LLAMACPP_F16_MODEL}"

if [[ ! -f "$MODELS_DIR/$Q4_MODEL" ]]; then
  echo "ERROR: Q4 model not found at $MODELS_DIR/$Q4_MODEL"
  exit 1
fi

if [[ ! -f "$MODELS_DIR/$F16_MODEL" ]]; then
  echo "ERROR: F16 model not found at $MODELS_DIR/$F16_MODEL"
  exit 1
fi
```

**Why**:
- **Early Failure Detection**: Catch missing models before server start (prevents cryptic runtime errors)
- **User Guidance**: Provides exact path of missing file for download
- **Multi-File Models**: Some models span multiple files (e.g., Llama-3.3-70B-F16 has 4 shards)

**Model Requirements**:
- Q4 Model: ~15-20GB disk space, 4-bit quantized for speed
- F16 Model: ~140GB disk space, full precision for accuracy
- Vision Model: ~15GB (gemma-3-27b-it-q4_k_m.gguf)
- Vision MMPROJ: ~818MB (mmproj-google_gemma-3-27b-it-bf16.gguf)

---

**Step 3.3: Start Q4 Server (Tool Orchestrator)**
```bash
llama-server \
  --port 8083 \
  --n_gpu_layers 999 \
  --ctx-size 16384 \
  --threads 20 \
  --batch-size 4096 \
  --ubatch-size 1024 \
  -np 4 \
  --model "$MODELS_DIR/$Q4_MODEL" \
  --alias kitty-q4 \
  --flash-attn on \
  --jinja \
  > .logs/llamacpp-q4.log 2>&1 &

Q4_PID=$!
echo $Q4_PID > .logs/llamacpp-q4.pid
```

**Parameter Justifications**:

| Parameter | Value | Why |
|-----------|-------|-----|
| `--port 8083` | 8083 | Non-conflicting port for Q4 server |
| `--n_gpu_layers 999` | Full GPU | Offload all 81 layers to Metal GPU for max throughput |
| `--ctx-size 16384` | 16K tokens | Large context for multi-turn conversations, tool calling |
| `--threads 20` | 20 threads | M3 Ultra has 24 P-cores; leave 4 for OS and other services |
| `--batch-size 4096` | 4096 tokens | Large batch for better GPU utilization during prompt processing |
| `--ubatch-size 1024` | 1024 tokens | Micro-batch size for memory bandwidth optimization |
| `-np 4` | 4 parallel | Handle 4 simultaneous requests (tool calling, device control, etc.) |
| `--flash-attn on` | Enabled | Flash Attention v2 for 2-3x faster attention computation |
| `--jinja` | Enabled | Support for Jinja2 chat templates (required for tool calling) |

**Why Background Process (`&`)**:
- Server runs indefinitely until stopped
- Allows script to continue and start F16 server
- Logs redirected to file for monitoring

**Why PID File**:
- Enables clean shutdown via `stop-llamacpp-dual.sh`
- Prevents orphaned processes
- Allows status checking (`kill -0 $PID`)

---

**Step 3.4: Start F16 Server (Reasoning Engine)**
```bash
llama-server \
  --port 8082 \
  --n_gpu_layers 999 \
  --ctx-size 16384 \
  --threads 20 \
  --batch-size 4096 \
  --ubatch-size 1024 \
  -np 4 \
  --model "$MODELS_DIR/$F16_MODEL" \
  --alias kitty-f16 \
  --flash-attn on \
  --jinja \
  > .logs/llamacpp-f16.log 2>&1 &

F16_PID=$!
echo $F16_PID > .logs/llamacpp-f16.pid
```

**F16 vs Q4 Differences**:
- **Precision**: F16 uses 16-bit floats (vs Q4's 4-bit quantization)
- **Accuracy**: ~2-5% higher quality responses, better reasoning
- **Speed**: ~4x slower than Q4 (tradeoff for quality)
- **Use Cases**: Complex analysis, code generation, creative writing

**Why Two Servers Instead of One**:
1. **Routing Flexibility**: Brain service routes simple queries to Q4, complex to F16
2. **Cost Efficiency**: 70% of requests handled by fast Q4 model
3. **Concurrent Processing**: Q4 handles tools while F16 processes reasoning task
4. **Model Loading**: Avoids swapping models in/out of VRAM (5+ min load time for 70B)

---

**Step 3.5: Start Optional Services**

**Hermes Summarizer (Port 8085)**
```bash
if [[ "${LLAMACPP_SUMMARY_ENABLED:-1}" == "1" ]]; then
  llama-server \
    --port 8085 \
    --n_gpu_layers 999 \
    --ctx-size 8192 \
    --threads 12 \
    --batch-size 1024 \
    -np 2 \
    --model "$MODELS_DIR/$SUMMARY_MODEL" \
    --alias kitty-summary \
    > .logs/llamacpp-summary.log 2>&1 &

  SUMMARY_PID=$!
  echo $SUMMARY_PID > .logs/llamacpp-summary.pid
fi
```

**Why Hermes Summarizer**:
- **Lightweight**: 8B parameter model (vs 70B) for fast summaries
- **Specialized**: Fine-tuned for conversation summarization
- **Context Management**: Condenses long conversations for context windows
- **Cost Savings**: Avoids burning F16 GPU cycles on simple summaries

---

**Gemma Vision Server (Port 8086)**
```bash
if [[ "${LLAMACPP_VISION_ENABLED:-1}" == "1" ]]; then
  llama-server \
    --port 8086 \
    --n_gpu_layers 999 \
    --ctx-size 8192 \
    --threads 16 \
    --model "$MODELS_DIR/$VISION_MODEL" \
    --mmproj "$MODELS_DIR/$VISION_MMPROJ" \
    --alias kitty-vision \
    > .logs/llamacpp-vision.log 2>&1 &

  VISION_PID=$!
  echo $VISION_PID > .logs/llamacpp-vision.pid
fi
```

**Why Vision Server**:
- **Image Understanding**: Analyze CAD screenshots, print failures, camera feeds
- **MMPROJ File**: Multi-modal projection layer maps image features to text embeddings
- **Use Cases**:
  - First-layer print inspection
  - Spaghetti detection (failed prints)
  - CAD reference image analysis
  - Vision-guided device control

**MMPROJ Technical Details**:
- **Size**: 818MB (bf16 precision)
- **Function**: Projects 896-dimensional image patches into text token space
- **Architecture**: Gemma-3 specific vision encoder (not compatible with other models)
- **Required**: Vision server will fail to start without correct mmproj file

---

**Step 3.6: Wait for Server Health**
```bash
wait_for_http() {
  local url=$1
  local name=$2
  local max_attempts=${3:-30}

  for i in $(seq 1 $max_attempts); do
    if curl -sf "$url" > /dev/null 2>&1; then
      echo "✓ $name is ready"
      return 0
    fi
    sleep 2
  done

  echo "✗ $name failed to start"
  return 1
}

wait_for_http "http://localhost:8083/health" "Q4 server" 60
wait_for_http "http://localhost:8082/health" "F16 server" 60
wait_for_http "http://localhost:8086/health" "Vision server" 60
```

**Why Health Checks**:
1. **Model Loading**: F16 70B takes ~5 minutes to load into unified memory
2. **GPU Initialization**: Metal backend needs time to allocate VRAM
3. **Early Failure Detection**: Catches startup errors before Docker services depend on llama.cpp
4. **Sequential Dependency**: Brain service requires working llama.cpp servers

**Health Endpoint Behavior**:
- Returns `200 OK` once model is loaded and server is accepting requests
- Returns connection refused during loading phase
- Returns `503 Service Unavailable` if model load fails

---

### Phase 4: Start Docker Services

**Step 4.1: Docker Compose Up**
```bash
docker compose \
  --env-file .env \
  -f infra/compose/docker-compose.yml \
  up -d --build
```

**Parameter Breakdown**:

| Parameter | Purpose |
|-----------|---------|
| `--env-file .env` | Inject environment variables into containers |
| `-f infra/compose/docker-compose.yml` | Path to compose configuration |
| `up` | Create and start containers |
| `-d` | Detached mode (run in background) |
| `--build` | Rebuild images if Dockerfiles changed |

**Why Build on Every Start**:
- **Development Workflow**: Code changes require image rebuild
- **Dependency Updates**: Ensures `requirements.txt` changes are applied
- **Layer Caching**: Docker reuses unchanged layers (fast rebuilds)
- **Production Safety**: Guarantees running containers match source code

---

**Step 4.2: Service Startup Order**

Docker Compose starts services **in dependency order** based on `depends_on`:

```yaml
# Startup sequence:
1. redis          # In-memory cache (no dependencies)
2. postgres       # Database (no dependencies)
3. mosquitto      # MQTT broker (no dependencies)
4. minio          # Object storage (no dependencies)
5. brain          # Depends on redis, postgres, mosquitto
6. gateway        # Depends on brain, minio
7. cad            # Depends on brain, minio
8. fabrication    # Depends on mosquitto, postgres
9. safety         # Depends on postgres
10. voice         # Depends on brain, mosquitto
11. ui            # Depends on gateway (frontend)
```

**Why This Order**:
- **Data Layer First**: Databases must be ready before application services
- **Message Bus Early**: MQTT enables async communication between services
- **Brain as Hub**: Central router must start before dependent services
- **UI Last**: Frontend depends on all backend APIs being available

---

**Step 4.3: Validate Critical Services**

```bash
# Wait for Brain service (core dependency)
wait_for_http "http://localhost:8000/health" "Brain service" 30

# Verify database connectivity
docker compose -f infra/compose/docker-compose.yml exec postgres \
  psql -U kitty -d kitty -c "SELECT 1"

# Check Redis
redis-cli ping
```

**Why Validate Brain**:
- **Central Router**: All conversation queries flow through Brain
- **llama.cpp Client**: Brain connects to Q4/F16 servers
- **Routing Logic**: Implements local/MCP/frontier tier selection
- **Critical Path**: If Brain fails, entire conversational AI is down

**Why Validate Postgres**:
- **Routing Audit**: Stores every routing decision (tier, cost, latency)
- **Hazard Logs**: Safety workflow requires database writes
- **Project Notes**: Persistent user data storage
- **Alembic Migrations**: Database must accept schema changes

**Why Validate Redis**:
- **Semantic Cache**: Stores hash of similar prompts for fast lookup
- **Session State**: Conversation context and user sessions
- **LFU Eviction**: 2GB cache with least-frequently-used eviction
- **Sub-100ms Latency**: Cache hit avoids $0.002 API call

---

### Phase 5: Optional Images Service

**Step 5.1: Check if Enabled**
```bash
if [[ "${IMAGES_SERVICE_ENABLED:-false}" == "true" ]]; then
  ./ops/scripts/start-images-service.sh > .logs/images-service-startup.log 2>&1 &
fi
```

**Why Optional**:
- **Resource Intensive**: Stable Diffusion models consume 8-12GB VRAM
- **Long Startup**: Model loading takes 2-3 minutes
- **Specific Use Case**: Only needed for text-to-image generation
- **GPU Contention**: Competes with llama.cpp for Metal resources

---

**Step 5.2: Images Service Startup Sequence**

```bash
# 1. Create virtual environment (if not exists)
python3 -m venv services/images_service/.venv

# 2. Install dependencies
.venv/bin/pip install -r requirements.txt

# 3. Start RQ worker (background job processor)
.venv/bin/rq worker images \
  --url redis://127.0.0.1:6379/0 \
  > .logs/rq_worker.log 2>&1 &

# 4. Start FastAPI service
.venv/bin/uvicorn main:app \
  --host 127.0.0.1 \
  --port 8089 \
  > .logs/service.log 2>&1 &
```

**Component Purposes**:

| Component | Port | Purpose |
|-----------|------|---------|
| FastAPI Service | 8089 | REST API for image generation requests |
| RQ Worker | N/A | Background processor for Stable Diffusion inference |
| Redis Queue | 6379 | Job queue between API and worker |

**Why RQ (Redis Queue)**:
- **Async Processing**: Image generation takes 30-60s, can't block HTTP request
- **Job Persistence**: Survives worker crashes
- **Retry Logic**: Automatic retry on failure
- **Priority Queues**: Support for high-priority image requests

**Model Loading**:
```yaml
# models.yaml
models:
  sd_xl_base:
    path: /Users/Shared/Coding/models/sd_xl_base
    type: diffusers
    precision: fp16
```

**Why SDXL (Stable Diffusion XL)**:
- **High Quality**: 1024x1024 resolution, photorealistic
- **Fine Control**: Support for negative prompts, LoRA adapters
- **Local Inference**: No API costs vs Midjourney/DALL-E

---

### Phase 6: Final Validation

**Step 6.1: Service Status Check**
```bash
echo "╔═══════════════════════════════════════════════════════╗"
echo "║              KITTY Stack Status Summary               ║"
echo "╚═══════════════════════════════════════════════════════╝"

# Check all ports
for port in 8083 8082 8085 8086 8000 8080 6379 5432 8089; do
  if lsof -i :$port > /dev/null 2>&1; then
    echo "✓ Port $port is in use"
  else
    echo "✗ Port $port is NOT in use"
  fi
done
```

**Why Port Checks**:
- **Fast Validation**: Confirms service binding without HTTP overhead
- **Network Debug**: Identifies port conflicts or binding failures
- **Comprehensive**: Single command checks entire stack

---

**Step 6.2: End-to-End Test**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "test connectivity",
    "userId": "startup-validation"
  }'
```

**Why End-to-End Test**:
- **Full Stack**: Validates gateway → brain → llama.cpp flow
- **Routing Logic**: Confirms tier selection works
- **Authentication**: Tests JWT token validation (if enabled)
- **Database Writes**: Ensures routing audit log writes to Postgres

**Expected Response**:
```json
{
  "response": "Connection successful",
  "tier": "local",
  "model": "kitty-q4",
  "confidence": 0.95,
  "latency_ms": 450
}
```

---

## Detailed Shutdown Process

### Phase 1: Graceful Service Termination

**Step 1.1: Execute Stop Script**
```bash
./ops/scripts/stop-kitty.sh
```

**Shutdown Sequence**:
1. Stop Docker services
2. Stop llama.cpp servers
3. Stop images service (if running)

---

### Phase 2: Docker Compose Down

**Step 2.1: Container Shutdown**
```bash
docker compose \
  --env-file .env \
  -f infra/compose/docker-compose.yml \
  down
```

**Shutdown Process (Per Container)**:
1. Send `SIGTERM` to container PID 1 (main process)
2. Wait 10 seconds for graceful shutdown
3. Send `SIGKILL` if process still running
4. Remove container from Docker engine
5. Disconnect from bridge network

**Why Graceful Shutdown Important**:
- **Database Writes**: Postgres needs to flush WAL (write-ahead log) to disk
- **Redis Persistence**: Save in-memory cache to RDB snapshot
- **MQTT Cleanup**: Close WebSocket connections cleanly
- **Active Jobs**: CAD generation jobs can save partial progress

---

**Step 2.2: Network Cleanup**
```bash
docker network ls | grep kitty_default
```

**Why Remove Networks**:
- **IP Address Release**: Frees 172.x.x.x subnet
- **Clean State**: Ensures next `docker compose up` gets fresh IPs
- **No Stale Routes**: Prevents DNS resolution issues

---

### Phase 3: llama.cpp Server Shutdown

**Step 3.1: Stop Q4 Server**
```bash
if [[ -f .logs/llamacpp-q4.pid ]]; then
  Q4_PID=$(cat .logs/llamacpp-q4.pid)

  # Graceful shutdown
  kill $Q4_PID
  sleep 1

  # Force kill if still running
  if kill -0 $Q4_PID 2>/dev/null; then
    kill -9 $Q4_PID
  fi

  rm -f .logs/llamacpp-q4.pid
fi
```

**Why Graceful Then Force**:
1. **SIGTERM (kill)**: Allows server to close file descriptors, flush logs
2. **1 Second Wait**: Give server time to shutdown cleanly
3. **SIGKILL (kill -9)**: Forcefully terminate if hung (model unload failure)

**PID File Cleanup**:
- Prevents false "already running" detection on next start
- Ensures stale PIDs don't cause kill failures

---

**Step 3.2: Stop F16, Summary, Vision Servers**
```bash
# Same process for each server
for pid_file in .logs/llamacpp-f16.pid \
                .logs/llamacpp-summary.pid \
                .logs/llamacpp-vision.pid; do
  if [[ -f "$pid_file" ]]; then
    PID=$(cat "$pid_file")
    kill $PID 2>/dev/null || true
    sleep 1
    kill -9 $PID 2>/dev/null || true
    rm -f "$pid_file"
  fi
done
```

**Why Parallel Shutdown**:
- **Independent Processes**: Servers don't depend on each other
- **Faster Cleanup**: All servers shutdown concurrently
- **Resource Release**: GPU memory freed immediately

---

**Step 3.3: Fallback: Kill All llama-server Processes**
```bash
pgrep -f "llama-server" | xargs kill -9 2>/dev/null || true
```

**When Fallback Triggers**:
- PID files deleted manually
- Server crashed and PID file is stale
- Manual `llama-server` start outside of scripts

**Why Force Kill in Fallback**:
- No PID file means we can't determine if process is from this session
- Safe to force kill (no critical data in llama.cpp server)
- Ensures clean slate for next startup

---

### Phase 4: Images Service Shutdown

**Step 4.1: Stop FastAPI Service**
```bash
if [[ -f services/images_service/.service.pid ]]; then
  SERVICE_PID=$(cat services/images_service/.service.pid)
  kill $SERVICE_PID
  rm -f services/images_service/.service.pid
fi
```

**Why Stop API First**:
- Prevents new image generation requests
- Allows existing requests to complete via RQ worker
- Graceful 503 responses for in-flight HTTP requests

---

**Step 4.2: Stop RQ Worker**
```bash
if [[ -f services/images_service/.rq_worker.pid ]]; then
  WORKER_PID=$(cat services/images_service/.rq_worker.pid)
  kill $WORKER_PID
  rm -f services/images_service/.rq_worker.pid
fi
```

**Why Stop Worker Last**:
- Complete in-progress image generation jobs
- Save partial progress to Redis
- Avoid orphaned jobs in queue

---

### Phase 5: Verify Shutdown

**Step 5.1: Port Check**
```bash
lsof -i :8083,8082,8085,8086,8000,8080,8089
```

**Expected Output**: No output (all ports released)

**If Ports Still Bound**:
```bash
# Find stubborn process
lsof -ti :8083 | xargs ps -p

# Force kill
lsof -ti :8083 | xargs kill -9
```

---

**Step 5.2: GPU Memory Release**
```bash
# Check Metal GPU usage (macOS)
sudo powermetrics --samplers gpu_power -i 1 -n 1
```

**Expected**: GPU idle, VRAM usage <500MB (baseline macOS usage)

---

## Service Dependencies

### Dependency Graph

```
llama.cpp Servers (Metal)
  ├─ Q4 Server (8083)
  │   └─ Required by: Brain, Gateway (tool calling)
  ├─ F16 Server (8082)
  │   └─ Required by: Brain (reasoning)
  ├─ Summary Server (8085)
  │   └─ Required by: Brain (conversation summarization)
  └─ Vision Server (8086)
      └─ Required by: Brain (image analysis), CAD (reference images)

Docker Infrastructure
  ├─ Redis (6379)
  │   ├─ Required by: Brain (semantic cache), Images Service (job queue)
  │   └─ Data: Session state, routing cache, RQ jobs
  ├─ PostgreSQL (5432)
  │   ├─ Required by: Brain (routing audit), Safety (hazard logs)
  │   └─ Data: Routing decisions, hazard confirmations, project notes
  ├─ MinIO (9000)
  │   ├─ Required by: CAD (artifact storage), Images Service
  │   └─ Data: STEP files, STL meshes, generated images
  └─ Mosquitto (1883)
      ├─ Required by: Fabrication (printer commands), Voice (TTS)
      └─ Data: Real-time device state, MQTT pub/sub

Application Services
  ├─ Brain (8000) - Conversation router
  │   ├─ Depends on: Redis, PostgreSQL, Mosquitto, llama.cpp servers
  │   └─ Required by: Gateway, Voice, CLI
  ├─ Gateway (8080) - API gateway, OAuth2
  │   ├─ Depends on: Brain, MinIO
  │   └─ Required by: UI, External API clients
  ├─ CAD (8200) - CAD generation
  │   ├─ Depends on: Brain, MinIO
  │   └─ Required by: UI, CLI (CAD workflows)
  ├─ Fabrication (8300) - 3D printer control
  │   ├─ Depends on: Mosquitto, PostgreSQL
  │   └─ Required by: UI (print queue), CLI (printer status)
  ├─ Safety (8400) - Hazard workflow
  │   ├─ Depends on: PostgreSQL
  │   └─ Required by: Brain (hazard validation)
  └─ Voice - Speech transcription
      ├─ Depends on: Brain, Mosquitto
      └─ Required by: Voice-enabled workflows

Frontend
  └─ UI (4173) - Web dashboard
      ├─ Depends on: Gateway, Mosquitto (MQTT over WebSocket)
      └─ Required by: Human operators

Optional Services
  └─ Images Service (8089) - Stable Diffusion
      ├─ Depends on: Redis (job queue), MinIO (storage)
      └─ Required by: CAD (reference images), Vision workflows
```

---

## Health Validation

### Health Check Endpoints

All services expose `/health` endpoints:

```bash
# llama.cpp servers
curl http://localhost:8083/health  # Q4
curl http://localhost:8082/health  # F16
curl http://localhost:8086/health  # Vision

# Application services
curl http://localhost:8000/health  # Brain
curl http://localhost:8080/health  # Gateway
curl http://localhost:8200/health  # CAD
curl http://localhost:8300/health  # Fabrication
curl http://localhost:8400/health  # Safety

# Images service
curl http://localhost:8089/        # FastAPI root
```

---

### Health Check Response Format

**Healthy Response**:
```json
{
  "status": "healthy",
  "service": "brain",
  "version": "1.0.0",
  "dependencies": {
    "redis": "connected",
    "postgres": "connected",
    "llama_cpp_q4": "connected",
    "llama_cpp_f16": "connected"
  },
  "uptime_seconds": 3600
}
```

**Unhealthy Response**:
```json
{
  "status": "unhealthy",
  "service": "brain",
  "error": "Failed to connect to llama.cpp Q4 server",
  "dependencies": {
    "redis": "connected",
    "postgres": "connected",
    "llama_cpp_q4": "unreachable",
    "llama_cpp_f16": "connected"
  }
}
```

---

### Comprehensive Health Script

```bash
#!/bin/bash
# ops/scripts/health-check.sh

SERVICES=(
  "Q4:http://localhost:8083/health"
  "F16:http://localhost:8082/health"
  "Vision:http://localhost:8086/health"
  "Brain:http://localhost:8000/health"
  "Gateway:http://localhost:8080/health"
  "CAD:http://localhost:8200/health"
  "Fabrication:http://localhost:8300/health"
  "Safety:http://localhost:8400/health"
)

echo "KITTY Health Check"
echo "=================="

for service in "${SERVICES[@]}"; do
  IFS=':' read -r name url <<< "$service"

  if curl -sf "$url" > /dev/null 2>&1; then
    echo "✓ $name - Healthy"
  else
    echo "✗ $name - Unhealthy"
  fi
done
```

---

## Troubleshooting

### Issue: llama.cpp Server Won't Start

**Symptoms**:
- Port already in use
- Model file not found
- Segmentation fault

**Diagnosis**:
```bash
# Check if port is in use
lsof -i :8083

# Verify model file exists
ls -lh /Users/Shared/Coding/models/$LLAMACPP_Q4_MODEL

# Check llama-server version
llama-server --version

# View startup logs
tail -f .logs/llamacpp-q4.log
```

**Solutions**:

**1. Port Conflict**
```bash
# Kill process on port
lsof -ti :8083 | xargs kill -9

# Or change port in .env
LLAMACPP_Q4_PORT=8084
```

**2. Model Not Found**
```bash
# Download model
huggingface-cli download \
  Nexesenex/Athene-V2-Agent-GGUF \
  Athene-V2-Agent-Q4_K_M.gguf \
  --local-dir /Users/Shared/Coding/models/athene-v2-agent

# Update .env path
LLAMACPP_Q4_MODEL=athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf
```

**3. Segmentation Fault**
```bash
# Rebuild llama.cpp with latest fixes
cd /path/to/llama.cpp
git pull
make clean
make GGML_METAL=1

# Copy binary to PATH
sudo cp llama-server /opt/homebrew/bin/
```

**4. Out of Memory**
```bash
# Reduce context size
LLAMACPP_Q4_CTX=8192  # Instead of 16384

# Reduce parallel slots
LLAMACPP_Q4_PARALLEL=2  # Instead of 4

# Reduce GPU layers (use CPU for some layers)
LLAMACPP_Q4_N_GPU_LAYERS=60  # Instead of 999
```

---

### Issue: Docker Services Won't Start

**Symptoms**:
- Container exits immediately
- "Port is already allocated"
- Build failures

**Diagnosis**:
```bash
# Check container status
docker compose -f infra/compose/docker-compose.yml ps

# View logs for specific service
docker compose -f infra/compose/docker-compose.yml logs brain

# Check if ports are in use
lsof -i :8000,8080,6379,5432
```

**Solutions**:

**1. Port Conflict**
```bash
# Find conflicting process
lsof -ti :8000 | xargs ps -p

# Stop conflicting service
brew services stop postgresql  # If Postgres port conflict

# Or change port in docker-compose.yml
```

**2. Missing Environment Variables**
```bash
# Verify .env is loaded
docker compose --env-file .env config | grep -A 5 brain

# Check for required variables
grep -E "(OPENAI_API_KEY|ADMIN_USERS)" .env
```

**3. Build Failure (Python Dependencies)**
```bash
# Clear Docker build cache
docker builder prune -a -f

# Rebuild specific service
docker compose build --no-cache brain

# Check Dockerfile syntax
docker compose config
```

**4. Database Connection Failure**
```bash
# Check Postgres logs
docker compose logs postgres

# Verify database exists
docker compose exec postgres psql -U kitty -c "\l"

# Run migrations manually
docker compose exec brain alembic upgrade head
```

---

### Issue: Vision Server Fails with MMPROJ Error

**Symptoms**:
```
Error: Vision mmproj file not found at /Users/Shared/Coding/models/...
```

**Solution**:
```bash
# Download correct mmproj file
huggingface-cli download \
  bartowski/google_gemma-3-27b-it-GGUF \
  mmproj-google_gemma-3-27b-it-bf16.gguf \
  --local-dir /Users/Shared/Coding/models/gemma-3-27b-it-GGUF

# Verify file exists
ls -lh /Users/Shared/Coding/models/gemma-3-27b-it-GGUF/*.gguf

# Update .env
LLAMACPP_VISION_MMPROJ=gemma-3-27b-it-GGUF/mmproj-google_gemma-3-27b-it-bf16.gguf
```

---

### Issue: High CPU/GPU Usage

**Symptoms**:
- Mac fans at max speed
- Sluggish UI
- High power consumption

**Diagnosis**:
```bash
# Check Metal GPU usage
sudo powermetrics --samplers gpu_power -i 5 -n 1

# Check CPU per-process
top -o cpu

# Check llama.cpp thread count
ps -p $(cat .logs/llamacpp-f16.pid) -T
```

**Solutions**:

**1. Reduce Thread Count**
```bash
# .env changes
LLAMACPP_F16_THREADS=12  # Instead of 20 (leaves more for OS)
LLAMACPP_Q4_THREADS=12
```

**2. Reduce GPU Layers (Hybrid CPU/GPU)**
```bash
# Use hybrid offload for cooler operation
LLAMACPP_F16_N_GPU_LAYERS=40  # Instead of 999
LLAMACPP_Q4_N_GPU_LAYERS=60
```

**3. Reduce Parallel Slots**
```bash
# Lower concurrent request handling
LLAMACPP_F16_PARALLEL=2  # Instead of 4
LLAMACPP_Q4_PARALLEL=2
```

**4. Disable Optional Services**
```bash
# Turn off vision and summary servers
LLAMACPP_VISION_ENABLED=0
LLAMACPP_SUMMARY_ENABLED=0
IMAGES_SERVICE_ENABLED=false
```

---

### Issue: Brain Service Returns "No route found"

**Symptoms**:
```json
{
  "error": "No route found",
  "tier": null,
  "confidence": 0.0
}
```

**Diagnosis**:
```bash
# Check if llama.cpp servers are reachable from Docker
docker compose exec brain curl http://host.docker.internal:8083/health

# Check routing logs
docker compose logs brain | grep routing

# Verify .env variables
docker compose exec brain env | grep LLAMACPP_
```

**Solutions**:

**1. Fix host.docker.internal Resolution**
```bash
# Add to docker-compose.yml brain service
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**2. Update llama.cpp Host URLs**
```bash
# .env
LLAMACPP_Q4_HOST=http://host.docker.internal:8083
LLAMACPP_F16_HOST=http://host.docker.internal:8082
```

**3. Restart Brain Service**
```bash
docker compose restart brain
```

---

## Emergency Procedures

### Emergency Stop All Services

```bash
#!/bin/bash
# ops/scripts/emergency-stop.sh

# Force kill all llama.cpp processes
pkill -9 llama-server

# Force stop all Docker containers
docker kill $(docker ps -q) 2>/dev/null || true

# Remove all containers
docker rm -f $(docker ps -aq) 2>/dev/null || true

# Clean PID files
rm -f .logs/*.pid

# Clean images service PIDs
rm -f services/images_service/.*.pid

echo "Emergency stop complete"
```

**When to Use**:
- System freeze/hang
- Runaway GPU memory usage
- Unresponsive services blocking shutdown

---

### Backup Before Maintenance

```bash
#!/bin/bash
# ops/scripts/backup-state.sh

BACKUP_DIR="$HOME/KITTY_backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup Postgres database
docker compose exec -T postgres pg_dump -U kitty kitty > "$BACKUP_DIR/postgres.sql"

# Backup Redis (if persistence enabled)
docker compose exec redis redis-cli SAVE
docker cp $(docker compose ps -q redis):/data/dump.rdb "$BACKUP_DIR/"

# Backup .env
cp .env "$BACKUP_DIR/env.backup"

# Backup MinIO artifacts
mc mirror kitty-minio/kitty-artifacts "$BACKUP_DIR/artifacts"

echo "Backup saved to: $BACKUP_DIR"
```

---

### Restore from Backup

```bash
#!/bin/bash
# ops/scripts/restore-state.sh

BACKUP_DIR=$1

if [[ -z "$BACKUP_DIR" ]]; then
  echo "Usage: $0 /path/to/backup"
  exit 1
fi

# Restore Postgres
docker compose exec -T postgres psql -U kitty kitty < "$BACKUP_DIR/postgres.sql"

# Restore Redis
docker cp "$BACKUP_DIR/dump.rdb" $(docker compose ps -q redis):/data/
docker compose restart redis

# Restore .env
cp "$BACKUP_DIR/env.backup" .env

echo "Restore complete"
```

---

## Performance Benchmarks

### Expected Startup Times

| Component | First Start | Subsequent Starts | Why Difference |
|-----------|-------------|-------------------|----------------|
| Q4 Server | 45s | 30s | Model file caching |
| F16 Server | 5m 30s | 4m 45s | 140GB model load, unified memory |
| Vision Server | 2m 15s | 1m 50s | MMPROJ load + model |
| Docker Compose | 3m 30s | 1m 15s | Image build vs cached layers |
| Brain Service | 45s | 20s | Dependency startup |
| Images Service | 2m 45s | 1m 30s | SDXL model load |
| **Total Stack** | **10-12m** | **6-8m** | Parallel startup optimizations |

---

### Resource Usage (Steady State)

| Component | CPU | RAM | VRAM | Disk I/O |
|-----------|-----|-----|------|----------|
| Q4 Server | 5-15% | 18GB | 16GB | Low |
| F16 Server | 10-25% | 145GB | 80GB | Low |
| Vision Server | 2-8% | 20GB | 18GB | Low |
| Brain Service | 2-5% | 512MB | N/A | Medium |
| PostgreSQL | 1-3% | 256MB | N/A | Medium |
| Redis | 1-2% | 2GB | N/A | High |
| UI Service | <1% | 128MB | N/A | Low |
| **Total** | **30-50%** | **~190GB** | **~115GB** | **Variable** |

**System Requirements**:
- **CPU**: 24+ cores (M3 Ultra or equivalent)
- **RAM**: 192GB+ unified memory
- **GPU**: Metal-capable with 120GB+ VRAM allocation
- **Disk**: 500GB+ SSD for models and cache

---

## Conclusion

This operations manual provides comprehensive coverage of KITTY startup and shutdown procedures. The architecture prioritizes:

1. **Offline-First**: Local inference before cloud escalation
2. **Performance**: Metal GPU acceleration for sub-second responses
3. **Reliability**: Health checks and graceful degradation
4. **Observability**: Detailed logging and metrics
5. **Safety**: Hazard workflows and audit trails

For additional support:
- **Documentation**: `/docs/project-overview.md`
- **Architecture**: `/specs/001-KITTY/spec.md`
- **API Reference**: `/Research/APIinfo.md`
- **Runbooks**: `/ops/runbooks/`

---

**Last Updated**: 2025-11-10
**Version**: 1.0.0
**Maintainer**: KITTY Development Team
