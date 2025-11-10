# KITTY Vision MCP — Web Image Search → CLIP → Human Selection → CAD Handoff

**Experts:** Machine Learning Engineer; Computer Vision Engineer; Full‑Stack Engineer (FastAPI/React); DevOps (Docker/MinIO); Product/UX

**Question:** Design and implement an end‑to‑end pipeline so KITTY can search the web for images (e.g., “duck”), verify relevance with a vision model, present a gallery for human selection, store only selected images, and later pass those references into CAD APIs (Tripo).

**Plan (high level):** Integrate a Vision MCP Server (tools: `image_search`, `image_filter`, `store_selection`) + Gateway endpoints + React gallery UI + MinIO storage + CAD adapter for Tripo image refs. Use CLIP (OpenCLIP) for zero‑shot relevance; SearXNG for image search with Brave fallback; persist only user‑picked references in MinIO; extend CAD service to accept `image_refs` for Tripo. Leverage existing ReAct/MCP routing and storage layers.

---

## Key building blocks

- Image search: self‑hosted SearXNG with Brave fallback.
- Relevance (verification): CLIP (OpenCLIP) zero‑shot scoring on macOS (PyTorch MPS).
- Store only selections: MinIO (S3‑compatible) artifact bucket; presigned URLs for downstream tools.
- CAD handoff: extend CAD provider adapter to send `image_refs` to Tripo (text+image → 3D).

## 0) Integration points in KITTY

- MCP/Tools layer: Add a Vision MCP Server alongside existing Research, CAD, Memory, etc.
- Storage layer: Use MinIO for reference images (store only picked ones).
- CAD service: Already supports Zoo/Tripo; extend Tripo adapter to accept `image_refs`.
- Web UI: Add a gallery picker route and component (UI runs on `:4173`, API on `:8080`, MinIO console `:9001`).

---

## 1) Environment, dependencies, and config

.env additions (example)

```env
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
```

Python deps (server-side, `pyproject.toml` excerpt)

```toml
[project.optional-dependencies]
vision = [
  "httpx>=0.25",
  "Pillow>=10.0",
  "torch>=2.2",         # MPS backend on macOS
  "open_clip_torch>=2.24.0",
  "minio>=7.2.7",
  "pydantic>=2.6",
]
```

---

## 2) Vision MCP Server (new)

Create `services/mcp/src/mcp/servers/vision_server.py` with three tools:

- `image_search(q, top_k, safesearch)` → list of candidate image hits
- `image_filter(q, images[], threshold)` → ranked images with CLIP scores
- `store_selection(session_id, selected_images[])` → put into MinIO and return object keys + presigned URLs

Key implementation notes (summary):

- Use SearXNG first, fallback to Brave for image search results.
- Run CLIP (OpenCLIP) on macOS using MPS if available; compute zero‑shot scores and rank.
- Only store user‑selected images to MinIO under `references/{session}/{uuid}.jpg` and return presigned GET URLs.

Example responsibilities:

- Fetch candidates (`image_search_searxng`, `image_search_brave`).
- Download image bytes for scoring (`fetch_image_bytes`).
- Compute `clip_score(query, image)` and filter by threshold.
- Persist selected images to MinIO and return keys + presigned URLs.

The Vision MCP should register the three tools with the MCP framework and implement `execute_tool` routing accordingly.

---

## 3) Gateway endpoints (thin wrappers)

Add a FastAPI router at `services/gateway/src/routers/vision.py` with endpoints:

- `POST /api/vision/search` — calls MCP `vision.image_search` and returns candidates.
- `POST /api/vision/filter` — calls MCP `vision.image_filter` to rank candidates by CLIP.
- `POST /api/vision/store` — calls MCP `vision.store_selection` to persist selected images.

Each endpoint accepts a Pydantic request model and returns structured JSON (or raises `HTTPException` on MCP errors).

Include the router in the gateway app (e.g., `app.include_router(vision.router)`).

---

## 4) React gallery component (web UI)

Create a small component (e.g., `ui/src/components/VisionPicker.tsx`) that:

- Calls `/api/vision/search` with a query.
- Sends returned URLs to `/api/vision/filter` to get CLIP‑ranked results.
- Renders a gallery of thumbnails, allows user selection, and calls `/api/vision/store` to persist chosen images.

Core UX points:

- Only store what the user explicitly picks.
- Show CLIP scores and thumbnails; allow multi‑select and session scoping (use `crypto.randomUUID()` for `session_id`).

Example usage (TypeScript / React):

```tsx
// VisionPicker.tsx (sketch)
// - calls /api/vision/search -> /api/vision/filter -> /api/vision/store
```

