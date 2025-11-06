# KITTY Warehouse Orchestrator

> Offline-first control plane for fabrication labs: voice, CLI, CAD generation, printer workflows, and safety automation running on a Mac Studio M3 Ultra.

This repository hosts the implementation plan, infrastructure, and services that transform a Mac Studio into a warehouse-grade conversational assistant. KITTY runs local language models through llama.cpp, escalates to cloud providers when needed, orchestrates CAD jobs, and drives printers, cameras, lighting, and access control.

---

## Table of contents

1. [Feature overview](#feature-overview)
2. [System requirements](#system-requirements)
3. [First-time setup](#first-time-setup)
4. [Launching the stack](#launching-the-stack)
5. [Operating KITTY](#operating-kitty)
6. [Observability & budgeting](#observability--budgeting)
7. [Directory map](#directory-map)
8. [Troubleshooting](#troubleshooting)
9. [Continuous integration](#continuous-integration)

---

## Feature overview

- **Local-first inference** – llama.cpp backed by Metal acceleration serves primary and coder models; router promotes to Perplexity/GPT/Claude only when confidence or freshness demands.
- **Voice & text control** – Whisper/voice service for hands-free commands and a SSH-friendly CLI (`kitty-cli`) for remote sessions.
- **CAD AI cycling** – Zoo (parametric) + Tripo (organic) pipelines, offline CadQuery/FreeCAD fallback, automated artifact storage.
- **Fabrication workflows** – OctoPrint/Klipper integration, printer state via MQTT, one-click queue from UI or CLI.
- **Safety engine** – UniFi Access integration, confirmation phrases, audit logging, and hazard workflows.
- **Observability** – Prometheus/Grafana dashboards, routing audit logs, semantic cache statistics, configurable verbosity.

---

## System requirements

| Component | Notes |
|-----------|-------|
| Hardware | Mac Studio M3 Ultra (256 GB unified memory recommended). |
| OS | macOS 14 or newer with Rosetta + Xcode command line tools. |
| Dependencies | Docker Desktop, Python 3.11, Node 20, Homebrew (for git-lfs, huggingface-cli, etc.). |
| Local models | GGUF shards stored under `/Users/Shared/Coding/models` (aliases `kitty-primary`, `kitty-coder`). |
| Network | Optional Tailscale for remote mode; no inbound ports required. |

---

## First-time setup

```bash
git clone https://github.com/.../KITT.git
cd KITT

# Install developer tooling
pip install --upgrade pip pre-commit
pre-commit install

# Create environment file
cp .env.example .env

# Configure admin credentials (bcrypt hash)
python -c "from services.common.src.common.security import hash_password; print(hash_password('changeme'))"
# Set ADMIN_USERS=admin:<hash> in .env

# Edit .env to match your model paths, API keys, and safety phrases
```

### Download models

1. Clone GGUF repositories into `/Users/Shared/Coding/models` (examples):
   ```bash
   huggingface-cli download Mungert/gemma-3-27b-it-GGUF --local-dir /Users/Shared/Coding/models/gemma-3-27b-it-GGUF --include "*.gguf"
   huggingface-cli download Qwen/Qwen2.5-72B-Instruct-GGUF ...
   ````
2. Update `LLAMACPP_PRIMARY_MODEL` and `LLAMACPP_CODER_MODEL` in `.env` to point at the quantisations you want to serve (for example `q4_k_m`).
3. Ensure `USER_NAME`, `HAZARD_CONFIRMATION_PHRASE`, and other placeholders reflect your environment.

---

## Launching the stack

Everything runs through the launcher scripts under `ops/scripts/`.

```bash
# Start llama.cpp + Docker compose
./ops/scripts/start-kitty.sh

# (first run) apply database migrations for shared models
alembic -c services/common/alembic.ini upgrade head
```

`start-kitty.sh` will:

1. Source `.env` and render the system prompt with your USER_NAME.
2. Start `llama-server` using the configured models (logs in `.logs/llamacpp.log`).
3. Launch Docker Compose with the same env file so all services share configuration.

The script keeps running; press `Ctrl+C` or use `./ops/scripts/stop-kitty.sh` to stop compose and the llama.cpp process.

---

## Operating KITTY

### Web console

- UI: `http://localhost:4173`
- Brain API docs: `http://localhost:8080/docs`
- Use the **Fabrication Console** tab to:
  - Change verbosity and model alias for ad-hoc queries.
  - Generate CAD previews (`/api/cad/generate`).
  - Inspect artifact metadata and queue a print to OctoPrint.

### CLI (SSH-friendly)

```bash
pip install -e services/cli      # one-time install
kitty-cli shell                  # interactive session
```

Inside the shell:
- `/model <alias>` – change the local model for routing.
- `/verbosity <1-5>` – override response detail level.
- `/cad <prompt>` – run the CAD cycler and cache artifacts.
- `/queue <idx> <printer>` – queue the cached artifact on a printer.
- `/exit` – end session.

For quick one-offs: `kitty-cli say "Summarize today’s print queue"`.

### Voice service

- The voice FastAPI service consumes audio transcripts (`/api/voice/transcript`).
- `VOICE_SYSTEM_PROMPT` in `.env` now injects `USER_NAME`, locale, and model hints automatically.
- Start/stop the voice module with the main compose stack; remote mode can disable voice capture.

### REST shortcuts

- Conversation: `POST /api/query`
- CAD: `POST /api/cad/generate`
- Printer command: `POST /api/device/<printerId>/command`
- Routing logs: `GET /api/routing/logs`
- Local models: `GET /api/routing/models`

All endpoints honour the verbosity and model alias parameters used by the UI/CLI.

---

## Observability & budgeting

- **Prometheus/Grafana** (`http://localhost:3000`): routing hit/miss, latency, semantic cache metrics, cost tracker totals.
- **Logs**: structured JSON via Loki; llama.cpp logs in `.logs/llamacpp.log`.
- **Budget**: `BUDGET_PER_TASK_USD` is available through `PerformanceSettings` and surfaced in the system prompt. Real-time enforcement requires extending the routing clients to record provider token costs.
- **Safety**: audit trails stored in PostgreSQL (`hazard_audit` table) with camera bookmark references.

---

## Directory map

| Path | Purpose |
|------|---------|
| `infra/compose/` | Docker Compose definitions, Prometheus config, Home Assistant bridge |
| `services/` | Service code (brain, cad, fabrication, safety, voice, ui, cli) |
| `services/common/` | Shared config, logging, ORM models, Alembic migrations |
| `services/cli/` | SSH/terminal client (`kitty-cli`) |
| `specs/001-KITTY/` | Plan, spec, data model, API contracts, tasks checklist |
| `ops/runbooks/` | Deployment, observability, and security procedures |
| `docs/` | Architecture overview, quickstart, research notes |

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| `start-kitty.sh` cannot find `.env` | Ensure you created `.env` at the repo root (`cp .env.example .env`). |
| llama.cpp refuses to start | Verify `LLAMACPP_*` paths exist and the `llama-server` binary is installed/built with Metal support. |
| UI shows “Voice Disabled (Remote Mode)” | Remote mode is active; update the MQTT topic or toggle the remote mode flag in `.env` and restart gateway. |
| CLI returns HTTP errors | Confirm services are running (`docker compose ps`) and endpoints are reachable (`curl http://localhost:8080/healthz`). |
| Disk usage huge in `/models` | Each repo clones multiple quantisations. Remove unused shards or prune git-lfs objects. |

---

## Continuous integration

GitHub Actions lint shared Python utilities, run import checks, and validate the compose definition. Pre-commit hooks mirror the formatting/typing checks locally.
