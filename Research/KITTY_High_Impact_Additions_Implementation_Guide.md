# KITTY — High‑Impact Additions (Offline, Model‑Agnostic) — Implementation Guide

|Expert(s)|Offline LLM Infra Architect; Retrieval/RAG Engineer; Multi‑Agent Systems Engineer; DevOps/SRE|
|:--|:--|
|Question|Implement **all high‑impact additions** to improve KITTY’s LangGraph agents and meta‑collectives while staying **offline‑first**.|
|Plan|Add a dedicated **Coder** model (alias `kitty-coder`), wire **Embeddings + local Reranker** into the Memory MCP (Qdrant), introduce a **Diversity seat** for councils (second small‑family model), and optionally add **Judge concurrency**. Provide file‑by‑file changes, env knobs, service routes, code snippets, tests, and a DoD.|

> This guide assumes your baseline stack is running with **dual llama.cpp** servers — **Q4 @ 8083** (tool orchestrator) and **F16 @ 8082** (deep reasoner); **Gateway @ 8080**, **Brain @ 8000**, **UI @ 4173**, Prometheus/Grafana; startup **order matters**. fileciteturn1file0 fileciteturn1file8 fileciteturn1file10

---

## 0) Scope & Constraints

- **Offline‑first**: no cloud calls. All models run locally via `llama.cpp` or CPU‑bound Transformers.
- **Non‑intrusive**: use the **tool registry** to expose new capabilities without changing agent code; Brain discovers tools on restart. fileciteturn1file7
- **Safety/observability**: keep **hazard workflows**, command **allow‑lists**, **audit logging**, **Prometheus** metrics. fileciteturn1file6 fileciteturn1file12

---

## 1) Dedicated *Coder* Model (Qwen2.5‑Coder‑32B‑Instruct, GGUF `q4_k_m`)

### 1.1 Download / Stage the model
```bash
# Recommended (already used in KITTY docs)
huggingface-cli download Qwen/Qwen2.5-Coder-32B-Instruct-GGUF \
  --local-dir /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF \
  --include "*q4_k_m.gguf"
```
Update paths per your host and storage. The README already shows the same pattern for **primary/coder** models. fileciteturn1file12 fileciteturn1file15

### 1.2 Set aliases in `.env`
Append (or confirm) the following:
```bash
# Local Models
LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models
LLAMACPP_PRIMARY_MODEL=Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q4_k_m.gguf
LLAMACPP_PRIMARY_ALIAS=kitty-primary
LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf
LLAMACPP_CODER_ALIAS=kitty-coder
```
These keys/aliases follow KITTY’s documented configuration. fileciteturn1file4

### 1.3 Start the servers then services
Use the **validated startup script** or the **Model Manager TUI** sequence (start llama.cpp servers, then Compose services). fileciteturn1file8 fileciteturn1file16

```bash
./ops/scripts/start-kitty-validated.sh
# or, with the TUI:
kitty-model-manager tui
# then in a new terminal:
docker compose -f infra/compose/docker-compose.yml up -d --build
```

### 1.4 Wire the agent runtime to use the coder alias
In your LangGraph/Agent Runtime (e.g., `services/agent-runtime/src/agent_runtime/llm_client.py`), ensure a **CODER** route uses the coder server/alias. (Matches the earlier LangGraph integration.)

```python
# excerpt: llm_client.py
def chat(messages, *, which="F16", temperature=None, max_tokens=None):
    base = {
        "Q4":  os.getenv("LLAMACPP_Q4_BASE",  "http://localhost:8083"),
        "F16": os.getenv("LLAMACPP_F16_BASE", "http://localhost:8082"),
        "CODER": os.getenv("LLAMACPP_CODER_BASE", os.getenv("LLAMACPP_F16_BASE","http://localhost:8082")),
    }[which]
    ...
```

