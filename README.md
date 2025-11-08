# 🐱 KITTY: Your AI-Powered Fabrication Lab Assistant

> **K**nowledgeable **I**ntelligent **T**ool-using **T**abletop **Y**ielder
>
> An offline-first, voice-enabled warehouse orchestrator running on Mac Studio M3 Ultra. Think "JARVIS for your workshop" - but it actually works, runs locally, and won't spy on you.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/typescript-5.x-blue.svg" alt="TypeScript 5.x"/>
  <img src="https://img.shields.io/badge/platform-macOS_14+-lightgrey.svg" alt="macOS 14+"/>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"/>
</p>

---

## 🚀 Quick Command Reference

### 🎬 First Time Setup

**Option 1: TUI-First Workflow (Recommended)**

The easiest way to get started is using the Model Manager TUI to interactively select and start models:

```bash
# 1. Install Model Manager
pip install -e services/model-manager/

# 2. Launch TUI and select a model
kitty-model-manager tui
# Use arrow keys to browse models
# Press Enter to expand families and select models
# Press 's' to start the selected model

# 3. Start KITTY services (in a new terminal)
./ops/scripts/start-kitty-validated.sh
```

**Option 2: Auto-Bootstrap Workflow**

For automation or CI environments, configure models in `.env` for automatic startup:

```bash
# 1. Copy example configuration
cp .env.example .env

# 2. Edit .env to set model paths:
#    LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models
#    LLAMACPP_PRIMARY_MODEL=family/model.gguf

# 3. Start everything (auto-loads configured model)
./ops/scripts/start-kitty-validated.sh
```

> **Note**: If no model is configured and no server is running, the startup script will show helpful instructions.

---

### Start/Stop KITTY

```bash
# Start llama.cpp + all Docker services (validated startup)
./ops/scripts/start-kitty-validated.sh

# Quick start (legacy script, less validation)
./ops/scripts/start-kitty.sh

# Stop everything
./ops/scripts/stop-kitty.sh

# Only stop llama.cpp (leave Docker stack alone)
./ops/scripts/stop-llamacpp.sh

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
> /help                        # Show available commands
> /verbosity 3                 # Set response detail (1-5)
> /cad Create a hex box        # Generate CAD model
> /list                        # Show cached artifacts
> /queue 1 printer_01          # Queue artifact to printer
> /exit                        # Exit shell

# Quick one-off queries
kitty-cli say "What printers are online?"
kitty-cli say "Turn on bench lights"
```

### Unified Launcher TUI (Recommended!)

**The easiest way to manage KITTY** - single command interface with live system monitoring:

```bash
# Install Unified Launcher (one-time)
pip install -e services/launcher/

# Launch unified launcher - single command for everything
kitty

# TUI Features:
# h - Toggle system health status (Docker services, llama.cpp)
# d - Toggle detailed service list (all containers with ports)
# r - Toggle reasoning log viewer (watch AI thinking in real-time!)
# s - Show startup instructions
# m - Launch Model Manager (replaces launcher in same terminal)
# c - Launch CLI (validates health, replaces launcher in same terminal)
# q - Quit

# What you get:
# ✓ Real-time Docker service health monitoring
# ✓ llama.cpp server status with model info
# ✓ Live reasoning logs with tier distribution, confidence, costs
# ✓ Quick access to Model Manager and CLI
# ✓ Beautiful terminal UI with color coding
```

**Reasoning Log Viewer** (`r` key in launcher):
- Shows last 50 log entries with color coding by type
- Statistics: tier distribution, model usage, confidence scores
- Cost tracking across all routing decisions
- Auto-refreshes every 2 seconds
- Perfect for understanding how KITTY thinks and routes queries

### Model Manager TUI

