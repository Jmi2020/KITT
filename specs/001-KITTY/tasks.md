# Tasks: KITTY Warehouse Orchestrator

**Input**: Design documents from `/specs/001-KITTY/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish container orchestration, broker configuration, and developer tooling aligned with API integration requirements.

- [X] T001 Define container stack (FastAPI, Mosquitto, Home Assistant, Ollama, Redis, Postgres, Prometheus, Grafana, Loki, Tempo) in `infra/compose/docker-compose.yml`
- [X] T002 Create Mosquitto broker configuration with QoS/retained policies in `infra/compose/mosquitto.conf`
- [X] T003 Create Home Assistant MQTT bridge configuration in `infra/compose/homeassistant/configuration.yaml`
- [X] T004 Create environment template with integration secrets in `infra/compose/.env.example`
- [X] T005 [P] Configure CI workflow for services and UI in `.github/workflows/ci.yml`
- [X] T006 [P] Add repository-wide pre-commit hooks in `.pre-commit-config.yaml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Provide shared settings, security, and integration primitives required by all services.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T007 Create Python project manifest for shared utilities in `services/common/pyproject.toml`
- [X] T008 [P] Implement settings loader supporting `.env` overrides in `services/common/src/common/config.py`
- [X] T009 [P] Implement MQTT helper with QoS/retain helpers in `services/common/src/common/messaging.py`
- [X] T010 [P] Set up structured logging helpers (JSON + trace IDs) in `services/common/src/common/logging.py`
- [X] T011 Establish shared Pydantic schemas for entities in `services/common/src/common/schemas.py`
- [X] T012 [P] Implement OAuth2/JWT security helpers per FastAPI guide in `services/common/src/common/security.py`
- [X] T013 [P] Implement REST client wrapper with bearer/API-key support in `services/common/src/common/http.py`
- [X] T014 [P] Define integration credential models in `services/common/src/common/credentials.py`
- [X] T015 Implement database migrations scaffold (Alembic) in `services/common/alembic/`
- [X] T016 [P] Define SQLAlchemy ORM models for core entities in `services/common/src/common/db/models.py`
- [X] T017 [P] Implement Redis Streams semantic cache manager in `services/common/src/common/cache.py`

**Checkpoint**: Shared configuration, security, and transport utilities ready for reuse.

---

## Phase 3: User Story 1 - Conversational Device Orchestration (Priority: P1) 🎯 MVP

**Goal**: Deliver `/api/query` conversational control that authenticates via OAuth2, persists context, and issues Home Assistant service calls over MQTT.

**Independent Test**: Acquire access token via `/token`, send device command through `/api/query`, verify context persistence on `kitty/ctx/*`, and confirm corresponding Home Assistant REST call + MQTT command on `kitty/devices/<dev>/cmd`.

### Implementation for User Story 1

- [X] T018 [P] [US1] Define conversation context models in `services/brain/src/brain/models/context.py`
- [X] T019 [P] [US1] Implement MQTT-backed context store in `services/brain/src/brain/state/mqtt_context_store.py`
- [X] T020 [P] [US1] Implement Home Assistant REST client using bearer tokens in `services/brain/src/brain/clients/home_assistant.py`
- [X] T021 [P] [US1] Implement Home Assistant WebSocket listener for state sync in `services/brain/src/brain/clients/home_assistant_ws.py`
- [X] T022 [P] [US1] Implement device intent catalog mapping to Home Assistant services in `services/brain/src/brain/skills/home_assistant.py`
- [X] T023 [US1] Build orchestration service translating intents to MQTT + REST calls in `services/brain/src/brain/orchestrator.py`
- [X] T024 [US1] Expose `/api/query` route with OAuth2 dependency in `services/brain/src/brain/routes/query.py`
- [X] T025 [US1] Wire FastAPI application startup + dependency graph in `services/brain/src/brain/app.py`
- [X] T026 [US1] Implement `/token` OAuth2 password flow in `services/gateway/src/gateway/routes/token.py`
- [X] T027 [US1] Implement remote-mode guard middleware for read-only enforcement in `services/gateway/src/gateway/middleware/remote_mode.py`
- [X] T028 [US1] Add integration test for remote read-only policy in `tests/integration/test_remote_mode.py`

