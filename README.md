# KITTY: Technical AI Habitat for Fabrication

> **K**nowledgeable **I**ntelligent **T**ool-using **T**abletop **Y**oda
>
> An offline-first, voice-enabled fabrication lab orchestrator running on Mac Studio M3 Ultra. Think "JARVIS for your workshop" - but it actually works, runs locally, and won't spy on you.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/typescript-5.x-blue.svg" alt="TypeScript 5.x"/>
  <img src="https://img.shields.io/badge/platform-macOS_14+-lightgrey.svg" alt="macOS 14+"/>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"/>
</p>

---

## Vision: A Maker Space for Technical AI

KITTY is a **technical AI habitat** - a maker space purpose-built for AI models like Claude, GPT-5, Llama, Qwen, and Mistral to come "live," run research, and directly control fabrication hardware. Built on the energy-efficient Mac Studio M3 Ultra, it provides a secure network interface to 3D printers, CNC machines, test rigs, and sensing equipment.

**What makes KITTY different:**

- **AI Residency Model**: Models can spin up for a single query or remain active for deep, after-hours projects
- **Bounded Autonomy**: One KITTY-owned project per week with controlled access to printers, inventory, and research
- **Sustainable Manufacturing**: Prioritizes ethically sourced materials with robotic procurement workflows
- **Idea → Prototype Pipeline**: Investigate materials, estimate costs, run simulations, then orchestrate fabrication
- **Energy Efficient**: Mac Studio runs indefinitely with minimal power draw

> **Full Vision & Roadmap**: See [NorthStar/ProjectVision.md](NorthStar/ProjectVision.md) for the complete multi-phase implementation plan.

---

## Complete Tech Stack

### AI/ML Infrastructure

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Q4 Tool Orchestrator** | Fast tool calling, ReAct agent | llama.cpp (Athene V2 Agent Q4_K_M) @ port 8083 |
| **Primary Reasoner** | Deep reasoning with thinking mode | Ollama (GPT-OSS 120B) @ port 11434 |
| **Fallback Reasoner** | *(DEPRECATED)* Legacy fallback only | llama.cpp (Llama 3.3 70B F16) @ port 8082 |
| **Vision Model** | Image understanding, multimodal | llama.cpp (Gemma 3 27B Q4_K_M) @ port 8086 |
| **Summary Model** | Response compression | llama.cpp (Hermes 3 8B Q4_K_M) @ port 8084 |
| **Coder Model** | Code generation specialist | llama.cpp (Qwen2.5 Coder 32B Q8) @ port 8087 |
| **Cloud Fallbacks** | Complex queries, verification | OpenAI GPT-5, Claude Sonnet 4.5, Perplexity |

### Backend Services (Python 3.11 + FastAPI)

| Service | Port | Purpose |
|---------|------|---------|
| **Brain** | 8000 | Core orchestrator, ReAct agent, intelligent routing |
| **Gateway** | 8080 | REST API (HAProxy load-balanced, 3 replicas) |
| **CAD** | 8200 | 3D model generation (Zoo, Tripo, local CadQuery) |
| **Fabrication** | 8300 | Printer control, queue management, mesh segmentation, Bambu Labs integration |
| **Voice** | 8400 | Real-time STT/TTS with local Whisper + Piper |
| **Discovery** | 8500 | Network device scanning (mDNS, SSDP, Bamboo/Snapmaker UDP) |
| **Broker** | 8777 | Command execution with allow-list safety |
| **Images** | 8600 | Stable Diffusion generation with RQ workers |
| **Mem0 MCP** | 8765 | Semantic memory with vector embeddings |

### Frontend (React 18 + TypeScript + Vite)

| Component | Purpose |
|-----------|---------|
| **Menu** | Landing page with navigation cards to all sections |
| **Voice** | Real-time voice assistant with Local/Cloud toggle |
| **Shell** | Text chat with function calling and streaming |
| **Projects** | CAD project management with artifact browser |
| **Fabrication Console** | Printer status, queue management, mesh segmentation, job tracking |
| **Settings** | Bambu Labs login, preferences, API configuration |
| **I/O Control** | Feature toggles and provider management |
| **Research** | Autonomous research pipeline with real-time streaming |
| **Vision Gallery** | Reference image search and storage |
| **Image Generator** | Stable Diffusion generation interface |
| **Material Inventory** | Filament catalog and stock management |
| **Print Intelligence** | Success prediction and recommendations dashboard |

