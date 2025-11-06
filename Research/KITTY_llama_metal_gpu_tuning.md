# KITTY + llama.cpp (Metal) — GPU Utilization Tuning on Apple Silicon
**Version:** 1.0 • **Target host:** Mac Studio (Apple Silicon) • **Scope:** Raise *effective* GPU usage and tokens/sec for locally hosted models used by **KITTY**.

> **Why this doc?** On Apple Silicon with llama.cpp (Metal), it’s normal to see **CPU ~100%** and **GPU ~40–60%** during *single-stream decode*. Prefill (prompt ingest) can saturate the GPU; **decode is token‑by‑token** and hard to keep at 100%. This guide shows how to **increase average GPU use** and **reduce wall‑time** with build flags, runtime knobs, and concurrency.

---

## 0) TL;DR (apply these first)
1. **Build with Metal + Flash‑Attention** enabled.
2. Run with **all layers offloaded**: `-ngl 999` (or `--gpu-layers 999`).
3. Use **large prefill batch** and **micro‑batch**: e.g. `-b 4096 --ubatch 1024`.
4. Serve via **llama‑server** and handle **parallel streams**: `--parallel 4..8`.
5. (Optional) Enable **speculative decoding** with a small draft model for single prompts.
6. Set threads near **P‑core count**, not total cores: e.g. `-t 16–20` on M3 Ultra.

---

## 1) Understand what you’re seeing
- **Prefill (prompt ingest):** big matrix ops → **high GPU %** possible.
- **Decode (generation):** 1 token/step per stream → GPU often **under‑utilized**; CPU handles tokenization, sampling, scheduler & some residual ops → **CPU pegged**.
- **Key lever:** Give the GPU **more work per unit time** (bigger batches, more concurrent sequences, speculative decoding).

---

## 2) Build llama.cpp correctly (Metal)
> You can use either Make or CMake. Ensure **Metal backend** is compiled in.

### Makefile route
```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
make -j metal          # builds with Metal support
```

### CMake route
```bash
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
cmake -S . -B build -DGGML_METAL=ON -DGGML_METAL_EMBED_LIBRARY=ON
cmake --build build -j
```

**Verify on startup** you see Metal initialization lines (e.g., `ggml_metal_init …`). If you don’t, you’re not using the Metal build.

---

## 3) Sanity check: are layers actually offloaded?
Run with **all layers offloaded** and check logs:
```bash
./llama-cli \
  -m models/your-model.gguf \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  -t 20 --timings \
  -p "Say hello in one sentence."
```
- `-ngl 999` (or `--gpu-layers 999`) asks llama.cpp to offload as many layers as possible.
- `--flash-attn` enables fused attention kernels (Metal‑optimized builds only).
- `-b` is the **batch size** (prefill). `--ubatch` is the **micro‑batch** for kernel tiling.
- `--timings` prints prompt/decode timings to confirm improvements.

> If you see limited offload, reduce context (`-c`) or batch (`-b`/`--ubatch`) to fit memory so layers don’t spill back to CPU.

---

## 4) Runtime knobs that move the needle

### 4.1 Offload & kernels
- **All layers to GPU:** `-ngl 999`
- **Flash‑Attention:** `--flash-attn` (verify your build supports it)
- **KV/cache choices:** use the default fast KV unless you have a specific reason to change; higher‑precision KV increases memory traffic.

### 4.2 Batch sizing
- **Prefill batch (`-b`)**: larger values **feed the GPU** during prompt ingest. Start **2048 → 4096**, raise if memory allows.
- **Micro-batch (`--ubatch`)**: tune **512 → 2048**. Too small = poor GPU occupancy; too large = OOM / throttling.

### 4.3 Threads (CPU side)
- **Set near P‑core count** (performance cores), not total cores: e.g., `-t 16–20` on M3 Ultra.
- If supported, separate prefill vs decode threads (e.g., `--threads-batch` for prefill).

### 4.4 Concurrency (best lever during decode)
- Use **llama‑server** to serve multiple streams; decode becomes interleaved and keeps the GPU busier:
```bash
./llama-server \
  -m models/your-model.gguf \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  --parallel 6 \
  -t 20 --api
```
  - `--parallel N` controls how many **concurrent sequences** are processed. Increase until tokens/sec or GPU % no longer improves (watch memory).

### 4.5 Speculative decoding (single‑prompt speedup)
Use a small **draft model** to propose tokens; the big model verifies them:
```bash
./llama-cli \
  -m models/large.gguf \
  --draft models/small.gguf --speculative 5 \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  -t 20 -n 256
```
This increases effective throughput and often raises GPU activity without needing multiple users.

