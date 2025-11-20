
# KITT Integration Guide — Swap **Llama 3.3 70B (llama.cpp)** → **GPT‑OSS‑120B (Ollama, Thinking)**

> Purpose: Replace the current F16 reasoning server (Llama 3.3 70B on `llama.cpp`) with **GPT‑OSS‑120B** running under **Ollama** with **thinking** enabled, without breaking existing CLI → Gateway → Brain routing, MCP tools, or observability.

---

|Expert(s)|LLM Inference Engineer · MLOps/DevOps · Backend API Integrator|
|:--|:--|
|Question|Implement a safe, reversible swap from llama.cpp F16 (Llama 3.3 70B) to Ollama `gpt-oss:120b` with “thinking” enabled, updating env, router, health checks, and scripts.|
|Plan|Audit current request flow and ports → install/seed Ollama → bridge Docker↔host networking → add `OllamaReasonerClient` + router rule → wire “thinking” capture & redaction → update start/stop scripts and health checks → validate and benchmark → provide rollback path.|

---

## 0) What you’re replacing (at a glance)

- **Current**: `llama.cpp` F16 server at **:8082** aliased `kitty-f16` for deep reasoning; Q4 tool orchestrator at **:8083**; Hermes summarizer at **:8085**; Gemma Vision at **:8086**. Startup and ports are defined in the ops manual and used by the Brain router. fileciteturn0file1  
- **Flow**: CLI/UI → **Gateway** → **Brain** → router chooses **Local (llama.cpp)**, **MCP**, or **Frontier**; then responses are recorded and streamed back. We’ll add **Local (Ollama)** as the default “reasoner” tier. fileciteturn0file0

> References in this guide cite KITTY’s docs inline so you can jump to exact places in your repo.


## 1) Pre‑flight checklist

- macOS host (Mac Studio) with Docker Compose + existing KITTY stack. llama.cpp is started **outside Docker** for Metal performance; we’ll keep that for Q4/vision but **retire :8082** for the 70B F16 server. fileciteturn0file1  
- Ensure **Gateway/Brain containers can reach the host** via `host.docker.internal` (already used in troubleshooting). Add the host gateway mapping if missing. fileciteturn0file1
- Decide the default **reasoning effort** (`low|medium|high`) for GPT‑OSS:120B thinking (see §4.2). Ollama exposes this via the **`think`** parameter; GPT‑OSS expects the string values rather than booleans.

## 2) Install & seed **Ollama** + `gpt-oss:120b`

```bash
brew install ollama             # installs the daemon and CLI
ollama serve &                  # start the API server on :11434
ollama pull gpt-oss:120b        # ~65 GB model, MXFP4
```

Quick sanity checks:

```bash
# List models (health check stand‑in)
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# Local prompt (non-HTTP)
ollama run gpt-oss:120b --think=medium "Say hello in one sentence."
```

## 3) Network bridge: Docker ↔ host (so Brain can call Ollama)

Inside `infra/compose/docker-compose.yml`, ensure **Brain** (and optionally **Gateway**) can resolve the host from inside Docker:

```yaml
services:
  brain:
    extra_hosts:
      - "host.docker.internal:host-gateway"
  gateway:
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

This host mapping is already used in KITTY to hit llama.cpp on the host; we’ll reuse it for Ollama at **:11434**. fileciteturn0file1

## 4) Configuration: `.env` additions and deprecations

Add these **new** variables (keep Q4 and Vision as-is):

```dotenv
# --- OLLAMA Reasoner (replaces llama.cpp F16 :8082) ---
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_THINK=medium               # low | medium | high (GPT‑OSS), see docs
OLLAMA_TIMEOUT_S=120
OLLAMA_KEEP_ALIVE=5m              # keep model warm between calls

# Router selector: which local reasoner to use
LOCAL_REASONER_PROVIDER=ollama    # values: ollama | llamacpp
```

Deprecate or comment the old F16 endpoint to avoid accidental routing:

```dotenv
# LLAMACPP_F16_HOST=http://host.docker.internal:8082   # ← disable
# LLAMACPP_F16_MODEL=...                               # ← disable
```

> KITTY currently reads llama.cpp endpoints from `.env` (see ops manual and README). We’re mirroring that pattern for Ollama so Brain’s router can select the provider at runtime. fileciteturn0file1turn0file2

## 5) Brain: add an **OllamaReasonerClient** and route

Create `services/brain/src/brain/providers/ollama_client.py`:

```python
# SPDX-License-Identifier: MIT
# Minimal Ollama chat client with optional "thinking" capture for GPT‑OSS.
from __future__ import annotations
import httpx
from typing import Iterable, Optional, Dict, Any, Generator

