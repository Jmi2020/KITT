# KITTY — Collective‑Confidentiality & Memory Scoping (Implementation Guide)

|Expert(s)|Multi‑Agent Systems Researcher; Prompt/Memory Architect; DevOps/SRE|
|:--|:--|
|Question|Implement the **proposer‑blinding + memory scoping** strategy for KITTY’s council/debate collectives and decide whether to **remove** existing “KITTY development” memories.|
|Plan|Add **env flags**, upgrade **Memory MCP** with **tag‑aware retrieval**, update **Agent Runtime** graphs to **blind proposers** (domain‑only context) while **informing judges**, provide **A/B switch**, **diversity metrics**, and a **retag/migration** script. Integrate with Gateway/Brain **without breaking offline‑first**. Cite KITTY README for ports, endpoints, and tool‑registry patterns.|

> TL;DR — **Do not delete** development memories. Keep them in Memory MCP but **tag** them (`meta, dev, collective`) and **exclude** only for *proposers*. Judges/planners may see them. Memory endpoints already exist (`/api/memory/remember`, `/api/memory/search`) and map to Qdrant + embeddings via the Memory MCP. fileciteturn1file0

---

## 0) Assumptions & References

- **Memory MCP** is backed by **Qdrant**; Brain exposes `POST /api/memory/remember` and `POST /api/memory/search` (CLI: `/remember`, `/memories`). fileciteturn1file1 fileciteturn1file4 fileciteturn1file15  
- **Gateway** runs at **:8080** with Swagger; services follow the tool‑registry pattern (YAML → Gateway proxy → Brain auto‑discovers on restart). fileciteturn1file11 fileciteturn1file7  
- **Startup order**: **llama.cpp Q4 (8083)** + **F16 (8082)** → **Docker services** (Brain, Gateway, Memory, …) → **UIs**. fileciteturn1file2

---

## 1) Environment Flags (add to `.env`)

```bash
# Collective-confidentiality
COLLECTIVE_PROPOSER_BLIND=1                 # hide collective meta from proposers
MEMORY_EXCLUDE_TAGS=meta,dev,collective     # proposer retrieval excludes these
MEMORY_INCLUDE_TAGS=domain,procedure,safety # proposer retrieval prefers these

# Prompt hints
COLLECTIVE_HINT_PROPOSER="Solve independently; do not reference other agents or a group."
COLLECTIVE_HINT_JUDGE="You are the judge; prefer safety, clarity, testability."
```

- Flags are read by **Agent Runtime** and **Memory service** (below). No cloud calls are introduced; offline‑first preserved.

---

## 2) Memory MCP — Tag‑Aware Retrieval (Qdrant)

**Goal:** Keep your “KITTY development” notes but scope them via tags so **proposers** don’t see them; **judges/planners** still can.

### 2.1 Extend Memory search with include/exclude tags

Create/augment search function (Qdrant + embeddings) to honor tag filters:

```python
# services/memory/src/memory/search.py
import os
from typing import List, Optional
from qdrant_client import QdrantClient, models as qm
from sentence_transformers import SentenceTransformer, CrossEncoder

EXCLUDE = {t.strip() for t in os.getenv("MEMORY_EXCLUDE_TAGS","meta,dev,collective").split(",") if t}
INCLUDE = {t.strip() for t in os.getenv("MEMORY_INCLUDE_TAGS","domain,procedure,safety").split(",") if t}

emb = SentenceTransformer(os.getenv("EMBEDDING_MODEL","BAAI/bge-small-en-v1.5"))
reranker = None
rm = os.getenv("RERANKER_MODEL")
if rm:
    try: reranker = CrossEncoder(rm)
    except Exception: pass

cli = QdrantClient(os.getenv("QDRANT_URL","http://qdrant:6333"))
COL = os.getenv("QDRANT_COLLECTION","kitty_memories")

def _passes_tags(payload: dict) -> bool:
    tags = set((payload or {}).get("tags", []))
    if tags & EXCLUDE: return False
    if INCLUDE and not (tags & INCLUDE): return False
    return True

def search_filtered(query: str, top_k: int = 8):
    qv = emb.encode([query], normalize_embeddings=True)[0].tolist()
    hits = cli.search(collection_name=COL, query_vector=qv, limit=top_k*6)
    docs = [{"text": h.payload.get("text",""), "score": h.score, "payload": h.payload}
            for h in hits if _passes_tags(h.payload)]
    if reranker:
        pairs = [(query, d["text"]) for d in docs]
        scores = reranker.predict(pairs).tolist()
        for d, s in zip(docs, scores): d["rerank"] = float(s)
        docs.sort(key=lambda x: x.get("rerank",0.0), reverse=True)
    else:
        docs.sort(key=lambda x: x["score"], reverse=True)
    return docs[:top_k]
```

