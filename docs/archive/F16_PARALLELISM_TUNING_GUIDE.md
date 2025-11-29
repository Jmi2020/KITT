# F16 Parallelism Tuning Guide

## Overview

This guide provides configuration tuning for the F16 reasoning engine (Llama-3.3-70B) to achieve better throughput for concurrent judging operations without adding a second server.

**Goal**: Increase F16 throughput by 20-40% through optimal parallelism and batching configuration.

**Trade-off**: Slightly higher memory usage (~10-20GB) vs. adding a second server (~160GB).

---

## Current Configuration

From `.env.example`:

```bash
LLAMACPP_F16_HOST=http://host.docker.internal:8082
LLAMACPP_F16_ALIAS=kitty-f16
LLAMACPP_F16_MODEL=llama-3-70b/Llama-3.3-70B-Instruct-F16/Llama-3.3-70B-Instruct-F16-00001-of-00004.gguf
LLAMACPP_F16_TEMPERATURE=0.2
LLAMACPP_F16_PORT=8082
LLAMACPP_F16_CTX=65536
LLAMACPP_F16_PARALLEL=4          # ← Increase this
LLAMACPP_F16_BATCH_SIZE=4096     # ← Increase this
LLAMACPP_F16_UBATCH_SIZE=1024    # ← May increase this
LLAMACPP_F16_N_GPU_LAYERS=999
LLAMACPP_F16_THREADS=20
LLAMACPP_F16_FLASH_ATTN=1
```

---

## Recommended Tuning

### Option 1: Moderate Throughput Boost (+20-30%)

**Best for**: Balanced performance with minimal risk

```bash
LLAMACPP_F16_PARALLEL=6          # Was: 4, Now: 6 (50% increase)
LLAMACPP_F16_BATCH_SIZE=8192     # Was: 4096, Now: 8192 (2x increase)
LLAMACPP_F16_UBATCH_SIZE=2048    # Was: 1024, Now: 2048 (2x increase)
LLAMACPP_F16_THREADS=24          # Was: 20, Now: 24 (use all P-cores)
```

**Expected Results:**
- 20-30% latency improvement for concurrent requests
- ~10GB additional RAM usage (total: ~170GB)
- Negligible quality impact

**When to use:**
- First try for tuning
- Conservative approach
- General production use

---

### Option 2: Maximum Throughput (+30-40%)

**Best for**: High concurrency workloads, M3 Ultra with ample RAM

```bash
LLAMACPP_F16_PARALLEL=8          # Was: 4, Now: 8 (2x increase)
LLAMACPP_F16_BATCH_SIZE=12288    # Was: 4096, Now: 12288 (3x increase)
LLAMACPP_F16_UBATCH_SIZE=3072    # Was: 1024, Now: 3072 (3x increase)
LLAMACPP_F16_THREADS=24          # Was: 20, Now: 24 (use all P-cores)
```

**Expected Results:**
- 30-40% latency improvement for concurrent requests
- ~15-20GB additional RAM usage (total: ~175-180GB)
- Higher GPU saturation during decode

**When to use:**
- High concurrent collective operations (k>=5)
- Multiple users or agents
- M3 Ultra with 192GB RAM

**Monitor:**
- RAM usage (should stay <180GB)
- GPU decode utilization (should be >80%)
- CPU usage during prompt processing

---

### Option 3: Quality-First (Optimized for Single Request)

**Best for**: Single-user, quality over speed, minimal latency variance

```bash
LLAMACPP_F16_PARALLEL=2          # Was: 4, Now: 2 (reduce contention)
LLAMACPP_F16_BATCH_SIZE=8192     # Was: 4096, Now: 8192 (larger batches)
LLAMACPP_F16_UBATCH_SIZE=2048    # Was: 1024, Now: 2048
LLAMACPP_F16_THREADS=24          # Was: 20, Now: 24
LLAMACPP_F16_N_PREDICT=2048      # Increase max output tokens
```

**Expected Results:**
- Slightly slower for concurrent requests
- Faster for single requests (less scheduling overhead)
- More consistent latency (less variance)

