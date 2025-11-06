# Implementation Plan: KITTY Warehouse Orchestrator

**Branch**: `001-KITTY` | **Date**: 2024-11-24 | **Spec**: `/specs/001-KITTY/spec.md`
**Input**: Feature specification from `/specs/001-KITTY/spec.md`

## Summary

Build KITTY, an offline-first conversational orchestrator that unifies fabrication hardware, CAD AI services, and facility systems on the Mac Studio M3 Ultra. The solution uses FastAPI-based microservices, MQTT for state sync, and confidence-based routing that prefers local llama.cpp/MLX models while selectively escalating to Perplexity MCP and frontier LLMs. Fabrication workflows leverage OctoPrint and UniFi camera CV loops, CAD generation cycles Zoo and Tripo outputs with offline CadQuery/FreeCAD fallbacks, and observability captures routing/cost metrics. A dedicated voice-to-print stack (Whisper/Vosk capture, GPT command parsing, slicer automation) provides hands-free control from voice command through CAD generation and print upload, while a project memory store retains conversation history and associated assets for seamless voice ↔ desktop hand-offs.

## Technical Context

**Language/Version**: Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose)
**Primary Dependencies**: FastAPI, Pydantic, paho-mqtt, SQLAlchemy, Home Assistant API, OctoPrint REST, Perplexity MCP SDK, Zoo CAD SDK, Tripo API, CadQuery/FreeCAD, llama.cpp/MLX runtimes, Whisper.cpp, Vosk, Piper
**Storage**: PostgreSQL (audit & lineage), Redis Streams (semantic cache), MinIO S3-compatible object store (CAD artifacts)
**Testing**: pytest + pytest-asyncio (services), pytest-mqtt (MQTT), Playwright (PWA), robotframework or locust optional for end-to-end throughput
**Target Platform**: macOS 14 Mac Studio M3 Ultra host with Docker Desktop containers; remote access via Tailscale mesh
**Project Type**: Multi-service monorepo (`services/*`, `infra/*`, `ops/*`, `tests/*`)
**Performance Goals**: P95 ≤ 1.5 s for local device commands, ≥ 70% queries handled by local models, print monitoring latency ≤ 5 s for failure detection
**Constraints**: Offline-first default, safety confirmations for hazardous actions, containerized orchestration with host-native ML acceleration, VLAN segmentation, SLO logging
**Scale/Scope**: Single facility (initial), 3+ printers, dozens of IoT devices, concurrent conversations across Mac/iPad/wall terminals

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Offline-first routing**: Local llama.cpp/MLX default with confidence-based escalation (compliant).
- **Safety-by-design**: Hazard workflows include signed commands, zone presence, camera checks (compliant).
- **Model/tool neutrality**: CAD cycling across Zoo/Tripo/CadQuery ensures multiple perspectives (compliant).
- **Unified multimodal UX**: Conversational interface + dashboards + voice endpoints over MQTT (compliant).
- **Reproducibility**: Containers for orchestration; host-native ML with documented setup (compliant).
- **Observability & cost control**: Routing logs, Prometheus/Grafana dashboards, semantic cache metrics (compliant).

No constitutional violations identified; proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/001-KITTY/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
services/
├── brain/          # Conversational orchestrator + routing logic
├── gateway/        # REST ingress, auth, aggregation
├── cad/            # CAD AI cycling + storage
├── fabrication/    # OctoPrint bridges, CV pipelines, scenes
├── safety/         # Policy engine, hazard workflows
├── voice/          # Speech capture, NLP parsing, speech-to-print workflows
└── ui/             # PWA/tablet/wall terminal clients

services/common/    # Shared config, messaging, schemas

infra/
├── compose/
├── terraform/
└── ansible/        # Optional host automation

ops/
├── dashboards/
├── runbooks/
└── scripts/

tests/
├── contract/
├── integration/
└── e2e/
```

**Structure Decision**: Multi-service monorepo organized by domain service with shared utilities under `services/common`, infrastructure-as-code in `infra/`, operational collateral in `ops/`, and centralised test suites under `tests/` to enable consistent deployment and observability.

## Implementation Phases

- **Phase 0 — Foundations (Week 1)**: Compose containers (gateway, voice service placeholder, Open WebUI, API services, MQTT, vector DB, Grafana), set up host-native llama.cpp/MLX + Whisper/Piper, connect Tailscale, bootstrap CI/CD.
- **Phase 1 — Conversational Core (Week 2)**: Build FastAPI Brain API with function-calling interface, implement confidence router (local-first, logging), integrate Home Assistant baseline, add first MQTT skill for lights/camera.
- **Phase 2 — Fabrication Control (Week 3)**: Integrate OctoPrint for H2D/OrangeStorm/Snapmaker, add UniFi camera ingestion with CV monitoring for print QC, deliver end-to-end “start + monitor + notify + pause”.
- **Phase 3 — CAD AI v1 (Week 4)**: Connect Zoo (parametric/STEP) + Tripo (mesh); persist artifacts/lineage; seed voice-triggered CAD prompts using OpenSCAD/CadQuery templates for rapid voice-to-CAD iteration.
- **Phase 4 — Routing Maturity (Week 5)**: Wire Perplexity MCP, add frontier LLM adapters, implement semantic/prompt cache, extend observability dashboards for routing hit-rate, cost, latency.
- **Phase 5 — Safety & Access (Week 6)**: Implement hazard workflows (two-step confirmation, zone presence), integrate UniFi Access, build policy engine, document runbooks.
- **Phase 6 — Offline CAD Fallback (Week 7)**: Add CadQuery/FreeCAD pipeline, integrate TripoSR/InstantMesh local meshes, implement selector obeying “online by default; offline when forced”.
- **Phase 7 — UX & Voice Integration (Weeks 8–9)**: Deliver tablet/wall terminal PWAs, live model viewers, projector/touch bench MVP, and deploy voice-to-print pipeline (Whisper/Vosk capture, GPT command parser, slicer automation, Piper TTS confirmations) with safety gating.

## Complexity Tracking

No constitutional violations requiring justification at this time.
