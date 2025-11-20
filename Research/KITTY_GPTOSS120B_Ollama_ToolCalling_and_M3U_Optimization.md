# KITTY × GPT‑OSS 120B (Ollama) — Tool‑Calling Integration & Mac Studio M3 Ultra Optimization

**Audience:** KITTY maintainers & integrators (Gateway → Brain).  
**Goals:** (1) Wire **tool calling** with **GPT‑OSS 120B** running in **Ollama**; (2) Optimize performance on **Mac Studio (M3 Ultra)**.

---

## 0) Quick Start (TL;DR)

```bash
# 1) Install + start Ollama
brew install ollama || true
ollama serve &

# 2) Pull GPT‑OSS 120B (≈65 GB MXFP4, requires large unified memory)
ollama pull gpt-oss:120b

# 3) Local sanity check (thinking enabled)
curl -s http://localhost:11434/api/chat -d '{
  "model":"gpt-oss:120b",
  "messages":[{"role":"user","content":"One sentence hello."}],
  "think":"medium",
  "stream": false
}' | jq

# 4) KITTY env (brain/gateway)
export OLLAMA_HOST=http://host.docker.internal:11434
export OLLAMA_MODEL=gpt-oss:120b
export OLLAMA_THINK=medium  # low|medium|high
export LOCAL_REASONER_PROVIDER=ollama   # router flag
```

> References: Ollama **chat API**, **thinking**, **tool calling**, **structured outputs**, **keep_alive** (preload), **options/num_ctx**.  
> - Chat API: https://docs.ollama.com/api/chat  
> - Thinking: https://docs.ollama.com/capabilities/thinking  
> - Tool calling: https://docs.ollama.com/capabilities/tool-calling  
> - Structured outputs/JSON mode: https://docs.ollama.com/capabilities/structured-outputs  
> - Streaming (thinking/tool calls): https://docs.ollama.com/capabilities/streaming  
> - Keep-alive & context length (FAQ): https://docs.ollama.com/faq

---

## 1) Architecture for tool use

**Runtime:** `gpt-oss:120b` via **Ollama** (local server on `:11434`).  
**Pattern:** *ReAct loop* with **native tool calling** (preferred) and a **JSON‑contract fallback** when needed.

- **Native tool calling** (recommended): Pass a `tools` array to `/api/chat` and parse `message.tool_calls`. Execute tools, append **tool results** back into the conversation (role=`tool`), then continue the loop until the model returns a final message.  
- **JSON contract fallback**: Force `format:"json"` and require the model to emit either `{"type":"tool_call",...}` or `{"type":"final",...}`. Useful for non‑tool‑aware models or debugging.

> GPT‑OSS in Ollama **supports** both **tools** and **thinking** (reasoning trace). Keep the **thinking** trace out of user responses; log privately.

### 1.1 System prompt (minimal, global)

```
You are a professional tool-using assistant.
When a tool is needed, use native tool calling.
When you can answer, reply normally.
Never reveal chain-of-thought; if available, keep it internal.
If a requested action is hazardous (physical device control), require the exact confirmation phrase before proceeding.
If a request exceeds the task budget or uses cloud providers, request explicit approval.
```

---

## 2) Native tool calling — minimal loop (Python)

Below shows **(A)** define tools → **(B)** call `/api/chat` with `tools` + `think` → **(C)** route tool calls → **(D)** feed observations → **(E)** final answer.  
(Uses [`ollama` Python lib], or replace with raw HTTP.)

```python
# file: kitty_ollama_tools.py
# pip install ollama httpx pydantic
from typing import Any, Dict, List
import json, httpx, ollama

OLLAMA_HOST = "http://localhost:11434"
MODEL = "gpt-oss:120b"
THINK = "medium"  # "low" | "medium" | "high"

# ---- Define Python functions -> pass as tools ----
def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    # TODO: call your MCP/Perplexity/SearXNG here; this is a stub
    return {"results": [{"title": f"Result for {query}", "url": f"https://example.com/{i}"} for i in range(1, max_results+1)]}

def lighting_scene(zone: str, scene: str) -> Dict[str, Any]:
    # TODO: call Gateway → Home Assistant service
    return {"ack": True, "zone": zone, "scene": scene}

def cad_generate(kind: str, prompt: str, constraints: dict | None = None) -> Dict[str, Any]:
    # TODO: call CAD backend (Zoo/Tripo/local), return artifact URL
    return {"url": "s3://kitty/artifacts/demo.stl", "format": "stl", "provider": "demo"}

AVAILABLE_FUNCS = {
    "web_search": web_search,
    "lighting_scene": lighting_scene,
    "cad_generate": cad_generate,
}

def chat_with_tools(user_text: str) -> str:
    messages = [{"role": "user", "content": user_text}]
    # Pass real function refs as tools (schema auto-derived)
    r = ollama.chat(
        model=MODEL,
        messages=messages,
        tools=[web_search, lighting_scene, cad_generate],
        options={"num_ctx": 8192},     # tune later
        think=THINK,                   # enable thinking in GPT‑OSS
        stream=False
    )

    # Handle tool calls (single or multiple); loop until final
    while True:
        msg = r["message"]
        tool_calls = msg.get("tool_calls") or []

        if tool_calls:
            for tc in tool_calls:
                fname = tc["function"]["name"]
                fargs = tc["function"]["arguments"] or {}
                fn = AVAILABLE_FUNCS.get(fname)
                if not fn:
                    # Append an error observation
                    messages.append({"role":"tool","content": json.dumps({"name": fname, "ok": False, "error": "unknown tool"})})
                    continue
                try:
                    result = fn(**fargs)
                    messages.append({"role":"tool","content": json.dumps({"name": fname, "ok": True, "result": result})})
                except Exception as ex:
                    messages.append({"role":"tool","content": json.dumps({"name": fname, "ok": False, "error": str(ex)})})

            # Ask model to continue after observations
            r = ollama.chat(
                model=MODEL,
                messages=messages + [{"role": "user", "content":"Proceed."}],
                tools=[web_search, lighting_scene, cad_generate],
                think=THINK,
                stream=False
            )
            continue

        # No tool calls → final content
        return msg.get("content", "").strip()

if __name__ == "__main__":
    print(chat_with_tools("Find 2 sources on PETG annealing; then propose a lighting.scene for bay-1 to film a demo."))
```

