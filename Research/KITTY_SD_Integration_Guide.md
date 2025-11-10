# KITTY × Stable Diffusion (Mac Studio M3 Ultra) — Integration Guide

|Expert(s)|ML Systems Engineer (Apple Silicon), Generative AI Engineer, MLOps/SRE, Backend/API Engineer|
|:--|:--|
|Question|Integrate **local** Stable Diffusion text‑to‑image generation into KITTY on a Mac Studio M3 Ultra with queued jobs and results surfaced in the **/vision** gallery and **CLI** selection.|
|Plan|Use a **modular backend adapter** (default: InvokeAI; alternates: ComfyUI or Automatic1111) behind a small KITTY “images” service that: (1) accepts text prompts, (2) enqueues jobs, (3) calls the chosen engine, (4) stores images + metadata to **MinIO (S3)**, (5) exposes list/select endpoints for UI/CLI. Optimize for **Metal (MPS)**, full‑precision stability, and clean observability.|\n
---

## 🚀 Executive Summary

This guide adds **local Stable Diffusion** image generation to KITTY with an asynchronous **queue** and unified storage in MinIO. The recommended engine for day‑to‑day work is **InvokeAI** (balanced quality, speed, and API/CLI ergonomics). We also include adapters for **ComfyUI** (workflow power, headless API) and **Automatic1111** (simple HTTP API).  

- Hardware fit: Mac Studio **M3 Ultra**, large unified memory, **Metal (MPS)** acceleration via 🧪 [PyTorch MPS](https://www.google.com/search?q=pytorch+mps+apple+silicon+metal).  
- Storage/UI fit: Images and JSON metadata go to **MinIO**; KITTY’s web gallery (**/vision**) and **CLI** list/select from that store. 🗃️ [MinIO S3 setup](https://www.google.com/search?q=minio+s3+setup+macos+docker).  
- Quality parity: With **SDXL** + LoRAs/ControlNets and good prompts, output quality matches or exceeds most hosted SD services. Proprietary cloud‑only models (e.g., Midjourney‑only styles) aren’t replicated 1:1, but the local stack covers **portraits, product renders, concept art, textures,** and more. 🖼️ [SDXL best practices](https://www.google.com/search?q=stable+diffusion+xl+best+practices+samplers+cfg+prompting).

## 🧩 Architecture (High Level)

```
┌────────────────────────────────────────────────────────────────┐
│                        KITTY Host (Mac Studio M3 Ultra)        │
│                                                                │
│  [User] ───► Gateway/API ──►  images-service  ─┬─► Engine (InvokeAI*) 
│                           (queue + adapters)    ├─► Engine (ComfyUI)
│                                                └─► Engine (A1111)
│                                                     (Metal/MPS) 
│                                                                │
│     ◄────── UI /vision   ◄── MinIO (S3): images/, metadata/ ───┘
│     ◄────── CLI select   ◄── list/query latest results
│
│  *Recommended default. Engines are swappable via config.
└────────────────────────────────────────────────────────────────┘
```

**Flow:**  
1) Client submits prompt to `images-service` → **enqueue** job.  
2) Worker calls configured **engine** (InvokeAI/ComfyUI/A1111).  
3) Save **PNG** + **JSON metadata** to MinIO; return job status + object keys.  
4) KITTY **/vision** lists from MinIO; **CLI** lists/selects via the same API.

### Why this shape?
- Decouples KITTY from any one SD UI. You can switch engines with a **config flag**.  
- Preserves a **single source of truth** (MinIO) for gallery & downstream toolchains.  
- Plays well with KITTY’s existing services and observability patterns.

## ✅ Prerequisites (macOS 14+)