Use `which="CODER"` in your coding graph nodes (code, tests, refine). This mirrors how your CLI can switch to `kitty-coder` as a model. fileciteturn1file17

### 1.5 Quick validation
```bash
curl -s -X POST http://localhost:8080/api/coding/generate \
  -H "Content-Type: application/json" \
  -d '{"request":"Write a prime sieve and pytest tests"}' | jq
```
The coding agent route and CLI flows are consistent with Gateway/Brain wiring in README. fileciteturn1file10

---

## 2) Embeddings + Local Reranker (Memory MCP → Qdrant)

**Goal:** Improve retrieval quality for planning/judging. Memory MCP already exposes `/api/memory/remember` and `/api/memory/search` (Qdrant + embeddings). We add a stronger embedder and a CPU reranker. fileciteturn1file4

### 2.1 Dependencies (Memory service)
`services/memory/requirements.txt` (or the appropriate memory component):
```txt
qdrant-client>=1.8
sentence-transformers>=3.0
```
*(If your Memory code already has these, keep versions consistent.)*

### 2.2 Env knobs
Append to `.env`:
```bash
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5          # or BAAI/bge-m3 for multilingual
RERANKER_MODEL=BAAI/bge-reranker-base
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=kitty_memories
```

### 2.3 Memory: embed + upsert
Implement/confirm in Memory service (pseudo‑module `services/memory/src/memory/store.py`):
```python
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models as qm

emb = SentenceTransformer(os.getenv("EMBEDDING_MODEL","BAAI/bge-small-en-v1.5"))
cli = QdrantClient(os.getenv("QDRANT_URL","http://localhost:6333"))
COL = os.getenv("QDRANT_COLLECTION","kitty_memories")

def remember(text: str, metadata: dict):
    vec = emb.encode([text], normalize_embeddings=True)[0].tolist()
    cli.upsert(collection_name=COL, points=[
        qm.PointStruct(id=str(uuid.uuid4()), vector=vec, payload={**metadata, "text": text})
    ])
    return {"ok": True}
```

### 2.4 Memory: search + rerank
`services/memory/src/memory/search.py`:
```python
from sentence_transformers import SentenceTransformer, CrossEncoder

emb = SentenceTransformer(os.getenv("EMBEDDING_MODEL","BAAI/bge-small-en-v1.5"))
reranker = None
rm = os.getenv("RERANKER_MODEL")
if rm:
    try:
        reranker = CrossEncoder(rm)
    except Exception:
        reranker = None  # safe fallback

def search(query: str, top_k: int = 8):
    qv = emb.encode([query], normalize_embeddings=True)[0].tolist()
    hits = cli.search(collection_name=COL, query_vector=qv, limit=top_k*3)
    docs = [{"text": h.payload.get("text",""), "score": h.score, "payload": h.payload} for h in hits]

    if reranker:
        pairs = [(query, d["text"]) for d in docs]
        scores = reranker.predict(pairs).tolist()
        for d, s in zip(docs, scores): d["rerank"] = float(s)
        docs.sort(key=lambda x: x.get("rerank", 0.0), reverse=True)
    else:
        # fall back to vector score
        docs.sort(key=lambda x: x["score"], reverse=True)

    return docs[:top_k]
```

### 2.5 Expose via Gateway/Brain
This augments the existing Memory MCP endpoints; your CLI already maps `/remember` and `/memories` to them. fileciteturn1file4 fileciteturn1file3

**Smoke tests**:
```bash
# store
curl -s -X POST http://localhost:8080/api/memory/remember \
  -H "Content-Type: application/json" \
  -d '{"text":"Prefers ABS on Voron"}' | jq

# search
curl -s -X POST http://localhost:8080/api/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query":"Voron ABS preference"}' | jq
```

---

## 3) Diversity Seat for Councils (Second Small‑Family Model)

