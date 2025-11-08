# Effective Memory MCP Server for Local LLMs (Athene‑V2 Agent · Llama 3.3 · gpt‑oss‑120B)

> **TL;DR**: Build a production‑ready **Model Context Protocol (MCP)** “memory” server that exposes `save`, `search`, `update`, `delete`, `link`, and `export` tools over **Streamable HTTP** and **stdio**. Use **SQLite + FTS5** for lexical search, optional **dense embeddings** for semantic recall, and a light **knowledge‑graph** layer for relationships. Wire it to local LLM runtimes (Athene‑V2 via vLLM, Llama 3.3 via Ollama, gpt‑oss‑120B via vLLM/Ollama).

---

## 🧭 Why MCP for memory?

- Standard, tool‑centric interface usable by many agents and IDEs.
- Swap storage backends (file → SQLite → pgvector) without changing your agents.
- Strong lifecycle, schema, and auth primitives (OAuth 2.1) in official SDKs.

---

## 🏗️ Reference architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                  Local Agent / Client (MCP client)               │
│  • Athene‑V2 via vLLM (OpenAI‑compatible)                        │
│  • Llama 3.3 via Ollama tools                                    │
│  • gpt‑oss‑120B via vLLM / Ollama                                │
│          │  (tool call: memory.search / memory.save ...)         │
├──────────┼───────────────────────────────────────────────────────┤
│          ▼                                                       │
│        MCP Transport (stdio or Streamable HTTP)                  │
├──────────────────────────────────────────────────────────────────┤
│        Our Memory MCP Server (Python FastMCP / TS SDK)           │
│  Tools: save, search, update, delete, link, topics, export       │
│  Resources: memory://{id}, memindex://stats                    │
├──────────────────────────────────────────────────────────────────┤
│  Storage + Retrieval                                             │
│   • SQLite tables (+ FTS5)                                       │
│   • Optional FAISS (or pgvector/Chroma)                          │
│   • Knowledge‑graph edges (src, rel, dst)                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📦 Python implementation (FastMCP + SQLite/FTS5 + optional embeddings)

> Minimal but complete **single‑file server**: `server.py`

### 0) Dependencies

```bash
# Recommended: uv (fast Python manager) or pip
uv venv && source .venv/bin/activate

uv pip install "mcp[cli]" pydantic "fastapi>=0.115" "uvicorn[standard]"                python-dotenv "sentence-transformers>=3.0,<4.0"                "faiss-cpu>=1.8,<2.0" sqlite-utils
```

### 1) `server.py`