- macOS 14+ (Sonoma) on **M3 Ultra**.  
- Python 3.11, Homebrew, Docker Desktop (already used by KITTY).  
- 🧪 [PyTorch with MPS](https://www.google.com/search?q=install+pytorch+mps+macos+apple+silicon) available in the chosen engine’s environment.  
- MinIO running (KITTY already uses it) and an **S3 bucket**, e.g., `kitty-artifacts`.  
- (Optional) Redis for queuing (already in KITTY). 🧱 [Redis RQ intro](https://www.google.com/search?q=python+rq+redis+queue+tutorial).

> **Metal tuning (Apple Silicon):** prefer **full precision** on MPS for numerical stability (disable half where applicable) and export `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` to let PyTorch use available memory. 🛠️ [MPS memory high watermark](https://www.google.com/search?q=PYTORCH_MPS_HIGH_WATERMARK_RATIO+meaning).

## ⚙️ Install & Run a Backend Engine

Below are **three** proven engines. Pick the one that best fits your workflow; you can swap later by changing a config value in the adapter.

### Option A — InvokeAI (recommended)

- 📦 Install: 🧭 [InvokeAI macOS quick start](https://www.google.com/search?q=invokeai+macos+quick+start+install).  
- Run the Web/REST server (headless is fine). Example:
  ```bash
  # create a clean venv
  python3 -m venv ~/venvs/invokeai && source ~/venvs/invokeai/bin/activate
  pip install --upgrade pip
  pip install invokeai  # or use official installer/launcher
  
  # first-time model/config guided setup
  invokeai-configure
  
  # run the server (adjust host/port as needed)
  export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
  invokeai-web --host 127.0.0.1 --port 9091
  ```
- Notes: The **Invocation/REST API** is primarily designed for the WebUI client; it’s usable for server‑side automation but not exhaustively documented. For robust integration, keep requests simple (txt2img/img2img) or use the CLI/workflow route if you prefer. 🔌 [InvokeAI invocation concepts](https://www.google.com/search?q=InvokeAI+Invocation+API+invocations+sessions+services).

### Option B — ComfyUI (workflow power, fast)

- 📦 Install: 🧭 [ComfyUI Apple Silicon install](https://www.google.com/search?q=comfyui+install+apple+silicon+metal).  
- Run server with API enabled:
  ```bash
  git clone https://github.com/comfyanonymous/ComfyUI.git
  cd ComfyUI
  python3 -m venv .venv && source .venv/bin/activate
  pip install --upgrade pip -r requirements.txt
  export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
  python main.py --listen 127.0.0.1 --port 8188  # add --enable-api if available
  ```
- Headless API use: export a **workflow JSON** (dev mode) and POST it to the server (e.g., `/prompt`), overriding the text inputs at runtime. 🧩 [ComfyUI API JSON submit](https://www.google.com/search?q=comfyui+api+workflow+json+submit+%2Fprompt).

### Option C — Automatic1111 (simple HTTP API)

- 📦 Install: 🧭 [Automatic1111 Mac install guide](https://www.google.com/search?q=automatic1111+mac+install+MPS+--no-half).  
- Launch with Apple‑friendly flags:
  ```bash
  ./webui.sh --skip-torch-cuda-test --precision full --no-half --port 7860
  ```
- API: POST `txt2img` to `/sdapi/v1/txt2img`; returns base64 images. 📡 [A1111 HTTP API docs](https://www.google.com/search?q=automatic1111+api+sdapi+v1+txt2img+parameters).

---

## 🧠 KITTY “images-service” (Queue + Adapters)

We add a small FastAPI service to **enqueue prompts**, call the chosen engine, and **persist** results to MinIO. Engines are swappable via `IMAGE_ENGINE`.

### 1) Service config

```env
# images-service .env
IMAGE_ENGINE=invokeai           # invokeai | comfyui | a1111
ENGINE_BASE_URL=http://127.0.0.1:9091  # InvokeAI server (if used)
COMFY_BASE_URL=http://127.0.0.1:8188   # ComfyUI server
A1111_BASE_URL=http://127.0.0.1:7860   # Automatic1111 server

S3_ENDPOINT_URL=http://minio:9000
S3_BUCKET=kitty-artifacts
S3_REGION=us-east-1
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_PREFIX=images/    # where images go in the bucket

REDIS_URL=redis://redis:6379/0
```

### 2) API surface

```http
POST /api/images/generate        # body: {prompt, model?, steps?, cfg?, width?, height?}
GET  /api/images/jobs/{job_id}   # returns {status: queued|running|done|error, artifacts:[...]}
GET  /api/images/latest?limit=50 # list latest from MinIO (for UI/CLI)
POST /api/images/select          # body: {object_key} -> returns imageRef for downstream tools
```

### 3) Minimal implementation (FastAPI + RQ)

```python
# services/images_service/main.py
import os, json, base64, time, uuid, io
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from rq import Queue
import boto3, requests

app = FastAPI()
redis = Redis.from_url(os.getenv("REDIS_URL"))
q = Queue("images", connection=redis)

# ---------- S3 ----------
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name=os.getenv("S3_REGION"),
)
BUCKET = os.getenv("S3_BUCKET")
PREFIX = os.getenv("S3_PREFIX", "images/")

# ---------- Jobs ----------
class GenReq(BaseModel):
    prompt: str
    model: str | None = None
    steps: int = 30
    cfg: float = 7.0
    width: int = 1024
    height: int = 1024
    seed: int | None = None

@app.post("/api/images/generate")
def generate(req: GenReq):
    job = q.enqueue(run_job, req.model_dump())
    return {"job_id": job.id, "status": job.get_status()}

@app.get("/api/images/jobs/{job_id}")
def job_status(job_id: str):
    from rq.job import Job
    job = Job.fetch(job_id, connection=redis)
    if job.is_finished:
        return {"status": "done", "result": job.result}
    if job.is_failed:
        return {"status": "error", "error": str(job.exc_info)[-800:]}
    return {"status": job.get_status()}

@app.get("/api/images/latest")
def latest(limit: int = 50):
    # list newest objects under PREFIX
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
    items = resp.get("Contents", [])
    items.sort(key=lambda x: x["LastModified"], reverse=True)
    out = []
    for obj in items[:limit]:
        out.append({
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": obj["LastModified"].isoformat(),
        })
    return {"items": out}

class SelectReq(BaseModel):
    key: str

@app.post("/api/images/select")
def select_image(body: SelectReq):
    # Return a reference {downloadUrl, storageUri} for KITTY
    key = body.key
    # presign for 24h
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=86400
    )
    return {
        "imageRef": {
            "downloadUrl": url,
            "storageUri": f"s3://{BUCKET}/{key}"
        }
    }

# ---------- Worker ----------
def run_job(params: dict):
    engine = os.getenv("IMAGE_ENGINE", "invokeai").lower()
    if engine == "a1111":
        return run_a1111(params)
    elif engine == "comfyui":
        return run_comfyui(params)
    else:
        return run_invokeai(params)  # default

def _save_png_and_meta(png_bytes: bytes, meta: dict):
    ts = time.strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    base = f"{PREFIX}{ts}_{uid}"
    png_key = f"{base}.png"
    meta_key = f"{base}.json"
    s3.put_object(Bucket=BUCKET, Key=png_key, Body=png_bytes, ContentType="image/png")
    s3.put_object(Bucket=BUCKET, Key=meta_key, Body=json.dumps(meta).encode("utf-8"),
                  ContentType="application/json")
    return {"png_key": png_key, "meta_key": meta_key}

def run_a1111(p):
    base = os.getenv("A1111_BASE_URL", "http://127.0.0.1:7860")
    payload = {
        "prompt": p["prompt"],
        "steps": p.get("steps", 30),
        "cfg_scale": p.get("cfg", 7.0),
        "width": p.get("width", 1024),
        "height": p.get("height", 1024),
    }
    if p.get("seed") is not None:
        payload["seed"] = p["seed"]
    if p.get("model"):
        # switch model
        requests.post(f"{base}/sdapi/v1/options", json={"sd_model_checkpoint": p["model"]})
    r = requests.post(f"{base}/sdapi/v1/txt2img", json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    # decode first image
    img_b64 = data["images"][0]
    png_bytes = base64.b64decode(img_b64.split(",",1)[-1])
    meta = {"engine":"a1111","request":p,"a1111":data.get("parameters",{})}
    return _save_png_and_meta(png_bytes, meta)

def run_comfyui(p):
    base = os.getenv("COMFY_BASE_URL", "http://127.0.0.1:8188")
    # Load a saved workflow JSON (exported from ComfyUI) and override text input
    wf_path = os.getenv("COMFY_WORKFLOW_JSON","/opt/workflows/txt2img_sdxl.json")
    with open(wf_path,"r") as f:
        graph = json.load(f)
    # naive override: find a node with 'text' input and set prompt
    for node in graph.values():
        if isinstance(node, dict):
            inputs = node.get("inputs", {})
            if "text" in inputs and isinstance(inputs["text"], str):
                inputs["text"] = p["prompt"]
    r = requests.post(f"{base}/prompt", json={"prompt": graph}, timeout=900)
    r.raise_for_status()
    # ComfyUI usually saves to disk via SaveImage node; fetch last image by polling /history or read from disk.
    # For simplicity, assume the server returns a binary or we read from a known output path.
    # (Implement according to your workflow's SaveImage path.)
    raise RuntimeError("Implement ComfyUI image retrieval based on your workflow output path.")

def run_invokeai(p):
    base = os.getenv("ENGINE_BASE_URL", "http://127.0.0.1:9091")
    # Example: submit a simple text->image request to InvokeAI.
    # The public API is primarily intended for the WebUI; consider using CLI or a thin Python diffusers worker for production.
    payload = {
        "prompt": p["prompt"],
        "width": p.get("width", 1024),
        "height": p.get("height", 1024),
        "steps": p.get("steps", 30),
        "cfg_scale": p.get("cfg", 7.0),
    }
    try:
        r = requests.post(f"{base}/api/v1/generate/txt2img", json=payload, timeout=900)
        r.raise_for_status()
        # Expectation: server returns JSON with a file path or bytes (adjust to actual schema).
        data = r.json()
        if "image" in data and isinstance(data["image"], str) and data["image"].startswith("data:image/png;base64,"):
            png_bytes = base64.b64decode(data["image"].split(",",1)[-1])
            meta = {"engine":"invokeai","request":p}
            return _save_png_and_meta(png_bytes, meta)
        elif "path" in data:
            with open(data["path"], "rb") as f:
                png_bytes = f.read()
            meta = {"engine":"invokeai","request":p}
            return _save_png_and_meta(png_bytes, meta)
        else:
            raise RuntimeError(f"Unexpected InvokeAI response keys: {list(data.keys())}")
    except Exception as e:
        # Fallback: raise for now; in production use a diffusers-based local worker here.
        raise
```
> 🔎 Swap engines by changing `IMAGE_ENGINE`. The A1111 adapter is fully runnable; ComfyUI/InvokeAI adapters show the pattern—complete the return path per your workflow/server.

---

## 🖥️ UI (/vision) & 🧰 CLI Integration

- **Backend:** Point the existing **/vision** list view to `GET /api/images/latest`. Thumbnails use a presigned URL (or a gateway proxy) for each S3 object.  
- **Selection:** Clicking a tile calls `POST /api/images/select` → returns `{ imageRef: { downloadUrl, storageUri } }`, which downstream tools (e.g., CAD) already consume.  
- **CLI:** Add commands like:
  ```bash
  kitty-cli images.generate "a photoreal product render on white"
  kitty-cli images.list --limit 12
  kitty-cli images.select <index>
  ```
  The CLI maps to the images-service API and prints a gallery URL (`/vision?query=…`) for quick review.

🗂️ File layout in S3 (example):
```
s3://kitty-artifacts/
  images/
    20251110_101530_ab12cd34.png
    20251110_101530_ab12cd34.json   # prompt, engine, params, model, seed, etc.
```

---

## 📏 Prompts, Models, and Quality

- Use **SDXL** for complex scenes & product renders; SD1.5 fine‑tunes for portraits; add **LoRA**/**ControlNet** when needed. 🎨 [Best SDXL samplers & settings](https://www.google.com/search?q=best+sampler+for+sdxl+cfg+scale+high+res+fix).  
- Curate a **model library** under `/Users/Shared/Coding/models` and expose model choices in the request body (`model` field). 📚 [Safetensors models](https://www.google.com/search?q=safetensors+stable+diffusion+models+download).  
- For **textures**, prefer tile‑aware workflows or prompt patterns; ComfyUI can bake seamless tiling nodes into one pass. 🧵 [Seamless textures Stable Diffusion](https://www.google.com/search?q=stable+diffusion+seamless+texture+tiling+workflow).

---

## 📈 Performance & Stability (Apple Silicon)

- Run **full precision** on MPS (avoid half unless you validate it on M3 Ultra).  
- Keep macOS, Python, and PyTorch **current**; Metal kernels improve over time. ⏫ [Update PyTorch MPS performance](https://www.google.com/search?q=pytorch+mps+performance+macos+update).  
- Use **1024×1024** for SDXL starting points; do staged upscales rather than massive single‑pass renders.  
- Consider **two queues** (normal / high‑res) so long jobs don’t starve quick ones.  
- Monitor memory with Activity Monitor; if pressure rises, reduce concurrent jobs or steps. 📊 [macOS unified memory tips](https://www.google.com/search?q=macos+unified+memory+gpu+cpu+best+practices).

---

## 🔒 Security & Safety

- Bind engines to `127.0.0.1`; expose only the KITTY **images-service** over the internal network.  
- Add a shared **API token** header to images-service. 🔑 [FastAPI auth header pattern](https://www.google.com/search?q=fastapi+api+key+auth+header+example).  
- (Optional) Add **NSFW classification** before publishing to /vision. 🧯 [NSFW image classifier python](https://www.google.com/search?q=python+nsfw+image+classifier+open+source).

---

## 🧪 Smoke Test

1) Start your chosen engine (InvokeAI/ComfyUI/A1111).  
2) Launch `images-service` and Redis.  
3) `POST /api/images/generate {"prompt":"studio photo of a steel water bottle on white, soft shadow", "width":1024, "height":1024}`  
4) Poll `/api/images/jobs/{id}` until `done`.  
5) Open **/vision**; confirm the new image is present.  
6) `kitty-cli images.select <index>` → verify it returns `{imageRef:…}` and can be consumed by downstream tasks.

---

## 🔄 Alternates & Extensions

- **ComfyUI-first**: build a master **workflow** (txt2img → hi‑res fix → upscaler), export JSON, and submit to `/prompt`. Useful when you need **repeatable pipelines** with many steps. 🧩 [ComfyUI workflow export](https://www.google.com/search?q=comfyui+export+workflow+json+dev+mode).  
- **Diffusers worker**: implement a pure‑Python worker using 🧨 **Diffusers** + MPS for maximal control without any external UI. 📦 [Diffusers Stable Diffusion on M1/M2/M3](https://www.google.com/search?q=diffusers+stable+diffusion+apple+silicon+mps+example).  
- **Multi-engine routing**: keep both InvokeAI and ComfyUI installed; route prompts by **profile** (e.g., “portrait”, “product”, “texture”) to the engine best suited for the workflow.

---

## 🧭 Ops & Observability

- Expose Prometheus counters: jobs queued/running/succeeded/failed; job latency; engine errors. 📊 [Prometheus FastAPI metrics](https://www.google.com/search?q=prometheus+fastapi+metrics+example).  
- Log metadata (prompt hash, model, seed) with the MinIO object key for reproducibility.  
- Add a **feature flag** in Gateway to toggle the images-service in environments.

---

## ❓FAQ

**Can we match online image generators?**  
For most categories (portraits, concepts, product renders, textures), **yes**—especially with SDXL + tuned prompts, LoRA, and ControlNet. Some proprietary styles remain unique to closed services.

**What if InvokeAI’s public API doesn’t fit our automation?**  
Use the **CLI**, a **diffusers worker**, or swap to **ComfyUI**’s JSON workflow API. The adapter pattern keeps KITTY decoupled.

**Will this compete with llama.cpp for GPU?**  
Yes, briefly during generation. If contention is noticeable, limit concurrency or add a mutex so long SD jobs don’t collide with latency‑sensitive LLM replies.

---

## See also
- 🧭 [InvokeAI quick start (macOS)](https://www.google.com/search?q=invokeai+macos+quick+start+install) — installer/launcher & initial model setup.  
- 🧩 [ComfyUI API JSON submit](https://www.google.com/search?q=comfyui+api+workflow+json+submit+%2Fprompt) — export + POST a workflow headlessly.  
- 📡 [A1111 HTTP API](https://www.google.com/search?q=automatic1111+api+sdapi+v1+txt2img+parameters) — simple txt2img POST schema.  
- 🧪 [PyTorch MPS on Apple Silicon](https://www.google.com/search?q=pytorch+mps+apple+silicon+metal) — GPU acceleration on macOS.  
- 🗃️ [MinIO S3 SDK (boto3)](https://www.google.com/search?q=boto3+s3+upload+example+minio) — save images + metadata for KITTY’s gallery.