```bash
# Install Model Manager (one-time)
pip install -e services/model-manager/

# Launch TUI interface
kitty-model-manager tui

# TUI Commands:
# s - Start server
# x - Stop server
# t - Restart server
# h - Check health
# m - Scan for models
# r - Refresh status
# q - Quit

# CLI Commands (non-interactive)
kitty-model-manager start              # Start llama.cpp server
kitty-model-manager stop               # Stop server
kitty-model-manager restart            # Restart server
kitty-model-manager status             # Show current status
kitty-model-manager scan               # Scan for available models
kitty-model-manager switch <model>     # Switch to different model
```

### Web Interfaces

```bash
# Access web interfaces (after starting KITTY)
open http://localhost:4173             # Main UI
open http://localhost:8080/docs        # API Documentation (Swagger)
open http://localhost:3000             # Grafana (metrics)
open http://localhost:9090             # Prometheus
open http://localhost:9001             # MinIO Console
```

### Development Commands

```bash
# Run tests
pytest tests/unit -v                   # Unit tests
pytest tests/integration -v            # Integration tests
pytest tests/e2e -v                    # End-to-end tests

# Linting and formatting
ruff check services/ --fix             # Auto-fix linting issues
ruff format services/                  # Format Python code
pre-commit run --all-files             # Run all pre-commit hooks

# Database migrations
alembic -c services/common/alembic.ini upgrade head    # Apply migrations
alembic -c services/common/alembic.ini current         # Show current version
```

### Useful Utility Commands

```bash
# View logs
docker compose -f infra/compose/docker-compose.yml logs brain      # Brain service logs
docker compose -f infra/compose/docker-compose.yml logs -f gateway # Follow gateway logs
tail -f .logs/llamacpp-q4.log                                      # Q4 server logs (Tool Orchestrator)
tail -f .logs/llamacpp-f16.log                                     # F16 server logs (Reasoning Engine)
tail -f .logs/llamacpp-dual.log                                    # Dual-server startup logs
# Stop llama.cpp servers if you launched them manually
./ops/scripts/stop-llamacpp-dual.sh

# Rebuild specific service
docker compose -f infra/compose/docker-compose.yml build --no-cache brain

# Generate admin password hash
python -c "from services.common.src.common.security import hash_password; print(hash_password('your-password'))"

# Discover Home Assistant instances
python ops/scripts/discover-homeassistant.py --all

# Benchmark llama.cpp performance
./ops/scripts/benchmark-llamacpp.sh

# Test CAD generation
./tests/test_cad_e2e.sh
```

---

## 🎯 What is KITTY?

KITTY transforms your Mac Studio into a conversational command center for your entire fabrication lab. It's like having a knowledgeable assistant who:

- **Talks to you** via voice (Whisper) or CLI/web interface
- **Thinks locally first** using llama.cpp with Metal GPU acceleration (70%+ queries handled offline)
- **Knows your tools** - integrates with 3D printers (OctoPrint/Klipper), smart home (Home Assistant), cameras (UniFi), and more
- **Generates CAD models** on demand using AI (Zoo API, Tripo, or local CadQuery/FreeCAD)
- **Manages fabrication workflows** from voice command through slicing, printing, and quality monitoring
- **Stays safe** with built-in hazard workflows, confirmation phrases, and audit logging
- **Keeps learning** with semantic memory storage and citation-tracked research capabilities

### Why "Offline-First"?

Because the internet goes down, APIs get expensive, and your workshop shouldn't stop working when AWS has a bad day. KITTY runs powerful local models (Qwen2.5, Llama, Gemma) on your Mac's Metal GPU and only escalates to cloud providers (OpenAI, Anthropic, Perplexity) when truly necessary.

---

## ✨ Key Features

### 🗣️ **Conversational Control**

```bash
You: "Turn on the bench lights and preheat the Prusa to 210°C"
KITTY: *executes via Home Assistant and OctoPrint*
      "Bench lights are on. Prusa preheating to 210°C for PLA."

You: "Generate a parametric hex storage box, 50mm wide"
KITTY: *calls Zoo CAD API*
      "Generated! Preview ready. Want me to queue it for printing?"
```

### 🧠 **Intelligent Routing**

