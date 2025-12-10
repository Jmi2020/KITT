

0. High‑level goals

What you want Codex to implement:
	1.	Per‑model workers: each heavy LLM (Qwen, Gemma, GPT‑OSS, etc.) runs in its own process on the Mac Studio, loads its model, exposes a small HTTP API, and can be shut down cleanly.
	2.	Central WorkerManager in KITTY’s orchestrator that:
	•	Starts workers on demand
	•	Reuses them while hot
	•	Shuts them down on idle or when the graph says “done”
	•	Kills them if they don’t exit cleanly to free unified memory
	3.	LangGraph integration: graph nodes call tools that talk to workers via HTTP instead of loading models in‑process.
	4.	Ollama / GPT‑OSS integration: GPT‑OSS either:
	•	runs as a normal worker (preferred), or
	•	is accessed via 🧱 ⛔️ Ollama HTTP API￼ with an optional “reset daemon” hook.
	5.	Basic observability for memory and worker status, so KITTY’s UI can show which models are live.

Everything below is framed as tasks you can give to Codex.

⸻

1. Components and responsibilities

1.1. Components
	•	KITTY Orchestrator (Python)
	•	Uses 🧠 ⛔️ LangGraph￼ to define meta‑agents and flows
	•	Owns WorkerManager and exposes tools for “call model X”
	•	Model Worker (per model type)
	•	A small HTTP server process hosting a single LLM (via 🐎 ⛔️ llama.cpp / llama-cpp-python￼)
	•	Loads exactly one model, answers completion/chat requests, exposes /health and /shutdown
	•	Optional: Ollama bridge
	•	A thin client wrapper in the orchestrator for 🧱 ⛔️ Ollama￼ models and a script to restart the daemon when needed
	•	System metrics agent
	•	Scripts / small Python module to expose memory+worker status to KITTY’s UI

⸻

2. Suggested repo and process layout

Codex can assume something like:

kitty/
  orchestrator/
    kitty_orchestrator/
      __init__.py
      config/
        models.yaml          # per-model config
      worker_manager.py      # spawns/manages workers
      tools/
        llm_workers.py       # LangGraph tools
      graphs/
        research_graph.py    # example graph using workers
  workers/
    llama_worker/
      __init__.py
      server.py              # HTTP server hosting one model
      cli.py                 # `python -m workers.llama_worker.cli`
  scripts/
    restart_ollama.sh
    list_workers.sh
    memory_health.sh

Task for Codex: scaffold this layout and create empty modules with docstrings describing the intent of each file.

⸻

3. Model config: models.yaml

This file describes how each logical model ID maps to a worker:

# orchestrator/kitty_orchestrator/config/models.yaml
models:
  qwen_32b:
    backend: llama_worker          # process-based worker using llama.cpp
    model_path: /models/qwen2.5-32b-q4.gguf
    host: 127.0.0.1
    port: 7001
    threads: 12
    ngl: 99                        # layers on GPU/Metal
    idle_shutdown_seconds: 900     # 15 min

  gptoss_120b:
    backend: llama_worker          # preferred: same worker architecture
    model_path: /models/gptoss-120b-q4.gguf
    host: 127.0.0.1
    port: 7002
    threads: 16
    ngl: 99
    idle_shutdown_seconds: 300     # shut down sooner; huge model

  # Optional: via Ollama instead of a worker
  gptoss_120b_ollama:
    backend: ollama
    ollama_model: gpt-oss-120b
    idle_shutdown_seconds: 0       # controlled by daemon reset instead

Task for Codex: implement a small loader function:

# orchestrator/kitty_orchestrator/config/__init__.py
from dataclasses import dataclass
from typing import Literal, Optional

Backend = Literal["llama_worker", "ollama"]

@dataclass
class ModelConfig:
    id: str
    backend: Backend
    model_path: Optional[str]
    host: str
    port: int
    threads: int
    ngl: int
    idle_shutdown_seconds: int
    ollama_model: Optional[str] = None

def load_model_configs(path: str) -> dict[str, ModelConfig]:
    ...


⸻

4. Model worker API and implementation

4.1. HTTP API contract

Each llama_worker process exposes:
	•	GET /health
→ {"status": "ok", "model_id": "qwen_32b"}
	•	POST /v1/completions (OpenAI‑style)
Request:

{
  "prompt": "string",
  "max_tokens": 512,
  "temperature": 0.7,
  "stop": null
}

Response:

{
  "id": "completion-uuid",
  "model": "qwen_32b",
  "choices": [
    {
      "text": "completion text...",
      "index": 0
    }
  ]
}


	•	POST /shutdown