**Goal:** Reduce correlated failure by adding a second model family for at least one council seat (e.g., **Mistral‑7B‑Instruct** or **Gemma‑2‑9B‑Instruct**, `q4_k_m`). This can run as an extra Q4‑class server or re‑use Q4 with different seeds (lower diversity). Startup order and TUI management are already documented. fileciteturn1file8 fileciteturn1file16

### 3.1 Download / stage the diversity model
```bash
# Example: Mistral-7B-Instruct (choose a GGUF Q4 variant you trust)
huggingface-cli download TheBloke/Mistral-7B-Instruct-v0.2-GGUF \
  --local-dir /Users/Shared/Coding/models/Mistral-7B-Instruct-GGUF \
  --include "*q4_k_m.gguf"
```

### 3.2 Start an additional Q4 server (port 8084)
If your scripts/TUI don’t manage a third server, launch `llama-server` directly (second terminal):
```bash
/path/to/llama.cpp/llama-server \
  --host 0.0.0.0 --port 8084 \
  --model "/Users/Shared/Coding/models/Mistral-7B-Instruct-GGUF/<file>.gguf" \
  --ctx-size 8192 --parallel 2 --seed 42
```
*(Adjust flags to your build.)* Your **launcher/TUI** can still monitor health of known ports; use logs to verify. fileciteturn1file13

### 3.3 Add an env for the new seat and route one agent to it
Append to `.env`:
```bash
LLAMACPP_Q4B_BASE=http://localhost:8084    # diversity seat
```

Update the Agent Runtime client so LangGraph can target it:
```python
# llm_client.py (add mapping)
base = {
  "Q4":  os.getenv("LLAMACPP_Q4_BASE",  "http://localhost:8083"),
  "Q4B": os.getenv("LLAMACPP_Q4B_BASE", "http://localhost:8083"),  # fallback to Q4 if absent
  "F16": os.getenv("LLAMACPP_F16_BASE", "http://localhost:8082"),
  "CODER": os.getenv("LLAMACPP_CODER_BASE", os.getenv("LLAMACPP_F16_BASE","http://localhost:8082")),
}[which]
```

In your **collective** council builder, send at least one specialist to `which="Q4B"` and **vary seeds/temperature** across members:
```python
# collective/graph.py (council proposers)
for i in range(k):
    which = "Q4B" if i == 0 else "Q4"
    props.append(chat([
      {"role":"system","content":f"You are specialist_{i+1}."},
      {"role":"user","content":s["task"]}
    ], which=which, temperature=0.8, max_tokens=600))
```

**Smoke test**:
```bash
curl -s -X POST http://localhost:8080/api/collective/run \
  -H "Content-Type: application/json" \
  -d '{"task":"Compare PETG vs ABS for Voron 0.2mm.","pattern":"council","k":3}' | jq
```

---

## 4) *Optional* Judge Concurrency (F16 scaling)

**Goal:** Reduce latency during council/debate **judging** by adding another F16‑class server and doing simple **round‑robin**. (Only if memory allows.)

### 4.1 Start a second F16 server (port 8085)
```bash
/path/to/llama.cpp/llama-server \
  --host 0.0.0.0 --port 8085 \
  --model "/Users/Shared/Coding/models/Llama-3.3-70B-Instruct-F16/<file>.gguf" \
  --ctx-size 12288 --parallel 2 --seed 7
```
See README tuning notes for context/predict/timeouts. fileciteturn1file18

### 4.2 Add env and route judges round‑robin
```bash
LLAMACPP_F16_B_BASE=http://localhost:8085
```

```python
# llm_client.py (judge balancer)
import itertools
_f16_cycle = itertools.cycle([
    os.getenv("LLAMACPP_F16_BASE","http://localhost:8082"),
    os.getenv("LLAMACPP_F16_B_BASE", os.getenv("LLAMACPP_F16_BASE","http://localhost:8082"))
])

def chat(messages, *, which="F16", **kw):
    if which == "F16":
        base = next(_f16_cycle)
    ...
```