### Infrastructure (Docker Compose)

| Service | Technology | Purpose |
|---------|------------|---------|
| **Load Balancer** | HAProxy | Gateway traffic distribution, health checks |
| **Database** | PostgreSQL 16 | Audit logs, state, projects (clustering optional) |
| **Cache** | Redis 7 | Semantic cache, routing state, feature flags |
| **Vector DB** | Qdrant 1.11 | Memory embeddings, semantic search |
| **Object Storage** | MinIO | CAD artifacts, images, snapshots (S3-compatible) |
| **Message Queue** | RabbitMQ 3.12 | Async events, job distribution |
| **MQTT Broker** | Eclipse Mosquitto 2.0 | Device communication, printer telemetry |
| **Search Engine** | SearXNG | Private, local web search |
| **Smart Home** | Home Assistant | Device control, automation |
| **Metrics** | Prometheus + Grafana | Observability dashboards |
| **Logs** | Loki | Log aggregation |
| **Traces** | Tempo | Distributed tracing |

---

## Quick Start

### Prerequisites

- **Hardware**: Mac Studio M3 Ultra recommended (256GB+ RAM for large models)
- **OS**: macOS 14+ with Xcode command line tools
- **Software**: Docker Desktop, Python 3.11, Node 20, Homebrew

### Installation (5 minutes)

```bash
# Clone the repository
git clone https://github.com/yourusername/KITT.git
cd KITT

# Install developer tools
pip install --upgrade pip pre-commit
pre-commit install

# Create environment file
cp .env.example .env
# Edit .env with your settings (see Configuration section below)

# Setup artifacts directory (for accessing 3MF/GLB files in Finder)
./ops/scripts/setup-artifacts-dir.sh

# Start everything
./ops/scripts/start-all.sh
```

### Accessing KITTY

After startup, open your browser to:

| Interface | URL | Description |
|-----------|-----|-------------|
| **Main UI** | http://localhost:4173 | Menu landing page with all features |
| **Voice** | http://localhost:4173/?view=voice | Real-time voice assistant |
| **API Docs** | http://localhost:8080/docs | Swagger/OpenAPI documentation |
| **Grafana** | http://localhost:3000 | Metrics and dashboards |

---

## Voice Service

KITTY includes a **hybrid voice system** with local-first processing and cloud fallback:

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Voice Service (:8400)                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐       ┌─────────────────────┐          │
│  │    STT (Speech)     │       │    TTS (Synthesis)  │          │
│  │  ┌───────────────┐  │       │  ┌───────────────┐  │          │
│  │  │ Local Whisper │◄─┼─Toggle─┼─►│  Local Piper  │  │          │
│  │  │   (base.en)   │  │       │  │ (amy/ryan)    │  │          │
│  │  └───────┬───────┘  │       │  └───────┬───────┘  │          │
│  │          │ Fallback │       │          │ Fallback │          │
│  │  ┌───────▼───────┐  │       │  ┌───────▼───────┐  │          │
│  │  │  OpenAI API   │  │       │  │  OpenAI TTS   │  │          │
│  │  │   Whisper     │  │       │  │   tts-1       │  │          │
│  │  └───────────────┘  │       │  └───────────────┘  │          │
│  └─────────────────────┘       └─────────────────────┘          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                   WebSocket Handler                          ││
│  │  Real-time audio streaming with sentence-level buffering    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Local Voice Models

**Speech-to-Text (Whisper.cpp)**
- Model: `base.en` (English-optimized, ~150MB)
- Location: `~/.cache/whisper/ggml-base.en.bin`
- Features: VAD, real-time transcription

**Text-to-Speech (Piper)**
- Models: `en_US-amy-medium` (female), `en_US-ryan-medium` (male)
- Location: `/Users/Shared/Coding/models/Piper/`
- Sample rate: 22050 Hz
- Voice mapping:
  - alloy, nova, shimmer → amy (female)
  - echo, fable, onyx → ryan (male)

### Voice Configuration

