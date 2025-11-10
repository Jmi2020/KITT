Expert(s)	Machine Learning Engineer; Computer Vision Engineer; Full‑Stack Engineer (FastAPI/React); DevOps (Docker/MinIO); Product/UX
Question	Design and implement an end‑to‑end pipeline so KITTY can search the web for images (e.g., “duck”), verify relevance with a vision model, present a gallery for human selection, store only selected images, and later pass those references into CAD APIs (Tripo).
Plan	Integrate a Vision MCP Server (tools: image_search, image_filter, store_selection) + Gateway endpoints + React gallery UI + MinIO storage + CAD adapter for Tripo image refs. Use 🧠 CLIP for zero‑shot relevance; 🔎 SearXNG for image search with Brave fallback; persist only user‑picked references in MinIO; extend CAD service to accept image_refs for Tripo. Leverage existing ReAct/MCP routing and storage layers.  ￼  ￼  ￼


⸻

KITTY Vision: Web Image Search → CLIP Relevance → Human Selection → CAD Handoff

This guide adds a vision-assisted image retrieval capability to KITTY. It’s designed to be offline‑first (local CLIP, self‑hosted SearXNG) with cloud fallbacks and to plug cleanly into KITTY’s existing ReAct/MCP, storage, and CAD layers.  ￼

Key building blocks
	•	🔎 Image search: SearXNG (self‑hosted) with Brave fallback.  ￼  ￼
🍀 SearXNG image search JSON￼ · 🧭 Brave Image Search API￼
	•	🧠 Relevance (verification): CLIP (OpenCLIP) zero‑shot scoring on macOS (PyTorch MPS).
🧠 CLIP zero‑shot classification￼ · ⚙️ OpenCLIP PyTorch￼ · 🍎 PyTorch MPS backend￼
	•	📦 Store only selections: MinIO (S3‑compatible) artifact bucket; presigned URLs for downstream tools.  ￼  ￼
📦 MinIO presigned URLs￼
	•	🧱 CAD handoff: Extend CAD provider adapter to send image_refs to Tripo (text+image → 3D).  ￼
🧱 Tripo text+image to 3D API￼

⸻

0) Where this plugs into KITTY
	•	MCP/Tools layer: Add a Vision MCP Server alongside existing Research, CAD, Memory, etc.  ￼
	•	Storage layer: Use MinIO for reference images (store only picked ones).  ￼
	•	CAD service: Already supports Zoo/Tripo; extend Tripo adapter to accept image_refs.  ￼
	•	Web UI: Add a gallery picker route and component (UI runs on :4173, API docs on :8080, MinIO console :9001).  ￼

⸻

1) Environment, deps, and config

.env additions

# Image search
SEARXNG_BASE_URL=http://localhost:8888        # self-hosted SearXNG
BRAVE_SEARCH_API_KEY=...                      # optional fallback
IMAGE_SEARCH_SAFESEARCH=1                     # 0/1/2 (SearXNG semantics)
IMAGE_SEARCH_TOPK=12

# Vision / CLIP
CLIP_MODEL_NAME=ViT-B-32
CLIP_PRETRAIN=laion2b_s34b_b79k

# Storage (MinIO)
MINIO_ENDPOINT=localhost:9000
MINIO_SECURE=false
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET=kitty-artifacts

# CAD / Tripo
TRIPO_API_URL=https://api.tripo.ai/v1
TRIPO_API_KEY=...

Python deps (server-side)

# pyproject.toml (excerpt)
[project.optional-dependencies]
vision = [
  "httpx>=0.25",
  "Pillow>=10.0",
  "torch>=2.2",         # MPS backend on macOS
  "open_clip_torch>=2.24.0",
  "minio>=7.2.7",
  "pydantic>=2.6",
]


⸻

2) Vision MCP Server (new)

Create services/mcp/src/mcp/servers/vision_server.py.

Tools:
	•	image_search(q, top_k, safesearch) → list of candidates
	•	image_filter(q, images[], threshold) → ranked with CLIP scores
	•	store_selection(session_id, selected_images[]) → MinIO keys + presigned URLs

# services/mcp/src/mcp/servers/vision_server.py
from __future__ import annotations
import io, os, uuid, math, asyncio
from typing import List, Dict, Any
import httpx
from PIL import Image
from pydantic import BaseModel
import torch
import open_clip
from minio import Minio
from datetime import timedelta