---

## 5) Quick‑start recipes

### A) Single interactive generation (max GPU effort)
```bash
./llama-cli \
  -m models/qwen2.5-72b.Q4_K_M.gguf \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  -t 20 --timings \
  -n 256 -p "Explain how KITTY routes CAD jobs."
```

### B) API server for KITTY (higher GPU via concurrency)
```bash
./llama-server \
  -m models/qwen2.5-72b.Q4_K_M.gguf \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  --parallel 6 -t 20 --api --host 127.0.0.1 --port 11434
```
- Point **Open WebUI / KITTY** at `http://127.0.0.1:11434` (OpenAI‑style or llama.cpp API).
- Raise `--parallel` if GPU has headroom; drop if you see context‑cache OOM or swapping.

### C) Speculative decode (single‑user speed)
```bash
./llama-cli \
  -m models/llama-70b.Q4_K_M.gguf \
  --draft models/llama-8b.Q4_K_M.gguf --speculative 6 \
  -ngl 999 --flash-attn \
  -c 8192 -b 4096 --ubatch 1024 \
  -t 20 -n 256 --timings
```

> **Note:** Binary names may differ by revision (`./main` vs `./llama-cli`). Substitute accordingly.

---

## 6) Measuring success
Use the built‑in timings and your system monitors:
- **`--timings`**: compare **prompt eval ms/token** and **decode ms/token** before/after.
- **mactop/Activity Monitor**: look for **higher average GPU %** and **lower wall‑time**.
- **Tokens/sec**: steady increase with `--parallel` up to a saturation point is expected.

---

## 7) Memory & stability on M‑series
- More context (`-c`) and larger batches (`-b`, `--ubatch`) **consume unified memory** quickly.
- If you see regressions or fallback to CPU, **lower `-c` or `--ubatch`** first.
- Keep an eye on **thermals**; sustained high GPU load can throttle if airflow is poor.

---

## 8) Troubleshooting
**GPU stays low / CPU pegged**
- Not a Metal build → rebuild with Metal/CMake flags.
- Forgot `-ngl` → add `-ngl 999`.
- Micro-batch too small → raise `--ubatch`.
- Single stream only → use `llama-server --parallel N` or speculative decoding.

**OOM / crashes**
- Reduce `-c`, `-b`, or `--ubatch`.
- Use a smaller quant (Q4_K_M → Q5_K_M/Q6_K for quality vs memory trade).
- Confirm no other GPU‑heavy tasks are running.

**Throughput stalls at high `--parallel`**
- You’re saturating memory bandwidth or KV cache. Dial `--parallel` back down; consider a slightly smaller context window.

---

## 9) Integration tips for KITTY
- Run **llama‑server** as a managed service and let KITTY send requests concurrently to lift GPU utilization.
- For chat‑style UIs (Open WebUI), set the base URL to the local server; keep your **local model as primary** and escalate to cloud only when confidence is low.
- Log **tokens/sec, route, and timings** per request to visualize impact of `--parallel` and batching.

---

## 10) Appendix — Flag glossary (common)
- `-ngl N` / `--gpu-layers N`: number of layers to offload; `999` = as many as possible.
- `--flash-attn`: enable flash‑attention kernels for Metal build.
- `-c N`: context window (tokens).
- `-b N`: prefill batch size.
- `--ubatch N`: micro‑batch size for kernels.
- `-t N`: CPU threads (set near P‑core count).
- `--parallel N`: number of concurrent sequences in `llama-server`.
- `--draft MODEL --speculative K`: speculative decoding with draft model.
- `--timings`: print latency metrics after run.

---

### Example “known‑good” settings for Mac Studio (M3 Ultra, 256 GB RAM)
- **Large models (60–70B, Q4_K_M)**
  `-ngl 999 --flash-attn -c 8192 -b 4096 --ubatch 1024 -t 20`
  Server: add `--parallel 6` (increase if stable).

- **Medium models (7–13B, Q4_K_M)**
  `-ngl 999 --flash-attn -c 8192 -b 4096 --ubatch 2048 -t 16`
  Server: `--parallel 8–12` (memory permitting).

> Always validate with `--timings` and real workloads; tune upward until you hit either OOM or diminishing returns.

---

**Maintainer notes:** Keep this document with your KITTY infra repo. If llama.cpp flags evolve, update the examples accordingly.