```
┌─────────────────────────────────────────────────────┐
│  Your Query                                         │
└──────────────────┬──────────────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │  Brain Router      │
         │  (Confidence-Based)│
         └─────────┬──────────┘
                   │
        ┌──────────┴───────────┐
        │                      │
┌───────▼────────┐   ┌─────────▼─────────┐
│ Local Model    │   │  Cloud APIs       │
│ (Qwen2.5/Llama)│   │  (GPT/Claude/     │
│ 70%+ of queries│   │   Perplexity)     │
│ FREE           │   │  30%- queries     │
└────────────────┘   │  BUDGET GATED     │
                     └───────────────────┘
```

**Smart routing features:**
- Confidence-based escalation (local model runs first)
- Semantic caching (Redis) to avoid redundant LLM calls
- Budget tracking with "omega" password gate for expensive APIs
- Cost estimation before every cloud call
- Prometheus metrics for hit rate, latency, and costs

### 🛠️ **ReAct Agent with Tool Use**

KITTY uses a **ReAct (Reasoning + Acting) agent** that can:

- **Reason** about complex multi-step tasks
- **Use tools** via Model Context Protocol (MCP) servers:
  - 🏠 **Home Assistant**: Control lights, locks, sensors, climate
  - 🖨️ **CAD Generation**: Create 3D models with Zoo/Tripo/local tools
  - 🧠 **Memory**: Store and recall semantic memories (Qdrant vector DB)
  - 🔧 **Command Broker**: Execute system commands (with allow-list safety)
  - 🔍 **Web Research**: Search DuckDuckGo, fetch pages, track citations
- **Observe** results and adapt its strategy
- **Iterate** until task completion (max 10 reasoning steps)

**Example agent workflow:**
```
Query: "Research best PLA filament brands and create a comparison table"

Step 1: [Thought] Need to search for PLA filament reviews
        [Action] web_search("best PLA filament brands 2024")
        [Observation] Found 8 results from 3DPrintingToday, All3DP, etc.

Step 2: [Thought] Need detailed info on top brands
        [Action] fetch_webpage("https://all3dp.com/best-pla-filament")
        [Observation] Content retrieved, citation added

Step 3: [Thought] Need more sources for comparison
        [Action] fetch_webpage("https://3dprintingtoday.com/pla-guide")
        [Observation] Content retrieved, citation added

Step 4: [Thought] Have enough data, create comparison
        [Action] None
        [Answer] "Here's a comparison of top PLA brands..."
        [Citations] Markdown-formatted sources with access dates
```

### 🔐 **Safety-First Design**

- **Hazard workflows**: Two-step confirmation for dangerous operations (e.g., unlocking doors)
- **Command allow-lists**: Only pre-approved system commands can execute
- **Audit logging**: Every tool use logged to PostgreSQL with timestamps
- **Budget gates**: Cloud API calls require password confirmation
- **Zone presence**: UniFi Access integration for physical safety zones

### 📦 **CAD AI Cycling**

Generate 3D models from natural language using multiple AI providers:

```bash
kitty-cli cad "Create a phone stand with 45° angle and cable management"
```

**Providers** (automatic fallback chain):
1. **Zoo API** (parametric, produces STEP files)
2. **Tripo** (mesh generation, produces STL/OBJ)
3. **Local CadQuery** (Python-based parametric, offline fallback)
4. **Local FreeCAD** (offline fallback with scripting)

**Features:**
- Artifact storage in MinIO (S3-compatible)
- Metadata tracking (prompts, parameters, lineage)
- Visual previews in web UI
- One-click queue to OctoPrint/Klipper

### 🎤 **Voice-to-Print Pipeline**

End-to-end fabrication from voice command:

```
 [1]          [2]         [3]         [4]         [5]
Voice    →  Whisper  →  GPT-4   →   CAD AI  →  Slicer  →  OctoPrint
Command     (STT)     (Intent)   (Generate)   (Auto)     (Queue)
             ↓
          "Create     Parse to    Zoo/Tripo   PrusaSlicer  Print
           a desk     structured  generates   with preset   starts!
           organizer" CAD params  STEP file   profile
```