class OllamaReasonerClient:
    def __init__(self, base_url: str, model: str, timeout_s: int = 120, keep_alive: str = "5m"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout_s
        self.keep_alive = keep_alive

    def _make_payload(self, messages: Iterable[Dict[str, str]], think: Optional[str] = None, stream: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": stream,
            "keep_alive": self.keep_alive,
        }
        # GPT‑OSS expects "low|medium|high"; other models support true/false
        if think is not None:
            payload["think"] = think  # e.g., "medium"
        return payload

    def chat(self, messages: Iterable[Dict[str, str]], think: Optional[str] = None, stream: bool = True) -> Dict[str, Any]:
        # Non-streaming convenience
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/api/chat", json=self._make_payload(messages, think, stream=False))
            resp.raise_for_status()
            data = resp.json()
            # Normalize shape across Ollama versions
            msg = data.get("message", {})
            return {
                "content": msg.get("content", ""),
                "role": msg.get("role", "assistant"),
                "thinking": msg.get("thinking") or data.get("thinking"),
                "raw": data,
            }

    def stream_chat(self, messages: Iterable[Dict[str, str]], think: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        # Yields incremental deltas; consumer should buffer 'content' and optionally 'thinking'.
        with httpx.stream("POST", f"{self.base_url}/api/chat", json=self._make_payload(messages, think, stream=True), timeout=self.timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                # Lines may be NDJSON or SSE "data: {json}"
                if line.startswith("data:"):
                    line = line[5:].strip()
                try:
                    import json
                    chunk = json.loads(line)
                except Exception:
                    continue
                msg = chunk.get("message", {})
                yield {
                    "delta": msg.get("content", ""),
                    "delta_thinking": msg.get("thinking"),
                    "done": chunk.get("done", False),
                }
```

Router integration in `services/brain/src/brain/routing/router.py` (illustrative diff):

```diff
@@
-from .llamacpp_client import LlamaCppClient
+from .llamacpp_client import LlamaCppClient
+from .providers.ollama_client import OllamaReasonerClient

 class Router:
     def __init__(self, settings):
         self.settings = settings
-        self.llama_f16 = LlamaCppClient(base_url=settings.LLAMACPP_F16_HOST) if settings.LLAMACPP_F16_HOST else None
+        self.llama_f16 = LlamaCppClient(base_url=settings.LLAMACPP_F16_HOST) if getattr(settings, "LLAMACPP_F16_HOST", None) else None
+        self.ollama = OllamaReasonerClient(
+            base_url=settings.OLLAMA_HOST,
+            model=settings.OLLAMA_MODEL,
+            timeout_s=settings.OLLAMA_TIMEOUT_S,
+        ) if getattr(settings, "OLLAMA_HOST", None) else None

     def route_local_reasoner(self):
-        # legacy: default to llama.cpp F16
-        return self.llama_f16
+        provider = getattr(self.settings, "LOCAL_REASONER_PROVIDER", "ollama")
+        if provider == "ollama" and self.ollama:
+            return self.ollama
+        return self.llama_f16  # fallback if someone still wants the old path

     async def generate_response(self, messages, **kwargs):
         # ... existing tier selection (local/mcp/frontier) ...
-        engine = self.route_local_reasoner()
-        result = engine.chat(messages, stream=False)
+        engine = self.route_local_reasoner()
+        think_level = getattr(self.settings, "OLLAMA_THINK", "medium")
+        # Non-streaming example; or wire to your streaming path
+        result = engine.chat(messages, think=think_level, stream=False)
         # capture 'thinking' if present; store only to structured logs, not user output
-        return Result(output=result["content"])
+        self._maybe_log_thinking(result.get("thinking"))
+        return Result(output=result["content"], metadata={"provider": "ollama", "thinking_present": bool(result.get("thinking"))})
```

> KITTY’s router today chooses **Local / MCP / Frontier**; this keeps that shape, swapping the “local reasoner” from llama.cpp F16 to Ollama GPT‑OSS. The rest of your request/response lifecycle (DB writes, MQTT context, cost tracking) stays intact. fileciteturn0file0

### 5.1 Thinking trace hygiene (privacy & UX)

- **Do not** stream or store the full thinking trace into user‑visible chat unless explicitly requested. Log to `reasoning.jsonl` as structured telemetry with redaction, matching existing logging practices. fileciteturn0file0

## 6) Gateway & CLI adjustments

**Gateway:** No schema changes needed—Brain still exposes the same `/api/query` contract. If you proxy Brain from Gateway, nothing else changes. fileciteturn0file0

**CLI:** Expose an optional switch for operators to override the default effort:

```bash
# Example additions
kitty-cli say --think high "Plan a 3-step print recovery SOP"
# or set default for the session
kitty-cli /think medium
```

Map this flag to `OLLAMA_THINK` in the payload your CLI sends to Brain (e.g., an extra header or JSON field your API already forwards in `payload`/`metadata`). KITTY’s CLI already forwards verbosity and agent toggles similarly. fileciteturn0file2

## 7) Start/Stop scripts

Update `./ops/scripts/start-all.sh` to stop launching the F16 llama.cpp server (**:8082**) and ensure Ollama is up. Keep **Q4** and **Vision** llama.cpp servers untouched (ports **8083/8086**). fileciteturn0file1

## 8) Health checks & observability

- **Ollama health**: use `GET /api/tags` as a lightweight readiness probe (200 + includes the pulled model). Wire a Brain dependency check similar to your existing llama.cpp checks. fileciteturn0file1  
- **Metrics**: add counters for `provider=ollama`, latency, and a boolean `thinking_present`. Align with existing routing audit to preserve dashboards. fileciteturn0file0

## 9) Validation plan (zero‑downtime)

1. **Unit smoke test**: call Brain’s `/health` and `/api/query` with `LOCAL_REASONER_PROVIDER=ollama`. Expect tier=`local`, provider=`ollama`, and `thinking_present=true`. fileciteturn0file1  
2. **End‑to‑end**: run the same startup validation curl used in the ops manual; confirm output, latency, and routing metadata. fileciteturn0file1  
3. **Agent/tool runs**: leave Q4 (tool orchestrator) untouched—ReAct flows should behave identically since only the deep‑reasoning hop changed. fileciteturn0file2

## 10) Rollback

- Flip `LOCAL_REASONER_PROVIDER=llamacpp` in `.env`, restart **Brain**, and (optionally) re‑start the F16 llama.cpp server on **:8082** using your existing scripts. All other services stay up. fileciteturn0file1

## 11) API shapes: request/response (for Codex/Claude)

### 11.1 Brain → Ollama (non‑streaming)

```http
POST {OLLAMA_HOST}/api/chat
Content-Type: application/json

{
  "model": "gpt-oss:120b",
  "messages": [
    {"role": "system", "content": "You are KITTY..."},
    {"role": "user", "content": "Summarize the print queue status."}
  ],
  "think": "medium",
  "stream": false,
  "keep_alive": "5m"
}
```

**Response (shape excerpt):**
```json
{
  "model": "gpt-oss:120b",
  "created_at": "2025-11-18T21:41:01Z",
  "message": {
    "role": "assistant",
    "content": "…final answer…",
    "thinking": "…reasoning trace…"
  },
  "done": true
}
```

### 11.2 Brain → Ollama (streaming)

```http
POST {OLLAMA_HOST}/api/chat
{
  "model":"gpt-oss:120b",
  "messages":[...],
  "think":"medium",
  "stream": true
}
```

The HTTP body streams NDJSON/SSE lines. Each line includes a `message.content` delta and may include `message.thinking`. Accumulate content for display; handle thinking separately for logs/telemetry.

---

## Appendix A — Where this plugs into KITTY

- **Request flow**: CLI/UI → Gateway → Brain → `orchestrator.generate_response()` → Router picks Local/MCP/Frontier → **Local** now resolves to **Ollama** instead of llama.cpp F16. fileciteturn0file0  
- **Ports**: Leave **:8083** (Athene Q4), **:8086** (Gemma Vision) intact; retire **:8082**; Ollama listens on **:11434**. fileciteturn0file1  
- **Startup**: Your `start-all.sh` previously launched multiple llama.cpp servers; keep Q4/Vision/Hermes; replace the F16 start with `ollama serve &` + warmup. fileciteturn0file1  
- **CLI/Gateway**: No API contract changes; only provider metadata shifts to `ollama`. fileciteturn0file2

## Appendix B — Quick commands (operator cribsheet)

```bash
# Verify Ollama is up and model present
curl -s http://localhost:11434/api/tags | jq '.models[].name'

# One-off local run with thinking
ollama run gpt-oss:120b --think=high "Draft a 3-step recovery plan for failed first layers."

# Flip provider (rollback)
export LOCAL_REASONER_PROVIDER=llamacpp && docker compose restart brain
```

---

**Changelog:** v1.1 — Reissued download (same content as v1.0).
