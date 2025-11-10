# KITTY × Stable Diffusion — **Recommended Stack** Integration (Mac Studio M3 Ultra)

|Expert(s)|ML Systems Engineer (Apple Silicon), Generative AI Engineer, Backend/API Engineer, MLOps/SRE|
|:--|:--|
|Question|Implement the **recommended stack** for local Stable Diffusion in KITTY with queued jobs, MinIO persistence, `/vision` gallery surfacing, and CLI selection.|
|Plan|Stand up **InvokeAI** for day‑to‑day authoring & model management; add a small **images-service** (FastAPI + Redis/RQ + boto3) that queues text prompts and either (A) calls InvokeAI, or (B) uses a built‑in **Diffusers/MPS worker** for headless reliability. Persist PNG + JSON to **MinIO (S3)**, expose list/select APIs for UI/CLI, and instrument with metrics.|

> This guide is production‑oriented for **macOS 14+** on **M3 Ultra** with **Metal (MPS)** acceleration. It includes concrete commands, code, and model downloads.  
> Concepts align with KITTY’s storage & vision flows (**MinIO artifacts**, `/vision` **imageRefs**) so the gallery and CLI “select” just work. fileciteturn1file15 fileciteturn1file0

---

## 0) What you get

- 🔁 **Queued** text‑to‑image jobs (non‑blocking)  
- 🧠 **InvokeAI** as the preferred creative surface (optional headless)  
- 🧰 A robust **Diffusers/MPS worker** for guaranteed headless runs  
- 🗃️ Images + metadata to **MinIO (S3)**, listed in the **/vision** gallery and selectable from the **CLI** (returns `{imageRef: {downloadUrl, storageUri}}`) fileciteturn1file0 fileciteturn1file1  
- 📊 Basic metrics and logs; clean process model

> Why this shape? KITTY already standardizes on **MinIO** and **/vision** for artifacts & image references, so plugging SD in via a thin “images‑service” keeps the rest of the system untouched. fileciteturn1file15 fileciteturn1file14

---

## 1) Prereqs (macOS 14+, M3 Ultra)

- Xcode CLT, Homebrew, Python 3.11, Redis, Node 20 (KITTY already uses these) fileciteturn1file5  
- Docker Desktop for existing KITTY services (not used for the MPS worker) fileciteturn1file5  
- MinIO running (see KITTY docs; default console at :9001) fileciteturn1file16

