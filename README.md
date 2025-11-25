# 🐱 KITTY: Technical AI Habitat for Fabrication

> **K**nowledgeable **I**ntelligent **T**ool-using **T**abletop **Y**ardMaster
>
> An offline-first, voice-enabled fabrication lab orchestrator running on Mac Studio M3 Ultra. Think "JARVIS for your workshop" - but it actually works, runs locally, and won't spy on you.

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"/>
  <img src="https://img.shields.io/badge/typescript-5.x-blue.svg" alt="TypeScript 5.x"/>
  <img src="https://img.shields.io/badge/platform-macOS_14+-lightgrey.svg" alt="macOS 14+"/>
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License"/>
</p>

---

## 🎯 Vision: A Maker Space for Technical AI

KITTY is a **technical AI habitat** - a maker space purpose-built for AI models like Claude, GPT-5, Llama, Qwen, and Mistral to come "live," run research, and directly control fabrication hardware. Built on the energy-efficient Mac Studio M3 Ultra, it provides a secure network interface to 3D printers, CNC machines, test rigs, and sensing equipment.

**What makes KITTY different:**

- **AI Residency Model**: Models can spin up for a single query or remain active for deep, after-hours projects
- **Bounded Autonomy**: One KITTY-owned project per week with controlled access to printers, inventory, and research
- **Sustainable Manufacturing**: Prioritizes ethically sourced materials with robotic procurement workflows
- **Idea → Prototype Pipeline**: Investigate materials, estimate costs, run simulations, then orchestrate fabrication
- **Energy Efficient**: Mac Studio runs indefinitely with minimal power draw

> 📖 **Full Vision & Roadmap**: See [NorthStar/ProjectVision.md](NorthStar/ProjectVision.md) for the complete multi-phase implementation plan.

---

## 🛠️ Complete Tech Stack

### AI/ML Infrastructure

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Q4 Tool Orchestrator** | Fast tool calling, ReAct agent | llama.cpp (Athene V2 Agent Q4_K_M) @ port 8083 |
| **Primary Reasoner** | Deep reasoning with thinking mode | Ollama (GPT-OSS 120B) @ port 11434 |
| **Fallback Reasoner** | Deep reasoning (when Ollama unavailable) | llama.cpp (Llama 3.3 70B F16) @ port 8082 |
| **Vision Model** | Image understanding, multimodal | llama.cpp (Gemma 3 27B Q4_K_M) @ port 8086 |
| **Summary Model** | Response compression | llama.cpp (Hermes 3 8B Q4_K_M) @ port 8084 |
| **Coder Model** | Code generation specialist | llama.cpp (Qwen2.5 Coder 32B Q8) @ port 8085 |
| **Cloud Fallbacks** | Complex queries, verification | OpenAI GPT-5, Claude Sonnet 4.5, Perplexity |

### Backend Services (Python 3.11 + FastAPI)

| Service | Port | Purpose |
|---------|------|---------|
| **Brain** | 8000 | Core orchestrator, ReAct agent, intelligent routing |
| **Gateway** | 8080 | REST API (HAProxy load-balanced, 3 replicas) |
| **CAD** | 8200 | 3D model generation (Zoo, Tripo, local CadQuery) |
| **Fabrication** | 8300 | Printer control, queue management, outcome tracking |
| **Safety** | 8400 | Hazard workflows, policy engine, audit logging |
| **Discovery** | 8500 | Network device scanning (mDNS, SSDP, Bamboo/Snapmaker UDP) |
| **Broker** | 8777 | Command execution with allow-list safety |
| **Images** | 8600 | Stable Diffusion generation with RQ workers |
| **Mem0 MCP** | 8765 | Semantic memory with vector embeddings |

### Frontend

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Web UI** | React 18 + TypeScript + Vite | Main dashboard, vision gallery, I/O control |
| **CLI** | Python Click | Terminal interface (`kitty-cli`) |
| **Launcher TUI** | Python Textual | Unified control center (`kitty`) |
| **Model Manager** | Python Textual | Model selection and server control |

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

**The Easy Way** - `./ops/scripts/start-all.sh` handles this entire sequence automatically:
1. Checks for running llama.cpp servers (or starts them if configured in `.env`)
2. Starts all Docker services (including RabbitMQ message queue)
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
./ops/scripts/start-all.sh
# This automatically:
# ✓ Starts Q4 llama.cpp server (port 8083)
# ✓ Starts F16 llama.cpp server (port 8082)
# ✓ Waits for both to be healthy
# ✓ Starts all Docker services (including RabbitMQ)
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
./ops/scripts/start-all.sh

# Stop everything
./ops/scripts/stop-all.sh

# Only stop llama.cpp (leave Docker stack alone)
./ops/scripts/stop-llamacpp.sh

# Check service status
docker compose -f infra/compose/docker-compose.yml ps

# Optional: Hermes 3 summary server (q4) boots automatically from the same script.
# Toggle with LLAMACPP_SUMMARY_ENABLED=0 or point LLAMACPP_SUMMARY_MODEL to another GGUF.

# Gemma 3 Vision (kitty-vision) also launches automatically. Set
#   LLAMACPP_VISION_MODEL=/path/to/gemma-3-27b-it-q4_k_m.gguf
#   LLAMACPP_VISION_MMPROJ=/path/to/gemma-3-27b-it-mmproj-bf16.gguf
# if you store the GGUF files elsewhere, or disable with LLAMACPP_VISION_ENABLED=0.

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
> /help                              # Show available commands
> /research <query>                  # Autonomous research with real-time streaming
> /sessions [limit]                  # List all research sessions
> /session <id>                      # View detailed session info and metrics
> /stream <id>                       # Stream progress of active research
> /verbosity 3                       # Set response detail (1-5)
> /cad Create a hex box              # Generate CAD model
> /list                              # Show cached artifacts
> /queue 1 printer_01                # Queue artifact to printer
> /remember Ordered more PLA         # Save a long-term note
> /memories PLA                      # Recall saved notes (optional query)
> /vision gandalf rubber duck        # Search & store reference images
> /images                            # List stored reference image links
> /generate futuristic drone         # Generate image with Stable Diffusion
> /collective council k=3 Compare... # Multi-agent collaboration
> /usage 5                           # Monitor paid provider usage (refresh every 5s)
> /reset                             # Start a fresh conversation/session
> /exit                              # Exit shell

