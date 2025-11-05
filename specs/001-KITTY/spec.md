# JarvisV3: Conversational Warehouse Orchestrator — Product Spec

## Overview
JarvisV3 transforms a Mac Studio M3 Ultra into an offline-first conversational control plane for fabrication labs and smart warehouses. The system routes between local and cloud AI models based on confidence, orchestrates CAD generation and fabrication equipment, and exposes multimodal experiences across Mac, iPad, wall terminals, and remote clients while enforcing safety and access policies.

## Personas
- **Fabrication Operator**: Runs additive/subtractive jobs, monitors prints, needs hands-free control and quick insights.
- **Design Engineer**: Iterates on CAD concepts, compares parametric vs. mesh outputs, requires artifact lineage.
- **Facilities/Safety Lead**: Manages access, hazardous operations, compliance logs.
- **AI Systems Architect**: Maintains routing logic, model catalogs, observability, and deployment pipelines.

## User Stories

### US1 (P1) — Conversational Device Orchestration
As a fabrication operator, I want to control printers, lighting, power, doors, and cameras via conversational commands with context persistence so I can manage the shop floor hands-free across devices.
- **Acceptance Criteria**
  - `/api/query` routes device intents to MQTT/Home Assistant skills.
  - Context (device selections, job references) persists across sessions and clients via `jarvis/ctx/*`.
  - Voice endpoints (Mac/iPad/wall terminal) share synchronized state through MQTT.

### US2 (P1) — Confidence-Based Model Routing
As an AI systems architect, I want JarvisV3 to try local models first and escalate to online tools only when confidence is low or fresh data is required, logging each decision, so we minimize cost and preserve privacy.
- **Acceptance Criteria**
  - Router thresholds configurable; local LLMs (7B–72B) invoked by default.
  - Escalations trigger Perplexity MCP or registered frontier adapters with retry queueing.
  - Routing decisions recorded in audit DB and exposed via `/api/routing/logs`.

### US3 (P1) — Fabrication Control & CV Monitoring
As a fabrication operator, I want JarvisV3 to integrate OctoPrint/Klipper printers and monitor prints with UniFi cameras so the system can pause and alert on failures while orchestrating lighting and power scenes.
- **Acceptance Criteria**
  - `jarvis/devices/<printer>/cmd` drives heat/upload/start/abort sequences.
  - CV pipelines detect first-layer failures/spaghetti and pause jobs, sending snapshots.
  - Scene control (lights, power relays) triggered per job profile.

### US4 (P1) — CAD AI Cycling
As a design engineer, I want to generate parametric and organic CAD variants via a single conversational flow with side-by-side comparison so I can choose or iterate on the best approach quickly.
- **Acceptance Criteria**
  - Zoo (STEP/DXF) and Tripo (mesh) integrations produce artifacts stored with lineage.
  - Conversational UI cycles multiple prompts/perspectives and presents results side-by-side.
  - Offline fallback (CadQuery/FreeCAD, TripoSR/InstantMesh) triggered when cloud unavailable and yields workable STEP/STL.

### US5 (P2) — Routing Observability & Cost Control
As an AI systems architect, I want dashboards and logs showing routing hit rates, latency, and spend so I can tune the system and ensure SLO compliance.
- **Acceptance Criteria**
  - Prometheus metrics exported for routing hit/miss, latency percentiles, and cost per request.
  - Grafana dashboards visualize local vs. cloud usage, queue depths, and failure modes.
  - Semantic/prompt cache hit rates tracked and adjustable.

### US6 (P2) — Safety & Access Controls
As a facilities lead, I want hazardous actions gated by policy, confirmations, and zone presence so we prevent unsafe operations and maintain auditable records.
- **Acceptance Criteria**
  - Signed commands for hazard intents with two-step confirmation workflow.
  - UniFi Access integration validates identity and zone presence before unlocking or powering equipment.
  - Audit log captures who approved what, with camera bookmarks for critical actions.

### US7 (P3) — Unified UX Across Endpoints
As a fabrication operator, I want consistent interfaces on Mac, iPad, wall terminals, and remote web so I can pick up tasks on any device seamlessly.
- **Acceptance Criteria**
  - PWAs for tablet/wall terminals with live status dashboards and voice input.
  - Remote access via Tailscale with degraded (read-only) mode when local connectivity limited.
  - Shared state via MQTT ensures conversation continuity and device states across endpoints.

## Non-Goals
- Fully autonomous operation of hazardous equipment without human confirmation.
- Perfect mesh-to-parametric conversion; rely on native parametric outputs when necessary.

## Metrics
- ≥70% requests served locally, ≥50% cloud cost reduction vs. cloud-only baseline.
- P95 latency ≤1.5 s for local device queries.
- 0 safety incidents; >95% success for canonical flows (“start print”, “generate STEP”, “show camera”).

## Risks & Mitigations
- **Hazardous actuation** → Two-factor approvals, PPE/camera checks, physical lockouts.
- **API/provider drift** → Abstraction layers, contract tests, feature flags.
- **Mesh manufacturability** → Route critical jobs to Zoo parametric pipeline, provide detection heuristics.