from ..server import MCPServer, ToolDefinition, ToolResult  # KITTY MCP base (pattern)  [oai_citation:13‡README.md](sediment://file_000000004bd871f59e6c951a041e1cff)

SEARX = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
BRAVE_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
SAFESEARCH = int(os.getenv("IMAGE_SEARCH_SAFESEARCH", "1"))
TOPK = int(os.getenv("IMAGE_SEARCH_TOPK", "12"))

# ---- CLIP init (MPS on macOS) ----
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
MODEL_NAME = os.getenv("CLIP_MODEL_NAME", "ViT-B-32")
PRETRAIN = os.getenv("CLIP_PRETRAIN", "laion2b_s34b_b79k")
model, _, preprocess = open_clip.create_model_and_transforms(MODEL_NAME, pretrained=PRETRAIN, device=DEVICE)
tokenizer = open_clip.get_tokenizer(MODEL_NAME)

# ---- MinIO client ----
MINIO = Minio(
    os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
)
BUCKET = os.getenv("MINIO_BUCKET", "kitty-artifacts")

class ImageHit(BaseModel):
    id: str
    url: str
    thumb: str | None = None
    title: str | None = None
    source: str | None = None
    width: int | None = None
    height: int | None = None

def _searxng_params(q: str) -> Dict[str, Any]:
    return {
        "q": q, "format": "json", "categories": "images",
        "safesearch": SAFESEARCH, "language": "en"
    }

async def image_search_searxng(q: str, top_k: int = TOPK) -> List[ImageHit]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{SEARX}/search", params=_searxng_params(q))
        r.raise_for_status()
        data = r.json()
    hits = []
    for i, item in enumerate(data.get("results", [])[:top_k]):
        # SearXNG commonly returns 'img_src' (full), 'thumbnail_src'
        url = item.get("img_src") or item.get("url")
        if not url: 
            continue
        hits.append(ImageHit(
            id=f"searx_{i}",
            url=url,
            thumb=item.get("thumbnail_src"),
            title=item.get("title"),
            source=item.get("source"),
            width=item.get("img_width"),
            height=item.get("img_height"),
        ))
    return hits