# Quick one-off queries
kitty-cli say "What printers are online?"
kitty-cli say "Turn on bench lights"
kitty-cli images "gandalf rubber duck" --max-results 6

# Generate images with Stable Diffusion
kitty-cli generate-image "studio photo of a water bottle" --wait
kitty-cli list-images
kitty-cli select-image 1

# Monitor paid usage / provider cost
kitty-cli usage
kitty-cli usage --refresh 5
```

### Print Queue Management

```bash
# Install queue CLI helper (for shell users)
chmod +x scripts/queue-cli.sh

# List all jobs in queue
./scripts/queue-cli.sh list

# Show queue statistics
./scripts/queue-cli.sh status

# Show printer status
./scripts/queue-cli.sh printers

# Submit a new print job
./scripts/queue-cli.sh submit /path/to/model.stl "bracket_v2" pla_black_esun 3

# Cancel a job
./scripts/queue-cli.sh cancel job_20251116_123456_abc123

# Update job priority (1-10, 1=highest)
./scripts/queue-cli.sh priority job_20251116_123456_abc123 1

# Trigger job scheduling
./scripts/queue-cli.sh schedule

# Watch queue in real-time (updates every 5s)
./scripts/queue-cli.sh watch

# Web dashboard (after starting KITTY)
open http://localhost:8300/queue
```

**Multi-Printer Coordination Features:**
- Parallel job scheduling across 3 printers (Bamboo H2D, Elegoo Giga, Snapmaker Artisan)
- Intelligent queue optimization with deadline awareness
- Material batching to reduce filament swaps (50% reduction)
- Automatic printer selection based on build volume and availability
- Real-time queue monitoring with visual dashboard
- CLI helper for shell-based workflows

The CLI prints a gallery link (default `http://localhost:4173/?view=vision&session=...&query=...`) whenever image selection would help. Override the target with `KITTY_UI_BASE` if your React UI runs elsewhere.

### Autonomous Research Pipeline

KITTY includes a **5-phase autonomous research system** that combines multi-strategy exploration, multi-layer validation, multi-model coordination, quality metrics, and intelligent stopping criteria.

```bash
# Launch interactive shell
kitty-cli shell

# Start autonomous research with real-time streaming
> /research latest advances in multi-material 3D printing

# Live progress appears with beautiful visualization:
┌─ Research in Progress... ────────────────────────────┐
│ Current Node: execute_iteration                      │
│ Iteration: 5/15                                       │
│ Findings: 18                                          │
│ Saturation: 🟢 No (novelty: 28%)                     │
└───────────────────────────────────────────────────────┘

# List all research sessions
> /sessions

# View detailed metrics for a specific session
> /session abc123def456

# Resume streaming an active session
> /stream abc123def456
```

**Research Pipeline Features:**

1. **Multi-Strategy Research**
   - `breadth_first`: Cast wide net across many sources
   - `depth_first`: Deep dive into specific topics
   - `task_decomposition`: Break complex queries into subtasks
   - `hybrid`: Adaptive combination (default)

2. **Multi-Layer Validation**
   - Schema validation for tool outputs
   - Format validation (JSON, citations, etc.)
   - Quality validation (hallucination detection, claim support)
   - Chain validation across multiple layers

3. **Multi-Model Coordination**
   - **Local models** (llama.cpp):
     - Athene V2 Agent Q4_K_M (tool orchestrator, 32K context)
     - Llama 3.3 70B F16 (deep reasoning, 65K context)
     - Gemma 3 27B Q4_K_M Vision (multimodal with mmproj)
     - Qwen2.5 Coder 32B Q8 (code generation specialist)
   - **External models**: GPT-5, Claude Sonnet 4.5
   - **5-tier consultation**: trivial → low → medium → high → critical
   - **Budget-aware**: $2/session max, 10 external calls limit
   - **Mixture-of-Agents debate**: Multi-model consensus for critical decisions

4. **Quality Metrics & Stopping**
   - **RAGAS metrics**: Faithfulness, relevancy, precision, recall
   - **Confidence scoring**: 6-factor analysis (source quality, diversity, claim support, model agreement, citations, recency)
   - **Saturation detection**: Novelty rate tracking, diminishing returns detection
   - **Knowledge gap detection**: Critical gaps identified for targeted exploration
   - **Multi-signal stopping**: Quality threshold + saturation + budget + gaps resolved

5. **Session Management**
   - Full state checkpointing via PostgreSQL + LangGraph
   - Resume from any point after failure
   - WebSocket streaming for real-time progress
   - Comprehensive metrics dashboard

**Example Workflow:**

```bash
# Research with default settings (hybrid strategy, $2 budget)
> /research best practices for PETG outdoor use

# System automatically:
# 1. Selects hybrid strategy
# 2. Executes tools in parallel waves (tool dependency graph)
# 3. Validates outputs through multi-layer pipeline
# 4. Consults models based on task complexity (tier-based)
# 5. Computes quality metrics after each iteration
# 6. Detects saturation and knowledge gaps
# 7. Stops when quality thresholds met + gaps resolved
# 8. Synthesizes final answer

# View sessions
> /sessions 20
╭─────────────────── Research Sessions ───────────────────╮
│ #  Session ID      Query          Status    Strategy  ... │
│ 1  abc123...       best practice  completed hybrid    ... │
│ 2  def456...       PETG vs ABS    active    breadth   ... │
╰──────────────────────────────────────────────────────────╯

# Detailed view shows:
> /session abc123def456
- Strategy: hybrid (adaptive)
- Iterations: 8/15 (stopped early - quality met)
- Budget: $0.15 / $1.85 remaining
- External calls: 2/10 used
- Findings: 24 (avg confidence: 0.82)
- Quality score: 0.91 (target: 0.70)
- Saturation: Yes (novelty: 12% < 15% threshold)
- Knowledge gaps: 0 critical gaps remaining
- Models used: llama3.1:8b-q4, gemma2:27b, claude-sonnet-4-5

Final Answer:
╭────────────────────────────────────────────────────╮
│ Based on 24 validated sources with 82% confidence │
│ ...comprehensive synthesized answer...             │
╰────────────────────────────────────────────────────╯
```