**Note:** If you cannot run a second F16, keep one judge and tighten prompts or raise `LLAMACPP_N_PREDICT/CTX` per hardware guidance. fileciteturn1file18

---

## 5) Compose & Service Env (summary)

If you prefer Compose‑managed env injection for **agent-runtime**, add:
```yaml
# infra/compose/docker-compose.yml
  agent-runtime:
    environment:
      - LLAMACPP_Q4_BASE=${LLAMACPP_Q4_BASE:-http://llamacpp-q4:8083}
      - LLAMACPP_Q4B_BASE=${LLAMACPP_Q4B_BASE:-http://llamacpp-q4b:8084}   # optional
      - LLAMACPP_F16_BASE=${LLAMACPP_F16_BASE:-http://llamacpp-f16:8082}
      - LLAMACPP_F16_B_BASE=${LLAMACPP_F16_B_BASE:-http://llamacpp-f16b:8085} # optional
      - LLAMACPP_CODER_BASE=${LLAMACPP_CODER_BASE:-http://llamacpp-f16:8082}
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}
      - RERANKER_MODEL=${RERANKER_MODEL:-BAAI/bge-reranker-base}
```
Ports and service roles align with the **Service Breakdown** and **Gateway/Brain** structure. fileciteturn1file10

---

## 6) CLI / Operator Examples

```bash
# Turn on agent mode (routes through Brain to tools)
kitty-cli shell
> /agent on                                      # enable tool use fileciteturn1file3
> call collective.run pattern=council k=3 compare PETG vs ABS
> /model kitty-coder                             # switch to coder model if desired fileciteturn1file17
> /remember Ordered more PLA                     # Memory MCP store fileciteturn1file4
> /memories PLA                                  # Memory MCP search
```

```bash
# REST smoke
curl -s http://localhost:8080/docs > /dev/null   # Gateway alive (Swagger) fileciteturn1file10
curl -s -X POST http://localhost:8080/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"task":"Write fizzbuzz + pytest","mode":"coding"}' | jq
```

---

## 7) Definition of Done (DoD)

- [ ] **Coder** model present; alias `kitty-coder` resolves; coding graph uses `which="CODER"`; end‑to‑end test passes. fileciteturn1file4  
- [ ] **Memory** service indexes with **BGE embeddings** and re‑ranks with **BGE reranker**; `/remember` + `/memories` return higher‑quality matches. fileciteturn1file4  
- [ ] **Diversity seat** available (port **8084**); council requests show mixed families in proposals; verdict produced by F16. fileciteturn1file8  
- [ ] *(Optional)* **Judge concurrency** (port **8085**) working or tuned single‑judge with context/predict settings. fileciteturn1file18  
- [ ] Metrics and logs visible in Grafana/Prometheus; audit trail records tool invocations. fileciteturn1file12

---

## 8) Troubleshooting

- **Gateway 502** → check agent‑runtime logs; verify llama.cpp servers on **8082/8083** (and optional **8084/8085**) are reachable; confirm startup order. fileciteturn1file0 fileciteturn1file8  
- **Coder not used** → ensure `LLAMACPP_CODER_BASE` set and graph nodes use `which="CODER"`; CLI `/model kitty-coder` also works. fileciteturn1file17  
- **Memory results weak** → verify embedding model loaded and **reranker** is not failing (fallback is vector‑only).  
- **OOM / slow** → reduce council `k`, use smaller diversity model, or drop second F16; adjust **CTX/N_PREDICT** (README tuning). fileciteturn1file18

---

### Appendix — Where this matches KITTY

- Startup order (llama.cpp → Docker services → UI), port layout, and service roles (Gateway/Brain/MCP/Memory) are unchanged. fileciteturn1file0 fileciteturn1file10  
- Tooling remains **registry‑driven**; Brain discovers on restart; CLI `/agent` mirrors ReAct orchestration. fileciteturn1file7 fileciteturn1file3