**Safety gates:**
- Confirmation prompts via Piper TTS
- Preview generation before printing
- Material/printer compatibility checks

### 📊 **Observability & Metrics**

**Prometheus + Grafana dashboards:**
- Routing tier distribution (local vs cloud)
- Response latency (P50, P95, P99)
- Cost tracking per provider
- Semantic cache hit rate
- Tool execution statistics
- Print job monitoring

**Logs:**
- Structured JSON via Python logging
- Q4 server logs in `.logs/llamacpp-q4.log`
- F16 server logs in `.logs/llamacpp-f16.log`
- Dual-server startup logs in `.logs/llamacpp-dual.log`
- Routing decisions with confidence scores
- Tool use audit trail in PostgreSQL

---

## 🚀 Quick Start

### Prerequisites

- **Hardware**: Mac Studio M3 Ultra recommended (64GB+ RAM for large models)
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

# Edit .env with your settings:
# - Model paths (LLAMACPP_PRIMARY_MODEL, LLAMACPP_CODER_MODEL)
# - API keys (optional: OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
# - Home Assistant URL and token
# - Safety phrases and user name

# Generate admin password hash
python -c "from services.common.src.common.security import hash_password; print(hash_password('your-password-here'))"
# Add to .env: ADMIN_USERS=admin:<hash>
```

### Download Models

KITTY works best with local GGUF models. Recommended setup:

```bash
# Create models directory
mkdir -p /Users/Shared/Coding/models

# Download Qwen2.5-72B-Instruct (recommended for primary)
huggingface-cli download Qwen/Qwen2.5-72B-Instruct-GGUF \
  --local-dir /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-GGUF \
  --include "*q4_k_m.gguf"

# Download Qwen2.5-Coder-32B (recommended for code tasks)
huggingface-cli download Qwen/Qwen2.5-Coder-32B-Instruct-GGUF \
  --local-dir /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF \
  --include "*q4_k_m.gguf"

# Update .env with your chosen models:
# LLAMACPP_PRIMARY_MODEL=Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q4_k_m.gguf
# LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf
```

**Alternative models:**
- Llama 3.3 70B (great general purpose)
- Gemma 2 27B (fast, efficient)
- Mistral 7B (lightweight for testing)

### Launch KITTY

```bash
# Start llama.cpp + Docker services
./ops/scripts/start-kitty.sh

# (First run only) Apply database migrations
alembic -c services/common/alembic.ini upgrade head
```

That's it! KITTY is now running. Press `Ctrl+C` to stop, or run `./ops/scripts/stop-kitty.sh`.

---

## 🎮 Using KITTY

### Web Interface

Open your browser to:

- **UI**: http://localhost:4173
- **API Docs**: http://localhost:8080/docs (Swagger/OpenAPI)
- **Grafana**: http://localhost:3000 (metrics and dashboards)

**Features:**
- Chat interface with model selection
- CAD generation with visual preview
- Fabrication console (printer status, queue management)
- Verbosity control (1-5 levels)
- Real-time streaming responses

### CLI (SSH-Friendly)

```bash
# Install CLI tool (one-time)
pip install -e services/cli

# Interactive shell
kitty-cli shell

# Inside the shell:
> /model kitty-coder           # Switch to coder model
> /verbosity 3                  # Set response detail level
> What printers are available?
> /cad Create a 50mm hex box
> /queue 0 prusa-mk4            # Queue artifact #0 to printer
> /exit

# Quick one-off queries
kitty-cli say "Turn on bench lights"
kitty-cli say "What's the print queue status?"
```

### Voice Control

```bash
# Voice service runs automatically with Docker Compose
# Transcripts sent to /api/voice/transcript endpoint

# Example voice commands:
"KITTY, turn on the bench lights"
"Generate a phone stand with cable routing"
"What's the status of the Prusa printer?"
"Preheat the hotend to 210 degrees"
```

### REST API

```bash
# Chat query
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What printers are online?", "verbosity": 3}'

