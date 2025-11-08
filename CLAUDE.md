# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KITTY is an offline-first warehouse orchestrator running on Mac Studio M3 Ultra. It provides conversational control over fabrication equipment (3D printers, lasers), CAD generation, safety workflows, and device control through voice, CLI, and web interfaces. The system uses local llama.cpp models as primary inference with intelligent routing to cloud providers (Perplexity/GPT/Claude) when confidence or freshness demands.

## Core Architecture

### Multi-Service System
The stack runs as containerized microservices orchestrated via Docker Compose with a local llama.cpp server running outside containers. See `docs/project-overview.md` for detailed architecture.

- **brain** (port 8000): Conversational router, context management, safety integration, routing logs. Main endpoint: `/api/query`
- **gateway** (port 8080): Public ingress, OAuth2 token issuance, device command proxy. Handles `/token` and `/api/device/<id>/command`
- **cad** (port 8200): Multi-provider CAD generation (Zoo/Tripo) with MinIO storage. Endpoint: `/api/cad/generate`
- **fabrication** (port 8300): OctoPrint/Klipper orchestration, MQTT command handling, printer state updates via `kitty/devices/<printer>/cmd/state`
- **safety** (port 8400): Policy engine for hazardous actions, UniFi Access checks, signature validation, audit logging
- **voice**: Speech transcript ingestion (`/api/voice/transcript`), parser/router integration, note logging
- **ui** (port 4173): Web dashboard, Fabrication Console, wall terminal view with MQTT subscriptions
- **cli**: SSH-friendly text interface (`kitty-cli`) for conversation, CAD preview, printer queuing
- **common**: Shared config, ORM models, logging, semantic cache, HTTP utilities imported by all Python services

### Supporting Infrastructure
- **mosquitto**: MQTT broker for device events, printer status, KITT state
- **homeassistant**: Device control bridge
- **redis**: LFU cache (2GB) for semantic cache and session state
- **postgres**: Persistent storage for routing audit logs, hazard audit, project notes
- **minio**: S3-compatible artifact storage for CAD files, STLs, GCODEs
- **prometheus/grafana/loki/tempo**: Observability stack for metrics, logs, traces

### Intelligent Routing (services/brain/src/brain/routing/)

The `BrainRouter` implements tiered inference with semantic caching:

1. **Semantic cache check** (Redis): Hash-based lookup for similar prompts
2. **Local tier** (llama.cpp): Primary model via Metal acceleration, 85% confidence threshold
3. **MCP tier** (Perplexity): Search-augmented generation for freshness
4. **Frontier tier** (GPT-4/Claude): Fallback for complex queries

Key files:
- `router.py`: Core routing logic, tier selection, cache integration
- `llama_cpp_client.py`: llama.cpp server client with model alias support
- `cloud_clients.py`: MCP and Frontier API clients
- `cost_tracker.py`: Per-tier cost accumulation for budget enforcement
- `audit_store.py`: PostgreSQL-backed routing decision log

Model configuration is in `.env`:
- `LLAMACPP_PRIMARY_MODEL`: Path to primary GGUF (e.g., Qwen2.5-72B q4_k_m)
- `LLAMACPP_CODER_MODEL`: Path to coder-specialized GGUF
- `LOCAL_MODEL_PRIMARY`, `LOCAL_MODEL_CODER`: Aliases for dynamic routing

### Shared Configuration (services/common/)

All services import from `common.config.Settings`:
- Pydantic settings with `.env` file loading
- Nested delimiter support for complex config (`MQTT__USERNAME`)
- Shared between Python services via volume mount in compose

Database models in `common.db.models`:
- SQLAlchemy ORM for routing logs, hazard audit, project notes
- Alembic migrations in `services/common/alembic/`

Security utilities in `common.security`:
- Bcrypt password hashing for admin users
- JWT token generation/validation
- Use: `python -c "from common.security import hash_password; print(hash_password('password'))"`

## Common Development Commands

### First-time Setup
```bash
# Install pre-commit hooks
pip install --upgrade pip pre-commit
pre-commit install

# Create environment file
cp .env.example .env
# Edit .env: set USER_NAME, HAZARD_CONFIRMATION_PHRASE, model paths, API keys

# Generate admin password hash
python -c "from services.common.src.common.security import hash_password; print(hash_password('changeme'))"
# Set ADMIN_USERS=admin:<hash> in .env

# Download GGUF models to /Users/Shared/Coding/models
huggingface-cli download Qwen/Qwen2.5-72B-Instruct-GGUF --local-dir /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-GGUF --include "*.gguf"
```