**Notes**
- The Ollama Python SDK can auto‑derive **tool schemas** from Python function signatures & docstrings and returns `message.tool_calls`.  
- For **streaming** tool calling, see: https://ollama.com/blog/streaming-tool  
- Keep **`message.thinking`** private; it may appear in chunks in streaming mode.

---

## 3) JSON‑contract fallback (portable)

If you prefer a model‑agnostic parser, force JSON mode and require the model to output either a `tool_call` or `final` object. (Useful when mixing models.)

**Contract**
```text
{"type":"tool_call","name":"<tool_name>","arguments":{...}}  OR  {"type":"final","content":"..."}
```

**Call**
```bash
curl http://localhost:11434/api/chat -d '{
  "model":"gpt-oss:120b",
  "messages":[
    {"role":"system","content":"Reply ONLY with JSON per the contract."},
    {"role":"user","content":"Set bench lights in bay-1 to film."}
  ],
  "format":"json",
  "think":"low",
  "stream": false
}'
```

**Validate** the JSON before executing a tool. If invalid, respond with a tool error and let the model self‑repair on the next turn.  
- JSON mode / schema: https://docs.ollama.com/capabilities/structured-outputs

---

## 4) KITTY integration steps

### 4.1 Environment (.env)

```
# Ollama local reasoner
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_THINK=medium        # low|medium|high
OLLAMA_TIMEOUT_S=120
LOCAL_REASONER_PROVIDER=ollama

# Optional: keep model warm for low-latency
OLLAMA_KEEP_ALIVE=30m
```

- Docker → host bridge (compose):
```yaml
services:
  brain:
    extra_hosts: ["host.docker.internal:host-gateway"]
  gateway:
    extra_hosts: ["host.docker.internal:host-gateway"]
```

### 4.2 Router hookup (Brain)

- **Pass `tools`** to `/api/chat` from your tool registry when the **Local** tier is selected.  
- Parse `message.tool_calls` and **dispatch** via your existing skill executors; append results as `role:"tool"` messages; continue until final.  
- **Safety gates:**
  - Require the exact confirmation phrase (e.g., `Confirm: proceed`) for hazardous actuations before dispatch.  
  - Enforce **budget per task** before calling any paid/cloud tools.  
- **Logging:** capture provider=`ollama`, model=`gpt-oss:120b`, `think`, latency, tool traces, and **never** expose `thinking` in user responses.

### 4.3 Tool registry mapping (examples)

| Tool name          | Backend → Endpoint                                  |
|--------------------|------------------------------------------------------|
| `web_search`       | MCP/Perplexity or gateway web-search proxy          |
| `lighting.scene`   | Gateway → Home Assistant (HTTP/MQTT)                |
| `cad.generate`     | Zoo (parametric) / Tripo (organic) / local fallback |
| `printer.start`    | Gateway → printer controller                         |
| `vision.inspect`   | Vision service (first-layer/QC)                      |

---

## 5) Mac Studio (M3 Ultra) — Performance & Stability Tuning

> Target: **low latency**, **stable long contexts**, **sustained throughput** for local agents.

### 5.1 Memory & model facts
- `gpt-oss:120b` in Ollama reports **~65 GB** model file (`MXFP4`) — plus KV cache for context. A **128 GB** unified memory Mac Studio is recommended for comfortable headroom.  
  - Model page shows size & format (MXFP4): https://ollama.com/library/gpt-oss%3A120b/blobs/90a618fe6ff2
  - Library entry: https://ollama.com/library/gpt-oss%3A120b