**Checkpoint**: Conversational device control operational with authenticated access and synchronized context.

---

## Phase 4: User Story 2 - Confidence-Based Model Routing (Priority: P1)

**Goal**: Implement routing that prefers local Ollama/MLX models, escalates to MCP/frontier adapters when confidence or freshness requires, and logs every decision.

**Independent Test**: Trigger queries for local success, forced MCP escalation, and frontier escalation; confirm routing decisions persisted with confidence, latency, and cost metrics, and retrievable via `/api/routing/logs`.

### Implementation for User Story 2

- [X] T029 [P] [US2] Define routing configuration models in `services/brain/src/brain/routing/config.py`
- [X] T030 [P] [US2] Implement Ollama client with keep-alive controls in `services/brain/src/brain/routing/ollama_client.py`
- [X] T031 [P] [US2] Implement MLX local model wrapper in `services/brain/src/brain/routing/ml_local_client.py`
- [X] T032 [P] [US2] Implement MCP/frontier adapter clients (Perplexity, GPT-5, Sonnet, Gemini) in `services/brain/src/brain/routing/cloud_clients.py`
- [X] T033 [P] [US2] Implement routing audit store persisting decision metadata in `services/brain/src/brain/routing/audit_store.py`
- [X] T034 [US2] Build confidence router core in `services/brain/src/brain/routing/router.py`
- [X] T035 [US2] Integrate router + decision logging into query flow in `services/brain/src/brain/orchestrator.py`
- [X] T036 [US2] Expose `/api/routing/logs` endpoint in `services/gateway/src/gateway/routes/routing.py`
- [X] T037 [US2] Integrate semantic cache into routing path with metrics in `services/brain/src/brain/routing/router.py`

**Checkpoint**: Confidence router operational with audited local/cloud escalations.

---

## Phase 5: User Story 3 - Fabrication Control & CV Monitoring (Priority: P1)

**Goal**: Control OctoPrint/Klipper via REST/JSON-RPC, monitor UniFi Protect feeds for failures, and orchestrate lighting/power scenes.

**Independent Test**: Start print via `/api/device/<printer>/command`, observe OctoPrint upload/start sequence, simulate CV alert triggering pause with snapshot from UniFi Protect, and verify lighting scene activation.

### Implementation for User Story 3

- [X] T038 [P] [US3] Create fabrication service manifest in `services/fabrication/pyproject.toml`
- [X] T039 [P] [US3] Implement OctoPrint REST client covering file upload/job control in `services/fabrication/src/fabrication/octoprint/client.py`
- [X] T040 [P] [US3] Implement Moonraker JSON-RPC client for Klipper telemetry in `services/fabrication/src/fabrication/klipper/moonraker_client.py`
- [X] T041 [P] [US3] Implement UniFi Protect client for RTSP/snapshot access in `services/fabrication/src/fabrication/clients/unifi_protect.py`
- [X] T042 [P] [US3] Implement CV monitoring pipeline with spaghetti/adhesion detection in `services/fabrication/src/fabrication/cv/monitor.py`
- [X] T043 [US3] Implement print job manager coordinating heat/upload/start in `services/fabrication/src/fabrication/jobs/manager.py`
- [X] T044 [US3] Implement MQTT command handlers bridging `/api/device` to device topics in `services/fabrication/src/fabrication/mqtt/handlers.py`
- [X] T045 [US3] Implement lighting/power scene controller invoking Home Assistant services in `services/fabrication/src/fabrication/scenes/controller.py`
- [X] T046 [US3] Integrate fabrication workflow with `/api/device/:id/command` in `services/gateway/src/gateway/routes/devices.py`

**Checkpoint**: Fabrication workflows automated with CV-based safety pauses and facility scene orchestration.

---

## Phase 6: User Story 4 - CAD AI Cycling (Priority: P1)

**Goal**: Generate parametric (Zoo) and organic (Tripo) CAD variants with lineage tracking and offline fallback (CadQuery/FreeCAD + TripoSR/InstantMesh).