→ {"status": "shutting_down"} then the process exits.

This is intentionally minimal so LangGraph tools can use a standard HTTP client.

4.2. Worker process implementation (Python + llama-cpp-python)

Have Codex implement:

# workers/llama_worker/server.py
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from llama_cpp import Llama  # binds to ⛔️ [llama.cpp Metal build](https://www.google.com/search?q=llama.cpp+metal+build+mac+arm64)
import os
import sys
import signal
import threading

app = FastAPI()
llm: Llama | None = None
model_id: str | None = None

class CompletionRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7
    stop: list[str] | None = None

def init_model():
    global llm, model_id
    model_id = os.environ["KITTY_MODEL_ID"]
    model_path = os.environ["KITTY_MODEL_PATH"]
    n_threads = int(os.environ.get("KITTY_THREADS", "8"))
    n_gpu_layers = int(os.environ.get("KITTY_NGL", "99"))

    llm = Llama(
        model_path=model_path,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
        # Ensure Metal is enabled via build flags / env
    )

@app.on_event("startup")
def on_startup():
    init_model()

@app.get("/health")
def health():
    return {"status": "ok", "model_id": model_id}

@app.post("/v1/completions")
def completions(req: CompletionRequest):
    assert llm is not None
    out = llm(
        req.prompt,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        stop=req.stop,
    )
    text = out["choices"][0]["text"]
    return {
        "id": out.get("id", ""),
        "model": model_id,
        "choices": [{"text": text, "index": 0}],
    }

@app.post("/shutdown")
def shutdown():
    # Best-effort cleanup, then exit process to free unified memory
    def _shutdown():
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return {"status": "shutting_down"}

def main():
    host = os.environ.get("KITTY_HOST", "127.0.0.1")
    port = int(os.environ["KITTY_PORT"])
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()

Startup helper:

# workers/llama_worker/start_worker.sh
#!/usr/bin/env bash
set -euo pipefail

export KITTY_MODEL_ID="$1"
export KITTY_MODEL_PATH="$2"
export KITTY_HOST="$3"
export KITTY_PORT="$4"
export KITTY_THREADS="${5:-8}"
export KITTY_NGL="${6:-99}"

# Optionally set extra Metal-related env vars here

exec python -m workers.llama_worker.server

Key property: when /shutdown is called, the process dies, so all Metal/unified memory allocations vanish.

⸻

5. WorkerManager in the orchestrator

5.1. Responsibilities
	•	Track per‑model workers (PID, URL, last_used, status).
	•	Start a worker if it’s missing.
	•	Provide an HTTP client for tools.
	•	Implement idle shutdown.
	•	Implement “force release worker X now” for graph nodes that want to free memory at the end of a phase.

5.2. Data structures

# orchestrator/kitty_orchestrator/worker_manager.py
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional
import subprocess
import requests
import time
import os
import signal

from .config import load_model_configs, ModelConfig

@dataclass
class WorkerRuntime:
    model_id: str
    config: ModelConfig
    pid: Optional[int] = None
    base_url: Optional[str] = None
    last_used: Optional[datetime] = None
    status: str = "stopped"  # "starting" | "ready" | "stopping" | "stopped"