```bash
# Voice service
VOICE_BASE_URL=http://localhost:8400
VOICE_PREFER_LOCAL=true              # Use local models first
VOICE_DEFAULT_VOICE=alloy            # Default TTS voice
VOICE_SAMPLE_RATE=16000              # Audio sample rate

# Local Whisper STT
WHISPER_MODEL=base.en                # Model size (tiny, base, small, medium, large)
WHISPER_MODEL_PATH=                  # Optional custom path

# Local Piper TTS
PIPER_MODEL_DIR=/Users/Shared/Coding/models/Piper
OPENAI_TTS_MODEL=tts-1               # Cloud fallback model
```

### Starting Voice Service

```bash
# Start voice service standalone
./ops/scripts/start-voice-service.sh

# Stop voice service
./ops/scripts/stop-voice-service.sh

# Check voice status
curl http://localhost:8080/api/voice/status | jq .
```

### Voice API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/voice/status` | GET | Provider status (local/cloud availability) |
| `/api/voice/transcribe` | POST | Transcribe audio to text |
| `/api/voice/synthesize` | POST | Convert text to speech |
| `/api/voice/ws` | WebSocket | Real-time bidirectional streaming |
| `/api/voice/chat` | POST | Full voice chat (STT → LLM → TTS) |

---

## Web UI

### Menu Landing Page

The UI starts with a **Menu page** showing all available sections:

| Section | Icon | Description |
|---------|------|-------------|
| **Voice** | Microphone | Real-time voice assistant with STT/TTS |
| **Chat Shell** | Terminal | Text chat with function calling |
| **Projects** | Folder | CAD project management |
| **Fabrication** | Printer | Printer control and queue |
| **Vision Gallery** | Images | Reference image search |
| **Image Generator** | Palette | Stable Diffusion generation |
| **Research** | Magnifier | Autonomous research pipeline |
| **I/O Control** | Toggle | Feature and provider toggles |
| **Material Inventory** | Cube | Filament stock management |
| **Print Intelligence** | Chart | Success prediction dashboard |
| **Cameras** | Camera | Print monitoring feeds |
| **Autonomy** | Calendar | Weekly autonomous project scheduling |
| **Wall Terminal** | Display | Ambient status display |
| **Settings** | Gear | Bambu Labs, preferences, API config |

### Running the UI

```bash
cd services/ui

# Development mode (hot reload)
npm run dev --host 0.0.0.0 --port 4173

# Production build
npm run build
npm run preview
```

### UI Configuration

```env
KITTY_UI_BASE=http://localhost:4173      # UI base URL
VITE_API_BASE=http://localhost:8080      # Gateway API URL
```

---

## Command Reference

### Start/Stop KITTY

```bash
# Start everything (llama.cpp + Docker + Voice)
./ops/scripts/start-all.sh

# Stop everything
./ops/scripts/stop-all.sh

# Start only voice service
./ops/scripts/start-voice-service.sh

# Stop only voice service
./ops/scripts/stop-voice-service.sh

# Check service status
docker compose -f infra/compose/docker-compose.yml ps
```

### CLI Interface

```bash
# Install CLI (one-time)
pip install -e services/cli/

# Launch interactive shell
kitty-cli shell

# Inside the shell:
> /help                              # Show available commands
> /voice                             # Toggle voice mode
> /research <query>                  # Autonomous research
> /cad Create a hex box              # Generate CAD model
> /split /path/to/model.stl         # Split oversized model for printing
> /remember Ordered more PLA         # Save long-term note
> /memories PLA                      # Recall saved notes
> /vision gandalf rubber duck        # Search reference images
> /generate futuristic drone         # Generate SD image
> /collective council k=3 Compare... # Multi-agent collaboration
> /exit                              # Exit shell

# Quick one-off queries
kitty-cli say "What printers are online?"
kitty-cli say "Turn on bench lights"
```

### Unified Launcher TUI

```bash
# Install launcher (one-time)
pip install -e services/launcher/

# Launch unified control center
kitty

# TUI Shortcuts:
# k - Start KITTY stack
# x - Stop stack
# c - Launch CLI
# v - Launch Voice interface
# m - Launch Model Manager
# o - Open Web Console
# i - Launch I/O dashboard
# q - Quit
```

---

## Core Features

### Intelligent Routing

```
Query arrives → Local model (free, instant) → Confidence check
                                                    ↓
                          High confidence? ──→ Return answer
                                                    ↓
                          Low confidence? ──→ Escalate to cloud (budget gated)
```

### ReAct Agent with Tool Use