**Independent Test**: Submit CAD job, confirm Zoo/Tripo artifacts stored with metadata, enforce offline mode to produce CadQuery STEP + TripoSR mesh, and verify lineage records tie outputs to conversation.

### Implementation for User Story 4

- [ ] T047 [P] [US4] Create CAD service manifest in `services/cad/pyproject.toml`
- [ ] T048 [P] [US4] Implement Zoo API client with create/status polling in `services/cad/src/cad/providers/zoo_client.py`
- [ ] T049 [P] [US4] Implement Tripo cloud client for IM2Tripo in `services/cad/src/cad/providers/tripo_client.py`
- [ ] T050 [P] [US4] Implement TripoSR/InstantMesh local runner in `services/cad/src/cad/providers/tripo_local.py`
- [ ] T051 [P] [US4] Implement artifact store + MinIO lineage tracker in `services/cad/src/cad/storage/artifact_store.py`
- [ ] T052 [US4] Implement CAD cycling orchestrator sequencing providers in `services/cad/src/cad/cycler.py`
- [ ] T053 [US4] Implement `/api/cad/generate` route in `services/cad/src/cad/routes/generate.py`
- [ ] T054 [US4] Implement CadQuery/FreeCAD fallback pipeline in `services/cad/src/cad/fallback/freecad_runner.py`

**Checkpoint**: CAD AI subsystem delivers multi-perspective outputs with resilient offline fallbacks.

---

## Phase 7: User Story 5 - Routing Observability & Cost Control (Priority: P2)

**Goal**: Instrument routing decisions with Prometheus metrics, cost tracking, and Grafana dashboards using API reference configs.

**Independent Test**: View Grafana dashboard to confirm cost, latency, and hit-rate metrics populate; verify Prometheus scrapes metrics endpoints and cost tracker records MCP/frontier spend.

### Implementation for User Story 5

- [X] T055 [P] [US5] Implement routing cost tracker aggregating API usage in `services/brain/src/brain/routing/cost_tracker.py`
- [X] T056 [P] [US5] Expose Prometheus metrics (latency/confidence/hit-rate) in `services/brain/src/brain/metrics/__init__.py`
- [X] T057 [P] [US5] Add Prometheus scrape configuration in `infra/compose/prometheus.yml`
- [X] T058 [P] [US5] Create Grafana routing dashboard JSON in `ops/dashboards/routing.json`
- [X] T059 [US5] Document observability operations/runbook in `ops/runbooks/routing-observability.md`
- [X] T060 [US5] Implement SLO computation job for local-handling % and P95 latency in `services/brain/src/brain/metrics/slo.py`
- [X] T061 [US5] Add Grafana panels for SLO metrics in `ops/dashboards/routing.json`

**Checkpoint**: Routing observability live with actionable dashboards and cost controls.

---

## Phase 8: User Story 6 - Safety & Access Controls (Priority: P2)

**Goal**: Enforce hazard workflows using UniFi Access APIs, signed commands, and dual confirmations.

**Independent Test**: Attempt hazardous unlock, ensure UniFi Access identity + zone check completes, require second confirmation, and verify audit log with signature + snapshot evidence.

### Implementation for User Story 6

- [X] T062 [P] [US6] Create safety service manifest in `services/safety/pyproject.toml`
- [X] T063 [P] [US6] Implement policy definitions with zone hazard rules in `services/safety/src/safety/policies.py`
- [X] T064 [P] [US6] Implement signature verification utilities in `services/safety/src/safety/signing.py`
- [X] T065 [P] [US6] Implement UniFi Access client for identity/door endpoints in `services/safety/src/safety/unifi/client.py`
- [X] T066 [US6] Implement hazard workflow engine coordinating approvals in `services/safety/src/safety/workflows/hazard.py`
- [X] T067 [US6] Integrate safety checks into orchestrator decision flow in `services/brain/src/brain/orchestrator.py`
- [X] T068 [US6] Add safety audit logging with snapshot references in `services/safety/src/safety/audit.py`

**Checkpoint**: Hazardous actions gated by policy with full identity verification and auditing.

---

## Phase 9: User Story 7 - Unified UX Across Endpoints (Priority: P3)