**Benefits:**

- **Cost-effective**: Local models handle 70%+ of work, external models only for complex/critical tasks
- **High quality**: Multi-layer validation catches hallucinations, RAGAS ensures factual accuracy
- **Intelligent stopping**: Doesn't waste budget on saturated exploration
- **Transparent**: Real-time streaming shows exactly what's happening
- **Fault-tolerant**: Full checkpointing, resume from any failure point
- **Budget-aware**: Hard limits prevent runaway costs ($2/session ceiling)

#### Permission System & Budget Control

The research pipeline uses a **3-layer permission hierarchy** to control API usage and costs:

**Layer 1: I/O Control** (Hard Gate)
- Checks if API provider is enabled in dashboard
- Respects offline mode and cloud routing settings
- Instant denial if provider disabled
- Control via I/O Control dashboard (Redis-backed)

**Layer 2: Budget** (Hard Gate)
- Enforces `$2.00/session` budget limit (configurable via `RESEARCH_BUDGET_USD`)
- Tracks external API call limit (`10 calls` default, configurable via `RESEARCH_EXTERNAL_CALL_LIMIT`)
- Instant denial if budget exceeded or call limit reached

**Layer 3: Runtime Approval** (Soft Gate)
- **Trivial (< $0.01)**: Auto-approve always (Perplexity small queries)
- **Low (< $0.10)**: Auto-approve if enabled, else prompt with omega password
- **High (>= $0.10)**: Always prompt for omega password (GPT-5, Claude Sonnet 4.5)

**Configuration:**
```bash
# Set in environment or I/O Control dashboard
RESEARCH_BUDGET_USD=2.0              # Max budget per session
RESEARCH_EXTERNAL_CALL_LIMIT=10     # Max external calls per session
API_OVERRIDE_PASSWORD=omega          # Omega password for approval
AUTO_APPROVE_TRIVIAL=true           # Auto-approve < $0.01
AUTO_APPROVE_LOW_COST=false         # Auto-approve < $0.10
```

**Example Permission Flows:**

```bash
# Free tools (web_search) - no permission needed
> /research latest llama.cpp features
# ✅ Executes immediately, $0.00 cost

# Trivial cost (< $0.01) - auto-approved
> /research vector database comparison
# ✅ Auto-approved, executes, $0.005 charged

# Low cost (< $0.10) - prompts if not auto-approved
> /research comprehensive ML framework analysis
# Prompts:
# ──────────────────────────────────────────────────
# API Permission Required
# Provider: Perplexity
# Estimated cost: $0.05
# Budget remaining: $1.95
#
# Enter 'omega' to approve, or press Enter to deny:

# High cost (>= $0.10) - always prompts
# (Critical decision requiring GPT-5)
# ══════════════════════════════════════════════════
# ⚠️  HIGH-COST API CALL
# ══════════════════════════════════════════════════
# Provider: OpenAI
# Estimated cost: $0.50
# Budget remaining: $2.00
#
# ⚠️  This call requires explicit approval.
# Enter 'omega' to approve, or press Enter to deny:

# Blocked by I/O Control
> /research test query
# ❌ Perplexity API disabled in I/O Control. Enable in dashboard to use.

# Blocked by budget
# (After spending $1.95)
> /research another query
# ❌ Budget exceeded. Remaining: $0.05, Required: $0.10
```

**Key Features:**
- **Single source of truth**: UnifiedPermissionGate replaces 3 separate permission managers
- **90% reduction in complexity**: 5 layers → 3 layers, cleaner flow
- **Smart cost-based approval**: Different rules for trivial/low/high cost calls
- **Real-time budget tracking**: Always know how much you've spent
- **I/O Control integration**: Respect dashboard settings, no surprises
- **Comprehensive testing**: 50+ test cases ensure reliability

For detailed architecture, see `Research/PermissionSystemArchitecture.md`.

### Vision Web Gallery

```bash
cd services/ui && pnpm install        # first-time setup

# Run the React app in dark mode (default http://localhost:4173)
pnpm dev --host 0.0.0.0 --port 4173

# Forward the port in VS Code Remote SSH
# Command Palette → "Ports: Focus on Ports View" → "Forward a Port" (4173)
# Share the forwarded URL with teammates who need to pick images
```

Env knobs:

```env
KITTY_UI_BASE=http://your-ui-host:4173     # where the React gallery is served
KITTY_CLI_API_BASE=http://gateway:8080     # optional override for CLI API target
VITE_API_BASE=http://gateway:8080          # UI fetches vision endpoints from the gateway
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

1. **Run SearXNG locally (free, private)** - already bundled in KITTY
   ```bash
   # start the built-in SearXNG container (listens on the internal name `searxng:8080`)
    docker compose -f infra/compose/docker-compose.yml up -d searxng
   ```
   - Containers use `INTERNAL_SEARXNG_BASE_URL=http://searxng:8080` automatically.
   - If you want host access, expose it via `SEARXNG_BASE_URL=http://localhost:8888` (optional).

2. **Add Brave as the freemium fallback**
   - Sign up at https://api.search.brave.com/ (2 000 queries/day free).
   - Put the key in `.env` (`BRAVE_SEARCH_API_KEY`), keep the default endpoint unless you’re in a different region.
   - Brave only triggers when SearXNG is down or returns zero results.
   - Advanced knobs: set `IMAGE_SEARCH_PROVIDER=brave|searxng|duckduckgo|auto`, tweak `IMAGE_SEARCH_SAFESEARCH=off|moderate|strict`, or override `BRAVE_SEARCH_ENDPOINT` if Brave launches a regional edge.

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
# k - Start KITTY stack (llama.cpp + Docker via start-all.sh)
# x - Stop stack (stop-all.sh)
# c - Launch CLI (health checks + kitty-cli shell)
# m - Launch Model Manager (swap llama.cpp models)
# o - Open Web Console (React/Vision UI)
# i - Launch I/O dashboard (feature toggles & presets)
# h - Toggle system health panel, d - detailed services
# r - Reasoning log viewer, s - startup instructions, q - Quit

