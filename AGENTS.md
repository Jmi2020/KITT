# KITT Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-11-14

## Active Technologies

- Python 3.11 + FastAPI/Pydantic/SQLAlchemy for the `brain`, `gateway`, `fabrication`, `common`, and automation services
- TypeScript 5.x + React/Vite (Vision PWA) with pnpm; shared CLI/TUI stacks in Python (kitty-cli, unified launcher, model manager)
- Bash/YAML ops tooling (`ops/scripts/*.sh`, `infra/compose/docker-compose.yml`) orchestrating Docker, llama.cpp dual servers, and observability stack
- Messaging & devices: paho-mqtt, Home Assistant API, OctoPrint/Klipper REST, UniFi cameras, Prometheus/Grafana, Redis, PostgreSQL, MinIO
- AI/ML runtimes: llama.cpp/MLX (Athene V2 Q4 on 8083, Llama‑3.3 70B F16 on 8082, Hermes summary model, Gemma 3 Vision), Whisper.cpp STT, Piper TTS
- CAD/3D stack: Zoo CAD SDK, Tripo API + local CadQuery/FreeCAD and trimesh; artifact sync via `/Users/Shared/KITTY/artifacts`
- Research toolchain: Perplexity MCP SDK, self-hosted SearXNG, Brave Search fallback, Jina Reader content extraction, DuckDuckGo/Perplexity fallthrough

## Project Structure

```text
.
├── services/
│   ├── brain/                    # prompts, routing, tool registry
│   ├── gateway/                  # FastAPI ingress + io-control routes
│   ├── fabrication/              # printer orchestration, monitoring
│   ├── common/                   # io_control, settings, shared libs
│   ├── cli/                      # kitty-cli REPL + commands
│   ├── launcher/                 # unified TUI (`kitty`)
│   ├── model-manager/            # llama.cpp model selection TUI/CLI
│   └── ui/                       # React/Vite vision gallery
├── ops/scripts/                  # startup/health scripts (start-kitty, watchdog, memory)
├── infra/compose/                # docker-compose stack
├── docs/ + Reference/            # feature guides, roadmap, IO control docs
├── tests/                        # unit/integration/e2e + CAD/phase4 suites
└── storage/, data/, logs/, etc.  # runtime artifacts and logs
```

## Startup & Operations

- `./ops/scripts/start-kitty-validated.sh` boots llama.cpp dual servers, Docker stack, Hermes/Gemma helpers, and validates service health; use instead of legacy start script.
- Manual flow: `./ops/scripts/start-llamacpp-dual.sh` → `docker compose -f infra/compose/docker-compose.yml up -d --build` → verify with `docker compose ... ps`.
- Unified launcher (`pip install -e services/launcher/` → `kitty`) exposes dual-server health, Docker status, reasoning logs, shortcuts to CLI/model-manager.
- CLI: `pip install -e services/cli/ && kitty-cli shell` for interactive REPL; `/agent`, `/trace`, `/verbosity`, `/remember`, `/memories`, `/generate`, `/vision`, `/cad`, `/queue`, `/usage`, `/reset`, `/exit` mirror the internal ReAct router. Quick calls: `kitty-cli say "…"`, `kitty-cli images …`, `kitty-cli generate-image …`.
- Vision PWA: `cd services/ui && pnpm install` (once) then `pnpm dev --host 0.0.0.0 --port 4173`; configure `KITTY_UI_BASE`, `KITTY_CLI_API_BASE`, `VITE_API_BASE`.
- Model management: `pip install -e services/model-manager/ && kitty-model-manager tui` (interactive) or `kitty-model-manager start|stop|scan|switch` (non-interactive); Hermes summary + Gemma vision servers toggle via `LLAMACPP_SUMMARY_ENABLED`, `LLAMACPP_VISION_ENABLED`.
- Maintenance scripts: `./ops/scripts/memory-snapshot.sh` (baseline), `./ops/scripts/llamacpp-watchdog.sh [--kill]` (clean stray llama.cpp), `./ops/scripts/benchmark-llamacpp.sh`, `./ops/scripts/setup-artifacts-dir.sh`.
- Autonomy budget/status: `curl -s "http://localhost:8000/api/autonomy/status?workload=scheduled" | jq` and `/api/autonomy/budget?days=7`; configure via `AUTONOMOUS_ENABLED`, `AUTONOMOUS_DAILY_BUDGET_USD`, `AUTONOMOUS_IDLE_THRESHOLD_MINUTES`.