# Generate CAD
curl -X POST http://localhost:8080/api/cad/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "hex storage box 50mm", "provider": "zoo"}'

# Control device (via Home Assistant)
curl -X POST http://localhost:8080/api/device/light.bench/command \
  -H "Content-Type: application/json" \
  -d '{"command": "turn_on"}'

# Get routing logs
curl http://localhost:8080/api/routing/logs
```

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Mac Studio Host                         │
│  ┌───────────────────────────────┐  ┌──────────────────┐   │
│  │ Dual llama.cpp Servers        │  │ Docker Compose   │   │
│  │ (Metal GPU + CPU Hybrid)      │◄─┤ Services         │   │
│  │                               │  │                  │   │
│  │ ┌──────────┐  ┌─────────────┐│  │ ┌──────────┐    │   │
│  │ │Q4 Server │  │ F16 Server  ││  │ │ Gateway  │    │   │
│  │ │Tool      │  │ Reasoning   ││  │ │  (REST)  │    │   │
│  │ │Calling   │  │ Engine      ││  │ └────┬─────┘    │   │
│  │ │Port 8083 │  │ Port 8082   ││  │      │          │   │
│  │ └──────────┘  └─────────────┘│  │ ┌────▼─────┐    │   │
│  │ • 35 GPU layers (Q4)          │  │ │  Brain   │    │   │
│  │ • 30 GPU layers (F16)         │  │ │ (Router) │    │   │
│  │ • 24 P-cores shared           │  │ └────┬─────┘    │   │
│  └───────────────────────────────┘  │      │          │   │
│                                      │ ┌────▼─────┐    │   │
│  ┌──────────────┐                   │ │ ReAct    │    │   │
│  │ Whisper.cpp  │                   │ │ Agent    │    │   │
│  │ (Voice STT)  │                   │ └────┬─────┘    │   │
│  └──────────────┘                   │      │          │   │
│                                      │ ┌────▼─────┐    │   │
│                                      │ │   MCP    │    │   │
│                                      │ │ Servers  │    │   │
│                                      │ └────┬─────┘    │   │
│                                      │      │          │   │
│                                      │ ┌────▼───────┐  │   │
│                                      │ │  CAD │ Fab │  │   │
│                                      │ │Voice │ UI  │  │   │
│                                      │ │Safety│Mem  │  │   │
│                                      │ └────────────┘  │   │
│                                      └──────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Storage Layer                          │  │
│  │  • PostgreSQL (audit logs, state)                   │  │
│  │  • Redis (semantic cache, routing state)            │  │
│  │  • Qdrant (vector embeddings for memory)            │  │
│  │  • MinIO (CAD artifacts, S3-compatible)             │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
              │                           │
              │                           │
         ┌────▼────┐              ┌───────▼────────┐
         │  Home   │              │   OctoPrint    │
         │Assistant│              │   Printers     │
         │ (MQTT)  │              │  (REST/MQTT)   │
         └─────────┘              └────────────────┘
```

### Service Breakdown

| Service | Purpose | Tech Stack |
|---------|---------|------------|
| **Gateway** | REST ingress, auth, request aggregation | FastAPI, JWT auth |
| **Brain** | Orchestrator, routing logic, ReAct agent | FastAPI, llama.cpp client |
| **CAD** | Model generation, artifact storage | FastAPI, Zoo SDK, Tripo API |
| **Fabrication** | Printer integration, CV monitoring | FastAPI, OctoPrint API |
| **Safety** | Hazard workflows, policy engine | FastAPI, PostgreSQL |
| **Voice** | Speech capture, NLP parsing | FastAPI, Whisper |
| **UI** | Web console (PWA) | React, TypeScript, Vite |
| **CLI** | Terminal interface | Python Click |
| **MCP Servers** | Tool protocol for agent | Custom MCP implementation |
| **Research** | Web search, citation tracking | DuckDuckGo, BeautifulSoup |
| **Memory** | Semantic storage & recall | Qdrant, sentence-transformers |