async def image_search_brave(q: str, top_k: int = TOPK) -> List[ImageHit]:
    if not BRAVE_KEY: return []
    headers = {"X-Subscription-Token": BRAVE_KEY}
    params = {"q": q, "count": top_k, "search_lang": "en"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        r = await client.get("https://api.search.brave.com/res/v1/images/search", params=params)
        if r.status_code != 200: return []
        j = r.json()
    hits = []
    for i, it in enumerate(j.get("results", [])[:top_k]):
        url = it.get("properties", {}).get("url") or it.get("url")
        thumb = it.get("thumbnail")
        hits.append(ImageHit(id=f"brave_{i}", url=url, thumb=thumb, title=it.get("title"), source=it.get("source")))
    return hits

async def fetch_image_bytes(url: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.content
    except Exception:
        return None

def clip_score(query: str, img: Image.Image) -> float:
    img_t = preprocess(img).unsqueeze(0).to(DEVICE)
    # include common confusions so softmax is meaningful
    labels = [
        "a photo of a duck", "a photo of a goose", "a photo of a swan",
        "a photo of a rubber duck", "a photo of a bird", "a photo of nothing"
    ]
    # first label is the positive target
    text = tokenizer(labels).to(DEVICE)
    with torch.no_grad(), torch.autocast(device_type=("mps" if DEVICE=="mps" else "cpu"), enabled=(DEVICE=="mps")):
        img_feat = model.encode_image(img_t)
        txt_feat = model.encode_text(text)
        img_feat /= img_feat.norm(dim=-1, keepdim=True)
        txt_feat /= txt_feat.norm(dim=-1, keepdim=True)
        logits = 100.0 * img_feat @ txt_feat.T
    probs = logits.softmax(dim=-1).squeeze(0)
    return float(probs[0].item())  # probability of "duck"

class VisionMCPServer(MCPServer):
    def __init__(self):
        super().__init__(name="vision", description="Image search, filtering, and storage")
        self._register_tools()

    def _register_tools(self):
        self.register_tool(ToolDefinition(
            name="image_search",
            description="Search web images for a query string",
            parameters={
                "type": "object",
                "properties": {
                    "q": {"type":"string"},
                    "top_k":{"type":"integer","default":TOPK},
                    "safesearch":{"type":"integer","default":SAFESEARCH}
                },
                "required":["q"]
            }
        ))
        self.register_tool(ToolDefinition(
            name="image_filter",
            description="Verify relevance of images to a query using CLIP, returning top-ranked",
            parameters={
                "type":"object",
                "properties":{
                    "q":{"type":"string"},
                    "images":{"type":"array","items":{"type":"string"}}, # URLs
                    "threshold":{"type":"number","default":0.27},
                    "max_keep":{"type":"integer","default":TOPK}
                },
                "required":["q","images"]
            }
        ))
        self.register_tool(ToolDefinition(
            name="store_selection",
            description="Download selected images and store into MinIO; return object keys + presigned URLs",
            parameters={
                "type":"object",
                "properties":{
                    "session_id":{"type":"string"},
                    "images":{"type":"array","items":{"type":"string"}} # URLs user selected
                },
                "required":["session_id","images"]
            }
        ))

    async def execute_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        try:
            if tool_name == "image_search":
                q = arguments["q"]
                top_k = arguments.get("top_k", TOPK)
                # prefer SearXNG; fallback to Brave if nothing (matches KITTY search order)  [oai_citation:14‡README.md](sediment://file_000000004bd871f59e6c951a041e1cff)
                hits = await image_search_searxng(q, top_k)
                if not hits:
                    hits = await image_search_brave(q, top_k)
                return ToolResult(success=True, data=[h.model_dump() for h in hits])

            if tool_name == "image_filter":
                q = arguments["q"]; urls = arguments["images"]
                th = float(arguments.get("threshold", 0.27))
                mk = int(arguments.get("max_keep", TOPK))
                scored = []
                for u in urls:
                    b = await fetch_image_bytes(u)
                    if not b: continue
                    try:
                        img = Image.open(io.BytesIO(b)).convert("RGB")
                        p = clip_score(q, img)
                        if p >= th:
                            scored.append({"url": u, "p_duck": p})
                    except Exception:
                        continue
                scored.sort(key=lambda x: x["p_duck"], reverse=True)
                return ToolResult(success=True, data=scored[:mk])

            if tool_name == "store_selection":
                session = arguments["session_id"]
                urls = arguments["images"]
                out = []
                for u in urls:
                    b = await fetch_image_bytes(u)
                    if not b: continue
                    key = f"references/{session}/{uuid.uuid4().hex}.jpg"
                    MINIO.put_object(
                        BUCKET, key, io.BytesIO(b), length=len(b),
                        content_type="image/jpeg"
                    )
                    url = MINIO.presigned_get_object(BUCKET, key, expires=timedelta(days=7))
                    out.append({"key": key, "url": url})
                return ToolResult(success=True, data=out)

            return ToolResult(success=False, error="unknown tool")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

Register the server

# services/brain/src/brain/tools/mcp_client.py
from mcp.servers.vision_server import VisionMCPServer

self._servers["vision"] = VisionMCPServer()

The pattern mirrors existing MCP servers (CAD, Research, Memory).  ￼

⸻

3) Gateway endpoints (thin wrappers)

Create services/gateway/src/routers/vision.py:

# services/gateway/src/routers/vision.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from ..deps import get_mcp  # your MCP client accessor

router = APIRouter(prefix="/api/vision", tags=["vision"])

class SearchReq(BaseModel):
    q: str
    top_k: int | None = None

@router.post("/search")
async def search(req: SearchReq):
    mcp = get_mcp()
    res = await mcp.run("vision", "image_search", req.model_dump())
    if not res.success: raise HTTPException(502, res.error)
    return {"results": res.data}

class FilterReq(BaseModel):
    q: str
    images: list[str]
    threshold: float | None = None
    max_keep: int | None = None

@router.post("/filter")
async def filter(req: FilterReq):
    mcp = get_mcp()
    res = await mcp.run("vision", "image_filter", req.model_dump())
    if not res.success: raise HTTPException(502, res.error)
    return {"ranked": res.data}

class StoreReq(BaseModel):
    session_id: str
    images: list[str]

@router.post("/store")
async def store(req: StoreReq):
    mcp = get_mcp()
    res = await mcp.run("vision", "store_selection", req.model_dump())
    if not res.success: raise HTTPException(502, res.error)
    return {"artifacts": res.data}

Add router include:

# services/gateway/src/main.py
from routers import vision
app.include_router(vision.router)


⸻

4) React gallery component (web UI)