# What you get:
# ✓ Access-All control center with quick-action buttons + keyboard shortcuts
# ✓ Start/stop scripts with live logs streamed into the console
# ✓ Real-time Docker + llama.cpp health overview, reasoning log viewer
# ✓ One-key access to CLI, Model Manager, I/O dashboard, and the web console
# ✓ Beautiful terminal UI with status chips, helpful notifications, and historical log panel
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

### Ollama Setup (GPT-OSS 120B with Thinking Mode)

KITTY supports **Ollama** as an alternative to llama.cpp for deep reasoning tasks. This allows you to use **GPT-OSS:120B** with built-in thinking mode for enhanced reasoning capabilities.

#### Installation

```bash
# Install Ollama
brew install ollama

# Start Ollama daemon
ollama serve &

# Pull GPT-OSS 120B model (~65 GB MXFP4)
ollama pull gpt-oss:120b
```

#### Configuration

1. **Set Ollama as the reasoner provider in `.env`:**

```bash
# Enable Ollama for F16 reasoning engine
LOCAL_REASONER_PROVIDER=ollama       # Use Ollama instead of llama.cpp F16

# Ollama configuration
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_THINK=medium                  # Thinking effort: low | medium | high
OLLAMA_TIMEOUT_S=120
OLLAMA_KEEP_ALIVE=5m
```

2. **Start KITTY with Ollama:**

```bash
# Ollama will start automatically when using start-all.sh
./ops/scripts/start-all.sh

# Or start Ollama separately
./ops/scripts/ollama/start.sh
```

#### Thinking Modes

GPT-OSS supports three thinking effort levels:

- **`low`**: Fast, minimal reasoning trace (for simple queries)
- **`medium`**: Balanced reasoning depth (recommended default)
- **`high`**: Maximum reasoning effort for complex problems

#### Rollback to llama.cpp

To switch back to llama.cpp F16:

```bash
# Update .env
LOCAL_REASONER_PROVIDER=llamacpp

# Restart KITTY
./ops/scripts/stop-all.sh
./ops/scripts/start-all.sh
```

#### Benefits

- **Easy Thinking Mode**: Ollama provides a simple `--think` flag for GPT-OSS reasoning traces
- **No Multi-File Models**: Single model file instead of llama.cpp's multi-shard F16 files
- **Same Interface**: Q4 tool orchestrator continues to delegate to F16 via `reason_with_f16` tool
- **Telemetry**: Thinking traces are captured separately for analysis (not shown to users)

#### Architecture Notes

- Q4 (llama.cpp port 8083): Tool orchestrator for ReAct workflows
- **Ollama (port 11434)**: Deep reasoning engine (replaces llama.cpp F16 on port 8082)
- Vision (llama.cpp port 8086): Image understanding
- Summary (llama.cpp port 8084): Text summarization
- Coder (llama.cpp port 8085): Code generation

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

KITTY transforms your Mac Studio into a **conversational command center** for your entire fabrication lab. It's the bridge between AI reasoning and physical manufacturing.

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **🧠 Local-First AI** | 70%+ of queries handled offline via llama.cpp with Metal GPU acceleration |
| **🗣️ Multi-Modal Input** | Voice (Whisper), CLI, Web UI, REST API |
| **🖨️ Printer Control** | OctoPrint, Klipper/Moonraker, Bamboo Labs MQTT, Snapmaker |
| **🏠 Smart Home** | Home Assistant integration for lights, climate, sensors |
| **📐 CAD Generation** | Zoo API, Tripo (image-to-3D), local CadQuery/FreeCAD |
| **🔍 Network Discovery** | Auto-discover printers and IoT devices on your network |
| **🧪 Research Pipeline** | 5-phase autonomous research with multi-model coordination |
| **🧠 Semantic Memory** | Long-term knowledge storage with Qdrant vector DB |
| **🎨 Image Generation** | Stable Diffusion via local GPU workers |
| **📊 Print Queue** | Multi-printer coordination with intelligent scheduling |
| **🔐 Safety System** | Hazard workflows, confirmation phrases, audit logging |

### Core Design Philosophy: "Everything Has a Switch"

A cornerstone principle of KITTY is **controllability**. Every external device, feature, and capability can be individually enabled or disabled through the I/O Control Dashboard:

| Principle | Benefit |
|-----------|---------|
| **🧪 Safe Development** | Test workflows without hardware by disabling cameras, printers, storage |
| **📈 Incremental Deployment** | Enable one camera at a time, add MinIO when ready |
| **🔧 Rapid Troubleshooting** | Isolate issues by toggling individual components |
| **🔄 Hot-Reload** | Most features update instantly via Redis without restart |
| **🎯 Smart Restarts** | Only affected service restarts, not full stack |
| **✅ Dependency Validation** | Can't enable features without their prerequisites |

**Control Interfaces:**
- **TUI**: `python ops/scripts/kitty-io-control.py` - Interactive terminal dashboard
- **Web API**: `http://localhost:8080/api/io-control/*` - Programmatic control
- **Documentation**: See `docs/IO_CONTROL_DASHBOARD.md`

### Why "Offline-First"?

Your workshop shouldn't stop working when AWS has a bad day. KITTY runs powerful local models on your Mac's Metal GPU and only escalates to cloud providers when truly necessary:

```
Query arrives → Local model (free, instant) → Confidence check
                                                    ↓
                          High confidence? ──→ Return answer
                                                    ↓
                          Low confidence? ──→ Escalate to cloud (with budget gate)
```

**Budget protection**: Cloud API calls require the `omega` password and respect per-session limits ($2/session default).

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

#### 🧩 **Tool Registry & MCP Integration**