**Goal**: Deliver PWA/wall terminal experiences with live MQTT state, Whisper/Piper voice commands, and Tailscale-aware remote access.

**Independent Test**: Install PWA on iPad, confirm live telemetry via MQTT hook, execute voice command processed through Whisper/Piper services, and toggle remote mode based on Tailscale connectivity.

### Implementation for User Story 7

- [X] T069 [P] [US7] Initialize PWA project in `services/ui/package.json`
- [X] T070 [P] [US7] Implement MQTT context hook in `services/ui/src/hooks/useKittyContext.ts`
- [X] T071 [P] [US7] Implement Whisper/Piper-backed voice module in `services/ui/src/modules/voice.ts`
- [X] T072 [P] [US7] Implement dashboard page with device status panels in `services/ui/src/pages/Dashboard.tsx`
- [X] T073 [US7] Implement remote access guard using Tailscale API in `services/ui/src/utils/tailscaleMode.ts`
- [X] T074 [US7] Configure wall terminal layout for kiosk/screensaver mode in `services/ui/src/pages/WallTerminal.tsx`
- [X] T075 [US7] Coordinate UI with remote read-only policy toggle via MQTT in `services/ui/src/hooks/useRemoteMode.ts`
- [X] T081 [US7] Expose conversation project summary API in `services/brain/src/brain/routes/projects.py`
- [X] T082 [US7] Add project memory persistence (migrations + models) in `services/common/src/common/db/projects.py`
- [X] T083 [US7] Implement UI project memory panel with voice ↔ desktop hand-off in `services/ui/src/pages/Projects.tsx`
- [X] T084 [US7] Implement voice service transcript endpoint and parser in `services/voice/src/voice`
- [X] T085 [US7] Add remote status API for voice ↔ desktop handoff in `services/gateway/src/gateway/routes/remote.py`
- [X] T086 [US7] Wire voice note commands to project memory in `services/voice/src/voice/router.py`

**Checkpoint**: Unified UX available across Mac, tablet, and wall terminals with synchronized context + voice.

---

## Final Phase: Polish & Cross-Cutting Concerns

**Purpose**: Harden documentation, security posture, and performance based on API reference best practices.

- [ ] T076 [P] Update architecture overview with integration diagrams in `docs/architecture.md`
- [ ] T077 [P] Document security and key rotation procedures in `ops/runbooks/security-hardening.md`
- [ ] T078 Consolidate deployment checklist covering Tailscale, API keys, and monitoring in `ops/runbooks/deployment-checklist.md`
- [ ] T079 Tune router and model performance knobs in `services/brain/src/brain/config/performance.py`
- [ ] T080 Validate quickstart scenarios end-to-end in `docs/quickstart.md`

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2**: Container + broker setup enables shared libraries; both must complete before user stories.
- **Phase 2 → Phases 3–9**: User stories require shared config, security, and integration clients.
- **User Stories**: Execute P1 stories (US1–US4) before P2 (US5–US6) and P3 (US7) while keeping each story independently testable.
- **Polish Phase**: Run after the targeted user stories are feature-complete.

---

## Parallel Execution Examples

- **Setup**: T005 and T006 can run in parallel once compose/env files (T001–T004) exist.
- **US1**: T020–T022 (Home Assistant clients/skills) can progress concurrently with T018–T019 (context state).
- **US2**: T030–T032 implement separate adapters (Ollama, MLX, MCP) in parallel after config (T029).
- **US3**: T039–T041 cover OctoPrint, Klipper, UniFi clients independently before orchestration tasks (T043–T046).
- **US4**: T048–T050 implement provider pipelines parallel to artifact store (T051) before orchestrator (T052).
- **US7**: T070–T072 build independent UI modules that converge for guard/layout tasks (T073–T075).

---

## Implementation Strategy

- **MVP First**: Complete Phases 1–2, then deliver US1 (Phase 3) for authenticated conversational control.
- **Incremental Delivery**: Sequence US2 → US3 → US4 to unlock routing, fabrication, and CAD loops before layering observability, safety, and UX.
- **Parallel Teams**: Assign teams to routing (US2/US5), fabrication (US3/US6), CAD (US4), and UX (US7) once foundational work is finished.
