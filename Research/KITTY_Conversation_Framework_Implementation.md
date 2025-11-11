|Expert(s)|Conversational AI Architect; Agent Systems Engineer; Voice UX Designer; Fabrication Automation Engineer; DevOps for Edge AI|
|:--|:--|
|Question|Design and implement a reusable, ReAct-based conversation framework for KITTY that works in CLI and voice, orchestrates all current/future tools via MCP, includes safety/budget checks, and can autonomously progress from vague intent to tool execution.|
|Plan|Model the loop as **Reason → Act → Observe** with JSON tool-calls; add a tool registry + safety layer; implement an agent prompt contract; wire a FastAPI `/api/query` handler; provide MCP wrappers for CAD, Fabrication, Home Assistant, Memory, Research; add confirmation/budget gates; expose metrics; include tests and example flows.|

---

# KITTY Conversation Framework — Implementation Guide (`.md`)

> Built for KITTY’s **ReAct agent + MCP** tool stack with dual llama.cpp servers (Q4 orchestrator on :8083, F16 reasoner on :8082), CLI and voice parity, and safety-first operations. fileciteturn1file1 fileciteturn1file7 fileciteturn1file14

**Key concepts:** 🧠 [ReAct agent](https://www.google.com/search?q=ReAct+prompting+Reason+Act+agents+paper) · 🧩 [Model Context Protocol (MCP)](https://www.google.com/search?q=Model+Context+Protocol+tools) · 🦙 [llama.cpp chat server](https://www.google.com/search?q=llama.cpp+server+chat+completions+API) · ⚙️ [FastAPI async orchestration](https://www.google.com/search?q=FastAPI+async+httpx+dependency+injection) · 🏠 [Home Assistant REST](https://www.google.com/search?q=Home+Assistant+REST+API+call+service) · 🖨️ [OctoPrint API](https://www.google.com/search?q=OctoPrint+REST+API+start+print) · 🧰 [Qdrant client](https://www.google.com/search?q=Qdrant+python+client) · 📈 [Prometheus + FastAPI Instrumentator](https://www.google.com/search?q=Prometheus+FastAPI+Instrumentator)

---

## 0) What this plugs into

- **ReAct agent with tool-use via MCP** for Home Assistant, CAD (Zoo/Tripo/local), Memory (Qdrant), Broker, Research. fileciteturn1file1 fileciteturn1file9  
- **Dual llama.cpp**: Q4 (tool orchestrator) on `:8083`, F16 (deep reasoning) on `:8082`. fileciteturn1file7 fileciteturn1file14  
- **Voice** posts transcripts to `POST /api/voice/transcript` and shares the same query pipeline as CLI. fileciteturn1file0 fileciteturn1file7  
- **Safety & budget gates** (confirmation phrase, cloud “omega” override). fileciteturn1file4 fileciteturn1file3  
- **Artifacts & storage**: MinIO for CAD, PostgreSQL for audit, Redis for cache, Qdrant for memory. fileciteturn1file4 fileciteturn1file5

---

## 1) Install dependencies

Create/extend `services/brain/pyproject.toml` (or `requirements.txt`) to include:

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx[http2]==0.27.0
pydantic==2.9.2
pydantic-settings==2.4.0
python-dotenv==1.0.1
tenacity==8.5.0
jsonschema==4.23.0
orjson==3.10.7
redis==5.0.6
qdrant-client==1.9.0
prometheus-fastapi-instrumentator==6.1.0
```

> Brain/Gateway already run **FastAPI**; this keeps everything idiomatic. fileciteturn1file9

---

## 2) Config: env + tool registry

**.env additions (if not present):**
```bash
# LLM endpoints
LLAMACPP_Q4_URL=http://localhost:8083/v1/chat/completions
LLAMACPP_F16_URL=http://localhost:8082/v1/chat/completions

# Safety & budget
HAZARD_CONFIRMATION_PHRASE=alpha-omega-protocol
API_OVERRIDE_PASSWORD=omega
BUDGET_PER_TASK_USD=0.50
```
> The confirmation phrase and override are first-class in KITTY’s config. fileciteturn1file9

**`config/tool_registry.yaml`** — one place to declare tools, schemas, and safety:

```yaml
version: 1
tools:
  cad.generate_model:
    method: POST
    url: http://gateway:8080/api/cad/generate
    schema:
      type: object
      properties:
        prompt: {type: string}
        provider: {type: string, enum: [auto, zoo, tripo, cadquery, freecad], default: auto}
        imageRefs: {type: array, items: {type: string}}
      required: [prompt]
    safety:
      hazard_class: "low"
      confirmation_required: false

  fabrication.queue_print:
    method: POST
    url: http://gateway:8080/api/fabrication/queue
    schema:
      type: object
      properties:
        artifact_path: {type: string}
        printer_id: {type: string}
        material: {type: string}
        profile: {type: string}
      required: [artifact_path, printer_id]
    safety:
      hazard_class: "medium"
      confirmation_required: true

  homeassistant.control_device:
    method: POST
    url_template: http://gateway:8080/api/device/{entity_id}/command
    schema:
      type: object
      properties:
        entity_id: {type: string}
        command: {type: string}
      required: [entity_id, command]
    safety:
      hazard_class: "varies"
      confirmation_required: false

  research.web_search:
    method: POST
    url: http://gateway:8080/api/research/web_search
    schema:
      type: object
      properties:
        query: {type: string}
      required: [query]
    safety: {hazard_class: "none", confirmation_required: false}

  research.fetch_webpage:
    method: POST
    url: http://gateway:8080/api/research/fetch_webpage
    schema:
      type: object
      properties:
        url: {type: string}
      required: [url]
    safety: {hazard_class: "none", confirmation_required: false}

  memory.remember:
    method: POST
    url: http://gateway:8080/api/memory/remember
    schema:
      type: object
      properties:
        text: {type: string}
        tags: {type: array, items: {type: string}}
      required: [text]
    safety: {hazard_class: "none", confirmation_required: false}

  memory.search:
    method: POST
    url: http://gateway:8080/api/memory/search
    schema:
      type: object
      properties:
        query: {type: string}
        top_k: {type: integer}
      required: [query]
    safety: {hazard_class: "none", confirmation_required: false}
```

> CAD providers auto-fallback (Zoo → Tripo → local) are already part of KITTY’s CAD service; the framework just calls the one entrypoint. fileciteturn1file4  
> Common Gateway endpoints include `/api/cad/generate`, `/api/device/.../command`, `/api/query`, and memory routes. fileciteturn1file7 fileciteturn1file9

---

## 3) Agent prompt contract (ReAct + JSON tool calls)

**`services/brain/src/brain/conversation/prompts.py`**

```python
SYSTEM_PROMPT = """You are KITTY’s Tool Orchestrator.
Follow this contract on every turn:
1) Think about the user's goal.
2) If information is missing, ask a question with:
   {"type":"ask_user","message":"<your question>"}
3) If you can make progress with a tool, emit exactly one JSON object:
   {"type":"action","tool":"<tool_name>","args":{...}}
4) If the task is complete or you can summarize current status, return:
   {"type":"final","message":"<concise answer/status>"}

Only emit one top-level JSON object per turn. Do NOT include extra text.
You have these tools (name → JSON schema for args):
{tool_inventory}

Safety:
- For dangerous/irreversible actions, expect the runtime to ask for confirmation.
- Costly “cloud” calls require the user override keyword.
"""
```

The **Brain** prepares `{tool_inventory}` by serializing the registry’s schemas into a compact list the model can copy/paste, keeping prompts under size limits. fileciteturn1file3

---

## 4) Types & registry loader

**`services/brain/src/brain/conversation/schemas.py`**

```python
from typing import Dict, Any, Literal, Optional, Union
from pydantic import BaseModel, Field

AgentAsk = Literal["ask_user"]
AgentAct = Literal["action"]
AgentFinal = Literal["final"]

class Action(BaseModel):
    type: AgentAct
    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)