All ReAct agent tools are defined in a central **tool registry** (`config/tool_registry.yaml`) with JSON schema validation and safety metadata. This makes it easy to add new capabilities without modifying agent code.

**Available tool categories:**

| Category | Tools | Safety Level |
|----------|-------|--------------|
| **CAD Generation** | `cad.generate_model`, `cad.image_to_mesh`, `cad.local_generate` | Low (non-destructive) |
| **Image Generation** | `images.generate`, `images.get_latest`, `images.select` | Low (local, offline) |
| **Fabrication** | `fabrication.open_in_slicer`, `fabrication.analyze_model`, `fabrication.printer_status` | Low (app launching) |
| **Network Discovery** | `discovery.scan_network`, `discovery.list_devices`, `discovery.find_printers`, `discovery.approve_device` | None/Low |
| **Home Assistant** | `homeassistant.turn_on`, `homeassistant.turn_off`, `homeassistant.activate_scene` | Varies by entity |
| **Vision & Research** | `vision.search`, `vision.store`, `research.web_search` | None |
| **Memory** | `memory.remember`, `memory.search` | None |

**Example: Image → CAD → Print workflow**

```yaml
User: "Generate an image of a water bottle, create a 3D model from it, and open it in the slicer"

Agent executes:
  1. images.generate(prompt="studio photo matte black water bottle")
     → Returns: s3://kitty-artifacts/images/20250111_143022.png

  2. cad.image_to_mesh(
       image_path="s3://kitty-artifacts/images/20250111_143022.png",
       provider="tripo"
     )
     → Returns: /Users/Shared/KITTY/artifacts/cad/bottle.stl

  3. fabrication.analyze_model(
       stl_path="/Users/Shared/KITTY/artifacts/cad/bottle.stl"
     )
     → Model: 150mm tall, recommends Bamboo Labs H2D (available, idle)

  4. fabrication.open_in_slicer(
       stl_path="/Users/Shared/KITTY/artifacts/cad/bottle.stl",
       print_mode="3d_print"
     )
     → Opened in BambuStudio. Complete slicing and printing manually in app.
```

**Example: Network discovery workflow**

```yaml
User: "Scan the network and find all 3D printers"

Agent executes:
  1. discovery.scan_network(timeout_seconds=30)
     → Scan started (ID: abc-123), estimated 12-30 seconds

  2. discovery.find_printers()
     → Found 3 printers:
      - Bamboo Labs H2D (192.168.0.144) - Not approved
      - Elegoo OrangeStorm Giga (Klipper, 192.168.0.63) - Not approved
       - Snapmaker Artisan (192.168.1.150) - Not approved

User: "Approve the Bamboo Labs printer"

Agent executes:
  3. discovery.approve_device(
       device_id="uuid-from-list",
       notes="Main workshop printer"
     )
     → Device approved for integration
```

### 🔍 **Network Discovery Service**

KITTY automatically discovers IoT devices on your network using multiple protocols:

| Protocol | Devices Found | How It Works |
|----------|--------------|--------------|
| **mDNS** | OctoPrint, Klipper instances | Bonjour/Avahi service discovery |
| **SSDP** | Smart plugs, cameras | UPnP device discovery |
| **Bamboo UDP** | Bamboo Labs printers | Proprietary broadcast protocol |
| **Snapmaker UDP** | Snapmaker printers | Proprietary broadcast protocol |
| **ARP Scan** | All network devices | Host-native MAC/IP mapping with OUI lookup |

**Discovery Workflow:**
```bash
# Trigger manual network scan
curl -X POST http://localhost:8500/api/discovery/scan \
  -H "Content-Type: application/json" \
  -d '{"methods": ["mdns", "ssdp", "bamboo_udp"], "timeout_seconds": 30}'

# List all discovered devices
curl http://localhost:8500/api/discovery/devices

# List only printers
curl http://localhost:8500/api/discovery/printers

# Approve a device for integration
curl -X POST http://localhost:8500/api/discovery/devices/{device_id}/approve \
  -d '{"notes": "Main workshop printer"}'
```

**Host-Native ARP Scanning:**