```python
# server.py
from __future__ import annotations
import os, sqlite3, json, uuid, time, datetime as dt, math
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession
from pydantic import BaseModel, Field

# ---- Config ----
DB_PATH = os.getenv("MEMORY_DB", "memory.db")
EMBEDDINGS = os.getenv("EMBED", "on").lower() in {"1","true","yes","on"}
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM: Optional[int] = None  # filled at runtime

# ---- Embedding model (lazy) ----
_embedder = None
def get_embedder():
    global _embedder, EMBED_DIM
    if not EMBEDDINGS:
        return None
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(EMBED_MODEL)
            EMBED_DIM = len(_embedder.encode("ok"))
        except Exception as e:
            print(f"[warn] embeddings disabled: {e}")
            EMBED_DIM = None
            return None
    return _embedder

def embed(texts: List[str]) -> List[List[float]]:
    emb = get_embedder()
    if emb is None:
        return []
    vecs = emb.encode(texts, normalize_embeddings=True).tolist()
    return vecs if isinstance(texts, list) else [vecs]

# ---- SQLite store ----
class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.db.cursor()
        cur.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS memory (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                tags TEXT,               -- JSON array
                source TEXT,
                session_id TEXT,
                importance REAL DEFAULT 0.5
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(id UNINDEXED, text, tokenize='porter');
            CREATE TABLE IF NOT EXISTS embeds (
                id TEXT PRIMARY KEY,
                vec BLOB                 -- JSON-encoded list[float]
            );
            CREATE TABLE IF NOT EXISTS edges (
                src TEXT, rel TEXT, dst TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (src, rel, dst)
            );
            """
        )
        self.db.commit()

    # ---- CRUD ----
    def add_memory(self, text: str, tags: List[str] | None, source: str|None,
                   session_id: str|None, importance: float|None,
                   vec: List[float] | None) -> Dict[str, Any]:
        mid = str(uuid.uuid4())
        now = dt.datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [])
        self.db.execute(
            "INSERT INTO memory(id,text,created_at,updated_at,tags,source,session_id,importance) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (mid, text, now, None, tags_json, source, session_id, importance or 0.5),
        )
        self.db.execute("INSERT INTO memory_fts(id,text) VALUES (?,?)", (mid, text))
        if vec is not None:
            self.db.execute("INSERT OR REPLACE INTO embeds(id,vec) VALUES (?,?)",
                            (mid, json.dumps(vec)))
        self.db.commit()
        return self.get_memory(mid)

    def get_memory(self, mid: str) -> Dict[str, Any]:
        row = self.db.execute("SELECT * FROM memory WHERE id=?", (mid,)).fetchone()
        if not row:
            raise KeyError(mid)
        d = dict(row)
        d["tags"] = json.loads(d["tags"] or "[]")
        return d

    def update_memory(self, mid: str, text: Optional[str], tags: Optional[List[str]],
                      importance: Optional[float]) -> Dict[str, Any]:
        cur = self.db.cursor()
        row = self.db.execute("SELECT * FROM memory WHERE id=?", (mid,)).fetchone()
        if not row:
            raise KeyError(mid)
        new_text = text if text is not None else row["text"]
        new_tags = json.dumps(tags) if tags is not None else row["tags"]
        new_imp = importance if importance is not None else row["importance"]
        now = dt.datetime.utcnow().isoformat()
        cur.execute(
            "UPDATE memory SET text=?, tags=?, importance=?, updated_at=? WHERE id=?",
            (new_text, new_tags, new_imp, now, mid),
        )
        # keep FTS in sync
        cur.execute("UPDATE memory_fts SET text=? WHERE id=?", (new_text, mid))
        # re-embed if available
        if EMBEDDINGS and text is not None:
            vec = embed([new_text])[0]
            cur.execute("INSERT OR REPLACE INTO embeds(id,vec) VALUES (?,?)",
                        (mid, json.dumps(vec)))
        self.db.commit()
        return self.get_memory(mid)

    def delete_memory(self, mid: str) -> int:
        cur = self.db.cursor()
        cur.execute("DELETE FROM memory WHERE id=?", (mid,))
        cur.execute("DELETE FROM memory_fts WHERE id=?", (mid,))
        cur.execute("DELETE FROM embeds WHERE id=?", (mid,))
        cur.execute("DELETE FROM edges WHERE src=? OR dst=?", (mid, mid))
        self.db.commit()
        return cur.rowcount

    def link(self, src: str, rel: str, dst: str) -> None:
        now = dt.datetime.utcnow().isoformat()
        self.db.execute("INSERT OR IGNORE INTO edges(src,rel,dst,created_at) VALUES (?,?,?,?)",
                        (src, rel, dst, now))
        self.db.commit()

    def stats(self) -> Dict[str, Any]:
        n = self.db.execute("SELECT COUNT(*) AS n FROM memory").fetchone()["n"]
        e = self.db.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]
        return {"items": n, "edges": e}

    # ---- Search ----
    def search(self, query: str, top_k: int = 8,
               tags: Optional[List[str]] = None,
               session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        # 1) Lexical via FTS5
        where = ["memory_fts MATCH ?"]
        args = [query]
        base_sql = "SELECT m.*, bm25(memory_fts) AS bm25 FROM memory_fts JOIN memory m USING(id)"
        if session_id:
            where.append("m.session_id = ?"); args.append(session_id)
        if tags:
            where.append("EXISTS (SELECT 1 FROM json_each(m.tags) je WHERE je.value IN (%s))" %
                         ",".join("?"*len(tags)))
            args.extend(tags)
        sql = f"{base_sql} WHERE {' AND '.join(where)} ORDER BY bm25 LIMIT ?"
        rows = self.db.execute(sql, (*args, top_k*4)).fetchall()  # overfetch
        lex = []
        for r in rows:
            d = dict(r); d["tags"] = json.loads(d["tags"] or "[]")
            # lower bm25 is better; convert to [0,1]
            bm25 = d.get("bm25", 10.0)
            d["_lex_score"] = 1.0 / (1.0 + bm25)
            lex.append(d)

        # 2) Dense (optional)
        dense_map: Dict[str, float] = {}
        if EMBEDDINGS:
            qv = embed([query])[0]
            # naive scan (OK < 50k items). For >50k, add FAISS/pgvector.
            cur = self.db.execute("SELECT id, vec FROM embeds")
            for rid, vec_json in cur.fetchall():
                vec = json.loads(vec_json)
                # cosine sim since vectors are normalized
                sim = sum(a*b for a,b in zip(qv, vec))
                dense_map[rid] = sim

        # 3) Combine (recency + importance + hybrid)
        def score(item):
            # recency in days
            created = dt.datetime.fromisoformat(item["created_at"])
            age_days = max((dt.datetime.utcnow() - created).days, 0)
            rec = 1.0 / (1.0 + age_days/7)
            imp = float(item.get("importance") or 0.5)
            dense = dense_map.get(item["id"], 0.0)
            hybrid = 0.45*item["_lex_score"] + 0.45*dense + 0.10*imp
            return 0.7*hybrid + 0.3*rec

        combined = {m["id"]: m for m in lex}
        # also include dense‑only hits
        for mid, dsc in sorted(dense_map.items(), key=lambda x: x[1], reverse=True)[:top_k*4]:
            if mid not in combined:
                m = self.get_memory(mid)
                m["_lex_score"] = 0.0
                combined[mid] = m

        ranked = sorted(combined.values(), key=score, reverse=True)[:top_k]
        # strip internal fields
        for r in ranked:
            r.pop("_lex_score", None)
        return ranked

store = Store(DB_PATH)

# ---- MCP server ----
@dataclass
class AppCtx:
    store: Store

mcp = FastMCP("memory", lifespan=lambda server: (yield AppCtx(store=store)))

class SaveInput(BaseModel):
    text: str = Field(..., description="Memory text to store")
    tags: Optional[List[str]] = Field(default=None, description="Freeform tags")
    source: Optional[str] = Field(default=None, description="Where did this memory come from?")
    session_id: Optional[str] = Field(default=None, description="Client/session scope")
    importance: Optional[float] = Field(default=0.5, ge=0.0, le=1.0)

class SaveOutput(BaseModel):
    id: str
    created_at: str
    text: str
    tags: List[str]
    source: Optional[str]
    session_id: Optional[str]
    importance: float

@mcp.tool()
def memory_save(ctx: Context[ServerSession, AppCtx], inp: SaveInput) -> SaveOutput:
    """Persist a memory snippet and optional metadata."""
    vec = embed([inp.text])[0] if EMBEDDINGS else None
    d = ctx.request_context.lifespan_context.store.add_memory(
        text=inp.text, tags=inp.tags, source=inp.source,
        session_id=inp.session_id, importance=inp.importance, vec=vec
    )
    return SaveOutput(**d)

class SearchInput(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=50)
    tags: Optional[List[str]] = None
    session_id: Optional[str] = None

class SearchHit(BaseModel):
    id: str
    text: str
    created_at: str
    tags: List[str] = []
    importance: float
    source: Optional[str] = None
    session_id: Optional[str] = None

@mcp.tool()
def memory_search(ctx: Context[ServerSession, AppCtx], inp: SearchInput) -> List[SearchHit]:
    """Hybrid (lexical + semantic) search over stored memories."""
    results = ctx.request_context.lifespan_context.store.search(
        query=inp.query, top_k=inp.top_k, tags=inp.tags, session_id=inp.session_id
    )
    return [SearchHit(**r) for r in results]

class UpdateInput(BaseModel):
    id: str
    text: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[float] = Field(default=None, ge=0, le=1)

@mcp.tool()
def memory_update(ctx: Context[ServerSession, AppCtx], inp: UpdateInput) -> SaveOutput:
    """Update the text/tags/importance of a memory."""
    d = ctx.request_context.lifespan_context.store.update_memory(
        mid=inp.id, text=inp.text, tags=inp.tags, importance=inp.importance
    )
    return SaveOutput(**d)

class DeleteInput(BaseModel):
    id: str

@mcp.tool()
def memory_delete(ctx: Context[ServerSession, AppCtx], inp: DeleteInput) -> int:
    """Delete a memory by id. Returns number of rows deleted (0 or 1)."""
    return ctx.request_context.lifespan_context.store.delete_memory(inp.id)

class LinkInput(BaseModel):
    src: str
    rel: str = Field(..., description="relationship name, e.g., 'refers_to'")
    dst: str

@mcp.tool()
def memory_link(ctx: Context[ServerSession, AppCtx], inp: LinkInput) -> str:
    """Create a knowledge-graph edge between two memories."""
    ctx.request_context.lifespan_context.store.link(inp.src, inp.rel, inp.dst)
    return "ok"

@mcp.resource("memory://{mid}")
def memory_resource(mid: str) -> str:
    """Fetch a memory item by id as plain text."""
    return store.get_memory(mid)["text"]

@mcp.resource("memindex://stats")
def stats_resource() -> Dict[str, Any]:
    """Index stats."""
    return store.stats()

if __name__ == "__main__":
    import argparse
    from mcp.server.stdio import stdio_server
    from mcp.server.streamable_http import make_asgi_app

    p = argparse.ArgumentParser()
    p.add_argument("transport", choices=["stdio","http"], nargs="?", default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()

    if args.transport == "stdio":
        stdio_server(mcp).run()
    else:
        # Mount as an ASGI app at /mcp
        app = make_asgi_app(mcp, mount_path="/mcp")
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
```

