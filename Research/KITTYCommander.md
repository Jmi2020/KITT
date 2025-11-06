# KITTY Commander

Offline-first control plane for fabrication labs and smart warehouses.

## Channels & Interfaces

- **Voice** – Whisper.cpp capture → Voice service → Brain router → device/CAD/safety workflows.
- **Web** – React PWA at `http://localhost:4173` (Dashboard, Projects, Wall Terminal, Fabrication Console).
- **CLI** – `kitty-cli shell` for SSH-friendly conversations, CAD previews, and print queueing.
- **MQTT** – Topics under the `kitty/` namespace for device commands, state, CAD jobs, and safety events.

## Services

| Service     | Purpose                                            |
|-------------|----------------------------------------------------|
| Brain       | Conversational routing, context, safety checks     |
| Gateway     | OAuth2 ingress, device command proxy               |
| Fabrication | OctoPrint/Klipper orchestration, camera monitoring |
| CAD         | Zoo/Tripo integrations, MinIO storage, fallback    |
| Safety      | UniFi Access integration, signature validation     |
| Voice       | Transcript ingestion, parser, MQTT integration     |
| UI          | PWA dashboards, Fabrication Console, wall display  |

## Model Routing

1. Semantic cache check (Redis Streams).
2. llama.cpp local inference (aliases `kitty-primary`, `kitty-coder`).
3. If confidence < threshold or forced, escalate → Perplexity MCP → frontier LLM (OpenAI/Anthropic/etc.).
4. Log decision (tier, confidence, latency, cost) → PostgreSQL + Prometheus.

## Safety

- Hazard intents require confirmation phrase (`Confirm: proceed`), role, and zone presence.
- UniFi Access hooks optional (disabled until credentials are configured).
- Audit trail captures signature, timestamps, and camera bookmark references.

## CAD Workflow

1. `/api/cad/generate` receives prompt + references.
2. CadCycler fans out to Zoo (STEP) + Tripo (mesh) + local fallback.
3. Artifacts saved to MinIO; metadata inserted into PostgreSQL projects table.
4. UI/CLI lists artifacts; `/api/device/<printer>/command` queues prints via MQTT.

## Launch Sequence

```bash
./ops/scripts/start-kitty.sh        # starts llama.cpp + Docker compose
alembic -c services/common/alembic.ini upgrade head  # first run
```

- UI: `http://localhost:4173`
- API docs: `http://localhost:8080/docs`
- CLI: `pip install -e services/cli && kitty-cli shell`

## Key Environment Variables

- `LLAMACPP_HOST`, `LLAMACPP_*` – llama.cpp configuration.
- `LOCAL_MODEL_PRIMARY`, `LOCAL_MODEL_CODER` – default routing aliases.
- `ADMIN_USERS` – semicolon-separated `user:hash` entries for JWT issuance.
- `HOME_ASSISTANT_BASE_URL`, `HOME_ASSISTANT_TOKEN` – device control bridge.
- `HAZARD_CONFIRMATION_PHRASE`, `OFFLINE_MODE`, `BUDGET_PER_TASK_USD` – safety and routing policy.

## Observability

- Prometheus/Grafana stack (routing hit-rate, cost, latency, semantic cache stats).
- Loki structured logs + `.logs/llamacpp.log` for llama.cpp.
- `/api/routing/logs` for detailed audit and analytics.

## TODO / Follow-ups

- Real-time cost accounting from provider APIs.
- Finish UniFi Access integration when credentials are available.
- Expand CLI with log streaming / status dashboards.
- Add browser MediaRecorder capture for voice.
- Add infrastructure-as-code automation (Terraform/Ansible) for remote deployments.