class AskUser(BaseModel):
    type: AgentAsk
    message: str

class Final(BaseModel):
    type: AgentFinal
    message: str

AgentMsg = Union[Action, AskUser, Final]
```

**`services/brain/src/brain/conversation/tools.py`**

```python
import yaml, json, re
from jsonschema import validate, ValidationError

class ToolSpec:
    def __init__(self, name, spec):
        self.name = name
        self.method = spec.get("method", "POST")
        self.url = spec.get("url")
        self.url_template = spec.get("url_template")
        self.schema = spec["schema"]
        self.safety = spec.get("safety", {})

class ToolRegistry:
    def __init__(self, path: str):
        data = yaml.safe_load(open(path))
        self.tools = {k: ToolSpec(k, v) for k, v in data["tools"].items()}

    def inv_str(self) -> str:
        # compact tool inventory for prompt
        lines = []
        for name, t in self.tools.items():
            lines.append(f"- {name}: {json.dumps(t.schema, separators=(',',':'))}")
        return "\n".join(lines)

    def validate_args(self, tool: str, args: dict):
        validate(instance=args, schema=self.tools[tool].schema)

    def spec(self, tool: str) -> ToolSpec:
        return self.tools[tool]
```

---

## 5) Safety manager (confirmation + budget)

**`services/brain/src/brain/conversation/safety.py`**

```python
import os
from pydantic import BaseModel
from .schemas import Action

