# Implementation Plan: JarvisV3 Warehouse Orchestrator

**Branch**: `001-KITTY` | **Date**: 2024-11-24 | **Spec**: `/specs/001-KITTY/spec.md`
**Input**: Feature specification from `/specs/001-KITTY/spec.md`

## Summary

Build JarvisV3, an offline-first conversational orchestrator that unifies fabrication hardware, CAD AI services, and facility systems on the Mac Studio M3 Ultra. The solution uses FastAPI-based microservices, MQTT for state sync, and confidence-based routing that prefers local Ollama/MLX models while selectively escalating to Perplexity MCP and frontier LLMs. Fabrication workflows leverage OctoPrint and UniFi camera CV loops, CAD generation cycles Zoo and Tripo outputs with offline CadQuery/FreeCAD fallbacks, and observability captures routing/cost metrics.

## Technical Context

**Language/Version**: Python 3.11 (services), TypeScript 5.x (PWA), Bash (ops), YAML (compose)  
**Primary Dependencies**: FastAPI, Pydantic, paho-mqtt, SQLAlchemy, Home Assistant API, OctoPrint REST, Perplexity MCP SDK, Zoo CAD SDK, Tripo API, CadQuery/FreeCAD, Ollama/MLX runtimes, Whisper.cpp, Piper  
**Storage**: PostgreSQL (audit & lineage), Redis Streams (semantic cache), MinIO S3-compatible object store (CAD artifacts)  
**Testing**: pytest + pytest-asyncio (services), pytest-mqtt (MQTT), Playwright (PWA), robotframework or locust optional for end-to-end throughput  
**Target Platform**: macOS 14 Mac Studio M3 Ultra host with Docker Desktop containers; remote access via Tailscale mesh  
**Project Type**: Multi-service monorepo (`services/*`, `infra/*`, `ops/*`, `tests/*`)  
**Performance Goals**: P95 ≤ 1.5 s for local device commands, ≥ 70% queries handled by local models, print monitoring latency ≤ 5 s for failure detection  
**Constraints**: Offline-first default, safety confirmations for hazardous actions, containerized orchestration with host-native ML acceleration, VLAN segmentation, SLO logging  
**Scale/Scope**: Single facility (initial), 3+ printers, dozens of IoT devices, concurrent conversations across Mac/iPad/wall terminals

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Offline-first routing**: Local Ollama/MLX default with confidence-based escalation (compliant).  
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

## Complexity Tracking

No constitutional violations requiring justification at this time.