### MCP (Model Context Protocol) Servers

KITTY implements custom MCP servers to expose tools to the ReAct agent:

1. **CAD MCP Server**: `generate_cad_model` tool
2. **Home Assistant MCP Server**: `control_device`, `get_entity_state`, `list_entities`
3. **Memory MCP Server**: `store_memory`, `recall_memory`
4. **Broker MCP Server**: `execute_command`, `list_commands`
5. **Research MCP Server**: `web_search`, `fetch_webpage`, `get_citations`

Each server follows a consistent pattern:
- JSON Schema tool definitions
- Async tool execution
- Structured result objects
- Safety classification (free/cloud/hazardous)

---

## 📚 Documentation

### Essential Reading

- **[Quick Start Guide](specs/001-KITTY/quickstart.md)**: Get KITTY running in 10 minutes
- **[Implementation Plan](specs/001-KITTY/plan.md)**: Full technical specification
- **[Data Model](specs/001-KITTY/data-model.md)**: Database schemas and relationships
- **[API Contracts](specs/001-KITTY/contracts/)**: REST endpoint specifications

### Operational Guides

- **[Deployment Checklist](ops/runbooks/deployment-checklist.md)**: Production readiness steps
- **[Security Hardening](ops/runbooks/security-hardening.md)**: Safety configurations
- **[Troubleshooting](docs/troubleshooting.md)**: Common issues and solutions

### Developer Resources

- **[Architecture Overview](docs/architecture.md)**: System design deep dive
- **[Contributing Guide](CONTRIBUTING.md)**: How to contribute code
- **[Testing Strategy](tests/README.md)**: Unit, integration, and E2E tests

---

## 🔧 Configuration

KITTY is configured via the `.env` file. Key settings:

### Core Settings

```bash
# User & Safety
USER_NAME=YourName
HAZARD_CONFIRMATION_PHRASE=alpha-omega-protocol
ADMIN_USERS=admin:$2b$12$...bcrypt.hash...

# Local Models
LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models
LLAMACPP_PRIMARY_MODEL=Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q4_k_m.gguf
LLAMACPP_PRIMARY_ALIAS=kitty-primary
LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf
LLAMACPP_CODER_ALIAS=kitty-coder

# Dual-Model Architecture (Q4 Tool Orchestrator + F16 Reasoning Engine)
LLAMACPP_Q4_MODEL=llama-3-70b/Llama-3.3-70B-Instruct-UD-Q4_K_XL.gguf
LLAMACPP_Q4_PORT=8083
LLAMACPP_Q4_N_GPU_LAYERS=35      # Hybrid: 35 layers to GPU, rest to CPU
LLAMACPP_Q4_THREADS=24           # M3 Ultra has 24 P-cores (not 20!)
LLAMACPP_Q4_PARALLEL=4           # Concurrent sequences for tool calling

LLAMACPP_F16_MODEL=llama-3-70b/Llama-3.3-70B-Instruct-F16/Llama-3.3-70B-Instruct-F16-00001-of-00004.gguf
LLAMACPP_F16_PORT=8082
LLAMACPP_F16_N_GPU_LAYERS=30     # Hybrid: 30 layers to GPU (memory-intensive)
LLAMACPP_F16_THREADS=24          # Shared P-cores with Q4
LLAMACPP_F16_PARALLEL=2          # Lower concurrency for deep reasoning

# GPU/CPU Hybrid Benefits: 20-40% throughput increase by utilizing both
# Research: Research/GPUandCPU.md

# Cloud APIs (optional)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
PERPLEXITY_API_KEY=pplx-...
API_OVERRIDE_PASSWORD=omega      # Required to use cloud APIs

# Budget Control
BUDGET_PER_TASK_USD=0.50         # Max spend per conversation
CONFIDENCE_THRESHOLD=0.85        # When to escalate to cloud
```

### Integration Settings

