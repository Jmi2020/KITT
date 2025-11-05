# JarvisV3 Research Notes

## Confidence-Based Routing

- **Decision**: Implement a tiered router in `services/brain` that scores model confidence using local model logprobs + retrieval overlap, defaulting to Ollama/MLX resident models (7B–72B) and escalating to MCP adapters (Perplexity, GPT-5, Claude Sonnet, Gemini) when confidence < threshold or freshness required.  
- **Rationale**: Local Metal-accelerated models on the M3 Ultra deliver ≤1.5 s P95 latency for routine commands while preserving privacy and reducing cost. MCP adapters provide uniform tooling for external searches and reasoning bursts.  
- **Alternatives Considered**: Direct OpenAI/AWS SDK calls (rejected: bypasses MCP contracts, increases integration drift); static per-intent model mapping (rejected: brittle and ignores confidence).

## Semantic & Prompt Cache

- **Decision**: Use Redis Streams + hash metadata for semantic cache keyed on intent embeddings.  
- **Rationale**: Streams support ordered replay for offline revalidation, while Redis remains lightweight and host-friendly.  
- **Alternatives**: PostgreSQL JSONB cache (rejected: higher latency for vector similarity); DuckDB or sqlite-vss (rejected: less suitable for concurrent MQTT-driven workloads).

## Storage & Artifact Handling

- **Decision**: PostgreSQL for routing/audit lineage, MinIO S3 bucket for CAD/STL artifacts, Redis Streams for transient job state.  
- **Rationale**: Postgres offers transactional logging and SQL analytics; MinIO provides S3-compatible API compatible with Zoo/Tripo outputs; Redis supports low-latency messaging and cache semantics.  
- **Alternatives**: MongoDB (rejected: limited relational guarantees for audits); AWS S3 (rejected: contradicts offline-first mandate); plain filesystem (rejected: lacks versioning + metadata).

## MQTT & State Synchronization

- **Decision**: Mosquitto broker with topic hierarchy `jarvis/ctx/*`, `jarvis/devices/<dev>/state|cmd`, `jarvis/ai/routing/*`, QoS 1 for critical commands, retained messages for device state only.  
- **Rationale**: Aligns with Home Assistant conventions, ensures idempotent command delivery while avoiding stale actions; MQTT suits low-latency, multi-device sync.  
- **Alternatives**: NATS JetStream (rejected: additional ops overhead, unnecessary feature set); WebSockets-only (rejected: poor device compatibility).

## Home Assistant Integration

- **Decision**: Use Home Assistant REST + WebSocket APIs via long-lived tokens to execute `light.scene`, `lock.unlock`, `camera.record`, bridging MQTT updates to HA automations.  
- **Rationale**: HA already manages device auth/automation; leveraging built-in services avoids duplicating integrations.  
- **Alternatives**: Direct vendor APIs (rejected: increases surface area, bypasses safety policies).

## Fabrication Control

- **Decision**: Wrap OctoPrint REST (upload/start/pause) and Klipper gcode macros via HTTP API keys; subscribe to job progress websockets; integrate UniFi Protect RTSP streams into CV pipeline using OpenCV + Ultralytics models for failure detection.  
- **Rationale**: OctoPrint exposes stable endpoints for multi-printer fleets; UniFi cameras provide deterministic RTSP; leveraging proven CV models speeds detection accuracy.  
- **Alternatives**: Direct Klipper Moonraker integration (rejected for initial phase: OctoPrint already deployed); custom camera firmware (rejected: time-intensive).

## CAD AI Cycling

- **Decision**: Sequence Zoo parametric jobs first, followed by Tripo mesh variants, presenting results in UI with metadata; offline fallback runs CadQuery scripts via FreeCAD headless CLI and TripoSR for mesh.  
- **Rationale**: Honors policy “STEP online by default” while ensuring offline resilience; retains lineage for manufacturing audit.  
- **Alternatives**: Exclusive reliance on Zoo (rejected: lacks organic/creative outputs); local-only pipeline (rejected: insufficient complexity coverage).

## Safety & Access

- **Decision**: Hazard workflows require signed JWT commands, zone presence via UniFi Access API, and manual confirmation; audit entries stored in Postgres with camera snapshot references in MinIO.  
- **Rationale**: Meets constitution safety tenets and ensures after-action traceability.  
- **Alternatives**: Simple API key gating (rejected: insufficient safety guarantees); physical-only checks (rejected: automation gaps).

## Observability Stack

- **Decision**: Prometheus Node/Custom exporters for routing latency, cost, CV event counts; Grafana dashboards; Loki for structured logs; Tempo optional for distributed traces.  
- **Rationale**: Open-source stack compatible with containerized deployment; integrates with existing developer tooling.  
- **Alternatives**: Datadog/New Relic (rejected: requires cloud connectivity and licensing); ELK stack (rejected: heavier footprint).

## Testing Strategy

- **Decision**: pytest + pytest-asyncio for service unit/integration tests, pytest-mqtt harness for pub/sub validation, Playwright for PWA acceptance, synthetic job scenarios scripted in Quickstart.  
- **Rationale**: Python-first tooling aligns with FastAPI services; Playwright handles multi-device UI; MQTT-specific fixtures ensure offline reliability.  
- **Alternatives**: Nose/unittest (obsolete); Cypress (browser-only, lacks MQTT simulation coverage).
