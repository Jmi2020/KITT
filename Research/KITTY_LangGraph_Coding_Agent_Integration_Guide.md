# KITTY + LangChain/LangGraph Coding Agent — Integration Guide

|Expert(s)|Machine Learning Systems Architect; Agent Orchestration Engineer; DevOps/SRE; Security Engineer|
|:--|:--|
|Question|Integrate LangChain/LangGraph to add an **offline, model‑agnostic coding agent** to KITTY, wired into the existing Brain/Gateway stack, CLI, safety rails, and observability.|
|Plan|Adopt a **Plan‑and‑Execute** LangGraph DAG specialized for coding tasks; package it as a new **`coder-agent`** FastAPI microservice; expose endpoints via **Gateway**; register tools in **`config/tool_registry.yaml`**; route to local **llama.cpp** models (Q4 tool orchestrator, F16 deep reasoner, optional coder model); enforce KITTY safety (allow‑lists, hazard confirmations), add metrics, and ship tests.|

> 🧠 You can keep everything fully offline. This guide uses only local components and plugs into KITTY’s existing architecture and conventions. Where helpful, references to KITTY’s current design are cited inline.

---

## 0) Scope & Goals

- **What you get**: A production‑ready **coding agent** implemented with **🧩 [LangChain](https://www.google.com/search?q=LangChain+Python+LLM+framework)** and **🕸️ [LangGraph](https://www.google.com/search?q=LangGraph+state+graph+multi+agent)**, packaged as `services/coder-agent` with a clean FastAPI interface and MCP‑compatible semantics.
- **Why it fits KITTY**: The agent plugs into **Gateway (8080)** and the **Brain router (8000)**, and talks to your **dual llama.cpp servers** (Q4 @ **8083**, F16 @ **8082**) already used for tool orchestration and deep reasoning fileciteturn1file10 fileciteturn1file11.
- **Tooling model**: Expose new `coding.*` tools via **`config/tool_registry.yaml`** (JSON‑schema + safety metadata). Gateway proxies; the Brain picks them up on restart—no code changes required fileciteturn1file5 fileciteturn1file6.
- **Safety/observability**: Re‑use KITTY’s **hazard workflows**, **allow‑lists**, **audit logging**, and **Prometheus/Grafana** dashboards to keep the agent grounded, safe, and measurable fileciteturn1file6 fileciteturn1file3.

---

## 1) Directory Layout

Create a new service alongside existing ones:

```
services/
  coder-agent/
    Dockerfile
    requirements.txt
    src/coder_agent/
      __init__.py
      prompts.py
      llm_client.py
      sandbox.py
      graph.py
      agent.py
      api.py        # FastAPI router
      main.py       # Uvicorn entrypoint
    tests/
      test_smoke.py
```

This mirrors KITTY’s microservice pattern (Gateway/Brain/CAD/etc.) and keeps the coding logic isolated yet discoverable in the tool registry fileciteturn1file4.

---

## 2) Dependencies (offline‑friendly)

Place this in `services/coder-agent/requirements.txt`:

```txt
fastapi>=0.112
uvicorn[standard]>=0.30
pydantic>=2.7
httpx>=0.27
tenacity>=8.3
langchain>=0.2
langgraph>=0.1
prometheus-client>=0.20
```
> All libs run locally. If you mirror wheels on your LAN, point `pip` to your internal index cache.

Install locally (or let Docker build step do it):
```bash
pip install -r services/coder-agent/requirements.txt
```

---

## 3) Configuration

Add environment knobs (extend `.env` as needed):

```bash
# Model endpoints (local llama.cpp servers)
LLAMACPP_Q4_BASE=http://localhost:8083     # tool orchestrator (Athene/Q4)
LLAMACPP_F16_BASE=http://localhost:8082    # deep reasoning
LLAMACPP_CODER_BASE=${LLAMACPP_F16_BASE}   # optional dedicated coder endpoint

# Timeouts / limits
CODER_MAX_TOKENS=768
CODER_TEMPERATURE=0.15
CODER_REFINE_PASSES=2
CODER_TEST_TIMEOUT_SEC=20

# Safety
SANDBOX_ENABLED=true
SANDBOX_PY_PATH=/usr/bin/python3          # inside container
```

Ports 8082/8083 and the Brain/Gateway pattern follow KITTY’s startup order and service map fileciteturn1file9 fileciteturn1file10.

---

## 4) LLM Client (llama.cpp – OpenAI‑compatible **or** native)

`services/coder-agent/src/coder_agent/llm_client.py`

```python
from __future__ import annotations
import os, httpx, json
from typing import List, Dict

def _env(key: str, default: str) -> str:
    return os.getenv(key, default)

def chat(messages: List[Dict[str, str]],
         base_url: str | None = None,
         model: str | None = None,
         temperature: float = 0.15,
         max_tokens: int = 768) -> str:
    """
    Try OpenAI-compatible /v1/chat/completions; fall back to llama.cpp /completion.
    Works against your local servers (Q4/F16/coder). Fully offline.
    """
    base = base_url or _env("LLAMACPP_CODER_BASE", "http://localhost:8082")

    # 1) Try OpenAI-compatible route if llama.cpp was started with --api
    try:
        r = httpx.post(
            f"{base}/v1/chat/completions",
            json={
                "model": model or "kitty-coder",
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": messages,
            },
            timeout=60,
        )
        if r.status_code == 200 and "choices" in r.json():
            return r.json()["choices"][0]["message"]["content"]
    except Exception:
        pass

    # 2) Fallback to native /completion
    prompt = ""
    for m in messages:
        role = m.get("role", "user")
        prompt += f"{role.upper()}: {m['content']}\n"
    prompt += "ASSISTANT:"

    r = httpx.post(
        f"{base}/completion",
        json={
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": max_tokens,
            "stop": ["USER:", "SYSTEM:", "ASSISTANT:"],
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    # llama.cpp returns a list of chunks; join them if needed
    if isinstance(data, dict) and "content" in data:
        content = data["content"]
        if isinstance(content, list):
            return "".join([c.get("text", "") for c in content])
    # Last resort
    return json.dumps(data)
```

> 🔌 If you prefer to route via the **Brain** instead, you can wrap its `/api/query` endpoint, but direct llama.cpp calls keep the agent deterministic and fast fileciteturn1file10.

---

## 5) Prompts

`services/coder-agent/src/coder_agent/prompts.py`

```python
CODER_SYSTEM = """You are KITTY's coding specialist.
- Write minimal, correct code first; then add comments.
- Always return a single self-contained module unless asked to scaffold.
- Prefer pure Python; no network calls; no file I/O unless explicitly allowed.
- When tests fail, explain succinctly and propose a fix.
"""

PLAN_PROMPT = "Plan the steps to fulfill the request. Return bullets with concrete sub-goals."
TEST_STYLE = "pytest"
```

---

## 6) Safe Execution Sandbox (no network, bounded time)

`services/coder-agent/src/coder_agent/sandbox.py`

```python
import os, subprocess, tempfile, textwrap, json, shlex, sys

def run_python_with_pytest(code: str, tests: str, timeout_sec: int = 20) -> dict:
    if os.getenv("SANDBOX_ENABLED", "true").lower() != "true":
        return {"ok": False, "stdout": "", "stderr": "Sandbox disabled", "returncode": -1}

    with tempfile.TemporaryDirectory() as td:
        mod_path = os.path.join(td, "solution.py")
        tst_path = os.path.join(td, "test_solution.py")

        with open(mod_path, "w") as f:
            f.write(code)
        with open(tst_path, "w") as f:
            f.write(tests)

        cmd = [os.getenv("SANDBOX_PY_PATH", sys.executable), "-m", "pytest", "-q", td]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_sec
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
            }
        except subprocess.TimeoutExpired as e:
            return {"ok": False, "stdout": e.stdout or "", "stderr": "timeout", "returncode": 124}
```

> ✅ This is equivalent to KITTY’s **command allow‑list** posture—execution is constrained and observable. Keep or extend your allow‑lists in the **Broker MCP** if you later move this to a separate tool fileciteturn1file6.

---

## 7) LangGraph: typed state + DAG

`services/coder-agent/src/coder_agent/graph.py`

```python
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from .llm_client import chat
from .prompts import CODER_SYSTEM, PLAN_PROMPT, TEST_STYLE
from .sandbox import run_python_with_pytest

class CoderState(TypedDict, total=False):
    user_request: str
    plan: str
    code: str
    tests: str
    run_stdout: str
    run_stderr: str
    passed: bool
    final_answer: str
    iterations: int

def node_plan(state: CoderState) -> CoderState:
    plan = chat([
        {"role": "system", "content": CODER_SYSTEM},
        {"role": "user", "content": f"{PLAN_PROMPT}\n\nRequest: {state['user_request']}"},
    ])
    return {**state, "plan": plan, "iterations": 0}

def node_code(state: CoderState) -> CoderState:
    code = chat([
        {"role": "system", "content": CODER_SYSTEM},
        {"role": "user", "content": f"Write Python module for:\n{state['user_request']}\nReturn ONLY code in one block."},
    ])
    return {**state, "code": code}

def node_tests(state: CoderState) -> CoderState:
    tests = chat([
        {"role": "system", "content": CODER_SYSTEM},
        {"role": "user", "content": f"Write {TEST_STYLE} tests for this code:\n{state['code']}\nAim for correctness and edge cases."},
    ])
    return {**state, "tests": tests}

def node_run(state: CoderState) -> CoderState:
    out = run_python_with_pytest(state["code"], state["tests"])
    return {**state, "run_stdout": out["stdout"], "run_stderr": out["stderr"], "passed": out["ok"]}

def node_refine(state: CoderState) -> CoderState:
    fix = chat([
        {"role": "system", "content": CODER_SYSTEM},
        {"role": "user", "content": (
            "Tests failed. Here are logs. Fix the code, return full corrected module.\n"
            f"STDOUT:\n{state['run_stdout']}\nSTDERR:\n{state['run_stderr']}\n"
            f"Original request:\n{state['user_request']}\n"
            f"Current code:\n{state['code']}\n"
        )},
    ])
    it = int(state.get("iterations", 0)) + 1
    return {**state, "code": fix, "iterations": it}

def node_summarize(state: CoderState) -> CoderState:
    summary = chat([
        {"role": "system", "content": CODER_SYSTEM},
        {"role": "user", "content": (
            "Summarize the solution with run results and a brief usage example.\n"
            f"Request:\n{state['user_request']}\n"
            f"Plan:\n{state.get('plan','')}\n"
            f"Passed: {state.get('passed')}\n"
            f"Logs:\n{state.get('run_stdout','')}\n"
            "Return markdown with a code block."
        )}
    ])
    return {**state, "final_answer": summary}

def build_graph(max_refine: int = 2) -> StateGraph:
    g = StateGraph(CoderState)
    g.add_node("plan", node_plan)
    g.add_node("code", node_code)
    g.add_node("tests", node_tests)
    g.add_node("run", node_run)
    g.add_node("refine", node_refine)
    g.add_node("summarize", node_summarize)

    g.set_entry_point("plan")
    g.add_edge("plan", "code")
    g.add_edge("code", "tests")
    g.add_edge("tests", "run")

    # Conditional edge: refine loop
    def after_run(state: CoderState):
        if not state.get("passed") and state.get("iterations", 0) < max_refine:
            return "refine"
        return "summarize"

    g.add_conditional_edges("run", after_run, {"refine": "refine", "summarize": "summarize"})
    g.add_edge("refine", "tests")
    g.add_edge("summarize", END)
    return g
```

This is a **Plan‑→Code‑→Tests‑→Run‑→(Refine)×N‑→Summarize** loop tuned for coding, fully offline. You can swap the underlying llama.cpp base (Q4/F16/coder) by changing `LLAMACPP_*_BASE` envs without code changes.

---

## 8) Agent API (FastAPI)

`services/coder-agent/src/coder_agent/api.py`

```python
from fastapi import APIRouter
from pydantic import BaseModel
from .graph import build_graph

router = APIRouter(prefix="/api/coding", tags=["coding"])
graph = build_graph()

class GenerateReq(BaseModel):
    request: str

class GenerateRes(BaseModel):
    plan: str | None = None
    code: str
    tests: str
    passed: bool
    run_stdout: str | None = None
    run_stderr: str | None = None
    final_answer: str

@router.post("/generate", response_model=GenerateRes)
def generate(req: GenerateReq):
    state = {"user_request": req.request}
    result = graph.invoke(state)
    return GenerateRes(**{
        "plan": result.get("plan"),
        "code": result["code"],
        "tests": result["tests"],
        "passed": bool(result.get("passed")),
        "run_stdout": result.get("run_stdout"),
        "run_stderr": result.get("run_stderr"),
        "final_answer": result["final_answer"],
    })
```

`services/coder-agent/src/coder_agent/main.py`

```python
import uvicorn
from fastapi import FastAPI
from .api import router as coding_router

def create_app() -> FastAPI:
    app = FastAPI(title="KITTY Coding Agent")
    app.include_router(coding_router)
    return app

if __name__ == "__main__":
    uvicorn.run(create_app(), host="0.0.0.0", port=8092)
```

---

## 9) Dockerfile

`services/coder-agent/Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
ENV PYTHONPATH=/app/src
EXPOSE 8092
CMD ["python", "-m", "coder_agent.main"]
```

---

## 10) Compose Integration

Append to `infra/compose/docker-compose.yml`:

```yaml
  coder-agent:
    build:
      context: ../../services/coder-agent
    image: kitty/coder-agent:local
    environment:
      - LLAMACPP_Q4_BASE=${LLAMACPP_Q4_BASE:-http://llamacpp-q4:8083}
      - LLAMACPP_F16_BASE=${LLAMACPP_F16_BASE:-http://llamacpp-f16:8082}
      - LLAMACPP_CODER_BASE=${LLAMACPP_CODER_BASE:-http://llamacpp-f16:8082}
      - CODER_MAX_TOKENS=${CODER_MAX_TOKENS:-768}
      - CODER_TEMPERATURE=${CODER_TEMPERATURE:-0.15}
      - CODER_REFINE_PASSES=${CODER_REFINE_PASSES:-2}
      - SANDBOX_ENABLED=${SANDBOX_ENABLED:-true}
      - SANDBOX_PY_PATH=${SANDBOX_PY_PATH:-/usr/bin/python3}
    ports:
      - "8092:8092"
    depends_on:
      - gateway
      - brain
```

This follows the same composition as other KITTY services (Gateway/Brain/CAD) fileciteturn1file13.

---

## 11) Tool Registry (plug into ReAct/MCP)

Add to `config/tool_registry.yaml`:

```yaml
coding.generate:
  method: POST
  url: http://gateway:8080/api/coding/generate
  schema:
    type: object
    properties:
      request: { type: string, description: "Natural language coding task" }
    required: [request]
  safety:
    hazard_class: "low"
    confirmation_required: false
```

- The **Gateway** proxies to backend services; the Brain reads this registry and tools are available on restart—no agent code changes needed fileciteturn1file6.
- This keeps parity with existing tool categories (CAD/Fabrication/Memory/etc.) fileciteturn1file0.

> 🔧 MCP note: If you prefer, expose the coding agent as a dedicated **MCP server** and attach it to KITTY’s toolbelt; both patterns are supported in the current design fileciteturn1file14.

---

## 12) Gateway Route

In **Gateway** (FastAPI), add a thin proxy (pattern mirrors existing routes):

```python
# services/gateway/src/routes/coding.py
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/coding", tags=["coding"])
BASE = "http://coder-agent:8092/api/coding"

class GenReq(BaseModel):
    request: str

@router.post("/generate")
async def proxy_generate(req: GenReq):
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{BASE}/generate", json=req.dict())
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    return r.json()
```

Register the router in Gateway’s app bootstrap (same as other service routers). Gateway is already exposed at **8080** with Swagger docs fileciteturn1file10.

---

## 13) Brain Router: when to call `coding.generate`

- Leave Brain’s heuristics intact. The **Brain router** already supports confidence‑based escalation and semantic caching; when a request contains cues like “write code / unit test / refactor,” route to the new tool by name (or make it selectable via prompt) fileciteturn1file3.
- The CLI can toggle agent mode (`/agent on`) so ReAct can call tools like `coding.generate`—this mirrors existing flows for web_search/CAD fileciteturn1file7.

---

## 14) CLI Usage (two quick paths)

- **Direct tool call via CLI**:
  ```bash
  kitty-cli say "/agent on. Call coding.generate to implement: write a function that returns all primes < 100, with pytest."
  ```
- (Optional) Add a dedicated CLI verb `code` that POSTs to `/api/coding/generate` like other commands; model selection can be `kitty-coder` via existing `/model` switch fileciteturn1file10.

---

## 15) Metrics & Logs

Export Prometheus counters in the agent (optional):

```python
# services/coder-agent/src/coder_agent/agent.py
from prometheus_client import Counter, Histogram

CODER_REQ = Counter("coder_requests_total", "Total coding requests")
CODER_LAT = Histogram("coder_latency_seconds", "End-to-end latency")

def run_coding_job(text: str):
    CODER_REQ.inc()
    with CODER_LAT.time():
        ...
```

Grafana/Prometheus endpoints are already part of KITTY’s stack; your service will be scraped alongside others fileciteturn1file10 fileciteturn1file3.

---

## 16) Safety & Policy

- **Hazard classes**: coding tools remain **low**. For anything that executes code outside the sandbox, require confirmation (hazard workflow) and an allow‑listed command path via the Broker MCP fileciteturn1file6.
- **Audit logging**: forward structured logs to the existing PostgreSQL audit trail like other tool invocations (reuse Gateway middleware) fileciteturn1file6.

---

## 17) End‑to‑End Test

`services/coder-agent/tests/test_smoke.py`

```python
import requests, os

BASE = os.getenv("CODER_BASE", "http://localhost:8092/api/coding")

def test_generate():
    r = requests.post(f"{BASE}/generate", json={"request": "Write fib(n) and tests"})
    assert r.status_code == 200
    j = r.json()
    assert "code" in j and "tests" in j
```

Run locally:
```bash
pytest services/coder-agent/tests -q
```

---

## 18) Bring‑up Checklist

1. **Build & run**: `docker compose -f infra/compose/docker-compose.yml up -d --build coder-agent`  
2. **Health**: `curl http://localhost:8092/docs` (FastAPI docs)  
3. **Gateway proxy**: `curl -X POST http://localhost:8080/api/coding/generate -H "Content-Type: application/json" -d '{"request":"Write fizzbuzz + pytest"}'` fileciteturn1file10  
4. **Agent mode** in CLI: `/agent on` → utter a natural request that implies coding; ReAct will call `coding.generate` if heuristics match fileciteturn1file7.

---

## 19) Design Notes & Extensions

- **Model neutrality**: swap local models freely—Q4 for tool‑calling, F16 for deeper synthesis, or a dedicated coder alias; KITTY already documents primary/coder model aliases (e.g., `kitty-coder`) fileciteturn1file14 fileciteturn1file19.
- **Memory integration**: pipe successful solutions into the Memory MCP (`/api/memory/remember`) so future coding tasks can retrieve patterns/snippets fast fileciteturn1file14.
- **Research bridge**: when offline later becomes optional, let ReAct escalate to research (SearXNG/Brave/Jina) only on explicit operator intent (password gate remains `omega`) fileciteturn1file12.
- **MCP first**: alternatively, expose `coding.generate` as its own MCP server to plug into KITTY’s tool stack uniformly, alongside Home Assistant, CAD, Memory, and Broker servers fileciteturn1file14.

---

## 20) Troubleshooting

- **llama.cpp server not reachable** → verify Q4/F16 servers are healthy (see logs and watchdog helpers) fileciteturn1file11 fileciteturn1file7.  
- **Gateway 502 for coding** → check the `coder-agent` container logs and ensure the route file is registered in Gateway (Swagger @ 8080) fileciteturn1file10.  
- **Sandbox timeouts** → increase `CODER_TEST_TIMEOUT_SEC`; keep unit tests minimal to stay deterministic.

---

### See also
- 🧠 [LangGraph DAG patterns](https://www.google.com/search?q=LangGraph+DAG+patterns+for+coding+agents) — patterns for plan/refine loops
- 🪝 [LangChain Tools](https://www.google.com/search?q=LangChain+tools+create+custom+tool) — wrap external actions as tools
- 🐍 [pytest best practices](https://www.google.com/search?q=pytest+best+practices) — keep tests fast/deterministic for LLM loops
- 🧱 [llama.cpp server API](https://www.google.com/search?q=llama.cpp+server+OpenAI+compatible+chat+completions) — configure OpenAI‑compatible endpoints locally

---

**Why this matches KITTY**  
- Microservice fits existing service breakdown (Gateway/Brain/CAD/…); MCP/tool‑registry pattern remains intact; llama.cpp dual‑server architecture is leveraged as intended.  
- Safety and observability reuse core KITTY features (hazard workflows, allow‑lists, audits, Prometheus), and the CLI’s agent mode enables tool invocation in natural language.  
All of these are consistent with KITTY’s documented architecture and operational conventions fileciteturn1file4 fileciteturn1file3 fileciteturn1file14.