KITTY uses a **ReAct (Reasoning + Acting) agent** that can:
- **Reason** about complex multi-step tasks
- **Use tools** via Model Context Protocol (MCP)
- **Observe** results and adapt strategy
- **Iterate** until task completion

### Safety-First Design

- **Hazard workflows**: Two-step confirmation for dangerous operations
- **Command allow-lists**: Only pre-approved system commands execute
- **Audit logging**: Every tool use logged to PostgreSQL
- **Budget gates**: Cloud API calls require password confirmation

### CAD Generation

Generate 3D models from natural language:

```bash
kitty-cli cad "Create a phone stand with 45° angle and cable management"
```

**Providers** (automatic fallback):
1. Zoo API (parametric STEP)
2. Tripo (mesh STL/OBJ)
3. Local CadQuery (offline)
4. Local FreeCAD (offline)

### Print Queue

Multi-printer coordination with intelligent scheduling:

```bash
# List queue
./scripts/queue-cli.sh list

# Submit job
./scripts/queue-cli.sh submit /path/to/model.stl "bracket_v2" pla_black_esun 3

# Watch queue
./scripts/queue-cli.sh watch
```

**Supported Printers:**
- Bamboo Labs H2D (MQTT)
- Elegoo OrangeStorm Giga (Klipper)
- Snapmaker Artisan (UDP)
- Any OctoPrint/Moonraker instance

### Mesh Segmentation

Split oversized 3D models into printable parts (supports 3MF and STL):

```bash
# Via CLI
kitty-cli shell
> /split /path/to/large_model.3mf

# Via API
curl -X POST http://localhost:8300/api/segmentation/segment \
  -H "Content-Type: application/json" \
  -d '{"mesh_path": "/path/to/model.3mf", "printer_id": "bamboo_h2d"}'
```

**Features:**
- **3MF native**: Prefers 3MF input/output for slicer compatibility (STL also supported)
- **Automatic splitting**: Detects oversized models and splits into printer-fit parts
- **SDF hollowing**: Reduce material usage with configurable wall thickness
- **Alignment joints**: Dowel pin holes for accurate part assembly
- **3MF assembly output**: Single file with all parts, colors, and metadata
- **Configurable printers**: Load build volumes from `printer_config.yaml`

**Segmentation Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `printer_id` | Target printer for build volume | auto-detect |
| `enable_hollowing` | Enable SDF-based hollowing | `true` |
| `wall_thickness_mm` | Wall thickness for hollowing | `2.0` |
| `joint_type` | Joint type: `dowel`, `dovetail`, `pyramid`, `none` | `dowel` |
| `max_parts` | Maximum parts to generate | `10` |

**Interfaces:**
- **CLI**: `/split` command in kitty-cli shell
- **Voice**: "Split this model for printing"
- **Web UI**: MeshSegmenter component in Fabrication Console
- **API**: `POST /api/segmentation/segment` on Fabrication service

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Mac Studio M3 Ultra Host                            │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         Local AI Inference Layer                         │ │
│  │                                                                          │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                  Ollama (Primary Reasoner) :11434                   │ │ │
│  │  │                      GPT-OSS 120B (Thinking Mode)                   │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                          │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                  llama.cpp Servers (Metal GPU)                      │ │ │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │ │ │
│  │  │  │Q4 Tool   │ │F16 DEPR  │ │Vision    │ │Summary   │ │Coder     │ │ │ │
│  │  │  │:8083     │ │:8082     │ │:8086     │ │:8084     │ │:8087     │ │ │ │
│  │  │  │Athene V2 │ │(Fallback)│ │Gemma 27B │ │Hermes 8B │ │Qwen 32B  │ │ │ │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         Docker Compose Services                          │ │
│  │                                                                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────────┐│ │
│  │  │                        HAProxy :8080 (Load Balancer)                ││ │
│  │  └───────────────────────────────┬─────────────────────────────────────┘│ │
│  │                                  │                                       │ │
│  │  ┌───────────────────────────────▼─────────────────────────────────────┐│ │
│  │  │                         Gateway (x3 replicas)                       ││ │
│  │  │                    REST API, Auth, Routing, Proxy                   ││ │
│  │  └───────────────────────────────┬─────────────────────────────────────┘│ │
│  │                                  │                                       │ │
│  │  ┌───────────────────────────────▼─────────────────────────────────────┐│ │
│  │  │                          Brain :8000                                ││ │
│  │  │          Orchestrator • ReAct Agent • Research Pipeline             ││ │
│  │  └──┬────────┬────────┬────────┬────────┬────────┬────────┬───────────┘│ │
│  │     │        │        │        │        │        │        │             │ │
│  │  ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐            │ │
│  │  │ CAD │ │ Fab │ │Voice│ │Disc │ │Brok │ │Imgs │ │Mem0 │            │ │
│  │  │:8200│ │:8300│ │:8400│ │:8500│ │:8777│ │:8600│ │:8765│            │ │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘            │ │
│  │                                                                       │ │
│  │  ┌───────────────────────────────────────────────────────────────────┐│ │
│  │  │                    Storage & Infrastructure                       ││ │
│  │  │  PostgreSQL │ Redis │ Qdrant │ MinIO │ RabbitMQ │ Mosquitto      ││ │
│  │  └───────────────────────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                              Web UI :4173                                │ │
│  │  Menu │ Voice │ Shell │ Projects │ Fab │ Research │ Settings │ ...     │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────┘
                │                           │                    │
     ┌──────────▼──────────┐     ┌──────────▼──────────┐   ┌────▼────┐
     │    Home Assistant   │     │      3D Printers    │   │ Cameras │
     │    (MQTT + REST)    │     │  Bamboo │ Elegoo    │   │  (Pi)   │
     │  Lights, Climate,   │     │  Snapmaker │ Others │   │         │
     │  Sensors, Locks     │     │  (OctoPrint/Klipper)│   │         │
     └─────────────────────┘     └─────────────────────┘   └─────────┘
