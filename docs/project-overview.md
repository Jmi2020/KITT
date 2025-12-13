# KITTY Warehouse Orchestrator — Project Overview

## 1. Mission & Scope

KITTY transforms a Mac Studio M3 Ultra into an offline-first control plane for fabrication labs and smart warehouses. The system’s responsibilities include:

- Conversational orchestration of printers, lighting, cameras, power, and physical access.
- Hybrid CAD generation (parametric + organic) with offline fallbacks and artifact lineage.
- Safety-by-design workflows (identity checks, confirmation phrases, audit logging).
- Confidence-based model routing that prefers local inference and escalates to cloud providers only when required.
- Unified operator experiences: voice, web dashboard, wall terminals, and an SSH-friendly CLI.

## 2. Technology Stack

### Core Languages & Frameworks

| Domain | Technologies |
|--------|-------------|
| Services | Python 3.11, FastAPI, Pydantic, SQLAlchemy, Alembic |
| UI | TypeScript, React (Vite), MQTT client libraries |
| CLI | Python, Typer, Rich |
| Messaging | MQTT (Mosquitto), Redis Streams (semantic cache) |
| Data | PostgreSQL (audit, lineage), MinIO (artifact storage) |
| Observability | Prometheus, Grafana, Loki, Tempo |
| Local AI | llama.cpp (GGUF models), Whisper.cpp for STT, Kokoro ONNX/Piper for TTS, Porcupine wake word |
| Cloud connectors | Perplexity MCP, OpenAI (frontier), Anthropic, Google Gemini, Zoo CAD, Tripo API |

### Infrastructure

- Docker Compose stack (`infra/compose/docker-compose.yml`) for services, databases, and observability.
- Host-level llama.cpp server launched via `ops/scripts/start-kitty.sh` (Metal acceleration, configurable models).
- Configuration via `.env` (shared across host scripts and containers).
- Tailscale for optional remote mode (read-only enforcement when offsite).

## 3. Services & Responsibilities

| Service | Purpose | Key Interfaces |
|---------|---------|----------------|
| `brain` | Conversational router, context management, safety integration, routing logs. | `/api/query`, `/api/routing/logs`, `/api/routing/models`, Prometheus metrics |
| `gateway` | Public ingress, OAuth2 token issuance, device command proxy. | `/api/device/<id>/command`, `/token`, remote-mode middleware |
| `fabrication` | OctoPrint/Klipper orchestration, MQTT command handling, printer state updates. | `kitty/devices/<printer>/cmd/state` topics |
| `cad` | Multi-provider CAD generation (Zoo/Tripo) with MinIO storage. | `/api/cad/generate`, artifact metadata |
| `safety` | Policy engine for hazardous actions, UniFi Access checks, signature validation, audit logging. | Shared safety workflow invoked by `brain` |
| `voice` | STT/TTS pipeline (Whisper, Kokoro ONNX, Piper), wake word detection, parser/router. | `/api/voice/ws`, `/api/voice/status`, MQTT notifications |
| `ui` | Web dashboard, Fabrication Console, wall terminal view. | HTTP front-end, MQTT subscriptions |
| `cli` | SSH-friendly text interface for conversation, CAD preview, printer queuing. | `kitty-cli` commands calling REST APIs |
| `common` | Shared config, ORM models, logging, semantic cache, HTTP utilities. | Imported by all Python services |

## 4. Runtime Launch Flow

1. **Environment preparation**
   - Operator copies `.env` from `.env.example`, configures model paths, API keys, `USER_NAME`, safety phrases, etc.
   - Optional: `pip install -e services/cli` for the CLI.

2. **Start-up**
   - `./ops/scripts/start-kitty.sh`
     1. Sources `.env` and sets shared environment variables.
     2. Launches `start-llamacpp.sh` (logs to `.logs/llamacpp.log`) with chosen GGUF models (`kittty-primary`, `kitty-coder`).
     3. Runs `docker compose --env-file .env -f infra/compose/docker-compose.yml up -d --build`.
   - `alembic -c services/common/alembic.ini upgrade head` (first run) upgrades shared database schema.

3. **Shutdown**
   - `./ops/scripts/stop-kitty.sh` tears down Docker services and stops `llama-server`.

## 5. Communication Layers

### REST API Surface

- **Brain** (`http://localhost:8080`):
  - `POST /api/query` — main conversational endpoint.
  - `GET /api/routing/logs` — audit decisions (tier, confidence, latency, cost).
  - `GET /api/routing/models` — advertised local/frontier models.
  - `GET /healthz` — service status.
- **Gateway** (`http://localhost:8080/api/device/{id}/command`) — device orchestration via MQTT.
- **CAD** (`http://localhost:8200/api/cad/generate`) — returns artifact metadata (provider, type, location).

### MQTT Topics

| Topic | Description |
|-------|-------------|
| `kitty/devices/<device>/cmd` | Commands sent from gateway/UI/CLI to device handlers. |
| `kitty/devices/<device>/state` | Fabrication service publishes printer state. |
| `kitty/ctx/<conversation>` | Brain service broadcasts context and last intent. |
| `kitty/ai/routing/decision` | Routing telemetry (optional). |
| `kitty/cad/jobs/<job>` | CAD progress updates. |
| `kitty/safety/events` | Safety approvals/audits. |
| `kitty/tts/<session>` | Voice/response playback (future). |