> Memory endpoints are already exposed by Brain/Gateway: `POST /api/memory/remember` and `POST /api/memory/search`. You can forward `include_tags`/`exclude_tags` through Gateway if you want operator control from CLI, or hard‑code them server‑side for proposers. fileciteturn1file0

### 2.2 Store with tags

When writing memories, include `tags` in the payload:

```python
# services/memory/src/memory/store.py (excerpt)
def remember(text: str, tags: list[str] = None, **meta):
    ...
    payload = {"text": text, "tags": tags or ["domain"], **meta}
    ...
```

**CLI examples** (unchanged at Gateway; the Memory service sets sensible defaults):  
`/remember Ordered more PLA` (implicit `["domain"]`) and `/memories PLA` work as documented. fileciteturn1file4

---

## 3) Agent Runtime — Blind Proposers, Informed Judge

Update your **collective graph** so council/debate *proposers* get only **domain context** (filtered), not meta/dev notes or collective framing. Judges/planners may read full context.

### 3.1 Context policy

```python
# services/agent-runtime/src/agent_runtime/context/policy.py
import os, httpx

EXCLUDE = os.getenv("MEMORY_EXCLUDE_TAGS","meta,dev,collective")
INCLUDE = os.getenv("MEMORY_INCLUDE_TAGS","domain,procedure,safety")

def fetch_domain_context(query: str, limit: int = 6):
    # Gateway proxies Memory MCP; documented at :8080/docs fileciteturn1file11
    r = httpx.post("http://gateway:8080/api/memory/search",
                   json={"query": query, "limit": limit,
                         "include_tags": INCLUDE, "exclude_tags": EXCLUDE},
                   timeout=30)
    r.raise_for_status()
    docs = r.json()
    return "\n".join(d.get("text","") for d in docs)
```

### 3.2 Proposer nodes (council/debate)

```python
# services/agent-runtime/src/agent_runtime/collective/graph.py (council)
import os
from ..context.policy import fetch_domain_context
HINT_PROPOSER = os.getenv("COLLECTIVE_HINT_PROPOSER",
                          "Solve independently; do not reference other agents or a group.")

def n_propose_council(state):
    k = int(state.get("k", 3))
    ctx = fetch_domain_context(state["task"], limit=6)
    proposals = []
    for i in range(k):
        which = "Q4B" if i == 0 else "Q4"      # diversity seat optional
        msg = [
          {"role":"system","content": HINT_PROPOSER},
          {"role":"user","content": f"Task:\n{state['task']}\n\nRelevant notes:\n{ctx}\n\n"
                                     "Return a concise proposal with justification."}
        ]
        proposals.append(chat(msg, which=which, temperature=0.8, max_tokens=600))
    return {**state, "proposals": proposals}
```

> Do **not** mention “you are 1 of K” or reveal other proposals to maintain conditional independence.

### 3.3 Judge node

```python
HINT_JUDGE = os.getenv("COLLECTIVE_HINT_JUDGE",
                       "You are the judge; prefer safety, clarity, and testability.")
def n_judge(state):
    proposals = state.get("proposals", [])
    msg = [
      {"role":"system","content": HINT_JUDGE + " You may consider process context."},
      {"role":"user","content": "Proposals:\n\n" + "\n\n---\n\n".join(proposals) +
                               "\n\nReturn: final decision, rationale, next step."}
    ]
    verdict = chat(msg, which="F16", temperature=0.1, max_tokens=700)
    return {**state, "verdict": verdict}
```

---

## 4) A/B Switch & Diversity Metric

### 4.1 Blindness toggle

```python
# services/agent-runtime/src/agent_runtime/collective/config.py
import os
BLIND = os.getenv("COLLECTIVE_PROPOSER_BLIND","1") == "1"
```

```python
# in propose nodes
if BLIND:
    ctx = fetch_domain_context(state["task"], 6)
else:
    ctx = fetch_domain_context(state["task"], 6)  # or a broader fetch without tag filters
```

### 4.2 Diversity metric (simple Jaccard)