### 2) Run & test

```bash
# stdio (great for Claude Desktop / Cursor)
python server.py stdio

# Streamable HTTP (great for browser clients and gateways)
python server.py http --port 8765
```

**Quick sanity check with MCP Inspector**:
```bash
npx @modelcontextprotocol/inspector http://localhost:8765/mcp
```

**Expected tools**: `memory_save`, `memory_search`, `memory_update`, `memory_delete`, `memory_link` and resources `memory://{id}`, `memindex://stats`.

> For large collections (>50k items), replace the naive dense scan with **FAISS** or migrate to **pgvector**. See the Production notes below.

---

## 🧪 Example: driving the server from local LLMs

### A) Athene‑V2 Agent (vLLM, OpenAI‑compatible tool calls)

```python
# athene_client.py
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")  # vLLM server

tools = [{
  "type": "function",
  "function": {
    "name": "memory_search",
    "description": "Recall user facts or prior tasks",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type":"string"},
        "top_k": {"type":"integer","minimum":1,"maximum":20,"default":6},
        "session_id": {"type":"string"}
      },
      "required": ["query"]
    }
  }
},{
  "type":"function",
  "function": {
    "name":"memory_save",
    "description":"Store a compact, canonical memory after a task",
    "parameters": {
      "type":"object",
      "properties": {
        "text":{"type":"string"},
        "tags":{"type":"array","items":{"type":"string"}},
        "session_id":{"type":"string"},
        "importance":{"type":"number","minimum":0,"maximum":1,"default":0.5}
      },
      "required":["text"]
    }
  }
}]

def call_mcp(tool_name, args):
    import httpx, json
    # call our Streamable HTTP server directly
    r = httpx.post("http://localhost:8765/mcp/tools/call",
                   json={"name": tool_name, "arguments": args}, timeout=30)
    r.raise_for_status()
    return r.json()

msgs=[
  {"role":"system","content":"You are Athene‑V2 with tool use; prefer recall before guessing."},
  {"role":"user","content":"What’s my preferred editor and last sprint goal?"}
]

resp = client.chat.completions.create(
  model="Nexusflow/Athene-V2-Agent",
  messages=msgs,
  tools=tools,
  tool_choice="auto",
  temperature=0.2,
)

choice = resp.choices[0]
tcalls = getattr(choice.message, "tool_calls", None) or []
if tcalls:
    for t in tcalls:
        if t.function.name in {"memory_search","memory_save"}:
            out = call_mcp(t.function.name, json.loads(t.function.arguments))
            msgs.append({"role":"tool","tool_call_id":t.id,"name":t.function.name,"content":json.dumps(out)})
    # continue the chat with tool results
    resp = client.chat.completions.create(model="Nexusflow/Athene-V2-Agent",
                                          messages=msgs, temperature=0.0)
print(resp.choices[0].message.content)
```