### 5.2 Enable Flash Attention + KV cache quantization
```bash
# Persist for the macOS app (see FAQ)
launchctl setenv OLLAMA_FLASH_ATTENTION 1
launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0   # or q4_0 for tighter memory, more quality loss
# restart Ollama app (menubar → quit; relaunch) or restart the service
```
- Flash Attention toggle: https://docs.ollama.com/faq  
- KV cache quantization values (`f16`, `q8_0`, `q4_0`): https://docs.ollama.com/faq

**Why:** FA reduces memory use & speeds long‑context attention; **q8_0** roughly halves KV memory with minimal quality impact; **q4_0** quarters memory with more loss. See background posts for trade‑offs.

### 5.3 Keep models in memory (preload & warm)
- **Preload** and **pin** the model to avoid cold starts:
```bash
# one-time warm, then keep alive
curl http://localhost:11434/api/chat -d '{"model":"gpt-oss:120b"}'
launchctl setenv OLLAMA_KEEP_ALIVE -1   # keep models resident (or use 30m/24h)
```
- Keep‑alive docs: https://docs.ollama.com/faq

### 5.4 Context length & generation options
- Use **`options.num_ctx`** to set the context (start at **8192**, raise gradually with FA+KV quantization).  
- Typical stable defaults for reasoning:
```json
{
  "num_ctx": 8192,
  "temperature": 0.3,
  "top_p": 0.9,
  "top_k": 40,
  "repeat_penalty": 1.1,
  "num_predict": 1024
}
```
- Options (overview): https://docs.ollama.com/modelfile (parameters) and API refs.

### 5.5 Concurrency & queueing
- Control concurrency with **`OLLAMA_NUM_PARALLEL`** (and queue size via **`OLLAMA_MAX_QUEUE`**). Start conservatively (e.g., 2–3) and measure.  
  - Parallelism behavior: https://github.com/ollama/ollama/issues/358  
  - Community notes on `OLLAMA_NUM_PARALLEL`: https://stackoverflow.com/questions/78188399/is-there-parallelism-inside-ollama
```bash
launchctl setenv OLLAMA_NUM_PARALLEL 3
```

### 5.6 Verify GPU usage & health
```bash
ollama ps            # shows PROCESSOR 100% GPU/CPU mix
ollama show gpt-oss:120b | sed -n '1,120p'
```
- GPU/CPU indicators: https://docs.ollama.com/faq

### 5.7 Observability
Capture: prompt tokens, `think` on/off, latency (end‑to‑end & tool hops), cache hits, and routing decisions. Graph P50/P95 across: chat-only, single tool, multi‑tool.

---

## 6) End‑to‑end test plan

1) **Tool call**: “Set bench lights in bay‑1 to film.” → expect `lighting.scene` tool call + ACK.  
2) **Multi‑step**: “Find 2 PETG annealing sources and summarize; then set bay‑1 to ‘film’.” → expect `web_search` then `final` with citations.  
3) **Hazard gate**: “Start welder” (no phrase) → expect refusal or `confirmation_required`; then with **Confirm: proceed** → dispatch.  
4) **Budget gate**: configure a mock tool with cost > budget → expect `budget_exceeded` pathway.  
5) **Long context**: feed 6–8K tokens, verify stability with FA+KV `q8_0`.  
6) **Throughput**: run 3 parallel short prompts and confirm responsiveness.

---

## 7) Troubleshooting quick hits

- **Model unloads between calls** → set `keep_alive` on requests or `OLLAMA_KEEP_ALIVE` globally.  
- **JSON parsing errors** (fallback mode) → echo validation error in a `tool` observation; model usually self‑repairs next turn.  
- **Slow long contexts** → ensure `OLLAMA_FLASH_ATTENTION=1`, consider `OLLAMA_KV_CACHE_TYPE=q8_0`, cap `num_ctx`.  
- **Tool not called** → add a one‑line hint in user message (“you may use tools”), or provide a small few‑shot.  
- **GPU not used** → verify `ollama ps` shows 100% GPU; update macOS & Ollama; restart after `launchctl setenv` changes.

---

## 8) References

- **GPT‑OSS 120B on Ollama**:  
  - Library & tags (tools/thinking): https://ollama.com/library/gpt-oss%3A120b  
  - Model blob (MXFP4 ~65GB): https://ollama.com/library/gpt-oss%3A120b/blobs/90a618fe6ff2

- **Ollama docs**:  
  - Chat API: https://docs.ollama.com/api/chat  
  - Thinking: https://docs.ollama.com/capabilities/thinking  
  - Tool calling: https://docs.ollama.com/capabilities/tool-calling  
  - Streaming (incl. tool calls & thinking fields): https://docs.ollama.com/capabilities/streaming  
  - Structured outputs (JSON mode): https://docs.ollama.com/capabilities/structured-outputs  
  - FAQ (keep_alive, context length, env vars, GPU check, Flash Attention, KV cache types): https://docs.ollama.com/faq

- **Articles/Notes**:  
  - Functions as tools (Python): https://ollama.com/blog/functions-as-tools  
  - Streaming tool calling: https://ollama.com/blog/streaming-tool  
  - Concurrency background: https://github.com/ollama/ollama/issues/358 , https://stackoverflow.com/questions/78188399/is-there-parallelism-inside-ollama