---

## 5) Persist only selected images

- Store selections in MinIO under `references/{session_id}/{uuid}.jpg` and return presigned GET URLs (3–7 days).
- Unselected candidates remain ephemeral in the browser memory and are not persisted.

---

## 6) Extend CAD service to accept `image_refs` (Tripo)

Update CAD generation contract to accept an optional `image_refs` array of presigned URLs and forward them to Tripo's text+image API.

Example request (Gateway → CAD):

```json
POST /api/cad/generate
{
  "prompt": "duck sculpture, stylized, smooth surface",
  "provider": "tripo",
  "image_refs": [
    "https://minio.local/presigned/...",
    "https://minio.local/presigned/..."
  ],
  "params": { "unit": "mm" }
}
```

Adapter sketch (`services/cad/src/providers/tripo_client.py`):

```py
async def tripo_generate(prompt: str, image_urls: list[str] | None = None) -> dict:
    payload = {"prompt": prompt}
    if image_urls:
        payload["image_urls"] = image_urls
    # POST to Tripo and return JSON
```

Re‑use CAD artifact storage and preview paths to store returned 3D assets (STL/OBJ/STEP).

---

## 7) Make it agent‑driven (ReAct/MCP)

- Add a routing rule in the Brain: when the user asks for images (e.g., “show me pictures of X”), invoke the Vision MCP (`image_search` → `image_filter`) and surface a gallery card to the UI for selection.

Example ReAct pseudocode:

```
[Thought] user requested images of "duck"
[Action] vision.image_search { q: "duck", top_k: 12 }
[Observation] 12 candidates
[Action] vision.image_filter { q: "duck", images: [...], threshold: 0.27 }
[Observation] 8 relevant; show gallery to user
```

---

## 8) CLI convenience (optional)

Add a `kitty-cli` subcommand to drive the flow from the terminal, e.g.:

```bash
kitty-cli images "duck" --pick 2,5
```

Under the hood it would call `vision.search` → `vision.filter`, render numbered thumbnails/URLs, then call `vision.store` for the picks.

---

## 9) Testing

- Unit tests:
  - Mock SearXNG JSON and verify parsing to `ImageHit[]`.
  - Test `clip_score("duck", sample.jpg)` returns high probability for duck images.
- Integration tests:
  - `POST /api/vision/search` returns candidates.
  - `POST /api/vision/filter` returns ranked results.
  - `POST /api/vision/store` creates MinIO objects with valid presigned URLs.
- E2E tests:
  - UI gallery flow + CAD generation with `image_refs` yields Tripo artifact stored and previewed.

---

## 10) Observability & safety

- Metrics: counters and latencies (e.g., `count/image_search`, `p95` latency, `clip_latency`, `store_success`) exposed via Prometheus.
- Budgeting: keep Brave/Tripo as fallbacks and enforce a “local first, cloud last” posture.
- Safety: enable SearXNG safesearch, cap allowed MIME types (`image/jpeg`, `image/png`) and sizes, persist only user‑approved images.

---

## 11) Developer quickstart

```bash
# 1) Ensure SearXNG is running at :8888 and env is set
pip install -e "services/mcp[vision]" -e services/gateway -e services/cad
docker compose -f infra/compose/docker-compose.yml up -d --build
# 4) Open UI at :4173 and try the Vision Picker
# 5) Verify MinIO uploads via its console at :9001
```

---

## 12) Appendix: Minimal “duck” smoke test

```py
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
```

---

## References & notes

- CLIP prompt engineering and SearXNG tuning tips.
- Brave image quotas and MinIO lifecycle rules.
- Tripo guidance for best fidelity when sending multiple image refs.

---

If you want, I can also generate the file patches (new server file, router includes, and UI component) as a one‑shot patch for this repo.

---

## Vision MCP — Patch, File Tree, and Design Call

**Experts:** Machine Learning Engineer • Vision/VLM • FastAPI/React Full‑Stack • DevOps (Docker/MinIO) • Agent/MCP Architect

**Question:** Produce file‑structure diffs and a one‑shot patch that adds a Vision MCP server (image search + CLIP/VLM filtering + storage) and minimal Gateway/UI hooks to KITTY; also advise whether an MCP server is the right abstraction for Gemma‑3‑Vision or other VLMs.

**Plan:** Add new files only (safe, drop‑in): Vision MCP server, Gateway router, UI gallery, smoke test, and an optional idempotent enable script to inject small imports/registrations if desired. Use environment‑gated activation so builds won’t break if deps aren’t installed. Keep search via SearXNG→Brave and artifacts in MinIO; pass presigned URLs to CAD/Tripo later. Cite/align with KITTY’s existing ports, search stack, MCP pattern, and CAD providers.