```bash
# Home Assistant
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your-long-lived-token

# OctoPrint
OCTOPRINT_URL=http://octopi.local
OCTOPRINT_API_KEY=your-api-key

# CAD Providers
ZOO_API_KEY=your-zoo-key          # Optional
TRIPO_API_KEY=your-tripo-key      # Optional

# UniFi (for cameras/access)
UNIFI_URL=https://unifi.local
UNIFI_USERNAME=admin
UNIFI_PASSWORD=...
```

### Performance Tuning

```bash
# Routing
SEMANTIC_CACHE_TTL=3600          # Cache duration (seconds)
MAX_TOKENS_LOCAL=4096            # Token limit for local models
MAX_TOKENS_CLOUD=8192            # Token limit for cloud models

# Observability
VERBOSITY_DEFAULT=3              # 1-5 response detail level
LOG_LEVEL=INFO                   # DEBUG, INFO, WARNING, ERROR
PROMETHEUS_ENABLED=true
```

---

## 🧪 Testing

### Run Test Suite

```bash
# Unit tests
pytest tests/unit -v

# Integration tests (requires running services)
pytest tests/integration -v

# End-to-end tests
pytest tests/e2e -v

# Specific test module
pytest tests/unit/test_router.py -v
```

### Test Coverage

```bash
pytest tests/ --cov=services --cov-report=html
open htmlcov/index.html
```

### Manual Testing

```bash
# Test CAD generation
./tests/test_kitty_cad.sh

# Benchmark llama.cpp performance
./ops/scripts/benchmark-llamacpp.sh

# Test Home Assistant integration
curl http://localhost:8080/api/device/light.bench/state
```

---

## 🎨 Customization

### Adding New MCP Tools

Create a new MCP server in `services/mcp/src/mcp/servers/`:

```python
from ..server import MCPServer, ToolDefinition, ToolResult

class CustomMCPServer(MCPServer):
    def __init__(self):
        super().__init__(name="custom", description="My custom tools")
        self._register_tools()

    def _register_tools(self):
        self.register_tool(
            ToolDefinition(
                name="my_tool",
                description="What my tool does",
                parameters={
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "..."}
                    },
                    "required": ["param1"]
                }
            )
        )

    async def execute_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        if tool_name == "my_tool":
            # Your tool logic here
            return ToolResult(success=True, data={"result": "..."})
```

Register it in `services/brain/src/brain/tools/mcp_client.py`:

```python
from mcp import CustomMCPServer

self._servers["custom"] = CustomMCPServer()
```

### Adding New Voice Commands

Extend the voice parser in `services/voice/src/voice/parser.py`:

```python
def parse_voice_command(transcript: str) -> dict:
    if "new command pattern" in transcript.lower():
        return {
            "intent": "new_intent",
            "params": {...}
        }
```

### Customizing System Prompts

Edit `services/brain/src/brain/config/prompts.py`:

```python
KITTY_SYSTEM_PROMPT = """
You are KITTY, a helpful AI assistant for {user_name}'s fabrication lab.
[Your custom personality and instructions here]
"""
```

---

## 🐛 Troubleshooting

### Common Issues

**Issue**: `llama.cpp` won't start

```bash
# Check if models exist
ls -lh /Users/Shared/Coding/models/

# Verify llama-server binary
which llama-server

# Check logs
tail -f .logs/llamacpp.log
```

**Issue**: Docker services won't start

```bash
# Check Docker Desktop is running
docker ps

# View service logs
docker compose -f infra/compose/docker-compose.yml logs brain

# Rebuild specific service
docker compose -f infra/compose/docker-compose.yml build --no-cache brain
```

**Issue**: "Permission denied" for cloud APIs

```bash
# Cloud APIs require the omega password (configured in .env)
# When prompted, enter the API_OVERRIDE_PASSWORD value
```

**Issue**: CLI returns HTTP errors

```bash
# Ensure services are running
docker compose -f infra/compose/docker-compose.yml ps

# Test endpoints
curl http://localhost:8080/healthz

# Check if gateway is accessible
curl http://localhost:4000/health
```