### Starting the Stack
```bash
# Start llama.cpp + all Docker services
./ops/scripts/start-kitty.sh

# (First run only) Apply database migrations
alembic -c services/common/alembic.ini upgrade head

# Stop everything
./ops/scripts/stop-kitty.sh
```

The start script:
1. Sources `.env`
2. Starts `llama-server` with configured models (logs to `.logs/llamacpp.log`)
3. Runs `docker compose up -d --build` with shared env file
4. Cleanup on Ctrl+C or script exit

### Development Workflow

**Python Services** (all services except UI):
```bash
# Lint and format (uses ruff)
ruff check services/brain/src --fix
ruff format services/brain/src

# Run pre-commit checks manually
pre-commit run --all-files

# Run tests (from repo root)
pytest tests/unit/test_router.py -v
pytest tests/integration/ -v

# Install service for development
pip install -e services/brain/
```

**UI (React/TypeScript)**:
```bash
cd services/ui

# Install dependencies
npm install

# Run dev server (with HMR)
npm run dev

# Production build
npm run build

# Preview production build
npm run preview

# Lint TypeScript
npm run lint
```

**CLI Client**:
```bash
# Install CLI
pip install -e services/cli/

# Interactive shell
kitty-cli shell

# Inside shell:
/model kitty-coder          # Switch to coder model
/verbosity 5                # Set detailed output
/cad design a bracket       # Generate CAD
/queue 0 printer_01         # Queue artifact to printer
/exit

# One-off command
kitty-cli say "What's the printer status?"
```

### Home Assistant Discovery

Auto-discover local Home Assistant OS instances on your network:

```bash
# Discover Home Assistant instances
python ops/scripts/discover-homeassistant.py

# Validate with token and update .env
python ops/scripts/discover-homeassistant.py --token YOUR_TOKEN --update-env

# Show all instances (default shows first only)
python ops/scripts/discover-homeassistant.py --all --timeout 10
```

**Getting a Long-Lived Access Token:**
1. Open Home Assistant → Profile → Long-Lived Access Tokens
2. Create Token → Name: "KITTY" → Copy token
3. Add to `.env`: `HOME_ASSISTANT_TOKEN=your_token`

**Enable auto-discovery on startup** by setting `HOME_ASSISTANT_AUTO_DISCOVER=true` in `.env`

### Accessing Services

- UI: http://localhost:4173
- Brain API docs: http://localhost:8080/docs
- Grafana dashboards: http://localhost:3000
- Prometheus: http://localhost:9090
- MinIO console: http://localhost:9001
- Home Assistant: http://homeassistant.local:8123 (or discovered URL)

### Database Migrations

Alembic configuration is in `services/common/alembic.ini`:

```bash
# Generate migration after model changes
alembic -c services/common/alembic.ini revision --autogenerate -m "description"

# Apply migrations
alembic -c services/common/alembic.ini upgrade head

# Rollback one version
alembic -c services/common/alembic.ini downgrade -1
```

## Key Architectural Patterns

### Environment Variable Substitution
The system prompt and voice prompt support runtime substitution:
- `{USER_NAME}` → from `USER_NAME` env var
- `{VERBOSITY}` → from `VERBOSITY` env var (1-5 scale)
- Rendered by `ops/scripts/start-kitty.sh` before llama.cpp launch

### Verbosity System
Configured per-request via query params, CLI commands, or UI controls:
- 1: Extremely terse
- 2: Concise
- 3: Detailed (default)
- 4: Comprehensive
- 5: Exhaustive

Implemented in `common.verbosity` and consumed by system prompts.

### Safety Workflows
Hazardous intents (unlock doors, enable power) require:
1. User-provided signature matching `HAZARD_CONFIRMATION_PHRASE`
2. UniFi Access zone verification
3. Audit log entry in PostgreSQL with camera bookmark

See `services/safety/workflows/hazard.py` and `services/brain/src/brain/orchestrator.py:39-62`.

### CAD Cycler
Multi-tier fallback pipeline in `services/cad/src/cad/cycler.py`:
1. Zoo API (parametric CAD)
2. Tripo API (organic/mesh generation)
3. Local CadQuery/FreeCAD (offline fallback)

Artifacts stored in MinIO with metadata in Redis cache.

## File Organization Conventions

- Each service follows: `services/<service>/src/<service>/`
- Shared utilities: `services/common/src/common/`
- Specs and plans: `specs/<feature-id>/` (spec.md, plan.md, tasks.md)
- Ops scripts: `ops/scripts/` (bash), `ops/runbooks/` (markdown procedures)
- Infrastructure: `infra/compose/` (docker-compose.yml, prometheus.yml, etc.)

