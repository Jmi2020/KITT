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

## 🎯 Vision: A Maker Space for Technical AI

I want to build a maker space purpose-built for technical AI: a place where models such as Claude, GPT-5, Llama, Qwen, and Mistral can run research and directly control fabrication hardware. The core will be a cluster of Mac Studios providing energy-efficient, reliable compute and a secure network interface to the devices we care about most — primarily 3D printers, but also CNC machines, test rigs, and sensing equipment.

This environment will let models investigate materials, estimate production costs, run simulations, and then orchestrate fabrication steps. By combining on-device processing with curated research pipelines, we can shorten the loop from idea to physical prototype. The facility will prioritize sustainable, ethically sourced materials and robotic procurement workflows that reduce supply-chain impacts and improve repeatability.

KITTY will serve as the orchestration layer: lightweight processes that can spin up for a single query and spin down when finished, or remain active for deeper, after-hours projects. A practical starting cadence could be one KITTY-owned project per week, giving it controlled access to printers, inventories, and simulation resources so it can propose, prototype, and iterate. Let's give KITTY the tools and permissions it needs to thrive and to create useful, verifiable improvements for humans and machines alike.

> 📖 **Full Vision & Roadmap**: See [Reference/NorthStar/ProjectVision.md](Reference/NorthStar/ProjectVision.md) for the complete multi-phase implementation plan.

---

## 🚀 Quick Command Reference

### 🎬 First Time Setup

#### Understanding the Startup Order

KITTY uses a layered architecture that must start in a specific order:

```
1. llama.cpp Servers (Dual-Model)
   ├─ Q4 Model (Port 8083) - Athene V2 Agent (Tool Orchestrator)
   └─ F16 Model (Port 8082) - Llama 3.3 70B (Deep Reasoning)
                    ↓
2. Docker Services
   ├─ Brain (Port 8000) - Routes queries to llama.cpp
   ├─ Gateway (Port 8080) - Public API
   ├─ CAD, Fabrication, Safety, etc.
   └─ PostgreSQL, Redis, Prometheus, etc.
                    ↓
3. User Interfaces
   ├─ kitty-cli - Command line interface
   ├─ Web UI (Port 4173)
   └─ Voice interface
```

**The Easy Way** - `./ops/scripts/start-kitty-validated.sh` handles this entire sequence automatically:
1. Checks for running llama.cpp servers (or starts them if configured in `.env`)
2. Starts all Docker services
3. Validates health of each component
4. Shows you what's ready and where to access it

---

#### Step-by-Step Startup Guide

**Automated Startup (Recommended)**

```bash
# 1. Copy and configure .env
cp .env.example .env

# 2. Edit .env to set dual-model configuration:
#    LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models
#    LLAMACPP_Q4_MODEL=athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf
#    LLAMACPP_F16_MODEL=llama-3-70b/Llama-3.3-70B-Instruct-F16/...gguf

# 3. Start everything with validated startup script
./ops/scripts/start-kitty-validated.sh
# This automatically:
# ✓ Starts Q4 llama.cpp server (port 8083)
# ✓ Starts F16 llama.cpp server (port 8082)
# ✓ Waits for both to be healthy
# ✓ Starts all Docker services
# ✓ Validates each service
# ✓ Shows you access points and log locations
```

**Manual Startup (Advanced)**

If you want more control over the startup process:

```bash
# Step 1: Start llama.cpp dual-model servers FIRST
./ops/scripts/start-llamacpp-dual.sh
# Wait for both servers to be ready (check .logs/llamacpp-q4.log and .logs/llamacpp-f16.log)

# Step 2: Start Docker services (they connect to llama.cpp)
docker compose -f infra/compose/docker-compose.yml up -d --build

# Step 3: Wait for services to be healthy
docker compose -f infra/compose/docker-compose.yml ps

# Step 4: Use KITTY interfaces
kitty-cli shell
```

**Alternative: TUI Model Manager Workflow**

For interactive model selection without editing `.env`:

```bash
# 1. Install Model Manager
pip install -e services/model-manager/

# 2. Launch TUI and select models
kitty-model-manager tui
# Use arrow keys to browse available models
# Press 's' to start the dual-model servers

# 3. Start Docker services (in a new terminal)
docker compose -f infra/compose/docker-compose.yml up -d --build
```

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

# Optional: Hermes 3 summary server (q4) boots automatically from the same script.
# Toggle with LLAMACPP_SUMMARY_ENABLED=0 or point LLAMACPP_SUMMARY_MODEL to another GGUF.