**What’s included (summary)**

- Vision MCP server (`image_search`, `image_filter`, `store_selection`) — default: OpenCLIP (CLIP) with macOS MPS acceleration; optional VLM backend via HTTP (e.g., Gemma‑3‑Vision).
- Gateway router (thin wrappers for MCP tools).
- UI gallery component (React) to preview, pick, and store chosen refs in MinIO for CAD handoff.
- Smoke test script.
- Optional enable script to idempotently wire imports/registrations (env‑gated).

---

### File‑structure diff (additive)

Add the following files (safe, additive):

- `services/mcp/src/mcp/servers/vision_server.py`
- `services/gateway/src/routers/vision.py`
- `ui/src/components/VisionPicker.tsx`
- `scripts/smoke_duck.py`
- `ops/scripts/enable-vision.sh` (optional helper to wire imports/routes)

Notes:

- Web UI: `:4173`, Gateway: `:8080`, MinIO console: `:9001`.
- Search stack order: SearXNG → Brave (fallback).
- CAD providers already include Tripo; image refs are passed as presigned URLs.

---

### One‑shot patch (apply guidance)

You can apply an additive unified patch (example name: `vision_mcp.patch`) from the repo root:

```bash
git apply --reject --whitespace=fix vision_mcp.patch
```

(If a hunk fails due to context changes, use the optional enable script below to inject wiring.)

The patch contains new files for the Vision MCP server, Gateway router, React component, smoke test, and an enable script. The MCP server uses a guarded import strategy so missing ML deps will not break builds; activation is gated via `VISION_ENABLED=1`.

---

### How to run (quickstart)

1) Enable vision in your environment (safe defaults):

```bash
export VISION_ENABLED=1
export SEARXNG_BASE_URL=http://localhost:8888
# Optional: use a VLM backend instead of CLIP
# export VISION_BACKEND=vlm
# export VISION_VLM_ENDPOINT=http://localhost:8005
# Ensure MinIO creds are set in your env/.env
```

2) Install deps (choose one):

```bash
# Option A: install via extras
pip install -e "services/mcp[vision]"
# Option B: minimal direct installs
pip install httpx Pillow torch open_clip_torch minio
```

3) Start KITTY services (matching project startup):

```bash
./ops/scripts/start-kitty-validated.sh
```

4) Smoke test:

```bash
python scripts/smoke_duck.py "duck"
```

5) UI: serve the UI on `:4173` and mount `VisionPicker` to try the gallery flow.

---

### Is an MCP server the right abstraction for vision (Gemma‑3‑Vision / VLMs)?

Yes. Treating Vision as an MCP server preserves KITTY’s existing tool‑first, model‑agnostic architecture. Benefits:

- Swapability: CLIP ↔ VLM backends can be swapped behind the same tool contract without changing orchestration or prompts.
- Local‑first posture: run CLIP on‑device (MPS) and SearXNG self‑hosted; cloud VLMs remain optional fallbacks.
- Unified safety & observability: MCP calls are audited and routed like other tools (Research, CAD, Memory).

If you want to use Gemma‑3‑Vision or similar VLMs, expose them as an HTTP microservice and call them from the MCP server (backend="vlm"). The MCP contract can be extended to return richer outputs (captions, bboxes, attributes) as needed while keeping the orchestration stable.

---

### Design notes & rationale

- Search: use SearXNG JSON first, Brave as fallback — mirrors KITTY’s Research stack and avoids vendor lock‑in.
- Verify: CLIP is fast and local for generic checks; flip to a VLM backend for complex perception tasks.
- Store: persist only user‑approved refs in MinIO; use presigned URLs for downstream tools (CAD/Tripo).
- Handoff: pass `image_refs` to Tripo alongside text prompts for image‑conditioned 3D generation.

---

### Post‑patch checks

- Gateway: `POST /api/vision/search|filter|store` → `200` when enabled.
- Artifacts: check MinIO for `references/<session>/<uuid>.jpg`.
- UI: `VisionPicker` shows ranked grid; selection persists and `store` creates artifacts.
- Smoke: run `python scripts/smoke_duck.py`.

If you want immediate route wiring, run the idempotent helper:

```bash
bash ops/scripts/enable-vision.sh .
```

This will attempt to insert router includes and MCP registration guarded by `VISION_ENABLED` without clobbering custom code.

---

If you want, I can now:

- Generate the actual one‑shot patch files and apply them to the repo (create the new files listed above).
- Or just create the `vision_mcp.patch` file so you can review & apply manually.

Which would you prefer?