```

---

## Configuration

### Core Settings (.env)

```bash
# User & Safety
USER_NAME=YourName
KITTY_USER_NAME=YourName
HAZARD_CONFIRMATION_PHRASE="Confirm: proceed"
API_OVERRIDE_PASSWORD=omega

# Budget
BUDGET_PER_TASK_USD=0.50
CONFIDENCE_THRESHOLD=0.80
```

### AI Models

```bash
# Ollama (Primary Reasoner)
LOCAL_REASONER_PROVIDER=ollama
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_THINK=medium

# llama.cpp Q4 (Tool Orchestrator)
LLAMACPP_Q4_HOST=http://host.docker.internal:8083
LLAMACPP_Q4_MODEL=athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf
LLAMACPP_Q4_PORT=8083

# DEPRECATED: llama.cpp F16 (Legacy Fallback - only used when LOCAL_REASONER_PROVIDER=llamacpp)
# LLAMACPP_F16_HOST=http://host.docker.internal:8082
# LLAMACPP_F16_MODEL=llama-3-70b/Llama-3.3-70B-Instruct-F16/...gguf
# LLAMACPP_F16_PORT=8082

# Vision
LLAMACPP_VISION_MODEL=gemma-3-27b-it-GGUF/gemma-3-27b-it-q4_k_m.gguf
LLAMACPP_VISION_MMPROJ=gemma3_27b_mmproj/mmproj-model-f16.gguf
LLAMACPP_VISION_PORT=8086
```

### Semantic Tool Selection

KITTY uses **embedding-based semantic search** to intelligently select relevant tools for each query, reducing context usage by ~90% when many tools are available.

**How it works:**
1. Tool definitions are converted to text embeddings using `all-MiniLM-L6-v2` (384 dimensions)
2. Embeddings are cached in Redis for cluster-wide sharing
3. For each query, cosine similarity finds the most relevant tools
4. Only top-k matching tools are passed to the model (instead of all 50+)

**Benefits:**
- **Context savings**: ~90% reduction (e.g., 600 tokens vs 7,500 for 50 tools)
- **Better tool selection**: Semantic matching beats keyword heuristics
- **Cluster-ready**: Redis caching shares embeddings across nodes
- **Fast**: ~10-15ms per search after initial model load

```bash
# Semantic tool selection (default: enabled)
USE_SEMANTIC_TOOL_SELECTION=true
EMBEDDING_MODEL=all-MiniLM-L6-v2
TOOL_SEARCH_TOP_K=5
TOOL_SEARCH_THRESHOLD=0.3
```

**Disabling**: Set `USE_SEMANTIC_TOOL_SELECTION=false` to fall back to keyword-based selection.

### Parallel Agent Orchestration (Experimental)

KITTY supports **parallel multi-agent orchestration** for complex, multi-step goals. When enabled, complex queries are decomposed into parallelizable tasks executed concurrently across multiple specialized agents.

**Architecture:**

```
User Goal → Decompose (Q4) → Dependency Graph → Parallel Execute → Synthesize (GPTOSS)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
                [Task 1]       [Task 2]       [Task 3]
                researcher     cad_designer   fabricator
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                            Final Response
```

**Specialized Agents:**

| Agent | Primary Model | Purpose | Tool Allowlist |
|-------|---------------|---------|----------------|
| researcher | Q4 (Athene V2) | Web research, information gathering | web_search, fetch_webpage |
| reasoner | GPTOSS 120B | Deep analysis, chain-of-thought | (none - pure reasoning) |
| cad_designer | Q4 (Athene V2) | 3D model generation | generate_cad_model, image_search |
| fabricator | Q4 (Athene V2) | Print preparation, segmentation | fabrication.* |
| coder | Qwen 32B | Code generation, analysis | (all code tools) |
| vision_analyst | Gemma 27B | Image understanding | vision.*, camera.* |
| analyst | Q4 (Athene V2) | Memory search, data analysis | memory.* |
| summarizer | Hermes 8B | Response compression | (none - compression only) |

**Slot Allocation (20 concurrent slots):**

| Endpoint | Port | Model | Slots | Context |
|----------|------|-------|-------|---------|
| Q4 | 8083 | Athene V2 Q4 | 6 | 128K |
| GPTOSS | 11434 | GPT-OSS 120B | 2 | 65K |
| Vision | 8086 | Gemma 27B | 4 | 4K |
| Coder | 8087 | Qwen 32B | 4 | 32K |
| Summary | 8084 | Hermes 8B | 4 | 4K |

**Configuration:**

```bash
# Enable parallel agent orchestration
ENABLE_PARALLEL_AGENTS=false           # Master enable flag (disabled by default)
PARALLEL_AGENT_ROLLOUT_PERCENT=0       # Gradual rollout (0-100%)
PARALLEL_AGENT_MAX_TASKS=6             # Max tasks per execution
PARALLEL_AGENT_MAX_CONCURRENT=8        # Max concurrent slot usage
PARALLEL_AGENT_COMPLEXITY_THRESHOLD=0.6 # Query complexity threshold (0.0-1.0)