### Database & Storage

- **PostgreSQL** — tables for routing audits, safety logs, conversation projects, cost summaries.
- **MinIO** — stores CAD artifacts (STEP, GLB, DXF) with metadata references stored in PostgreSQL.
- **Redis Streams** — semantic cache (prompt → response, confidence) with TTL control.

## 6. Interaction Modes

### Voice Workflow

1. Audio captured (e.g., via Whisper or UI microphone) → `POST /api/voice/transcript`.
2. Voice parser (`services/voice/src/voice/parser.py`) classifies intent (device command, note, routing request).
3. For conversational prompts:
   - `voice` service calls `brain` via shared orchestrator.
   - `brain` checks semantic cache, runs local model (llama.cpp alias from `LOCAL_MODEL_*`), escalates if confidence < threshold.
   - Decision (local/MCP/frontier) recorded in routing audit, cost tracker updated.
   - Response pushed back to voice service and optionally over MQTT for UI display.
4. For device intents, the orchestration pipeline ensures safety workflow is executed before MQTT command is published.

### CLI Workflow (`kitty-cli`)

1. CLI reads `.env` (via dotenv) for API base URLs, default model alias, verbosity.
2. `kitty-cli shell`
   - Maintains conversation ID, user ID, cached artifacts.
   - `/model`, `/verbosity`, `/cad`, `/queue`, `/list`, `/exit` commands map to brain/CAD/gateway APIs.
   - Text prompts call `POST /api/query` with `modelAlias` and `verbosity` overrides.
3. `kitty-cli cad "<prompt>"` mirrors Fabrication Console: calls `/api/cad/generate`, stores latest artifacts, can queue prints.

Both interfaces ultimately converge on the same REST/MQTT endpoints, ensuring voice and text interactions follow identical safety and routing rules.

## 7. Key Processes

### Confidence-Based Routing

1. `BrainRouter.route` hashes prompt for cache lookup.
2. Local inference:
   - llama.cpp called via HTTP (`/completion`, alias from configuration).
   - Response packaged with metadata (model, host).
3. If confidence < `local_confidence` or `force_tier == MCP`, escalate:
   - MCP client queries Perplexity (cost estimate recorded).
   - Frontier client (OpenAI) optional fallback.
4. `CostTracker` aggregates spend by tier; metrics exposed for Grafana.
5. All decisions logged in PostgreSQL (tier, latency, cost estimate, cached flag).

### CAD Generation & Printing

1. Prompt submitted via UI/CLI → `cad.generate`.
2. CAD cycler fans out to Zoo, Tripo, and optional local fallbacks, storing results in MinIO.
3. Artifacts returned with provider/type/URL metadata.
4. UI/CLI selects artifact & printer → `gateway` publishes MQTT command.
5. Fabrication service reacts, enqueues job to OctoPrint, updates printer state.

### Safety Workflow

1. Hazardous intent (unlock, high-power) triggers `safety` service:
   - Validates signature phrase (`Confirm: proceed` or configured value).
   - Confirms user role and zone presence via UniFi Access.
   - Logs event with snapshot/camera bookmark.
2. If any check fails, orchestrator responds with refusal and remediation steps.

## 8. Configuration Highlights

| Variable | Purpose |
|----------|---------|
| `USER_NAME` | Rendered into system prompt and CLI defaults (`ssh-operator`). |
| `ADMIN_USERS` | Semicolon-separated `user:secret` list (bcrypt hashes preferred) for local admin authentication. |
| `LLAMACPP_*` | Controls host-run llama.cpp instance (models, context, Metal options). |
| `LOCAL_MODEL_PRIMARY` / `LOCAL_MODEL_CODER` | Default aliases used by router/UI/CLI. |
| `VERBOSITY` | Global default (1–5) influencing API responses; adjustable per request. |
| `BUDGET_PER_TASK_USD` | Configures routing prompt (current measurement uses static tier costs; live cost tracking can be added via provider APIs). |
| `HAZARD_CONFIRMATION_PHRASE` | Safety workflow guard phrase. |
| `OFFLINE_MODE` | When `true`, prevents automatic cloud escalation (local inference only). |

## 9. Next Steps & Extensibility

- Integrate real-time cost accounting from provider APIs to enforce `BUDGET_PER_TASK_USD`.
|- Build CLI autocompletion for known printers/models and add log streaming commands.
- Add WebRTC/MediaRecorder capture for browser voice input (currently placeholder).
- Expand safety workflows with PPE detection (camera feed integration).
- Provide Terraform/Ansible automation for remote deployment beyond Docker Desktop.

---\n+
**Quick reference**\n+- Launch: `./ops/scripts/start-kitty.sh`\n+- Stop: `./ops/scripts/stop-kitty.sh`\n+- UI: `http://localhost:4173`\n+- CLI: `kitty-cli shell`\n+- Voice: `POST /api/voice/transcript`\n+- CAD: `POST /api/cad/generate`\n+- Printer command: `POST /api/device/<printer>/command`\n+- Routing logs: `GET /api/routing/logs`\n*** End Patch