# Capture a memory baseline (writes to .logs/memory/…)
./ops/scripts/memory-snapshot.sh

# Inspect/clean stray llama.cpp listeners (add --kill to terminate unexpected ones)
./ops/scripts/llamacpp-watchdog.sh
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
> /remember Ordered more PLA   # Save a long-term note
> /memories PLA                # Recall saved notes (optional query)
> /usage 5                     # Monitor paid provider usage (refresh every 5s)
> /reset                       # Start a fresh conversation/session
> /exit                        # Exit shell

# Quick one-off queries
kitty-cli say "What printers are online?"
kitty-cli say "Turn on bench lights"

# Monitor paid usage / provider cost
kitty-cli usage
kitty-cli usage --refresh 5
```

> **Long-running prompts**: Some research-heavy queries (multi-stage web extractions) can take several minutes. The CLI now waits up to 900 s by default (`KITTY_CLI_TIMEOUT`). Raise this env var if you need even longer windows.
>
> **Hermes summaries**: When Athene/ReAct responses get lengthy, a dedicated Hermes 3 (kitty-summary) server now rewrites the result + agent trace into a tight brief so the CLI doesn’t truncate key facts. Disable with `HERMES_SUMMARY_ENABLED=0` or view the original text via routing metadata.

**Memory hygiene:** capture a baseline after each reboot with `./ops/scripts/memory-snapshot.sh`, and if anything feels sluggish run `./ops/scripts/llamacpp-watchdog.sh --kill` to make sure only the expected llama.cpp listeners (kitty-q4 / kitty-f16 / kitty-summary) remain. The watchdog logs to `.logs/llamacpp-watchdog.log`, so you can correlate unexpected restarts with lingering processes.

#### Interactive CLI + Tool Routing

The CLI now mirrors the full ReAct stack that KITTY uses internally:

- `kitty-cli shell` keeps state (conversation id, verbosity, trace/agent toggles).
- `/trace` (or `kitty-cli say --trace "...")` streams the ReAct chain-of-thought plus tool calls.
- `/agent` (or `--agent/--no-agent`) enables the Athene V2 Q4 orchestrator so KITTY can call tools such as `web_search`, `generate_cad`, or delegate to the F16 reasoning model.
- `/remember <note>` stores highlights (preferences, project context, TODOs) in the Memory MCP server so you don’t need to keep entire transcripts in the prompt. `/memories [query]` searches those notes, and `/reset` rotates the conversation ID so llama.cpp always starts from a fresh context.
- **Paid providers (Perplexity MCP, OpenAI/Anthropic frontier)** now require the override keyword (default: `omega`) to be included in your prompt. Without it, KITTY will stay on free/local tools even if confidence is low. Example: `omega what's the latest CPI reading?`
- When agent mode is **off** (default), you get a direct llama.cpp answer. Turn it **on** for live research, CAD, or device orchestration.
- Prompts now include the current UTC timestamp, and if you mention “today/current/latest,” KITTY auto-marks the request as time-sensitive so the agent knows to hit `web_search` (or other MCP tools) instead of trusting stale training data.

Under the hood:

1. The CLI includes a compact system prompt + `<user_query>` wrapper whenever tools are passed to kitty-q4 (port 8083). That keeps prompts under 2k tokens, so tool instructions don’t get lost.
2. `brain.routing.tool_registry` auto-enables the entire toolset when the prompt implies “fresh data” (latest/price/news/etc.). Those heuristics also set `freshness_required=True`, so routing will escalate beyond cached local responses.
3. Parsed tool calls are delivered as dataclasses; `_execute_tools` now accepts both dicts and dataclasses, logs each invocation, and forwards results into the follow-up completion.
4. Successful tool runs (e.g., Perplexity web search) return structured answers which the ReAct agent summarizes back through kitty-q4/F16 before reaching the CLI.

**Example workflow**

```
> /trace
Trace mode enabled (verbosity forced to >=4)

> /agent on
Agent mode enabled

> perform a web search to find the best tacos in Seattle
# Trace shows kitty-q4 invoking web_search, Perplexity results, and the final ranked list
```

If a tool fails (e.g., network issue), the agent now reports the error in the trace instead of crashing, so you can immediately retry.

### Autonomy Status & Budget

Keep tabs on KITTY's bounded autonomy before enabling weekly projects:

```bash
# Evaluate whether KITTY can run scheduled or exploration workloads
curl -s "http://localhost:8000/api/autonomy/status?workload=scheduled" | jq

# Review the last 7 days of autonomous spend vs. the $5/day ceiling
curl -s "http://localhost:8000/api/autonomy/budget?days=7" | jq
```

- Gauges such as `kitty_autonomy_budget_available_usd` and `kitty_autonomy_ready_state` are exposed on `/metrics` for Prometheus/Grafana dashboards.
- `.env` toggles: `AUTONOMOUS_ENABLED=true`, `AUTONOMOUS_DAILY_BUDGET_USD=5.00`, `AUTONOMOUS_IDLE_THRESHOLD_MINUTES=120`.

### Web Search + Extraction Stack (SearXNG → Brave → DuckDuckGo → Perplexity → Jina Reader)

1. **Run SearXNG locally (free, private)**
   ```bash
   mkdir -p infra/search/searxng
   # drop the docker-compose snippet from Research/Web_searchTooloptions.md
   docker compose -f infra/search/searxng/docker-compose.yml up -d
   ```
   Set `SEARXNG_BASE_URL=http://localhost:8888` in `.env`. KITTY will hit this self-hosted metasearch first.

2. **Add Brave as the freemium fallback**
   - Sign up at https://api.search.brave.com/ (2 000 queries/day free).
   - Put the key in `.env` (`BRAVE_SEARCH_API_KEY`), keep the default endpoint unless you’re in a different region.
   - Brave only triggers when SearXNG is down or returns zero results.

3. **Full article extraction with Jina Reader (plus local fallback)**
   - Set `JINA_API_KEY` (free tier works) and KITTY will fetch the full article via `fetch_webpage` after each search hit.
   - If Jina is unavailable, we fall back to the built-in BeautifulSoup parser to keep responses flowing.

4. **Perplexity is now the last resort**
   - `web_search` + `fetch_webpage` will exhaust free tiers before calling `research_deep`.
   - Routing telemetry (`metadata.provider`) shows which backend and extractor handled the query so you can monitor savings.

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

   - Brain exposes `/api/memory/remember` and `/api/memory/search`, which proxy to the mem0 MCP server (Qdrant + embeddings). The CLI’s `/remember` and `/memories` map to these endpoints so operators can persist durable facts (e.g., “prefers ABS on Voron”) while still clearing conversational context via `/reset`.
   - Paid research helpers (`research_deep`, frontier escalations) are only offered when the prompt contains the override keyword (default `omega`). This ensures accidental questions don’t burn credits now that SearXNG/Brave/DuckDuckGo/Jina provide free coverage.
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

### Local Context & Completion Limits

KITTY’s llama.cpp servers enforce two key limits:

- **Context window (`LLAMACPP_CTX`)** – how many tokens (prompt + answer) fit in memory.
- **Completion limit (`LLAMACPP_N_PREDICT`)** – maximum tokens the model may emit per request.

By default we cap completions at **896 tokens** with a 90 s HTTP timeout. When KITTY hits the limit you’ll see a CLI warning (“output hit the token limit”). Ask the assistant to continue or raise the limit.

**Adjusting the limit**

1. Open `.env` (or use the Model Manager TUI) and set:
   ```bash
   LLAMACPP_N_PREDICT=1200      # or higher for long-form answers
   LLAMACPP_TIMEOUT=120        # seconds; keep slightly above expected runtime
   LLAMACPP_CTX=12288          # optional, if your model supports larger context
   ```
2. Restart the llama.cpp service (`./ops/scripts/start-llamacpp.sh` or via Model Manager) and `docker compose … restart brain`.

**Mac Studio (M2 Ultra, 24c CPU / 60c GPU, 192–256 GB unified memory) suggestions**

- Use the Metal backend with **flash attention** enabled.
- 30–40 GPU layers per model (as already configured) keeps VRAM usage comfortable.
- Safe starting values:
  ```bash
  LLAMACPP_CTX=12288
  LLAMACPP_N_PREDICT=1500
  LLAMACPP_TIMEOUT=150
  ```
  This still leaves plenty of headroom in unified memory while allowing multi-page answers. Monitor `kitty-cli` warnings or `llama-server.log`; if completions routinely stop early, raise `LLAMACPP_N_PREDICT` another 200–300 tokens.
- Remember that huge contexts slow generation. Treat the above as a ceiling and lower it for latency-sensitive workflows.

Free up prompt space by using `/remember` and `/memories` rather than replaying entire chat histories; long-term facts go into the Memory MCP server, while each session keeps a clean llama.cpp context.

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