class WorkerManager:
    def __init__(self, config_path: str):
        self.model_configs: Dict[str, ModelConfig] = load_model_configs(config_path)
        self.workers: Dict[str, WorkerRuntime] = {
            mid: WorkerRuntime(model_id=mid, config=cfg)
            for mid, cfg in self.model_configs.items()
        }

    # --- lifecycle ---
    def ensure_worker(self, model_id: str, timeout_s: int = 120) -> WorkerRuntime:
        rt = self.workers[model_id]
        if rt.status == "ready" and rt.pid and self._is_alive(rt.pid):
            return rt

        self._start_worker(rt)
        self._wait_for_health(rt, timeout_s)
        return rt

    def mark_used(self, model_id: str):
        self.workers[model_id].last_used = datetime.utcnow()

    def maybe_shutdown_idle(self, model_id: str, force: bool = False):
        rt = self.workers[model_id]
        cfg = rt.config
        if rt.status != "ready" or not rt.pid:
            return
        if not force and cfg.idle_shutdown_seconds <= 0:
            return
        if not force and rt.last_used:
            idle = datetime.utcnow() - rt.last_used
            if idle < timedelta(seconds=cfg.idle_shutdown_seconds):
                return

        self._graceful_shutdown(rt)
        if self._is_alive(rt.pid):
            self._kill_worker(rt)

    # --- internals ---
    def _start_worker(self, rt: WorkerRuntime):
        cfg = rt.config
        if cfg.backend != "llama_worker":
            # handled by a different path (e.g., Ollama)
            return

        cmd = [
            "bash",
            "workers/llama_worker/start_worker.sh",
            cfg.id,
            cfg.model_path,
            cfg.host,
            str(cfg.port),
            str(cfg.threads),
            str(cfg.ngl),
        ]
        proc = subprocess.Popen(
            cmd,
            start_new_session=True,  # allows killing process group on macOS
        )
        rt.pid = proc.pid
        rt.base_url = f"http://{cfg.host}:{cfg.port}"
        rt.status = "starting"

    def _wait_for_health(self, rt: WorkerRuntime, timeout_s: int):
        assert rt.base_url
        deadline = time.time() + timeout_s
        url = f"{rt.base_url}/health"
        while time.time() < deadline:
            try:
                r = requests.get(url, timeout=1.0)
                if r.ok and r.json().get("status") == "ok":
                    rt.status = "ready"
                    rt.last_used = datetime.utcnow()
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError(f"Worker {rt.model_id} failed to become healthy")

    def _graceful_shutdown(self, rt: WorkerRuntime, timeout_s: int = 30):
        assert rt.base_url and rt.pid
        rt.status = "stopping"
        try:
            requests.post(f"{rt.base_url}/shutdown", timeout=2.0)
        except Exception:
            pass
        # Wait briefly
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if not self._is_alive(rt.pid):
                rt.status = "stopped"
                return
            time.sleep(1)
        # will be force-killed by caller if still alive

    def _kill_worker(self, rt: WorkerRuntime):
        if not rt.pid:
            return
        try:
            os.killpg(os.getpgid(rt.pid), signal.SIGKILL)
        except Exception:
            try:
                os.kill(rt.pid, signal.SIGKILL)
            except Exception:
                pass
        rt.status = "stopped"
        rt.pid = None

    def _is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

Task for Codex: implement this with tests that:
	•	Start a worker for a fake qwen_32b configuration
	•	Hit /v1/completions
	•	Call maybe_shutdown_idle(..., force=True) and assert PID is gone

⸻

6. LangGraph integration: tools that use WorkerManager

KITTY’s graphs should call tools, not the worker directly.

6.1. Tool helpers

# orchestrator/kitty_orchestrator/tools/llm_workers.py
from typing import TypedDict
import requests

from ..worker_manager import WorkerManager

class LLMCompletionInput(TypedDict):
    model_id: str
    prompt: str
    max_tokens: int
    temperature: float

class LLMCompletionOutput(TypedDict):
    completion: str