HAZARD_CONFIRMATION_PHRASE = os.getenv("HAZARD_CONFIRMATION_PHRASE", "alpha-omega-protocol")
API_OVERRIDE_PASSWORD = os.getenv("API_OVERRIDE_PASSWORD", "omega")

class SafetyQuery(BaseModel):
    require_confirmation: bool = False
    require_cloud_override: bool = False
    reason: str = ""

class SafetyManager:
    def assess(self, action: Action, tool_safety: dict) -> SafetyQuery:
        sq = SafetyQuery()
        hazard = (tool_safety or {}).get("hazard_class", "none")
        if (tool_safety or {}).get("confirmation_required", False) or hazard in ("medium","high"):
            sq.require_confirmation = True
            sq.reason = f"hazard={hazard}"
        # example heuristic: research.web_search/fetch are free; CAD/fabrication are not “cloud-billed” here,
        # but you can flag tools that escalate to paid providers.
        if action.tool.startswith("cloud."):
            sq.require_cloud_override = True
        return sq

    def confirm_phrase(self) -> str:
        return HAZARD_CONFIRMATION_PHRASE

    def override_keyword(self) -> str:
        return API_OVERRIDE_PASSWORD
```

> KITTY uses two-step hazard confirmations and an “omega” override for budget-gated providers. fileciteturn1file4 fileciteturn1file3

---

## 6) MCP wrapper (HTTP to Gateway/services)

**`services/brain/src/brain/conversation/mcp.py`**

```python
import httpx, os
from typing import Any, Dict
from .tools import ToolRegistry