UI lives on port 4173; wire a simple picker that calls /api/vision/search then /api/vision/filter, and finally /api/vision/store.  ￼

// ui/src/components/VisionPicker.tsx
import React, { useState } from "react";

type Hit = { id:string; url:string; thumb?:string; title?:string; source?:string; };

export default function VisionPicker() {
  const [q, setQ] = useState("duck");
  const [hits, setHits] = useState<Hit[]>([]);
  const [ranked, setRanked] = useState<{url:string; p_duck:number}[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [sessionId] = useState<string>(() => crypto.randomUUID());

  const search = async () => {
    const r = await fetch("/api/vision/search", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({q})});
    const j = await r.json(); setHits(j.results || []);
    // ask server to rank by CLIP
    const urls = (j.results || []).map((h:Hit) => h.url);
    const fr = await fetch("/api/vision/filter", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({q, images: urls})});
    const fj = await fr.json(); setRanked(fj.ranked || []);
  };

  const toggle = (url:string) => setSelected(s => ({...s, [url]: !s[url]}));

  const store = async () => {
    const chosen = Object.keys(selected).filter(k => selected[k]);
    const r = await fetch("/api/vision/store", {method:"POST", headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: sessionId, images: chosen})});
    const j = await r.json();
    alert(`Stored ${j.artifacts.length} refs. Keys:\n` + j.artifacts.map((a:any)=>a.key).join("\n"));
  };

  return (
    <div>
      <h3>Vision Picker</h3>
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder="e.g., duck" />
      <button onClick={search}>Search</button>

      <h4>Ranked (by CLIP)</h4>
      <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(160px,1fr))', gap:12}}>
        {ranked.map(r => (
          <figure key={r.url} style={{border: selected[r.url]?'3px solid black':'1px solid #ccc', padding:6}}>
            <img src={r.url} alt="" style={{width:'100%', height:120, objectFit:'cover'}} onClick={()=>toggle(r.url)} />
            <figcaption>p(duck)={(r.p_duck*100).toFixed(1)}%</figcaption>
          </figure>
        ))}
      </div>

      <button onClick={store}>Save Selection</button>
    </div>
  );
}


⸻

5) Persist only the selected images
	•	Selections are stored to MinIO under references/{session_id}/{uuid}.jpg, returning presigned URLs for 3–7 days.
	•	Unselected candidates are never persisted — they stay ephemeral in browser memory.
📦 MinIO presigned URL how‑to￼ · MinIO is already part of KITTY’s storage stack.  ￼

⸻

6) Extend CAD service to accept image_refs (Tripo)

CAD providers already include Zoo and Tripo; add optional image_refs parameter and pass presigned URLs to Tripo’s text+image endpoint.  ￼

Contract update (Gateway → CAD):

POST /api/cad/generate
{
  "prompt": "duck sculpture, stylized, smooth surface",
  "provider": "tripo",
  "image_refs": [
    "https://minio.local/presigned/....",
    "https://minio.local/presigned/...."
  ],
  "params": { "unit": "mm" }
}

Adapter sketch (services/cad/src/providers/tripo_client.py):

import httpx, os

TRIPO_URL = os.getenv("TRIPO_API_URL", "https://api.tripo.ai/v1")
TRIPO_KEY = os.getenv("TRIPO_API_KEY")

async def tripo_generate(prompt: str, image_urls: list[str] | None = None) -> dict:
    headers = {"Authorization": f"Bearer {TRIPO_KEY}", "Content-Type": "application/json"}
    payload = {"prompt": prompt}
    if image_urls:
        payload["image_urls"] = image_urls  # Tripo: text+image conditioning
    async with httpx.AsyncClient(timeout=None, headers=headers) as client:
        r = await client.post(f"{TRIPO_URL}/cad/generate", json=payload)
        r.raise_for_status()
        return r.json()

The CAD stack already handles artifact storage and previews; reuse that to store returned 3D assets (STL/OBJ/STEP) and show them in the UI.  ￼

⸻

7) Make it agent‑driven (ReAct/MCP)
	•	Add a simple routing rule: if user asks “show me” / “pictures of” / “[object] image(s)”, Brain calls vision.image_search → vision.image_filter and sends a gallery card to UI.
	•	This mirrors how Research MCP is invoked for web search today.  ￼  ￼