## Testing & Quality

- Unit/integration/e2e: `pytest tests/unit -v`, `pytest tests/integration -v`, `pytest tests/e2e -v`, or targeted modules (e.g., `pytest tests/unit/test_print_outcome_tracker.py -v`).
- Coverage: `pytest tests/ --cov=services --cov-report=html` then `open htmlcov/index.html`.
- CAD/voice flows: `./tests/test_cad_e2e.sh`, `./tests/test_kitty_cad.sh`.
- Lint/format: `ruff check services/ --fix`, `ruff format services/`, `pre-commit run --all-files`.

## Operational Guardrails & Tooling

- `KittySystemPrompt` always wraps tool-capable prompts in `<user_query>…</user_query>` and fixes temperature=0 so the Athene V2 Q4 orchestrator never discards tool instructions (`services/brain/src/brain/prompts/unified.py`).
- Paid providers (Perplexity MCP, OpenAI, Anthropic, etc.) demand the override keyword (default `omega`) inside the prompt plus configured keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `API_OVERRIDE_PASSWORD`); budgets enforced via `BUDGET_PER_TASK_USD` + `CONFIDENCE_THRESHOLD`.
- Freshness heuristics (`services/brain/src/brain/routing/freshness.py`) auto-set `freshness_required` for anything mentioning “today/current/latest,” embed the UTC timestamp, and bias routing toward live tools such as `web_search`.
- Web search cascade (`brain.routing.web_search`): SearXNG container (default `http://searxng:8080`) → Brave Search (`BRAVE_SEARCH_API_KEY`/`BRAVE_SEARCH_ENDPOINT`) → DuckDuckGo/Perplexity fallback; tool results are summarized through kitty-q4/F16 before reaching the CLI.
- Content extraction: `fetch_webpage` first calls Jina Reader (set `JINA_API_KEY`, `JINA_READER_BASE_URL`), then falls back to the local BeautifulSoup parser to keep responses flowing.
- Observability: Prometheus/Grafana + `/metrics`, CLI `/trace`, and TUI reasoning log viewer expose routing cost/tier statistics; `KITTY_CLI_TIMEOUT` defaults to 900 s for long research prompts.

## I/O Control Dashboard

- Feature registry/state manager lives under `services/common/src/common/io_control/`. `feature_registry.py` defines devices/APIs + health probes, `state_manager.py` handles dependency resolution, restart previews, and persistence.
- New helpers: `health_checks.py` validates API keys/services (Perplexity, OpenAI, Anthropic, Zoo, Tripo, MQTT, MinIO, PostgreSQL, printers, cameras); `presets.py` ships Development/Production/Cost-Saving/Testing/Minimal presets with cost estimates; `tool_availability.py` surfaces active tool/function names based on I/O state.
- Gateway routes (`services/gateway/src/gateway/routes/io_control.py`) now expose:
  - `GET /api/io-control/health` – per-feature health results
  - `GET /api/io-control/features/{feature_id}/dependencies` – dependency gaps + auto-resolve map
  - `POST /api/io-control/preview` – dependency/cost/restart/conflict/health impact before applying
  - `GET /api/io-control/tool-availability` – ReAct tools and MCP functions unlocked under the current config
  - `GET /api/io-control/presets`, `GET /api/io-control/presets/{id}`, `POST /api/io-control/presets/{id}/apply` – quick mode switching with optional persistence
- Use `docs/IO_CONTROL_DASHBOARD.md` for complete API payloads plus the “Everything Has a Switch” development workflow.

## Fabrication Intelligence & Monitoring