### B) Llama 3.3 via Ollama Tool Calling

```python
# llama_ollama_client.py
from ollama import chat
import json, httpx

tools = [{
  "type":"function",
  "function":{
    "name":"memory_search",
    "description":"Recall facts",
    "parameters":{"type":"object","properties":{"query":{"type":"string"}}, "required":["query"]}
  }
}]

def memory_search(query:str):
    r = httpx.post("http://localhost:8765/mcp/tools/call",
                   json={"name":"memory_search","arguments":{"query":query,"top_k":6}})
    r.raise_for_status()
    return r.json()

res = chat(model="llama3.3", messages=[
    {"role":"system","content":"Use tools when helpful."},
    {"role":"user","content":"What did I say about my editor?"}
], tools=tools, stream=False)

for t in res.message.get("tool_calls", []):
    if t["function"]["name"]=="memory_search":
        out = memory_search(**t["function"]["arguments"])
        # send tool result back
        res = chat(model="llama3.3", messages=[
            {"role":"tool","content":json.dumps(out),"name":"memory_search",
             "tool_call_id":t["id"]}
        ])
        print(res.message["content"])
```

### C) gpt‑oss‑120B (OpenAI‑compatible via vLLM, or Ollama)

Use the same **OpenAI‑compatible** loop as (A), changing `model` to `openai/gpt-oss-120b` when served by vLLM, or use Ollama’s tool APIs for the Ollama build.