```python
# services/agent-runtime/src/agent_runtime/collective/metrics.py
import re
def jaccard(a: str, b: str):
    A, B = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(A & B) / max(1, len(A | B))

def pairwise_diversity(texts):
    sims = []
    for i in range(len(texts)):
        for j in range(i+1, len(texts)):
            sims.append(jaccard(texts[i], texts[j]))
    avg = sum(sims)/len(sims) if sims else 1.0
    return {"avg_jaccard": avg, "avg_diversity": 1.0 - avg}
```

Export to Prometheus using your existing metrics plumbing (Gateway/Agent Runtime already expose `/metrics` in the stack). fileciteturn1file9

---

## 5) Retag / Migration (Do **not** delete)

You **do not need to remove** existing “KITTY development” memories. Prefer **retagging** them so they are excluded for proposers and still available for judge/planner analysis.

### 5.1 Retag script (Qdrant)

```python
# scripts/retag_dev_memories.py
import os, re, uuid
from qdrant_client import QdrantClient, models as qm

cli = QdrantClient(os.getenv("QDRANT_URL","http://localhost:6333"))
COL = os.getenv("QDRANT_COLLECTION","kitty_memories")

PATTERNS = [r"(?i)KITTY (is|was|will be)", r"(?i)multi[- ]agent", r"(?i)collective", r"(?i)development notes?"]

def is_meta(text: str) -> bool:
    return any(re.search(p, text or "") for p in PATTERNS)

def retag(limit=5000):
    scroll = None
    processed = 0
    while True:
        res, scroll = cli.scroll(COL, with_payload=True, limit=256, scroll=scroll)
        if not res: break
        to_upsert = []
        for pt in res:
            text = (pt.payload or {}).get("text","")
            if is_meta(text):
                tags = set((pt.payload or {}).get("tags", []))
                tags.update({"meta","dev","collective"})
                to_upsert.append(qm.PointStruct(id=pt.id, vector=None,
                                 payload={**pt.payload, "tags": list(tags)}))
        if to_upsert:
            cli.upsert(COL, points=to_upsert)
        processed += len(res)
        if processed >= limit: break
    print("Retag complete")

if __name__ == "__main__":
    retag()
```

Run:
```bash
python scripts/retag_dev_memories.py
```

> Alternative: If you’d rather **hard‑exclude** by server policy, keep the memories as‑is and enforce `EXCLUDE`/`INCLUDE` purely at query time (Section 2).

---

## 6) Tests & Smoke

**Memory** (server‑side): add a unit test that `search_filtered` excludes `meta/dev/collective`.  
**Agent Runtime**: council run should show **no references** to “other agents”, and diversity should improve when `COLLECTIVE_PROPOSER_BLIND=1`.

**CLI smoke** (unchanged usage; Memory/collective wiring stays behind Gateway @ :8080):  
- `/remember` and `/memories` continue to function as in README. fileciteturn1file4  
- Swagger lists memory and collective routes under **API Docs**. fileciteturn1file11

---

## 7) Operational Notes

- Keep **tool‑registry** flow: you do not need new tools for this; the Memory and collective endpoints already fit the pattern (YAML → Gateway → Brain). fileciteturn1file7  
- Maintain **offline‑first** posture; no external calls were added.  
- Continue using the launcher/TUI and validated startup scripts to ensure llama.cpp → services → UI order. fileciteturn1file3

---

## 8) Decision: Remove memories?

**No.** Don’t delete them. Tag and **scope** them:
- **Proposers**: *exclude* `meta/dev/collective` via tag filters.  
- **Judges/Planners**: may see them for synthesis/safety.  
This preserves history, improves transparency, and avoids silent capability loss while eliminating groupthink/anchoring in proposals.

---

### See also
- 🧱 [Qdrant payload tag filters](https://www.google.com/search?q=Qdrant+payload+filter+tags) — structuring tags for include/exclude
- 🧠 [Council/ensemble prompting](https://www.google.com/search?q=mixture+of+agents+council+ensemble+LLM) — why independence matters
- 🗣️ [LLM debate + judge](https://www.google.com/search?q=LLM+debate+judge+multi-agent) — when to use debates
- 🧰 [Prompt independence patterns](https://www.google.com/search?q=prompting+independence+instructions+LLM+council) — phrasing to reduce anchoring
- 📊 [Prometheus FastAPI](https://www.google.com/search?q=prometheus+fastapi+metrics) — add counters/histograms