🧩 Model Context Protocol (MCP)￼

Example ReAct step (pseudocode)

[Thought] user requested images of "duck"
[Action] vision.image_search { q: "duck", top_k: 12 }
[Observation] 12 candidates
[Action] vision.image_filter { q: "duck", images: [..], threshold: 0.27 }
[Observation] 8 relevant; show gallery to user


⸻

8) CLI convenience (optional)

Add a subcommand:

kitty-cli images "duck" --pick 2,5
# Under the hood:
# 1) vision.search → vision.filter
# 2) render numbered URLs/thumbnails in terminal
# 3) on --pick, call vision.store and print MinIO keys

The CLI already mirrors the ReAct stack and can invoke tools; reuse its flags and streaming trace.  ￼

⸻

9) Testing

Unit
	•	Mock SearXNG JSON; verify parser returns ImageHit[].
	•	CLIP clip_score("duck", sample.jpg) returns p>0.5 for known duck images.

Integration
	•	POST /api/vision/search → returns N candidates.
	•	POST /api/vision/filter → returns sorted with p_duck.
	•	POST /api/vision/store → creates MinIO objects; presigned URLs are valid.

E2E
	•	UI gallery flow + CAD generation with image_refs results in Tripo artifact saved + preview shown (web UI already supports previews of CAD artifacts).  ￼

⸻

10) Observability & safety
	•	Metrics: count/image_search, p95 latency, CLIP latency, store_success; expose with existing Prometheus setups.  ￼
	•	Budget: these calls are local except Brave/Tripo; keep Brave behind the same “free first, pay last” posture.  ￼
	•	Safety: enable SearXNG safesearch, cap size and types (only image/jpeg|png), and only persist selected images.

⸻

11) Developer quickstart

# 1) Ensure SearXNG is running (as in README, :8888) and env set.  [oai_citation:26‡README.md](sediment://file_000000004bd871f59e6c951a041e1cff)
# 2) Install deps
pip install -e "services/mcp[vision]" -e services/gateway -e services/cad
# 3) Run/Restart mcp + gateway + ui
docker compose -f infra/compose/docker-compose.yml up -d --build
# 4) Open UI at :4173 and try the Vision Picker.  [oai_citation:27‡README.md](sediment://file_000000004bd871f59e6c951a041e1cff)
# 5) Verify MinIO uploads through console at :9001.  [oai_citation:28‡README.md](sediment://file_000000004bd871f59e6c951a041e1cff)


⸻

12) Appendix: Minimal “duck” smoke test

# scripts/smoke_duck.py
import asyncio, httpx, json
async def main():
    async with httpx.AsyncClient() as c:
        s = await c.post("http://localhost:8080/api/vision/search", json={"q":"duck"})
        urls = [h["url"] for h in s.json()["results"]]
        f = await c.post("http://localhost:8080/api/vision/filter", json={"q":"duck","images":urls})
        ranked = f.json()["ranked"][:3]
        print(json.dumps(ranked, indent=2))
        st = await c.post("http://localhost:8080/api/vision/store", json={"session_id":"demo", "images":[r["url"] for r in ranked]})
        print(st.json())
asyncio.run(main())


⸻

See also
	•	🧠 CLIP prompt engineering￼ — getting better zero‑shot scores
	•	🔎 SearXNG tuning￼ — enable/disable engines, safesearch levels
	•	🧭 Brave image quotas￼ — plan for fallback limits
	•	📦 MinIO lifecycle rules￼ — auto‑expire presigned artifacts
	•	🧱 Tripo tips￼ — improve fidelity with multiple refs

You may also enjoy
	•	🐦 Fine‑grained bird datasets￼ — explore accuracy on hard look‑alikes
	•	🧵 3D printing surface finishing￼ — useful after you print your duck
	•	🧩 Prompt‑to‑parametric CAD￼ — future direction for Zoo/local

⸻

Notes mapping to existing KITTY docs:
MinIO storage + services overview (Gateway/Brain/CAD etc.)  ￼  ￼ · CAD providers incl. Tripo  ￼ · Search stack SearXNG→Brave order and environment var setup  ￼  ￼ · Web UI/API/MinIO ports  ￼

🧭 If you’d like, I can also generate the file structure diffs (new server file paths, router includes, and UI route registration) and a one‑shot patch for the repo.