Helpful links (Google search):  
- 🧪 [PyTorch MPS on Apple Silicon](https://www.google.com/search?q=pytorch+mps+apple+silicon+macos+install)  
- 🗃️ [MinIO + boto3 quick start](https://www.google.com/search?q=boto3+minio+example+python)  
- 🔴 [launchd service .plist tutorial](https://www.google.com/search?q=launchd+create+plist+macos+user+agent)

---

## 2) Model installs (local, no cloud)

We’ll prepare a **models** folder and download standard, high‑quality baselines:

```bash
mkdir -p /Users/Shared/KITTY/models && cd /Users/Shared/KITTY/models

# Install HF CLI if needed
pipx install huggingface_hub || pip3 install -U "huggingface_hub[cli]"

# --- SDXL (base + refiner), best general quality ---
huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 \
  --local-dir sd_xl_base
huggingface-cli download stabilityai/stable-diffusion-xl-refiner-1.0 \
  --local-dir sd_xl_refiner

# --- SD 1.5 popular baseline ---
huggingface-cli download runwayml/stable-diffusion-v1-5 --local-dir sd15_base

# (Optional) Photoreal fine-tune (check license before use):
# huggingface-cli download SG161222/Realistic_Vision_V6.0_B1_noVAE --local-dir realistic_vision
```

> **Storage note:** Keep models under `/Users/Shared/KITTY/models` so both InvokeAI and the Diffusers worker can read them. You can also point InvokeAI’s model manager here.  
> **Legal note:** Verify model licenses before use (esp. 3rd‑party fine‑tunes). 🍏 [Hugging Face model licensing](https://www.google.com/search?q=hugging+face+model+license+sdxl)

---

## 3) Install InvokeAI (authoring UI + optional API/CLI)

**Why InvokeAI?** Excellent UX, solid performance, and a structured internal engine you can automate. (We still ship a headless Diffusers worker below to guarantee stability for jobs.)

**Install & configure:**  
🍎 [InvokeAI macOS install](https://www.google.com/search?q=InvokeAI+macOS+install+guide)
```bash
python3 -m venv ~/venvs/invokeai && source ~/venvs/invokeai/bin/activate
pip install --upgrade pip
pip install invokeai

# One-time guided setup (choose "existing models" and point to /Users/Shared/KITTY/models)
invokeai-configure

# Run locally (headless ok); bind to loopback
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
invokeai-web --host 127.0.0.1 --port 9091
```
- Keep **full precision** on Apple GPUs for numerical stability (avoid half unless validated on M3) 🧠 [MPS precision gotchas](https://www.google.com/search?q=apple+silicon+mps+float16+stable+diffusion+issue)

---

## 4) Images‑service (queue + MinIO + adapters)

A small FastAPI service adds: **enqueue → generate → store → list/select**.  
We ship two adapters:
- **invokeai**: attempts to call a simple REST/CLI path  
- **diffusers**: **reference worker** that’s rock‑solid on MPS (default if InvokeAI API isn’t exposed)

### 4.1 Project layout

```
services/images_service/
  ├─ requirements.txt
  ├─ .env.example
  ├─ main.py                # FastAPI + RQ endpoints
  ├─ worker_diffusers.py    # MPS pipeline (SDXL/SD1.5)
  ├─ engines/
  │   ├─ invokeai_client.py # optional adapter (CLI/REST)
  │   └─ a1111_client.py    # optional adapter (HTTP)
  └─ models.yaml            # model registry (name → local path)
```

### 4.2 `requirements.txt`

```text
fastapi==0.115.*
uvicorn[standard]==0.30.*
redis==5.*
rq==1.16.*
boto3==1.35.*
pydantic==2.*
pillow==10.*
# Headless generation
torch==2.*           # auto-detects MPS on macOS
transformers==4.*
diffusers==0.30.*
accelerate==0.34.*
safetensors==0.4.*
```

### 4.3 `.env.example`

```env
# Engine choice: diffusers | invokeai
IMAGE_ENGINE=diffusers

# InvokeAI (if used)
INVOKE_HOST=127.0.0.1
INVOKE_PORT=9091

# S3/MinIO
S3_ENDPOINT_URL=http://localhost:9000
S3_BUCKET=kitty-artifacts
S3_REGION=us-east-1
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_PREFIX=images/

# Queue
REDIS_URL=redis://127.0.0.1:6379/0

# Models
MODELS_YAML=/Users/Shared/KITTY/models/models.yaml
HF_HOME=/Users/Shared/KITTY/.cache/huggingface

# Apple Silicon tuning
PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
```

> **Matches KITTY:** Images + metadata flow to MinIO and appear in **/vision**; CLI can show and **select** images to pass to downstream tools as `{imageRef}`. fileciteturn1file0 fileciteturn1file1

### 4.4 `models.yaml`

```yaml
# name → on-disk directory (Diffusers format)
sdxl_base: /Users/Shared/KITTY/models/sd_xl_base
sdxl_refiner: /Users/Shared/KITTY/models/sd_xl_refiner
sd15_base: /Users/Shared/KITTY/models/sd15_base
# realistic_vision: /Users/Shared/KITTY/models/realistic_vision
```

### 4.5 `worker_diffusers.py` (MPS, SDXL default)

```python
# services/images_service/worker_diffusers.py
from __future__ import annotations
import io, os, json, time, uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any
import torch
from PIL import Image
import boto3

from diffusers import StableDiffusionXLPipeline, StableDiffusionXLImg2ImgPipeline
from diffusers import StableDiffusionPipeline, EulerAncestralDiscreteScheduler

@dataclass
class GenParams:
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg: float = 7.0
    seed: Optional[int] = None
    model: str = "sdxl_base"   # see models.yaml
    refiner: Optional[str] = None

class S3Store:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION"),
        )
        self.bucket = os.getenv("S3_BUCKET")
        self.prefix = os.getenv("S3_PREFIX", "images/")

    def save_png_and_meta(self, im: Image.Image, meta: Dict[str, Any]) -> Dict[str, str]:
        ts = time.strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        base = f"{self.prefix}{ts}_{uid}"
        png_key = f"{base}.png"
        meta_key = f"{base}.json"

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        self.client.put_object(Bucket=self.bucket, Key=png_key, Body=buf.getvalue(), ContentType="image/png")
        self.client.put_object(Bucket=self.bucket, Key=meta_key, Body=json.dumps(meta).encode("utf-8"),
                               ContentType="application/json")
        return {"png_key": png_key, "meta_key": meta_key}

class DiffusersWorker:
    def __init__(self, models_yaml: str):
        import yaml
        with open(models_yaml, "r") as f:
            self.models = yaml.safe_load(f)

        self.device = torch.device("mps") if torch.backends.mps.is_available() else torch.device("cpu")
        self.s3 = S3Store()

        # simple caches
        self._sdxl = {}
        self._sd15 = {}

    def _load_sdxl(self, name: str):
        if name in self._sdxl:
            return self._sdxl[name]

        base_path = self.models[name]
        pipe = StableDiffusionXLPipeline.from_pretrained(
            base_path, torch_dtype=torch.float32, variant=None, use_safetensors=True
        )
        pipe.to(self.device)
        # Slight memory friendliness on MPS
        pipe.enable_attention_slicing("max")
        self._sdxl[name] = pipe
        return pipe

    def _load_sd15(self, name: str):
        if name in self._sd15:
            return self._sd15[name]

        base_path = self.models[name]
        pipe = StableDiffusionPipeline.from_pretrained(
            base_path, torch_dtype=torch.float32, safety_checker=None, feature_extractor=None
        )
        pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
        pipe.to(self.device)
        pipe.enable_attention_slicing("max")
        self._sd15[name] = pipe
        return pipe

    def generate(self, p: GenParams) -> Dict[str, str]:
        g = None
        if p.seed is not None:
            g = torch.Generator(device=self.device).manual_seed(int(p.seed))

        if p.model.startswith("sdxl"):
            pipe = self._load_sdxl(p.model)
            image = pipe(
                prompt=p.prompt,
                num_inference_steps=p.steps,
                guidance_scale=p.cfg,
                width=p.width, height=p.height,
                generator=g
            ).images[0]

            # optional refiner pass
            if p.refiner:
                ref_pipe = self._load_sdxl(p.refiner)
                image = ref_pipe(
                    prompt=p.prompt,
                    num_inference_steps=10,
                    guidance_scale=min(5.0, p.cfg),
                    image=image
                ).images[0]

        else:
            pipe = self._load_sd15(p.model)
            image = pipe(
                prompt=p.prompt,
                num_inference_steps=p.steps,
                guidance_scale=p.cfg,
                width=p.width, height=p.height,
                generator=g
            ).images[0]

        meta = {
            "engine": "diffusers",
            "request": p.__dict__,
            "device": str(self.device),
            "library": "diffusers",
        }
        return self.s3.save_png_and_meta(image, meta)

# convenience entry for RQ
_worker_singleton = None
def run_diffusers_job(params: Dict[str, Any]) -> Dict[str, str]:
    global _worker_singleton
    if _worker_singleton is None:
        models_yaml = os.getenv("MODELS_YAML", "/Users/Shared/KITTY/models/models.yaml")
        _worker_singleton = DiffusersWorker(models_yaml)
    gp = GenParams(**params)
    return _worker_singleton.generate(gp)
```

### 4.6 `engines/invokeai_client.py` (optional adapter)

> Use if you want to route jobs to InvokeAI’s server/CLI instead of the headless worker. The server API surface can vary—keep it simple or shell out to a CLI/workflow.

```python
# services/images_service/engines/invokeai_client.py
import os, subprocess, shlex
from typing import Dict, Any
from .util_s3 import S3Store

def run_invokeai_job(p: Dict[str, Any]) -> Dict[str, str]:
    # Example: shell out to a simple InvokeAI CLI recipe that writes a PNG to disk,
    # then upload to MinIO. Adjust to your version of InvokeAI.
    prompt = p["prompt"].replace('"', '\\"')
    outdir = os.getenv("INVOKE_OUTDIR", "/tmp/invoke_out")
    os.makedirs(outdir, exist_ok=True)

    # Replace this with your preferred CLI/workflow command.
    cmd = f'invokeai --prompt "{prompt}" --steps {p.get("steps",30)} --cfg {p.get("cfg",7.0)} --outdir {outdir}'
    subprocess.run(shlex.split(cmd), check=True)

    # Find newest PNG and upload
    pngs = sorted([f for f in os.listdir(outdir) if f.endswith(".png")])
    if not pngs:
        raise RuntimeError("InvokeAI did not produce an image in outdir")
    latest = os.path.join(outdir, pngs[-1])

    with open(latest, "rb") as f:
        data = f.read()

    s3 = S3Store()
    meta = {"engine":"invokeai","request":p}
    return s3.save_png_and_bytes(data, meta)  # see util_s3 below
```

> **Tip:** If your InvokeAI exposes a minimal REST, you can replace the shell call with a `requests.post(...)` to that endpoint and capture the resulting file path/bytes.

### 4.7 `engines/a1111_client.py` (optional, known HTTP API)

```python
# services/images_service/engines/a1111_client.py
import os, base64, requests
from typing import Dict, Any
from .util_s3 import S3Store

def run_a1111_job(p: Dict[str, Any]) -> Dict[str, str]:
    base = os.getenv("A1111_BASE_URL", "http://127.0.0.1:7860")
    payload = {
        "prompt": p["prompt"],
        "steps": p.get("steps", 30),
        "cfg_scale": p.get("cfg", 7.0),
        "width": p.get("width", 1024),
        "height": p.get("height", 1024),
    }
    if "seed" in p and p["seed"] is not None:
        payload["seed"] = int(p["seed"])
    r = requests.post(f"{base}/sdapi/v1/txt2img", json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    b64 = data["images"][0].split(",",1)[-1]
    png_bytes = base64.b64decode(b64)
    s3 = S3Store()
    meta = {"engine":"a1111","request":p,"a1111":data.get("parameters",{})}
    return s3.save_png_and_bytes(png_bytes, meta)
```

### 4.8 `engines/util_s3.py` (shared MinIO helper)

```python
# services/images_service/engines/util_s3.py
import io, os, json, time, uuid, boto3

class S3Store:
    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            region_name=os.getenv("S3_REGION"),
        )
        self.bucket = os.getenv("S3_BUCKET")
        self.prefix = os.getenv("S3_PREFIX","images/")

    def save_png_and_bytes(self, png_bytes: bytes, meta: dict) -> dict:
        ts = time.strftime("%Y%m%d_%H%M%S")
        key_base = f"{self.prefix}{ts}_{uuid.uuid4().hex[:8]}"
        png_key = f"{key_base}.png"
        meta_key = f"{key_base}.json"
        self.client.put_object(Bucket=self.bucket, Key=png_key, Body=png_bytes, ContentType="image/png")
        self.client.put_object(Bucket=self.bucket, Key=meta_key, Body=json.dumps(meta).encode("utf-8"),
                               ContentType="application/json")
        return {"png_key": png_key, "meta_key": meta_key}
```

### 4.9 `main.py` (FastAPI + RQ)

```python
# services/images_service/main.py
import os, json
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from rq import Queue
import boto3

# ---- Queue ----
redis = Redis.from_url(os.getenv("REDIS_URL","redis://127.0.0.1:6379/0"))
q = Queue("images", connection=redis)

# ---- S3 ----
s3 = boto3.client(
    "s3",
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name=os.getenv("S3_REGION"),
)
BUCKET = os.getenv("S3_BUCKET")
PREFIX = os.getenv("S3_PREFIX","images/")

# ---- Job payload ----
class GenReq(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg: float = 7.0
    seed: Optional[int] = None
    model: str = "sdxl_base"
    refiner: Optional[str] = None

app = FastAPI(title="KITTY Images Service")

@app.post("/api/images/generate")
def generate(req: GenReq):
    engine = os.getenv("IMAGE_ENGINE","diffusers").lower()
    if engine == "a1111":
        from engines.a1111_client import run_a1111_job as fn
    elif engine == "invokeai":
        from engines.invokeai_client import run_invokeai_job as fn
    else:
        from worker_diffusers import run_diffusers_job as fn
    job = q.enqueue(fn, req.model_dump())
    return {"job_id": job.id, "status": "queued"}

@app.get("/api/images/jobs/{job_id}")
def job_status(job_id: str):
    from rq.job import Job
    job = Job.fetch(job_id, connection=redis)
    if job.is_failed:
        return {"status":"error","error":str(job.exc_info)[-800:]}
    if job.is_finished:
        return {"status":"done","result": job.result}
    return {"status": job.get_status()}

@app.get("/api/images/latest")
def latest(limit: int = 36):
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX)
    items = resp.get("Contents", [])
    items.sort(key=lambda x: x["LastModified"], reverse=True)
    out = [{
        "key": it["Key"],
        "size": it["Size"],
        "last_modified": it["LastModified"].isoformat()
    } for it in items[:limit] if it["Key"].lower().endswith(".png")]
    return {"items": out}

@app.post("/api/images/select")
def select_image(body: Dict[str, Any]):
    key = body.get("key")
    if not key:
        raise HTTPException(400, "missing key")
    url = s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=86400
    )
    return {"imageRef": {"downloadUrl": url, "storageUri": f"s3://{BUCKET}/{key}"}}
```

### 4.10 Run the service locally

```bash
# 1) Environment
cd services/images_service
cp .env.example .env && source .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Start Redis if not already running
brew services start redis   # or `redis-server` in a terminal

# 3) Run RQ worker
rq worker images &

# 4) Start FastAPI (loopback)
uvicorn main:app --host 127.0.0.1 --port 8089 --workers 1 --log-level info
```

- **Submit:** `curl -X POST http://127.0.0.1:8089/api/images/generate -H "content-type: application/json" -d '{"prompt":"studio photo of a matte black water bottle, soft shadow", "width":1024, "height":1024}'`  
- **Poll:** `curl http://127.0.0.1:8089/api/images/jobs/<job_id>`  
- **List:** `curl http://127.0.0.1:8089/api/images/latest`  
- **Select:** `curl -X POST http://127.0.0.1:8089/api/images/select -H "content-type: application/json" -d '{"key":"images/2025...png"}'` → returns `{ imageRef }` for downstream tools.  
(These map cleanly to KITTY’s `/vision` & CLI flows.) fileciteturn1file1

---

## 5) Wire into KITTY (Gateway/UI/CLI)

### 5.1 Gateway (FastAPI) proxy

Add a lightweight proxy so UI/CLI can hit a stable path under KITTY:

```python
# services/gateway/src/routes/images_proxy.py
from fastapi import APIRouter, Request
import httpx, os

router = APIRouter(prefix="/api/images", tags=["images"])
IMAGES_BASE = os.getenv("IMAGES_BASE","http://127.0.0.1:8089")

@router.post("/generate")
async def gen(request: Request):
    data = await request.json()
    async with httpx.AsyncClient(timeout=1200.0) as c:
        r = await c.post(f"{IMAGES_BASE}/api/images/generate", json=data)
        return r.json()

@router.get("/jobs/{job_id}")
async def job(job_id: str):
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{IMAGES_BASE}/api/images/jobs/{job_id}")
        return r.json()

@router.get("/latest")
async def latest(limit: int = 36):
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{IMAGES_BASE}/api/images/latest", params={"limit": limit})
        return r.json()

@router.post("/select")
async def select(request: Request):
    data = await request.json()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{IMAGES_BASE}/api/images/select", json=data)
        return r.json()
```

Register the router in Gateway and add `IMAGES_BASE` to Gateway’s `.env`. (Route shape mirrors existing API contracts.) fileciteturn1file10

### 5.2 UI `/vision`

Continue to list objects from the MinIO bucket (as today) and wire the **Select** action to `POST /api/images/select` so downstream consumers receive `{imageRef}`. This aligns with the documented **imageRefs** contract. fileciteturn1file0

### 5.3 CLI

Add commands (Python Click) that call the Gateway endpoints:

```bash
kitty-cli images.generate "photoreal studio product render, 85mm lens look"
kitty-cli images.latest --limit 12
kitty-cli images.select 3    # select by index from the latest list
```

The CLI already prints a gallery link for vision flows and supports listing stored image links. fileciteturn1file1 fileciteturn1file4

---

## 6) Ops (processes, persistence, metrics)

- Run **InvokeAI** and **images-service** under a login session (e.g., `tmux`) or as **launchd** user agents. 🍎 [launchd user agents](https://www.google.com/search?q=macos+launchd+user+agent+example)  
- Keep **MinIO** and **Redis** services healthy (Docker/launchd).  
- Add Prometheus counters if desired (jobs queued/ok/failed). 📊 [Prometheus + FastAPI](https://www.google.com/search?q=prometheus+fastapi+metrics)

---

## 7) Performance notes (Apple Silicon)

- Prefer **float32** on MPS; enable attention slicing to reduce peak memory.  
- SDXL: start at **1024×1024**, use a short **refiner** pass when you need that last 5–10% polish.  
- Batch vs. queue: keep **one generation at a time** per GPU for predictable latency alongside llama.cpp.  
- macOS unified memory: watch pressure; if high, reduce steps or resolution.  
- Keep macOS / PyTorch up to date for Metal kernel improvements. 🔧 [macOS Metal performance updates](https://www.google.com/search?q=macos+metal+pytorch+mps+performance+improvements)

---

## 8) Security & safety

- Bind all engines to **127.0.0.1**; expose only Gateway endpoints.  
- Add an API key header to images‑service for defense in depth. 🔐 [FastAPI API key auth](https://www.google.com/search?q=fastapi+api+key+auth+header)  
- Optional NSFW classifier pass before publishing to `/vision`. 🧯 [open-source NSFW image classifier](https://www.google.com/search?q=nsfw+image+classifier+python)

---

## 9) Smoke test

1. Start Redis, MinIO, InvokeAI, and images‑service.  
2. `POST /api/images/generate` with a product render prompt.  
3. Poll `/jobs/{id}` until `done`.  
4. Open the KITTY **/vision** gallery; image should appear (MinIO artifacts). fileciteturn1file15  
5. From CLI, `images.latest` and `images.select` to get an `{imageRef}` and pass it to a downstream CAD action (works with existing imageRefs flow). fileciteturn1file0

---

## 10) FAQ

**Q: Why bundle a Diffusers worker if InvokeAI is installed?**  
A: For **headless reliability** and strict control. The worker uses the same models, is Metal‑accelerated, and avoids API drift. Use InvokeAI’s UI for authoring, then run jobs via the worker in production.

**Q: Can we match online image gen quality?**  
A: For **portraits, concept art, product renders, textures**—yes, with SDXL, LoRAs, and good prompting. Some proprietary styles remain unique to their platforms, but SDXL ecosystems are excellent.

**Q: How do we add ComfyUI or A1111 later?**  
A: Drop their client into `engines/` and flip `IMAGE_ENGINE`. A1111 is already included (HTTP). ComfyUI can accept workflow JSON to `/prompt` (enable API), then upload output to MinIO (same pattern). 🔌 [ComfyUI workflow API](https://www.google.com/search?q=ComfyUI+API+submit+workflow+JSON)

---

### See also
- 🧭 [InvokeAI macOS install](https://www.google.com/search?q=InvokeAI+macOS+install+guide) — installer & model manager overview.  
- 🧪 [Diffusers on Apple Silicon](https://www.google.com/search?q=diffusers+apple+silicon+mps+stable+diffusion) — MPS tips & examples.  
- 🗃️ [MinIO + boto3 examples](https://www.google.com/search?q=boto3+minio+example+python) — upload PNG + JSON to S3.  
- 🧩 [ComfyUI API workflow submit](https://www.google.com/search?q=ComfyUI+API+submit+workflow+JSON) — headless pipelines.  
- 📡 [Automatic1111 txt2img API](https://www.google.com/search?q=automatic1111+sdapi+v1+txt2img) — quick alt backend.

> Aligns with KITTY’s **artifact storage in MinIO**, **/vision selections** as `{imageRef}`, and existing UI/CLI flows. fileciteturn1file0 fileciteturn1file1 fileciteturn1file15
