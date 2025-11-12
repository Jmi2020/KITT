
# Install — Collective Meta-Agent Drop-in (KITTY)

1) **Copy files** from this drop-in to your repo:
   - `services/agent-runtime/src/agent_runtime/collective/*`
   - `services/agent-runtime/src/agent_runtime/routers/collective.py`
   - `services/agent-runtime/tests/test_collective_smoke.py`
   - `services/gateway/src/routes/collective.py`
   - `config/tool_registry_collective.yaml` (append contents to `config/tool_registry.yaml`)
   - `docs/agents/collective.md`

2) **Agent Runtime**: register the router in your FastAPI app (usually `services/agent-runtime/src/agent_runtime/main.py`):
```python
from agent_runtime.routers.collective import router as collective_router
app.include_router(collective_router)
```

3) **Gateway**: register the proxy route (usually main app file under `services/gateway/src`):
```python
from routes.collective import router as collective_router
app.include_router(collective_router)
```

4) **Tool Registry**: append `config/tool_registry_collective.yaml` into your `config/tool_registry.yaml`.

5) **Build & Run**:
```bash
docker compose -f infra/compose/docker-compose.yml up -d --build agent-runtime gateway
```

6) **Smoke Test**:
```bash
curl -s -X POST http://localhost:8080/api/collective/run   -H "Content-Type: application/json"   -d '{"task":"Compare PETG vs ABS settings for Voron.","pattern":"council","k":3}' | jq
```

7) **CLI**:
```bash
kitty-cli say "/agent on. call collective.run pattern=council k=3 choose a printer for a 200mm tall vase."
```

> This module assumes your coding graph exists at `agent_runtime.graphs.graph_coding`. If not, `pipeline` falls back to collective judge on a single proposal stub.