- Print outcome tracking is centralized in `services/fabrication/src/fabrication/monitoring/outcome_tracker.py` (with companion `camera_capture.py`). The service records factual job data via `PrintOutcomeData` and optional human feedback through `record_human_feedback`.
- Gateway endpoints (via `services/fabrication/src/fabrication/app.py`) now align with the monitoring module:
  - `POST /api/fabrication/outcomes`
  - `GET /api/fabrication/outcomes/{job_id}`
  - `GET /api/fabrication/outcomes`
  - `PATCH /api/fabrication/outcomes/{job_id}/review`
  - `GET /api/fabrication/outcomes/statistics` (success rate, avg quality/duration, total cost; filterable by printer/material)
- `ENABLE_*` feature flags (Phase 4 I/O controls) gate cameras, MinIO uploads, print intelligence, and human feedback flows; keep them false in dev to rely on mocks, enable incrementally for production hardware.
- Snapshot refs and CAD artifacts remain synced to `/Users/Shared/KITTY/artifacts` via `./ops/scripts/setup-artifacts-dir.sh`; CLI automatically threads `/vision` selections into `<available_image_refs>` blocks before CAD/tool calls.

## Recent Changes

- 2025-11-14: I/O Control Dashboard gained health checks, quick presets with cost warnings, dependency resolution helpers, restart previews, and tool availability reporting (see `services/common/src/common/io_control/*`, `services/gateway/src/gateway/routes/io_control.py`, `docs/IO_CONTROL_DASHBOARD.md`).
- 2025-11-14: Fabrication print outcome tracking now reuses `monitoring/outcome_tracker.py` for all API endpoints, adds statistics reporting, and removes duplicate trackers (`services/fabrication/src/fabrication/app.py`, `monitoring/outcome_tracker.py`).
- 001-KITTY: Added Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose) + FastAPI, Pydantic, paho-mqtt, SQLAlchemy, Home Assistant API, OctoPrint REST, Perplexity MCP SDK, Zoo CAD SDK, Tripo API, CadQuery/FreeCAD, llama.cpp/MLX runtimes, Whisper.cpp, Piper

<!-- MANUAL ADDITIONS START -->
- 2025-11-14: **I/O Control Upgrades** — `feature_registry`, `state_manager`, `health_checks`, `presets`, and `tool_availability` power `/api/io-control/*` endpoints for health/cost/preset/dependency/tool visibility so agents must consult them before toggling devices or cloud APIs.
- 2025-11-14: **Fabrication Outcome APIs** — `/api/fabrication/outcomes{,/statistics,/…/review}` now pipe through `monitoring.outcome_tracker.PrintOutcomeTracker`; always emit factual telemetry first, then attach optional human feedback to avoid regressing the consolidated tracker.
- 2025-11-06: **Cornerstone** — All tool-capable queries now flow through the `<user_query>` wrapper produced by `KittySystemPrompt` (`services/brain/src/brain/prompts/unified.py`). This keeps tool instructions intact, locks temperature to 0, and prevents hallucinated tools; see `README.md` (CLI workflow) for operator guidance.
- 2025-11-06: **Autonomy Guardrails** — `/api/autonomy/status` + Prometheus gauges expose daily budget, idle state, and readiness (scheduled vs. exploration) driven by `ResourceManager`. Configure with `AUTONOMOUS_ENABLED`, `AUTONOMOUS_DAILY_BUDGET_USD`, and `AUTONOMOUS_IDLE_THRESHOLD_MINUTES=120`.
- 2025-11-06: **Freshness Heuristics** — Time-sensitive prompts now auto-set `freshness_required`, embed the current UTC timestamp, and instruct the LLM to prefer live tools (`web_search`) for anything after its training cutoff (`services/brain/src/brain/routing/freshness.py`, `KittySystemPrompt`).
- 2025-11-06: **Web Search Cascade** — `web_search` now tries self-hosted SearXNG, then Brave’s free tier, before falling back to DuckDuckGo/Perplexity. Configure `SEARXNG_BASE_URL`, `BRAVE_SEARCH_API_KEY`, and `BRAVE_SEARCH_ENDPOINT`. See README “Web Search Stack” for setup.
- 2025-11-08: **Content Extraction** — `fetch_webpage` calls Jina Reader for full-page Markdown and drops to the local BeautifulSoup parser if the API is unavailable. Configure `JINA_API_KEY` / `JINA_READER_BASE_URL` in `.env`.
<!-- MANUAL ADDITIONS END -->