---

## 🔐 Security & privacy hardening checklist

- OAuth 2.1 bearer token verification for protected servers (available in MCP Python SDK).
- Session scoping: all tools accept `session_id`; apply server‑side ACLs.
- PII handling: encrypt sensitive `text` at rest (SQLite `sqlcipher`, or app‑level libs).
- Data retention: scheduled compaction/summarization; deletion tools are **first‑class**.
- Observability: structured JSON logs per tool call (latency, hitcount, tokens).

---

## 🧱 Production notes

- **Dense index**: swap `search()`’s scan for **FAISS/HNSW** or **pgvector**; persist indexes.
- **Batching**: background job to embed new memories; backfill embeddings per table page.
- **Summarization/compaction**: nightly job to summarize old items into canonical notes.
- **Sharding**: partition by `session_id` or `customer_id` for >10M items.
- **Transport**: prefer **Streamable HTTP** for browser clients; stdio for desktop IDEs.
- **Backups**: periodic `.sql` dump + export tool (`.jsonl`).

---

## 🟦 TypeScript variant (Node, @modelcontextprotocol/sdk + better‑sqlite3)

```ts
// src/index.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/streamableHttp.js';
import Database from 'better-sqlite3';
import { z } from 'zod';
import express from 'express';

const db = new Database(process.env.MEMORY_DB ?? 'memory.db');
db.pragma('journal_mode = WAL');
db.exec(`
CREATE TABLE IF NOT EXISTS memory (
  id TEXT PRIMARY KEY, text TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT,
  tags TEXT, source TEXT, session_id TEXT, importance REAL DEFAULT 0.5
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(id UNINDEXED, text, tokenize='porter');
CREATE TABLE IF NOT EXISTS edges (src TEXT, rel TEXT, dst TEXT, created_at TEXT, PRIMARY KEY (src,rel,dst));
`);

const saveStmt = db.prepare(`INSERT INTO memory(id,text,created_at,tags,source,session_id,importance)
VALUES (@id,@text,@created_at,@tags,@source,@session_id,@importance)`);
const saveFts = db.prepare(`INSERT INTO memory_fts(id,text) VALUES (?,?)`);

const app = express();
app.use(express.json());

const server = new McpServer({ name: 'memory-ts' });

server.tool('memory_save',
  {
    text: z.string(),
    tags: z.array(z.string()).optional(),
    source: z.string().optional(),
    session_id: z.string().optional(),
    importance: z.number().min(0).max(1).default(0.5),
  },
  async ({ text, tags, source, session_id, importance }) => {
    const id = crypto.randomUUID();
    const created_at = new Date().toISOString();
    saveStmt.run({ id, text, created_at, tags: JSON.stringify(tags ?? []),
                   source, session_id, importance });
    saveFts.run(id, text);
    return { id, text, created_at, tags: tags ?? [], source, session_id, importance };
  }
);

server.tool('memory_search',
  {
    query: z.string(),
    top_k: z.number().int().min(1).max(50).default(8),
    session_id: z.string().optional(),
    tags: z.array(z.string()).optional(),
  },
  async ({ query, top_k, session_id, tags }) => {
    let sql = `SELECT m.*, bm25(memory_fts) as bm25
               FROM memory_fts JOIN memory m USING(id)
               WHERE memory_fts MATCH ?`;
    const args: any[] = [query];
    if (session_id) { sql += ` AND m.session_id = ?`; args.push(session_id); }
    if (tags?.length) {
      sql += ` AND EXISTS (SELECT 1 FROM json_each(m.tags) je WHERE je.value IN (${tags.map(()=>'?').join(',')}))`;
      args.push(...tags);
    }
    sql += ` ORDER BY bm25 LIMIT ?`; args.push(top_k);
    const rows = db.prepare(sql).all(...args);
    return rows.map(r => ({ id:r.id, text:r.text, created_at:r.created_at,
                            tags: JSON.parse(r.tags ?? '[]'),
                            source:r.source, session_id:r.session_id, importance:r.importance }));
  }
);

// HTTP transport
const transport = new StreamableHTTPServerTransport({ path: '/mcp' });
const port = parseInt(process.env.PORT || '8765', 10);
app.all('/mcp', (req, res) => transport.handleRequest(req, res, (req as any).body));
await server.connect(transport);

app.listen(port, () => console.log(`Memory MCP (TS) at http://localhost:${port}/mcp`));
```

Build/run:

```bash
npm i @modelcontextprotocol/sdk express zod better-sqlite3
node --env-file=.env --experimental-strip-types ./src/index.ts
# or compile then run
```

---

## 🧰 Client configuration snippets

**Claude Desktop / Cursor (`mcp.json`)**

```jsonc
{
  "mcpServers": {
    "memory": {
      "command": "python",
      "args": ["server.py", "stdio"],
      "env": {
        "MEMORY_DB": "/absolute/path/memory.db",
        "EMBED": "on"
      }
    }
  }
}
```

---

## ✅ Smoke test script

```bash
# 1) Start the server: python server.py http --port 8765
# 2) Save a memory:
curl -s http://localhost:8765/mcp/tools/call -X POST   -H 'content-type: application/json'   -d '{"name":"memory_save","arguments":{"text":"User prefers VS Code and works on Sprint 24.","tags":["prefs","sprint"],"session_id":"user:jeremiah"}}' | jq
# 3) Search:
curl -s http://localhost:8765/mcp/tools/call -X POST   -H 'content-type: application/json'   -d '{"name":"memory_search","arguments":{"query":"preferred editor sprint goal","session_id":"user:jeremiah"}}' | jq
```

---

## 📈 Observability (optional)

- Log every tool call with input hash, latency, result size.
- Periodic `memindex://stats` scrape to dashboards.
- Add `/healthz` and `/readyz` routes when mounting into a larger ASGI app.

---

## 📚 Notes & pointers

- MCP official Python/TS SDKs include **Streamable HTTP**, structured tool schemas, and OAuth 2.1 helpers.
- For dense retrieval, start with **BAAI/bge‑small‑en‑v1.5** or **bge‑m3**. For multi‑tenant scale, move to **pgvector**.
- For Ollama, ensure model/tool support is on (JSON‑schema tools).

---

## Appendix A — Minimal FAISS swap‑in (Python)

```python
# Replace the naive scan in Store.search() with FAISS (IVF or HNSW) when rows > 50k.
# Keep a parallel table embeds(id, vec) and rebuild the FAISS index on startup (or persist to disk).
import faiss, numpy as np
# Build:
vecs = [json.loads(v) for _,v in self.db.execute("SELECT id, vec FROM embeds").fetchall()]
ids  = [i for i,_ in self.db.execute("SELECT id, vec FROM embeds").fetchall()]
xb = np.asarray(vecs, dtype='float32')
index = faiss.IndexHNSWFlat(xb.shape[1], 32)
index.add(xb)
# Query:
q = np.asarray([qv], dtype='float32')
D,I = index.search(q, top_k*4)
candidates = [ids[i] for i in I[0]]
```

---

## Appendix B — Example “memory hygiene” prompt (optional)

```
When finishing a task, if you learned a durable user preference,
project milestone, or canonical fact that will be useful later, call
tool `memory_save` with a concise, de‑duplicated sentence and tags.
Do NOT save ephemeral or sensitive content without consent.
```

---

## License

This guide and example code are licensed under MIT. Replace the embedding model by your license constraints if needed.