**Issue**: Voice transcription not working

```bash
# Check voice service logs
docker compose logs voice

# Verify Whisper model downloaded
ls ~/.cache/whisper/

# Test transcript endpoint
curl -X POST http://localhost:8080/api/voice/transcript \
  -H "Content-Type: application/json" \
  -d '{"text": "test command"}'
```

### Getting Help

- **Documentation**: Check `docs/` and `specs/001-KITTY/`
- **Issues**: https://github.com/yourusername/KITT/issues
- **Discussions**: https://github.com/yourusername/KITT/discussions

---

## 🗺️ Roadmap

### Phase 1: Core Foundation ✅ COMPLETE
- [x] Docker Compose orchestration
- [x] llama.cpp integration with Metal GPU
- [x] FastAPI services (gateway, brain, CAD)
- [x] Home Assistant integration
- [x] Confidence-based routing

### Phase 2: Tool-Aware Agent ✅ COMPLETE
- [x] ReAct agent implementation
- [x] MCP server protocol
- [x] Safe tool executor with hazard workflows
- [x] CAD generation (Zoo/Tripo/local)
- [x] Command broker with allow-lists
- [x] Web research with citation tracking

### Phase 3: Voice & Fabrication 🚧 IN PROGRESS
- [ ] Voice-to-print pipeline
- [ ] OctoPrint/Klipper integration
- [ ] UniFi camera CV monitoring
- [ ] Print queue management
- [ ] Slicer automation

### Phase 4: Safety & Access 📋 PLANNED
- [ ] UniFi Access integration
- [ ] Zone presence detection
- [ ] Enhanced hazard workflows
- [ ] Multi-factor confirmation
- [ ] Audit dashboard

### Phase 5: Advanced Features 📋 PLANNED
- [ ] Multi-user support
- [ ] Role-based access control
- [ ] Advanced observability (Loki, Tempo)
- [ ] Mobile app (iOS/Android)
- [ ] Offline CAD model training

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** (following the existing code style)
4. **Run tests**: `pytest tests/ -v`
5. **Run linters**: `pre-commit run --all-files`
6. **Commit**: `git commit -m "feat: add amazing feature"`
7. **Push**: `git push origin feature/amazing-feature`
8. **Open a Pull Request**

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run formatter
black services/
ruff check services/ --fix

# Run type checker
mypy services/
```

### Code Style

- **Python**: Follow PEP 8, use Black formatter, type hints required
- **TypeScript**: Use Prettier, ESLint rules enforced
- **Commits**: Use [Conventional Commits](https://www.conventionalcommits.org/)
- **Documentation**: Update relevant docs with code changes

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

KITTY stands on the shoulders of giants:

- **[llama.cpp](https://github.com/ggerganov/llama.cpp)**: Incredible local LLM inference
- **[Qwen Team](https://github.com/QwenLM)**: Outstanding open-weight models
- **[FastAPI](https://fastapi.tiangolo.com/)**: Modern Python web framework
- **[Home Assistant](https://www.home-assistant.io/)**: Smart home integration
- **[OctoPrint](https://octoprint.org/)**: 3D printer management
- **[Zoo](https://zoo.dev/)**: Parametric CAD API
- **[Qdrant](https://qdrant.tech/)**: Vector database for semantic memory

---

## 💬 Philosophy

KITTY is built on these principles:

1. **Offline-First**: Your workshop shouldn't depend on the cloud
2. **Safety-First**: Dangerous operations require explicit confirmation
3. **Privacy-First**: Your conversations stay on your hardware
4. **Cost-Conscious**: Cloud APIs are expensive; use them sparingly
5. **Tool-Neutral**: Multiple providers for every capability
6. **Open**: Fully inspectable, modifiable, and extensible

---

<p align="center">
  <i>Built with ❤️ for makers, by makers</i>
</p>

<p align="center">
  <sub>KITTY: Because your workshop deserves an AI assistant that actually understands "turn that thing on over there"</sub>
</p>