# Coder Server (for parallel agents)
LLAMACPP_CODER_ENABLED=true
LLAMACPP_CODER_HOST=http://localhost:8087
LLAMACPP_CODER_PORT=8087
LLAMACPP_CODER_CTX=32768
LLAMACPP_CODER_PARALLEL=4
```

**Performance Benefits:**

| Scenario | Sequential | Parallel | Improvement |
|----------|------------|----------|-------------|
| 3-task research | ~45s | ~15s | **3x faster** |
| 5-task CAD+fab | ~90s | ~25s | **3.6x faster** |
| GPU utilization | ~15% | ~60% | **4x better** |

**How it works:**

1. **Complexity Detection**: Queries are scored for complexity (keywords, length, multiple questions)
2. **Task Decomposition**: Q4 model breaks goal into independent parallelizable tasks with dependencies
3. **Slot Acquisition**: Tasks acquire slots with exponential backoff and fallback tiers
4. **Parallel Execution**: Independent tasks run concurrently via asyncio.gather()
5. **Synthesis**: GPTOSS 120B aggregates all task results into final response

**Enabling:**

```bash
# In .env
ENABLE_PARALLEL_AGENTS=true
PARALLEL_AGENT_ROLLOUT_PERCENT=100

# Restart llama.cpp servers to pick up increased Q4 slots
./ops/scripts/llama/restart.sh
```

### Voice Settings

```bash
# Voice service
VOICE_BASE_URL=http://localhost:8400
VOICE_PREFER_LOCAL=true
VOICE_DEFAULT_VOICE=alloy
VOICE_SAMPLE_RATE=16000

# Local STT (Whisper)
WHISPER_MODEL=base.en
WHISPER_MODEL_PATH=

# Local TTS (Piper)
PIPER_MODEL_DIR=/Users/Shared/Coding/models/Piper
OPENAI_TTS_MODEL=tts-1
```

### Cloud APIs (Optional)

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...
ZOO_API_KEY=your-zoo-key
TRIPO_API_KEY=your-tripo-key
```