## Testing Strategy

- Unit tests in `tests/unit/`: Mock external dependencies (MQTT, Redis, API clients)
- Integration tests in `tests/integration/`: Require running services (mark with `@pytest.mark.integration`)
- Use pytest fixtures for common setup (database sessions, mock clients)

## Important Notes

### llama.cpp Model Paths
Models must exist at the paths specified in `.env`. The system expects GGUF files downloaded via `huggingface-cli` or `git lfs` into `/Users/Shared/Coding/models`. Quantization naming convention: `*-q4_k_m*.gguf` for 4-bit K-quant medium.

### Docker Volume Mounts
Services mount their source as read-only (`:ro`) in compose. For live code reloading during development, remove `:ro` or develop outside containers.

### Remote Mode
Setting `REMOTE_MODE=true` disables voice capture. Toggled via MQTT topic or `.env` restart.

### MQTT Topics
Prefix with `TOPIC_PREFIX` (default: `kitty`):
- `kitty/devices/<device>/cmd` - Commands from gateway/UI/CLI to device handlers
- `kitty/devices/<device>/state` - Fabrication service publishes printer state
- `kitty/ctx/<conversation>` - Brain service broadcasts context and last intent
- `kitty/ai/routing/decision` - Routing telemetry (optional)
- `kitty/cad/jobs/<job>` - CAD progress updates
- `kitty/safety/events` - Safety approvals/audits
- `kitty/tts/<session>` - Voice/response playback (future)

### Budget Enforcement
`BUDGET_PER_TASK_USD` is advisory only. Real enforcement requires extending routing clients to report token usage and block on threshold breach.

## Data Model and Entities

The system uses PostgreSQL for persistent storage with the following key entities (see `specs/001-KITTY/data-model.md` for full schema):

### Core Entities
- **User**: Operators, engineers, safety leads, admins with role-based access
- **Zone**: Physical areas (welding_bay, printer_bay, laser_room, warehouse) with hazard levels and PPE requirements
- **Device**: Printers, cameras, lights, doors, power relays with capabilities and online state
- **ConversationSession**: Persistent conversation context with state (jsonb), active participants, last message timestamp

### Fabrication Pipeline
- **CADJob** → **CADArtifact** (STEP/DXF/STL from Zoo/Tripo/CadQuery/FreeCAD)
- **FabricationJob**: Links CAD artifacts to printer execution with status tracking
- **PrintMonitorEvent**: Computer vision detections (first_layer_ok, spaghetti_detected, nozzle_clog)

### Safety and Compliance
- **ZonePresence**: UniFi Access integration tracking user presence in hazardous zones
- **SafetyEvent**: Hazard requests with signatures, dual confirmation, evidence snapshots
- **AccessPolicy**: Per-zone rules for required roles, PPE, dual confirmation

### Observability
- **RoutingDecision**: Audit log for local/mcp/frontier tier selection with confidence, cost, latency
- **TelemetryEvent**: Device state changes, MQTT messages, printer status
- **Notification**: Multi-channel alerts (push/email/slack/webhook) for job completion, failures, safety events

### State Transitions
- FabricationJob: `preparing → printing → (paused ↔ printing) → completed|failed|aborted`
- CADJob: `queued → running → completed|failed`
- SafetyEvent: `pending → approved|denied`
- DeviceCommand: `pending → sent → acked|failed`

## User Stories and Design Goals

KITTY serves four primary personas (see `specs/001-KITTY/spec.md`):

1. **Fabrication Operator**: Hands-free control, print monitoring, quick insights via voice/CLI
2. **Design Engineer**: CAD iteration with parametric vs. mesh comparison, artifact lineage
3. **Facilities/Safety Lead**: Access control, hazard workflow management, compliance logs
4. **AI Systems Architect**: Routing optimization, model catalog, observability, cost control

### Key Success Metrics
- ≥70% requests served locally (local-first SLO)
- ≥50% cloud cost reduction vs. cloud-only baseline
- P95 latency ≤1.5s for local device queries
- 0 safety incidents with >95% success for canonical flows

### Non-Goals
- Fully autonomous hazardous operations without human confirmation
- Perfect mesh-to-parametric conversion (rely on native parametric when critical)

## API Integration Reference

The system integrates with 18+ external systems (see `Research/APIinfo.md` for full API reference):

### Authentication
- **FastAPI services**: OAuth2 with JWT (Bearer tokens), HS256 algorithm
- **Home Assistant**: Long-lived access tokens via `/api/auth/long_lived_access_token`
- **UniFi Access**: API tokens with door/zone control permissions
- **External providers**: API keys in `.env` (OpenAI, Anthropic, Perplexity, Zoo, Tripo)