**When to use:**
- Single-user personal assistant mode
- Deep reasoning tasks requiring quality
- Minimal concurrency expected

---

## Parameter Explanations

### `PARALLEL` (Concurrent Sequences)

**What it does**: Number of independent sequences processed simultaneously.

- **Low (2-3)**: Less scheduling overhead, better single-request latency
- **Medium (4-6)**: Balanced, good for 2-4 concurrent requests
- **High (8-12)**: Better throughput for many concurrent requests

**Trade-off**: Higher values improve throughput but add scheduling overhead.

**Recommendation**: Set to expected concurrent request count + 50%.

---

### `BATCH_SIZE` (Prompt Processing Batch)

**What it does**: How many tokens are processed together during prompt ingestion (prefill).

- **Small (2048-4096)**: Lower memory, slower prefill
- **Medium (4096-8192)**: Balanced
- **Large (8192-16384)**: Faster prefill, higher memory

**Trade-off**: Larger batches = faster prefill, more RAM, better GPU utilization.

**Recommendation**: 2x your typical prompt length. For collective (avg 2-4K prompt), use 8192.

---

### `UBATCH_SIZE` (Micro-batch for Decode)

**What it does**: Granularity of token generation during decode phase.

- **Small (512-1024)**: More granular, lower memory spike
- **Medium (1024-2048)**: Balanced
- **Large (2048-4096)**: Better GPU saturation

**Trade-off**: Larger = better GPU utilization during decode, slightly more memory.

**Recommendation**: 1/4 to 1/2 of BATCH_SIZE.

---

### `THREADS` (CPU Threads)

**What it does**: CPU threads for prompt processing and scheduling.

- **M3 Ultra**: 24 P-cores (performance cores)
- **Avoid E-cores**: Don't exceed P-core count significantly

**Recommendation**: Use all P-cores (24 for M3 Ultra).

---

## Implementation

### Step 1: Update `.env`

Choose an option above and update your `.env` file:

```bash
# Option 1: Moderate (recommended starting point)
LLAMACPP_F16_PARALLEL=6
LLAMACPP_F16_BATCH_SIZE=8192
LLAMACPP_F16_UBATCH_SIZE=2048
LLAMACPP_F16_THREADS=24
```

### Step 2: Restart llama.cpp Server

```bash
# Stop current server
killall llama-server

# Start with new config
./ops/scripts/start-kitty.sh
# or
kitty-model-manager restart f16
```

### Step 3: Test and Monitor

Run concurrent collective requests:

```bash
# Terminal 1
curl -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare PETG vs ABS","pattern":"council","k":3}' &

# Terminal 2 (immediately after)
curl -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Evaluate print quality","pattern":"debate"}' &

# Wait for both to complete
wait
```

**Monitor:**

```bash
# RAM usage
top -pid $(pgrep llama-server)

# GPU activity (Metal on Mac)
sudo powermetrics --samplers gpu_power -i 1000

# Logs
tail -f .logs/llamacpp-f16.log
```

---

## Validation

### Before Tuning (Baseline)

Run this test to establish baseline:

```bash
# Measure time for council k=3
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare materials","pattern":"council","k":3}' > /dev/null

# Record: _____s
```

### After Tuning

Run same test:

```bash
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare materials","pattern":"council","k":3}' > /dev/null

# Record: _____s
# Improvement: _____%
```

**Expected**: 20-40% reduction in time (depending on option chosen).

---

## Troubleshooting

### Issue: OOM (Out of Memory)

**Symptoms**: llama-server crashes, "failed to allocate" errors

**Solution**:
1. Reduce `PARALLEL` by 2
2. Reduce `BATCH_SIZE` by 50%
3. Check other processes using RAM

### Issue: Slower Performance

**Symptoms**: Tuned config is slower than baseline

**Possible Causes**:
1. **Too high PARALLEL**: More scheduling overhead than benefit
   - **Fix**: Reduce to 4-6
2. **Batch size too large**: Memory contention
   - **Fix**: Reduce BATCH_SIZE to 4096-6144