### Integrations

```bash
# Home Assistant
HOME_ASSISTANT_TOKEN=your-long-lived-token

# Bambu Labs (via Settings page or .env)
# Configure through http://localhost:4173/?view=settings

# Database
DATABASE_URL=postgresql://kitty:changeme@postgres:5432/kitty
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## Troubleshooting

### Voice Service Issues

**Local STT not available:**
```bash
# Check Whisper model exists
ls ~/.cache/whisper/ggml-base.en.bin

# Download if missing
pip install whispercpp
# Model downloads automatically on first use
```

**Local TTS not available:**
```bash
# Check Piper models exist
ls /Users/Shared/Coding/models/Piper/*.onnx

# Download from: https://github.com/rhasspy/piper/releases
# Copy en_US-amy-medium.onnx and en_US-ryan-medium.onnx
```

**Check voice status:**
```bash
curl http://localhost:8080/api/voice/status | jq .
# Should show local_available: true for both stt and tts
```

### Services Not Starting

```bash
# Check Docker
docker ps

# View service logs
docker compose -f infra/compose/docker-compose.yml logs brain
tail -f .logs/llamacpp-q4.log

# Restart specific service
docker compose -f infra/compose/docker-compose.yml restart gateway
```

### UI Not Loading

```bash
# Rebuild and restart UI
cd services/ui
npm run build
npm run preview

# Check gateway proxy
curl http://localhost:8080/api/voice/status
```

---

## Roadmap

### Current Status (November 2025)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Core Foundation | ✅ Complete | Docker, llama.cpp, FastAPI, Home Assistant |
| Phase 2: Tool-Aware Agent | ✅ Complete | ReAct agent, MCP protocol, CAD generation |
| Phase 3: Autonomous Learning | ✅ Complete | Goal identification, research pipeline |
| Phase 3.5: Research Pipeline | ✅ Complete | 5-phase autonomous research, multi-model |
| Phase 4: Fabrication Intelligence | 🚧 90% | Voice service, dashboards, ML in progress |
| Phase 5: Safety & Access | 📋 Planned | UniFi Access, zone presence |

### Recent Additions (Phase 4.5)

- **Voice Service**: Local Whisper STT + Piper TTS with cloud fallback
- **Menu Landing Page**: Card-based navigation to all sections
- **Bambu Labs Integration**: Login/status via Settings page
- **Gateway Voice Proxy**: Full voice API proxying through gateway
- **Markdown Support**: UI renders formatted responses, TTS speaks clean text

---

## Project Stats

| Metric | Value |
|--------|-------|
| **Services** | 12 FastAPI microservices |
| **Docker Containers** | 20+ (including infrastructure) |
| **Local AI Models** | 6 (GPT-OSS 120B, Q4, F16, Vision, Summary, Coder) |
| **Voice Models** | 3 (Whisper base.en, Piper amy, Piper ryan) |
| **Cloud Providers** | 4 (OpenAI, Anthropic, Perplexity, Brave) |
| **UI Pages** | 16 (Menu, Voice, Shell, Projects, etc.) |
| **Supported Printers** | Bamboo Labs, Elegoo (Klipper), Snapmaker, OctoPrint |
| **Lines of Python** | 55,000+ |
| **Lines of TypeScript** | 18,000+ |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# Development setup
pip install -e ".[dev]"
pre-commit install

# Run tests
pytest tests/ -v

# Linting
ruff check services/ --fix
ruff format services/
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

KITTY stands on the shoulders of giants:

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)**: Local LLM inference
- **[Whisper.cpp](https://github.com/ggerganov/whisper.cpp)**: Local speech recognition
- **[Piper](https://github.com/rhasspy/piper)**: Local text-to-speech
- **[FastAPI](https://fastapi.tiangolo.com/)**: Python web framework
- **[Home Assistant](https://www.home-assistant.io/)**: Smart home integration
- **[Zoo](https://zoo.dev/)**: Parametric CAD API
- **[Qdrant](https://qdrant.tech/)**: Vector database

---

<p align="center">
  <i>Built with care for makers, by makers</i>
</p>

<p align="center">
  <sub>KITTY: Because your workshop deserves an AI assistant that actually understands "turn that thing on over there"</sub>
</p>