### Function Calling
Gateway and brain services support OpenAI-compatible function calling schema for device control:
```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "control_printer",
      "parameters": {"type": "object", "properties": {...}}
    }
  }]
}
```

### Deployment Patterns
- ASGI (Uvicorn) for production: `uvicorn --workers 4` (multi-core M3 Ultra)
- Automatic OpenAPI docs at `/docs` and `/redoc` for all FastAPI services
- JWT tokens require explicit expiration; set `ACCESS_TOKEN_EXPIRE_MINUTES` in `.env`

## Reference Implementation

The `Reference/JarvisV3/` directory contains a Streamlit-based AI assistant that demonstrates:
- Dual interaction modes (text + realtime audio)
- OpenAI realtime API integration with voice selection
- Dynamic settings management (API keys, model, prompts, function calling)
- VAD (Voice Activity Detection) configuration

This serves as a reference for voice interaction patterns and OpenAI API integration.

## Workflow Processes

### Voice Interaction Workflow
1. Audio captured via Whisper or UI microphone → `POST /api/voice/transcript`
2. Voice parser classifies intent (device command, note, routing request)
3. For conversational prompts:
   - Voice service calls brain via shared orchestrator
   - Brain checks semantic cache, runs local model, escalates if confidence < threshold
   - Response pushed back to voice service and optionally over MQTT for UI display
4. For device intents, safety workflow executes before MQTT command is published

### CLI Workflow
1. CLI reads `.env` for API base URLs, default model alias, verbosity
2. `kitty-cli shell` maintains conversation ID, user ID, cached artifacts
3. Commands: `/model`, `/verbosity`, `/cad`, `/queue`, `/list`, `/exit`
4. Text prompts call `POST /api/query` with `modelAlias` and `verbosity` overrides
5. `kitty-cli cad "<prompt>"` calls `/api/cad/generate`, stores artifacts, can queue prints

### CAD Generation & Printing
1. Prompt submitted via UI/CLI → `cad.generate`
2. CAD cycler fans out to Zoo, Tripo, and optional local fallbacks
3. Artifacts stored in MinIO, metadata returned
4. UI/CLI selects artifact & printer → gateway publishes MQTT command
5. Fabrication service reacts, enqueues job to OctoPrint, updates printer state

### Safety Workflow
1. Hazardous intent (unlock, high-power) triggers safety service
2. Validates signature phrase (default: "Confirm: proceed" or `HAZARD_CONFIRMATION_PHRASE`)
3. Confirms user role and zone presence via UniFi Access
4. Logs event with snapshot/camera bookmark
5. If any check fails, orchestrator responds with refusal and remediation steps

## Important Environment Variables

| Variable | Purpose |
|----------|---------|
| `USER_NAME` | Rendered into system prompt and CLI defaults |
| `ADMIN_USERS` | Semicolon-separated `user:hash` list (bcrypt) for local admin authentication |
| `LLAMACPP_PRIMARY_MODEL` / `LLAMACPP_CODER_MODEL` | Paths to GGUF files in `/Users/Shared/Coding/models` |
| `LOCAL_MODEL_PRIMARY` / `LOCAL_MODEL_CODER` | Aliases used by router/UI/CLI (e.g., `kitty-primary`, `kitty-coder`) |
| `VERBOSITY` | Global default (1–5) influencing API responses; adjustable per request |
| `BUDGET_PER_TASK_USD` | Advisory budget shown in routing prompt; live enforcement TBD |
| `HAZARD_CONFIRMATION_PHRASE` | Safety workflow guard phrase (default: "Confirm: proceed") |
| `OFFLINE_MODE` | When `true`, prevents automatic cloud escalation (local inference only) |
| `CONFIDENCE_THRESHOLD` | Minimum confidence to stay on local tier (default: 0.80) |

## Runbooks and Documentation

- **Comprehensive architecture**: `docs/project-overview.md` - detailed service responsibilities, communication layers, workflows
- Deployment checklist: `ops/runbooks/deployment-checklist.md`
- Security hardening: `ops/runbooks/security-hardening.md`
- Feature specs: `specs/001-KITTY/` (spec.md, plan.md, tasks.md, data-model.md, research.md, quickstart.md)
- API integration guide: `Research/APIinfo.md` - 18+ external system integrations with auth patterns
- Voice-to-print workflows: `Research/VoiceToPrint.md`
- Reference implementations: `Reference/JarvisV3/` (Streamlit voice assistant with OpenAI realtime API)
- Docker Brain current build time: 15 m 14 s, Model loading time: 5 m