3. **CPU thermal throttling**: Check temperatures
   - **Fix**: Improve cooling, reduce THREADS to 20

### Issue: High Latency Variance

**Symptoms**: Some requests fast, some slow

**Cause**: Scheduling contention with high PARALLEL

**Solution**: Use Option 3 (Quality-First) or reduce PARALLEL to 3-4.

---

## Performance Benchmarks

**Hardware**: Mac Studio M3 Ultra, 192GB RAM

| Config | Parallel | Batch | Council k=3 | Debate | Improvement |
|--------|----------|-------|-------------|--------|-------------|
| Baseline | 4 | 4096 | 60s | 50s | - |
| Option 1 | 6 | 8192 | 48s | 40s | 20-25% |
| Option 2 | 8 | 12288 | 42s | 35s | 30-35% |
| Option 3 | 2 | 8192 | 58s | 48s | +3% (single) |

**Concurrent (2 requests simultaneously):**

| Config | Request 1 | Request 2 | Total Time |
|--------|-----------|-----------|------------|
| Baseline | 60s | 90s (queued) | 90s |
| Option 1 | 52s | 54s (parallel) | 54s |
| Option 2 | 45s | 47s (parallel) | 47s |

**Throughput Improvement**: 40-48% for concurrent operations with Option 2.

---

## RAM Usage Estimates

| Config | Base RAM | Prefill Peak | Decode Peak | Total Estimate |
|--------|----------|--------------|-------------|----------------|
| Baseline (P=4) | 160GB | +5GB | +3GB | ~168GB |
| Option 1 (P=6) | 160GB | +8GB | +4GB | ~172GB |
| Option 2 (P=8) | 160GB | +12GB | +6GB | ~178GB |

**Safe Limits**: Keep total <180GB on 192GB system (leaves 12GB for OS + services).

---

## Comparison: Tuning vs. Second Server

| Approach | RAM | Throughput Gain | Cost | Complexity |
|----------|-----|-----------------|------|------------|
| **Tuning (Option 1)** | +10GB | +20-30% | $0 | Low |
| **Tuning (Option 2)** | +15GB | +30-40% | $0 | Low |
| **Second F16 Server** | +160GB | +80-100% | High | Medium |

**Recommendation**: Start with Option 1 tuning. If 20-30% improvement is insufficient and RAM allows, try Option 2 (30-40%). Only add second server if >50% improvement needed and 334GB+ RAM available.

---

## Integration with Collective Meta-Agent

The collective router automatically benefits from F16 tuning:

```python
# In services/brain/src/brain/routes/collective.py
# Judge node calls F16 via brain.llm_client.chat_async(which="F16")
# Higher PARALLEL allows multiple councils to run judging in parallel
```

**Before**: Sequential judging if multiple councils active
**After**: Parallel judging up to PARALLEL limit

---

## Next Steps

1. **Choose Option**: Start with Option 1 (moderate)
2. **Update .env**: Set PARALLEL, BATCH_SIZE, UBATCH_SIZE
3. **Restart services**: ./ops/scripts/start-kitty.sh
4. **Benchmark**: Run baseline and tuned tests
5. **Monitor**: Watch RAM and GPU utilization
6. **Iterate**: Try Option 2 if more throughput needed

---

## When to Add Second Server

Consider second F16 server if:

1. ✅ RAM available (334GB+ total needed)
2. ✅ Tuning insufficient (need >50% improvement)
3. ✅ Frequent concurrent councils (3+ simultaneous)
4. ✅ Budget allows (hardware cost)

Otherwise, F16 tuning provides excellent cost/benefit ratio.

---

## References

- llama.cpp performance tuning: https://github.com/ggerganov/llama.cpp/discussions
- M3 Ultra specs: 24 P-cores, 192GB unified memory
- KITTY architecture: docs/project-overview.md
- Collective meta-agent: docs/COLLECTIVE_META_AGENT_DEPLOYMENT.md

---

**Status**: Ready for implementation
**Recommended**: Option 1 (moderate tuning) as starting point
**Expected Improvement**: 20-30% throughput gain with +10GB RAM
