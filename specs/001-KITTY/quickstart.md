# KITTY Quickstart Scenarios

## Prerequisites

- Mac Studio M3 Ultra with macOS 14+, Docker Desktop, Python 3.11, Node 20.
- Tailscale authenticated and machine tagged for `jarvis-core`.
- Local `.env` copied from `infra/compose/.env.example` with secrets set.
- Ollama installed with required models (`qwen2.5-coder-32b`, `mistral-7b`, `llava`), MLX runtimes configured.

## Bootstrapping the Stack

1. **Start host services**
   ```bash
   make ollama-up        # loads configured local models
   make tailscale-up     # ensures tunnel active
   ```
2. **Launch containers**
   ```bash
   docker compose -f infra/compose/docker-compose.yml up -d
   ```
3. **Verify health**
   ```bash
   curl http://localhost:8000/healthz
   curl http://localhost:8080/api/ha/status
   mosquitto_sub -h localhost -t 'kitty/ctx/#' -C 1
   ```

## Scenario 1 — Conversational Device Command (US1)

1. POST `/api/query`:
   ```bash
   http POST :8000/api/query \
     conversationId=$(uuidgen) \
     userId=$(uuidgen) \
     channel=mac \
     input:='{"text":"Turn on the welding bay lights"}'
   ```
2. Confirm MQTT emission:
   ```bash
   mosquitto_sub -t 'kitty/devices/welding-lights/cmd' -C 1
   ```
3. Check Home Assistant log for executed `light.scene`.

## Scenario 2 — Confidence Escalation (US2)

1. Submit prompt needing fresh data:
   ```bash
   http POST :8000/api/query ... input:='{"text":"What are titanium powder prices this week?"}'
   ```
2. Verify response indicates tier `mcp` or `frontier` and inspect `/api/routing/logs?selectedTier=mcp`.
3. Validate routing record in PostgreSQL `routing_decisions` table with non-zero cost.

## Scenario 3 — Start & Monitor Print (US3)

1. Upload CAD artifact to MinIO and register new fabrication job.
2. POST `/api/device/{printerId}/command` with intent `start_print`.
3. Watch `kitty/devices/<printer>/cmd` for heat/upload/start sequence.
4. Simulate failure by injecting `spaghetti_detected` frame; ensure job pauses and notification emitted via MQTT/Slack.

## Scenario 4 — CAD AI Cycling (US4)

1. POST `/api/cad/generate` with `policyMode=auto`.
2. Monitor `kitty/cad/jobs/<id>` topic for provider updates.
3. Force offline mode (`policyMode=offline`) with network disconnected; confirm CadQuery + TripoSR outputs appear with STEP + STL artifacts.

## Scenario 5 — Routing Observability (US5)

- Access Grafana dashboard (`http://localhost:3000/d/jarvis-routing`) to ensure local vs cloud hit-rate panels populate.

## Scenario 6 — Safety Workflow (US6)

1. Attempt hazardous command (e.g., unlock welding bay).
2. Confirm `/api/device/...` returns `awaiting_confirmation`.
3. Approve via safety console; final command executes with audit trail entry referencing UniFi snapshot.

## Scenario 7 — Unified UX (US7)

- Install PWA on iPad; confirm live telemetry via MQTT, execute voice command through Whisper/Piper pipeline; verify remote mode toggles when Tailscale disconnected.

## Cleanup

```bash
docker compose -f infra/compose/docker-compose.yml down
make ollama-stop
```