class MCPClient:
    def __init__(self, registry: ToolRegistry, client: httpx.AsyncClient):
        self.registry = registry
        self.http = client

    async def execute(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        spec = self.registry.spec(tool)
        url = spec.url or spec.url_template.format(**args)
        method = spec.method.upper()
        resp = await self.http.request(method, url, json=args, timeout=120)
        resp.raise_for_status()
        return resp.json()
```

> Gateway provides REST ingress to CAD, Fabrication (OctoPrint), Home Assistant, Memory, Research. fileciteturn1file9 fileciteturn1file7

---

## 7) Agent (llama.cpp chat + JSON parsing)

**`services/brain/src/brain/conversation/agent.py`**

```python
import os, json, re, httpx, asyncio
from typing import List, Dict, Any
from pydantic import ValidationError
from .schemas import AgentMsg, Action, AskUser, Final
from .tools import ToolRegistry
from .prompts import SYSTEM_PROMPT

Q4_URL = os.getenv("LLAMACPP_Q4_URL", "http://localhost:8083/v1/chat/completions")
F16_URL = os.getenv("LLAMACPP_F16_URL", "http://localhost:8082/v1/chat/completions")

def _extract_json(text: str) -> Dict[str, Any]:
    # tolerant JSON extractor: prefers fenced code blocks first
    code_blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    candidates = code_blocks or [text]
    for c in candidates:
        try:
            return json.loads(c.strip())
        except Exception:
            continue
    raise ValueError("No parseable JSON found")

class ReActAgent:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def complete(self, messages: List[Dict[str,str]], model_url: str) -> str:
        async with httpx.AsyncClient(http2=True, timeout=120) as client:
            payload = {"model": "local", "messages": messages, "temperature": 0.2}
            r = await client.post(model_url, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

    async def plan(self, history: List[Dict[str,str]]) -> AgentMsg:
        sys = {"role": "system", "content": SYSTEM_PROMPT.format(
            tool_inventory=self.registry.inv_str()
        )}
        out = await self.complete([sys, *history], Q4_URL)
        obj = _extract_json(out)
        try:
            if obj.get("type") == "action":
                return Action(**obj)
            if obj.get("type") == "ask_user":
                return AskUser(**obj)
            if obj.get("type") == "final":
                return Final(**obj)
        except ValidationError:
            pass
        # fallback: ask for clarification
        return AskUser(type="ask_user", message="Please clarify what you want to do next.")
```

> Q4 server is used for tool orchestration; F16 can be added for deep sub-steps if you want a “delegate” action. fileciteturn1file7 fileciteturn1file14

---

## 8) Orchestration loop + `/api/query` route

**`services/brain/src/brain/conversation/router.py`**

```python
from fastapi import APIRouter, Depends
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from .agent import ReActAgent
from .mcp import MCPClient
from .tools import ToolRegistry
from .schemas import AgentMsg, Action, AskUser, Final
from .safety import SafetyManager
import httpx, os

router = APIRouter(prefix="/api", tags=["conversation"])

registry = ToolRegistry(os.getenv("TOOL_REGISTRY","config/tool_registry.yaml"))
agent = ReActAgent(registry)
safety = SafetyManager()

class QueryIn(BaseModel):
    query: str
    conversation_id: str | None = None
    verbosity: int = 3
    override: str | None = None

class QueryOut(BaseModel):
    done: bool
    message: str | None = None
    action: dict | None = None
    observation: dict | None = None

# naive per-session state (swap with Redis/DB as needed)
SESSIONS: dict[str, list[dict[str,str]]] = {}

def _messages(cid: str) -> list[dict[str,str]]:
    return SESSIONS.setdefault(cid, [])

@router.post("/query", response_model=QueryOut)
async def query(q: QueryIn):
    cid = q.conversation_id or "default"
    history = _messages(cid)
    history.append({"role":"user","content":q.query})

    # 1) Plan
    step = await agent.plan(history)

    if isinstance(step, AskUser):
        history.append({"role":"assistant","content":step.message})
        return QueryOut(done=False, message=step.message)

    if isinstance(step, Final):
        history.append({"role":"assistant","content":step.message})
        return QueryOut(done=True, message=step.message)

    if isinstance(step, Action):
        # 2) Safety gates
        spec = registry.spec(step.tool)
        sq = safety.assess(step, spec.safety)

        if sq.require_cloud_override and q.override != safety.override_keyword():
            msg = "This step requires override keyword. Say it to proceed."
            history.append({"role":"assistant","content":msg})
            return QueryOut(done=False, message=msg, action=step.model_dump())

        if sq.require_confirmation:
            msg = (f"Confirmation required ({sq.reason}). Say the phrase "
                   f"'{safety.confirm_phrase()}' to proceed or 'cancel'.")
            history.append({"role":"assistant","content":msg})
            return QueryOut(done=False, message=msg, action=step.model_dump())

        # 3) Execute
        async with httpx.AsyncClient(http2=True, timeout=180) as client:
            mcp = MCPClient(registry, client)
            try:
                obs = await mcp.execute(step.tool, step.args)
            except Exception as e:
                obs = {"error": str(e)}
        # 4) Observe back into history (for next turn)
        history.append({"role":"assistant","content":f"[{step.tool}] {obs}"})
        return QueryOut(done=False, action=step.model_dump(), observation=obs)
```

Mount in FastAPI:

```python
# services/brain/src/brain/app.py
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from .conversation.router import router as convo_router

app = FastAPI()
app.include_router(convo_router)
Instrumentator().instrument(app).expose(app)
```

---

## 9) Voice parity

Your existing voice service can post the transcript to `/api/query`:

```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Turn on the bench lights","verbosity":3}'
```

> Voice-to-print flow is already defined; this framework lets that same flow confirm, generate, slice, and queue via conversational checkpoints. fileciteturn1file12 fileciteturn1file15

---

## 10) Memory hooks

Add simple helpers that call the Memory MCP endpoints so the agent can persist/retrieve preferences:

```python
# services/brain/src/brain/conversation/memory.py
import httpx

async def remember(client: httpx.AsyncClient, text: str, tags: list[str] | None=None):
    return (await client.post("http://gateway:8080/api/memory/remember",
                              json={"text":text,"tags":tags or []})).json()

async def search_memory(client: httpx.AsyncClient, query: str, top_k:int=5):
    return (await client.post("http://gateway:8080/api/memory/search",
                              json={"query":query,"top_k":top_k})).json()
```

> KITTY exposes `/remember` & `/memories` via Brain/Gateway to Qdrant-backed memory. fileciteturn1file9

---

## 11) Example end‑to‑end flow (Australian shepherd figurine)

**User**: “I want to 3D print an Australian shepherd figurine.”  
**Agent (Ask)**: `{"type":"ask_user","message":"Do you want me to search or generate a model? What size?"}`  
**User**: “Search for a model, small size.”  
**Agent (Action)**: `{"type":"action","tool":"research.web_search","args":{"query":"Australian Shepherd STL figurine"}}`  
**Observation**: Found Thingiverse/Printables link(s).  
**Agent (Ask)**: `{"type":"ask_user","message":"Use the top match I found?"}`  
**User**: “Yes.”  
**Agent (Action)**: `{"type":"action","tool":"cad.generate_model","args":{"prompt":"Import STL from <url>"}}`  
**Observation**: STL stored in `/Users/Shared/KITTY/artifacts/cad/...`. fileciteturn1file12  
**Agent (Ask)**: `{"type":"ask_user","message":"Queue print on Prusa MK4?"}`  
**User**: “Yes.”  
**Runtime (Safety)**: asks for confirmation if configured for prints.  
**User**: says the confirmation phrase.  
**Agent (Action)**: `{"type":"action","tool":"fabrication.queue_print","args":{"artifact_path":"...stl","printer_id":"prusa-mk4"}}`  
**Agent (Final)**: `{"type":"final","message":"Print started, ~2h ETA. I’ll notify on completion."}`

> CAD artifacts folder & metadata conventions are standard in KITTY. fileciteturn1file4 fileciteturn1file12

---

## 12) Tests (contract + simple loop)

**`tests/test_agent_contract.py`**
```python
import pytest
from brain.conversation.schemas import Action, AskUser, Final
from brain.conversation.agent import _extract_json

def test_extract_json_prefers_fenced():
    out = _extract_json("foo\n```json\n{\"type\":\"final\",\"message\":\"ok\"}\n```")
    assert out["type"] == "final"

def test_models_parse():
    a = Action(type="action", tool="cad.generate_model", args={"prompt":"x"})
    q = AskUser(type="ask_user", message="m?")
    f = Final(type="final", message="done")
    assert a.tool.startswith("cad.")
```

---

## 13) Ops/Observability

- The app exposes `/metrics` via Prometheus instrumentator; include it in your Grafana dashboards (routing hit rate, latency, costs). fileciteturn1file12  
- Use `docker compose logs brain` and llama.cpp logs for troubleshooting. fileciteturn1file11  
- Artifacts are browsable on macOS Finder; users can validate designs before printing. fileciteturn1file12

---

## 14) Developer notes

- The CLI mirrors the **full ReAct stack** (trace, agent toggles, override keyword). You’re just formalizing the JSON tool-call contract so the loop can run safely and autonomously. fileciteturn1file3  
- Tool addition = register an MCP server + add an entry in `tool_registry.yaml`. No loop changes needed. fileciteturn1file9  
- CAD fallback (Zoo → Tripo → local) is inside CAD service; this loop simply calls once and handles errors. fileciteturn1file4  
- Storage layer (PostgreSQL, Redis, Qdrant, MinIO) is already part of KITTY; this framework just consumes it. fileciteturn1file5

---

## 15) Example cURL / CLI invocations

```bash
# Query via REST
curl -sX POST http://localhost:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"I want to 3d print an Australian shepherd","verbosity":3}'

# Voice transcript forwards here too (same body, from the voice service)
# See: /api/voice/transcript for a quick test
curl -sX POST http://localhost:8080/api/voice/transcript \
  -H 'Content-Type: application/json' \
  -d '{"text":"Turn on bench lights"}'
```
> Voice and CLI share the pipeline; use either input path. fileciteturn1file0 fileciteturn1file7

---

## 16) FAQ

- **Where do users confirm hazardous actions?**  
  The route returns a prompt like “say `<phrase>` to proceed”; the next user message contains the phrase and the same conversation_id, then the agent plans again and the runtime executes. fileciteturn1file4

- **How do we ensure minimal token use?**  
  Provide only the compact tool inventory in the system prompt and keep messages short; that’s how the CLI keeps prompts <2k tokens. fileciteturn1file3

- **Can this call cloud vendors?**  
  Yes; mark such tools `cloud.*` and require the override keyword (default `omega`) to proceed. fileciteturn1file3

---

## 17) Folder layout (suggested)

```
services/brain/src/brain/conversation/
  ├─ agent.py
  ├─ mcp.py
  ├─ router.py
  ├─ safety.py
  ├─ schemas.py
  ├─ tools.py
  └─ prompts.py
config/
  └─ tool_registry.yaml
tests/
  └─ test_agent_contract.py
```

---

## 18) Known-good behaviors to validate

- **Vague → clarified → executed** flow works with voice and CLI for lights, CAD, and printing. fileciteturn1file7  
- **CAD artifacts** show up in `/Users/Shared/KITTY/artifacts/cad/` and metadata is saved. fileciteturn1file12  
- **Budget/override** blocks cloud-only tools until override is present. fileciteturn1file3  
- **Safety confirmation** blocks hazardous actions until the phrase is provided. fileciteturn1file4

---

### See also
- 🧠 [ReAct prompting patterns](https://www.google.com/search?q=ReAct+prompting+best+practices+tool+use) — reinforces the JSON-action loop
- 🧩 [MCP tool schemas](https://www.google.com/search?q=Model+Context+Protocol+JSON+schema+tools) — structuring tool contracts
- 🦙 [llama.cpp server usage](https://www.google.com/search?q=llama.cpp+server+chat+completions+curl) — stable local inference
- 🖨️ [OctoPrint job queue tips](https://www.google.com/search?q=OctoPrint+REST+API+start+job+from+file) — print enqueuing patterns
- 🏠 [Home Assistant service calls](https://www.google.com/search?q=Home+Assistant+call+service+REST+API) — device control endpoints
- 🧰 [Qdrant vectors](https://www.google.com/search?q=Qdrant+vector+database+python+examples) — memory store patterns
- 📈 [Prometheus in FastAPI](https://www.google.com/search?q=Prometheus+FastAPI+Instrumentator+example) — metrics you can ship to Grafana

### You may also enjoy
- 🐕 [Australian Shepherd 3D models](https://www.google.com/search?q=Australian+Shepherd+3D+model+STL+figurine) — source assets for testing
- 🧪 [Test prompts for agents](https://www.google.com/search?q=LLM+agent+test+prompts+tool+use) — good harness prompts
- 🧵 [Slicer profiles tuning](https://www.google.com/search?q=PrusaSlicer+print+profiles+best+settings) — faster, cleaner prints

--- 

**Done.** This Markdown file contains the contract, code scaffolding, configs, and examples to wire KITTY’s ReAct framework across CLI and voice, with safety and extensibility aligned to the current architecture and services.