class LLMTools:
    def __init__(self, worker_manager: WorkerManager):
        self.worker_manager = worker_manager

    def completion(self, args: LLMCompletionInput) -> LLMCompletionOutput:
        model_id = args["model_id"]
        prompt = args["prompt"]
        max_tokens = args["max_tokens"]
        temperature = args["temperature"]

        rt = self.worker_manager.ensure_worker(model_id)
        self.worker_manager.mark_used(model_id)

        url = f"{rt.base_url}/v1/completions"
        resp = requests.post(
            url,
            json={
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["text"]
        return {"completion": text}

    def release_model(self, model_id: str):
        self.worker_manager.maybe_shutdown_idle(model_id, force=True)

6.2. Wiring into a LangGraph graph

Use 🧠 ⛔️ LangGraph node/tool pattern￼.

Example simplified state graph:

# orchestrator/kitty_orchestrator/graphs/research_graph.py
from langgraph.graph import StateGraph, END
from typing import Dict, Any

from ..worker_manager import WorkerManager
from ..tools.llm_workers import LLMTools

State = Dict[str, Any]

worker_manager = WorkerManager("kitty_orchestrator/config/models.yaml")
llm_tools = LLMTools(worker_manager)

def ensure_qwen_node(state: State) -> State:
    worker_manager.ensure_worker("qwen_32b")
    return state

def research_node(state: State) -> State:
    question = state["question"]
    out = llm_tools.completion(
        {
            "model_id": "qwen_32b",
            "prompt": f"Research this question:\n{question}",
            "max_tokens": 2048,
            "temperature": 0.3,
        }
    )
    state["research"] = out["completion"]
    return state

def release_qwen_node(state: State) -> State:
    llm_tools.release_model("qwen_32b")
    return state

graph = StateGraph(State)
graph.add_node("ensure_qwen", ensure_qwen_node)
graph.add_node("research", research_node)
graph.add_node("release_qwen", release_qwen_node)

graph.set_entry_point("ensure_qwen")
graph.add_edge("ensure_qwen", "research")
graph.add_edge("research", "release_qwen")
graph.add_edge("release_qwen", END)

research_app = graph.compile()

Pattern:
	•	Early node: ensure worker
	•	Middle nodes: use the worker many times
	•	Final node in that branch: release worker to free unified memory

⸻

7. Ollama / GPT‑OSS handling

If you still want to use 🧱 ⛔️ Ollama GPT‑OSS￼ sometimes:

7.1. Ollama client

# orchestrator/kitty_orchestrator/tools/ollama_client.py
import requests

class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434"):
        self.base_url = base_url

    def completion(self, model: str, prompt: str) -> str:
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

7.2. Daemon reset hook (macOS)

# scripts/restart_ollama.sh
#!/usr/bin/env bash
set -euo pipefail

# Bounce the macOS user daemon to reclaim memory
launchctl kickstart -k "gui/$UID/io.ollama.daemon"

You can call this script from a maintenance job or after a particularly heavy GPT‑OSS session when memory is fragmented.

Important: this is coarser than workers; the preferred path for GPT‑OSS on KITTY is to host it in a llama_worker just like Qwen.

⸻

8. System metrics and KITTY UI integration

Codex can add a small system metrics helper so KITTY can display worker status and approximate memory usage.

8.1. Worker status endpoint

# orchestrator/kitty_orchestrator/metrics.py
from fastapi import FastAPI
import psutil  # ok to add dependency

from .worker_manager import WorkerManager

def make_metrics_app(worker_manager: WorkerManager) -> FastAPI:
    app = FastAPI()

    @app.get("/kitty/system/workers")
    def workers():
        out = []
        for mid, rt in worker_manager.workers.items():
            rss_mb = None
            if rt.pid and psutil.pid_exists(rt.pid):
                rss_mb = psutil.Process(rt.pid).memory_info().rss / (1024 * 1024)
            out.append(
                {
                    "model_id": mid,
                    "status": rt.status,
                    "pid": rt.pid,
                    "rss_mb": rss_mb,
                    "last_used": rt.last_used.isoformat() if rt.last_used else None,
                }
            )
        return {"workers": out}

    return app

Expose this internally so KITTY’s UI can show “which models are live and how heavy they are.”

⸻

9. Testing checklist for Codex

Have Codex implement tests/scripts that verify:
	1.	Single worker lifecycle
	•	Start Qwen worker via WorkerManager
	•	Call /v1/completions
	•	Force shutdown and verify PID is gone
	2.	Idle shutdown
	•	Set idle_shutdown_seconds: 1 in a temp config
	•	Call the model once
	•	Sleep > 2 seconds
	•	Run an “idle reaper” that calls maybe_shutdown_idle for all models; assert worker is gone
	3.	Graph‑driven cleanup
	•	Run a LangGraph flow with ensure_qwen → research → release_qwen
	•	After completion, confirm the worker PID is dead
	4.	Ollama reset script
	•	Run scripts/restart_ollama.sh on a dev machine and make sure the daemon comes back and responds to /api/tags

⸻

10. How this achieves reliable unified‑memory cleanup on the M3 Ultra
	•	Each heavy model is in its own process → all Metal / unified allocations are tied to that process.
	•	Graph phases explicitly release workers → after a research/synthesis phase, you free the largest model(s).
	•	WorkerManager can force‑kill non‑cooperating workers → if /shutdown hangs, you still reclaim memory by killing the PID / process group.
	•	Ollama is treated as the exception, not the rule → when you do use it, you have a concrete “reset daemon” escape hatch.

That gives KITTY predictable, controllable memory behavior while still letting the meta‑agent spin up very large models on demand.

⸻

See also
	•	🧠 LangGraph tools & nodes￼ — patterns for wrapping your WorkerManager as tools
	•	🐎 llama-cpp-python server examples￼ — reference for serving llama.cpp via Python HTTP
	•	🍏 Apple Silicon unified memory behavior￼ — background on why process boundaries matter
	•	🧱 Ollama advanced usage￼ — details for daemon management on macOS
	•	📊 psutil process memory monitoring￼ — for better metrics in KITTY’s dashboard

You may also enjoy
	•	🧩 LangChain vs LangGraph comparisons￼ — context for why your graph‑first approach is nice for meta‑agents
	•	🚀 Agentic evaluation patterns￼ — ideas for testing KITTY’s multi‑model flows
	•	🧪 Prompting large local models￼ — tips for getting the most from Qwen/Gemma on‑box