For comprehensive device discovery (including devices that don't advertise via mDNS/SSDP), run the host-native discovery script:

```bash
# Run ARP scan from host (requires sudo for raw sockets)
./ops/scripts/discovery/run-host.sh

# This script:
# 1. Runs arp-scan on all local subnets
# 2. Performs OUI lookup for vendor identification
# 3. Submits results to the discovery service
# 4. Tags devices by manufacturer (Bamboo, Elegoo, Creality, etc.)
```

**Features:**
- Periodic automatic scans (configurable interval, default 15 min)
- Device registry with approval workflow
- Online/offline status tracking
- Manufacturer identification via OUI database
- Integration with fabrication service for printer control

**Adding new tools:**

1. Add to `config/tool_registry.yaml`:
   ```yaml
   myservice.action:
     method: POST
     url: http://gateway:8080/api/myservice/action
     schema: {...}
     safety: {hazard_class: "low", confirmation_required: false}
   ```

2. Gateway automatically proxies to backend service
3. Agent picks up new tool on restart (no code changes needed!)

**Documentation:** See `config/README.md` for complete tool registry reference and examples.


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
- Vision references: `/vision` selections are sent as `imageRefs` (download URL + storage URI). The CAD service mounts the shared `references_storage` volume, streams the original bytes to Tripo's `/upload` endpoint, kicks off `/image-to-3d`, polls `/task/<id>`, then submits a Tripo `/convert` task to emit binary STL (face-limit + unit aware) before falling back to local `trimesh` conversion whenever the API is unavailable.
- Reference ordering: the CLI persists selections newest-first and automatically shares the latest entries with KITTY inside an `<available_image_refs>` block whenever you chat or run `/cad`. Hermes/Gemini read this block and include the matching `imageRefs` when calling `generate_cad_model`, so you always know which photo is being used.
- Targeted references: use `kitty-cli cad --image rocketshipLaunch --image 1 "Convert this shuttle photo"` (friendly names, IDs, or newest-first indexes) to send only specific references; omit `--image` and the CLI will keyword-match your prompt against stored titles/captions to auto-select the best references (defaults to Tripo’s 2-image limit).
- Print intent workflow: When you tell KITTY to open a model in the slicer, it confirms you truly want to print, asks for the desired finished height (inches or millimeters), converts to mm automatically, and uses that value plus the configured build envelopes to choose between Bamboo H2D and Elegoo OrangeStorm Giga before launching the appropriate slicer (BambuStudio or ElegySlicer).
- Validation checklist: see `docs/tripo-stl-testing.md` for end-to-end test steps and timeout recommendations.

### 📂 **Accessing Generated Files from macOS Finder**

KITTY stores all generated CAD files in a **shared directory accessible from macOS Finder**, making it easy to open STL files in Fusion 360, Blender, or any other CAD software.

**Setup (one-time):**

```bash
# Run the setup script to create the artifacts directory
./ops/scripts/setup-artifacts-dir.sh

# The default location is: /Users/Shared/KITTY/artifacts
# Files are organized in subdirectories:
#   cad/       - STL, STEP, OBJ, GLB files
#   images/    - Reference images
#   metadata/  - JSON files with generation details
```

**Accessing Files:**

```bash
# Open artifacts folder in Finder
open /Users/Shared/KITTY/artifacts/cad

# Or navigate manually:
# Finder → Go → Go to Folder (⌘⇧G)
# Type: /Users/Shared/KITTY/artifacts
```

**Opening in Fusion 360:**

1. Generate a model: `kitty-cli cad "Create a phone stand with cable routing"`
2. Open Finder and navigate to `/Users/Shared/KITTY/artifacts/cad/`
3. Find your STL file (named with timestamp and description)
4. **Drag & drop** the STL into Fusion 360, or:
   - Fusion 360 → **File** → **Open** → Browse to artifacts directory
   - Select your STL file → **Open**
5. Edit the mesh or use it as a reference for parametric modeling

**File Organization:**

Each generated file includes:
- **CAD File**: `20251110_a3f2b1c_phone-stand.stl`
- **Metadata**: `20251110_a3f2b1c_phone-stand.json` (prompt, provider, parameters)
- Metadata includes the original prompt, provider used, and any reference images

**Custom Location:**

```bash
# To use a different directory, set in .env:
KITTY_ARTIFACTS_DIR=/path/to/your/custom/directory

# Then run setup script:
./ops/scripts/setup-artifacts-dir.sh
```

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

# Setup artifacts directory (for accessing STL files in Fusion 360)
./ops/scripts/setup-artifacts-dir.sh
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

That's it! KITTY is now running. Press `Ctrl+C` to stop, or run `./ops/scripts/stop-all.sh`.

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
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Mac Studio M3 Ultra Host                           │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                         Local AI Inference Layer                       │ │
│  │                                                                        │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                  Ollama (Primary Reasoner) :11434                │  │ │
│  │  │                      GPT-OSS 120B (Thinking Mode)                │  │ │
│  │  └──────────────────────────────┬──────────────────────────────────┘  │ │
│  │                                 │                                      │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                  llama.cpp Servers (Metal GPU)                   │  │ │
│  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐        │  │ │
│  │  │  │Q4 Tool    │ │F16 Fallback│ │Vision     │ │Summary    │        │  │ │
│  │  │  │Orchestrator│ │Reasoner   │ │Gemma 27B  │ │Hermes 8B  │        │  │ │
│  │  │  │:8083      │ │:8082      │ │:8086      │ │:8084      │        │  │ │
│  │  │  │Athene V2  │ │Llama 70B  │ │+mmproj    │ │           │        │  │ │
│  │  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘        │  │ │
│  │  └────────┼─────────────┼─────────────┼─────────────┼──────────────┘  │ │
│  └───────────┼─────────────┼─────────────┼─────────────┼─────────────────┘ │
│              └─────────────┴─────────────┴─────────────┘                   │
│                                    │                                       │
│  ┌─────────────────────────────────┼─────────────────────────────────────┐ │
│  │                    Docker Compose Services                             │ │
│  │                                 │                                      │ │
│  │  ┌──────────────────────────────▼────────────────────────────────┐   │ │
│  │  │                        HAProxy :8080                           │   │ │
│  │  │                    (Load Balancer, 3 replicas)                 │   │ │
│  │  └──────────────────────────────┬────────────────────────────────┘   │ │
│  │                                 │                                      │ │
│  │  ┌──────────────────────────────▼────────────────────────────────┐   │ │
│  │  │                        Gateway (x3)                            │   │ │
│  │  │                   REST API, Auth, Routing                      │   │ │
│  │  └──────────────────────────────┬────────────────────────────────┘   │ │
│  │                                 │                                      │ │
│  │  ┌──────────────────────────────▼────────────────────────────────┐   │ │
│  │  │                         Brain :8000                            │   │ │
│  │  │         Orchestrator • ReAct Agent • Research Pipeline         │   │ │
│  │  └───┬─────────┬─────────┬─────────┬─────────┬─────────┬────────┘   │ │
│  │      │         │         │         │         │         │            │ │
│  │  ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐      │ │
│  │  │  CAD  │ │  Fab  │ │Safety │ │Discov │ │Broker │ │Images │      │ │
│  │  │ :8200 │ │ :8300 │ │ :8400 │ │ :8500 │ │ :8777 │ │ :8600 │      │ │
│  │  └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘      │ │
│  │                                                                     │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │                    Storage & Infrastructure                  │   │ │
│  │  │  PostgreSQL │ Redis │ Qdrant │ MinIO │ RabbitMQ │ Mosquitto │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  │                                                                     │ │
│  │  ┌─────────────────────────────────────────────────────────────┐   │ │
│  │  │                      Observability                           │   │ │
│  │  │        Prometheus │ Grafana │ Loki │ Tempo │ SearXNG         │   │ │
│  │  └─────────────────────────────────────────────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                    │                           │                    │
         ┌──────────▼──────────┐     ┌──────────▼──────────┐   ┌────▼────┐
         │    Home Assistant   │     │      3D Printers    │   │ Cameras │
         │    (MQTT + REST)    │     │  Bamboo │ Elegoo │  │   │  (Pi)   │
         │  Lights, Climate,   │     │  Snapmaker │ Others │   │         │
         │  Sensors, Locks     │     │  (OctoPrint/Klipper)│   │         │
         └─────────────────────┘     └─────────────────────┘   └─────────┘
```

### Service Breakdown

| Service | Port | Purpose | Key Technologies |
|---------|------|---------|------------------|
| **Gateway** | 8080 | REST API, auth, load balancing | FastAPI, HAProxy (3 replicas), JWT |
| **Brain** | 8000 | Core orchestrator, ReAct agent, routing | FastAPI, llama.cpp client, LangGraph |
| **CAD** | 8200 | 3D model generation, artifact storage | FastAPI, Zoo SDK, Tripo API, CadQuery |
| **Fabrication** | 8300 | Printer control, queue, outcome tracking | FastAPI, OctoPrint, Klipper, Bamboo MQTT |
| **Safety** | 8400 | Hazard workflows, policy engine | FastAPI, PostgreSQL audit logs |
| **Discovery** | 8500 | Network device scanning | FastAPI, mDNS, SSDP, UDP broadcast |
| **Broker** | 8777 | Safe command execution | FastAPI, allow-list YAML |
| **Images** | 8600 | Stable Diffusion generation | FastAPI, RQ workers, Diffusers |
| **Mem0 MCP** | 8765 | Semantic memory storage | FastAPI, Qdrant, sentence-transformers |
| **UI** | 4173 | Web console, dashboards | React 18, TypeScript, Vite |
| **CLI** | - | Terminal interface | Python Click, Rich |

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

### Phase 4: Fabrication Intelligence

- **[Phase 4 Progress Summary](docs/PHASE4_PROGRESS_SUMMARY.md)**: Current implementation status and timeline
- **[Feature Flags Guide](docs/PHASE4_FEATURE_FLAGS_GUIDE.md)**: I/O controls for incremental testing (cameras, MQTT, MinIO)
- **[Computer Vision Print Monitoring](docs/CV_PRINT_MONITORING_DESIGN.md)**: Camera integration and human-in-loop design
- **[Materials Database Guide](docs/materials-database-guide.md)**: Filament catalog and inventory management
- **[Phase 4 Specification](specs/004-FabricationIntelligence/spec.md)**: Complete Phase 4 technical specification

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
# Optional Tripo overrides (only set if your account supports them)
# TRIPO_MODEL_VERSION=v2.5         # Maps to the `version` field on /task
# TRIPO_TEXTURE_QUALITY=HD
# TRIPO_TEXTURE_ALIGNMENT=align_image
TRIPO_POLL_INTERVAL=3             # seconds between task status checks
TRIPO_POLL_TIMEOUT=900            # generation + convert deadline (seconds)
TRIPO_CONVERT_ENABLED=false       # Optional legacy flow; keep false (local STL conversion is default)
TRIPO_STL_FORMAT=binary           # binary vs ascii STL (when convert enabled)
TRIPO_FACE_LIMIT=150000           # optional triangle budget for server-side reduction
TRIPO_UNIT=millimeters            # unit metadata for downstream slicers

# UniFi (for cameras/access)
UNIFI_URL=https://unifi.local
UNIFI_USERNAME=admin
UNIFI_PASSWORD=...
```

### Fabrication Hardware Limits

KITTY needs to know each printer’s safe build volume so it can pick the right machine and warn before slicing oversized parts. Set these env vars in `.env` (defaults shown) whenever firmware limits change or you swap hardware:

```env
H2D_BUILD_WIDTH=325
H2D_BUILD_DEPTH=320
H2D_BUILD_HEIGHT=325

ORANGESTORM_GIGA_BUILD_WIDTH=800
ORANGESTORM_GIGA_BUILD_DEPTH=800
ORANGESTORM_GIGA_BUILD_HEIGHT=1000
```

KITTY takes the smallest axis from each printer’s build volume as the conservative “max dimension” during printer selection.

### Phase 4 Feature Flags (I/O Controls)

Enable/disable external device dependencies for incremental testing. See **[Feature Flags Guide](docs/PHASE4_FEATURE_FLAGS_GUIDE.md)** for complete documentation.

```bash
# Print Outcome Tracking
ENABLE_PRINT_OUTCOME_TRACKING=true       # Database tracking (always enabled)

# Camera Integration (disable during development without hardware)
ENABLE_CAMERA_CAPTURE=false              # Master switch - returns mock URLs when disabled
ENABLE_BAMBOO_CAMERA=false               # Bamboo Labs built-in camera via MQTT
ENABLE_RASPBERRY_PI_CAMERAS=false        # Snapmaker/Elegoo Pi cameras via HTTP

# Camera Endpoints (when enabled)
SNAPMAKER_CAMERA_URL=http://snapmaker-pi.local:8080/snapshot.jpg
ELEGOO_CAMERA_URL=http://elegoo-pi.local:8080/snapshot.jpg

# Snapshot Configuration
CAMERA_SNAPSHOT_INTERVAL_MINUTES=5       # Progress snapshots during prints
CAMERA_FIRST_LAYER_SNAPSHOT_DELAY=5      # First layer capture timing

# Storage
ENABLE_MINIO_SNAPSHOT_UPLOAD=false       # Actual uploads vs mock URLs

# Human Feedback
ENABLE_HUMAN_FEEDBACK_REQUESTS=true      # MQTT notifications to UI
HUMAN_FEEDBACK_AUTO_REQUEST=true         # Auto-request after every print

# Intelligence (requires historical data)
ENABLE_PRINT_INTELLIGENCE=false          # Success prediction and recommendations
PRINT_INTELLIGENCE_MIN_SAMPLES=30        # Minimum outcomes before predictions
```

**Development Mode:**
Set `ENABLE_CAMERA_CAPTURE=false` to test the complete workflow without physical cameras. All features work with mock data, no external dependencies required.

**Production Mode:**
Enable features incrementally: test Snapmaker Pi camera first, then add Bamboo Labs, then enable MinIO storage, etc.

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

**Mac Studio (M3 Ultra, 24c CPU / 60c GPU, 192–256 GB unified memory) suggestions**

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

### Current Status (November 2025)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Core Foundation | ✅ Complete | Docker, llama.cpp, FastAPI, Home Assistant |
| Phase 2: Tool-Aware Agent | ✅ Complete | ReAct agent, MCP protocol, CAD generation |
| Phase 3: Autonomous Learning | ✅ Complete | Goal identification, research pipeline |
| Phase 3.5: Research Pipeline | ✅ Complete | 5-phase autonomous research, multi-model |
| Phase 4: Fabrication Intelligence | 🚧 85% | Dashboards complete, ML features in progress |
| Phase 5: Safety & Access | 📋 Planned | UniFi Access, zone presence |
| Phase 6: Advanced Features | 📋 Planned | Multi-user, mobile app |

---

### Phase 1: Core Foundation ✅ COMPLETE
- [x] Docker Compose orchestration with health checks
- [x] llama.cpp integration with Metal GPU acceleration
- [x] FastAPI services (gateway, brain, CAD, fabrication, safety)
- [x] Home Assistant integration (lights, climate, sensors)
- [x] Confidence-based routing with semantic caching

### Phase 2: Tool-Aware Agent ✅ COMPLETE
- [x] ReAct agent implementation (Reasoning + Acting)
- [x] MCP server protocol for tool use
- [x] Safe tool executor with hazard workflows
- [x] CAD generation (Zoo/Tripo/local CadQuery)
- [x] Command broker with allow-lists
- [x] Web research with citation tracking
- [x] Conversation history persistence
- [x] Multi-provider collective workflows

### Phase 3: Autonomous Learning ✅ COMPLETE
- [x] Goal identification system
- [x] Project proposal workflow
- [x] Research goal execution (Perplexity integration)
- [x] Outcome tracking and effectiveness measurement
- [x] Knowledge base integration
- [x] Budget-aware autonomous operation ($5/day)

### Phase 3.5: Autonomous Research Pipeline ✅ COMPLETE

**5-Phase Research System:**

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Database schema + LangGraph checkpointing | ✅ |
| 2 | Tool orchestration (dependency graph, wave execution) | ✅ |
| 3 | Model coordination (7 models, 5-tier consultation) | ✅ |
| 4 | Quality metrics (RAGAS, saturation detection) | ✅ |
| 5 | Integration (WebSocket streaming, CLI commands) | ✅ |

**Model Registry:**
- **Primary Reasoner**: GPT-OSS 120B via Ollama (thinking mode enabled)
- **Local (llama.cpp)**: Athene V2 Agent Q4, Llama 3.3 70B F16 (fallback), Gemma 3 27B Vision, Qwen2.5 Coder 32B, Hermes 3 8B (summary)
- **External**: GPT-5, Claude Sonnet 4.5, Perplexity

### Phase 4: Fabrication Intelligence 🚧 IN PROGRESS

**Completed Features:**

| Feature | Lines of Code | Status |
|---------|---------------|--------|
| I/O Control Dashboard | 1,500+ | ✅ |
| Material Inventory Dashboard | 1,014 | ✅ |
| Print Intelligence Dashboard | 1,302 | ✅ |
| Vision Service Dashboard | 823 | ✅ |
| Database Clustering (PostgreSQL + Redis) | 824 | ✅ |
| Message Queue (RabbitMQ) | 832 | ✅ |
| Multi-Printer Coordination | 1,200+ | ✅ |
| Automated Print Execution | 2,000+ | ✅ |
| Network Discovery Service | 1,500+ | ✅ |

**In Progress:**
- [ ] Print Intelligence ML (success prediction)
- [ ] Autonomous Procurement (low inventory alerts → research suppliers)

### Phase 5: Safety & Access 📋 PLANNED
- [ ] UniFi Access integration
- [ ] Zone presence detection
- [ ] Enhanced hazard workflows
- [ ] Multi-factor confirmation
- [ ] Audit dashboard

### Phase 6: Advanced Features 📋 PLANNED
- [ ] Multi-user support with RBAC
- [ ] Advanced observability (Loki, Tempo complete)
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

| Principle | Description |
|-----------|-------------|
| **Offline-First** | Your workshop shouldn't depend on the cloud. 70%+ queries handled locally. |
| **Safety-First** | Dangerous operations require explicit confirmation and audit logging. |
| **Privacy-First** | Your conversations stay on your hardware. No telemetry. |
| **Cost-Conscious** | Cloud APIs are expensive; budget gates prevent runaway costs. |
| **Everything Has a Switch** | Every feature toggleable via I/O Control for safe testing. |
| **Tool-Neutral** | Multiple providers for every capability with automatic fallback. |
| **Open** | Fully inspectable, modifiable, and extensible MIT-licensed code. |
| **AI Habitat** | Built for AI models to thrive - not just respond to queries. |

---

## 📊 Project Stats

| Metric | Value |
|--------|-------|
| **Services** | 11 FastAPI microservices |
| **Docker Containers** | 20+ (including infrastructure) |
| **Local AI Models** | 6 (GPT-OSS 120B primary, Q4, F16 fallback, Vision, Summary, Coder) |
| **Cloud Providers** | 4 (OpenAI, Anthropic, Perplexity, Brave) |
| **Supported Printers** | Bamboo Labs, Elegoo (Klipper), Snapmaker, OctoPrint |
| **CAD Providers** | 4 (Zoo, Tripo, CadQuery, FreeCAD) |
| **Discovery Protocols** | 5 (mDNS, SSDP, Bamboo UDP, Snapmaker UDP, ARP) |
| **Total Documentation** | 70+ markdown files |
| **Lines of Python** | 50,000+ |
| **Lines of TypeScript** | 15,000+ |

---

<p align="center">
  <i>Built with ❤️ for makers, by makers</i>
</p>

<p align="center">
  <sub>KITTY: Because your workshop deserves an AI assistant that actually understands "turn that thing on over there"</sub>
</p>
