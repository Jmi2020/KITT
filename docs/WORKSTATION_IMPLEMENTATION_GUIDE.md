# Workstation Implementation Guide
## High-Impact Additions Deployment

This guide provides step-by-step instructions for deploying all 4 phases of High-Impact Additions to KITTY on your Mac Studio M3 Ultra workstation.

---

## Quick Reference

**What's Being Deployed:**
- Phase 1: CODER model support (Qwen2.5-Coder-32B)
- Phase 2: Memory enhancement (BGE embeddings + reranker)
- Phase 3: Diversity seat (Q4B optional second model family)
- Phase 4: F16 parallelism tuning (20-40% throughput boost)

**Prerequisites:**
- Mac Studio M3 Ultra with 192GB RAM
- Qwen2.5-Coder-32B already downloaded in `/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF`
- Docker Desktop installed and running
- Git repository cloned to `~/KITT`

**Estimated Time:** 30-60 minutes (including testing)

---

## Pre-Flight Checklist

Before starting, verify your environment:

```bash
# 1. Check current branch
cd ~/KITT
git status
# Should show: On branch claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL

# 2. Verify coder model exists
ls -lh /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/*.gguf
# Should show: qwen2.5-coder-32b-instruct-q8_0.gguf or similar

# 3. Stop existing services
./ops/scripts/stop-kitty.sh

# 4. Backup current .env (recommended)
cp .env .env.backup.$(date +%Y%m%d)
```

---

## Phase 1: CODER Model Support

### Step 1.1: Update .env Configuration

Add CODER model configuration to your `.env` file:

```bash
# Find the correct GGUF filename
CODER_MODEL_FILE=$(ls /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/*.gguf | head -n1 | xargs basename)

# Add to .env (append to end of file)
cat >> .env << EOF

# ============================================
# HIGH-IMPACT ADDITIONS (Phase 1: CODER)
# ============================================

# CODER Model (Qwen2.5-Coder-32B)
LLAMACPP_CODER_ALIAS=kitty-coder
LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/${CODER_MODEL_FILE}
LLAMACPP_CODER_TEMPERATURE=0.2
LLAMACPP_CODER_PORT=8085
LLAMACPP_CODER_CTX=32768
LLAMACPP_CODER_PARALLEL=4
LLAMACPP_CODER_BATCH_SIZE=4096
LLAMACPP_CODER_UBATCH_SIZE=1024
LLAMACPP_CODER_N_GPU_LAYERS=999
LLAMACPP_CODER_THREADS=24
LLAMACPP_CODER_FLASH_ATTN=1
EOF

echo "✓ Phase 1 configuration added to .env"
```

### Step 1.2: Verify Configuration

```bash
# Check that CODER settings are present
grep "LLAMACPP_CODER" .env

# Expected output:
# LLAMACPP_CODER_ALIAS=kitty-coder
# LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf
# ... (and other settings)
```

---

## Phase 2: Memory Enhancement

### Step 2.1: Update .env for Memory Service

The `.env.example` already has these settings. Verify they exist in your `.env`:

```bash
# Check for memory enhancement settings
grep -E "EMBEDDING_MODEL|RERANKER_MODEL" .env

# If not present, add them:
cat >> .env << 'EOF'

# ============================================
# HIGH-IMPACT ADDITIONS (Phase 2: Memory)
# ============================================

# Memory Enhancement (BGE embeddings + reranker)
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIM=384
RERANKER_MODEL=BAAI/bge-reranker-base
EOF

echo "✓ Phase 2 configuration added to .env"
```

### Step 2.2: Models Will Auto-Download

The `sentence-transformers` library will automatically download the BGE models on first run:
- `BAAI/bge-small-en-v1.5` (~130MB)
- `BAAI/bge-reranker-base` (~400MB)

No manual download required!

---

## Phase 3: Diversity Seat (Optional)

This phase is **optional**. The code gracefully falls back to Q4 if Q4B is not configured.

### Option A: Enable Q4B with Mistral-7B

```bash
# Check if Mistral-7B already downloaded
ls /Users/Shared/Coding/models/Mistral*/

# If not downloaded:
cd /Users/Shared/Coding/models
mkdir -p Mistral-7B-Instruct-GGUF
cd Mistral-7B-Instruct-GGUF
huggingface-cli download TheBloke/Mistral-7B-Instruct-v0.2-GGUF mistral-7b-instruct-v0.2.Q4_K_M.gguf

# Add to .env
cat >> .env << 'EOF'

# ============================================
# HIGH-IMPACT ADDITIONS (Phase 3: Diversity)
# ============================================

# Diversity Seat (Q4B - Mistral-7B)
LLAMACPP_Q4B_BASE=http://host.docker.internal:8084
LLAMACPP_Q4B_ALIAS=kitty-q4b
LLAMACPP_Q4B_MODEL=Mistral-7B-Instruct-GGUF/mistral-7b-instruct-v0.2.Q4_K_M.gguf
LLAMACPP_Q4B_PORT=8084
LLAMACPP_Q4B_CTX=8192
LLAMACPP_Q4B_PARALLEL=2
LLAMACPP_Q4B_N_GPU_LAYERS=999
LLAMACPP_Q4B_THREADS=16
LLAMACPP_Q4B_FLASH_ATTN=1
EOF

echo "✓ Phase 3 configuration added (Q4B enabled)"
```

### Option B: Skip Q4B (Use Q4 for All Specialists)

```bash
# No configuration needed - Q4B will fall back to Q4
echo "✓ Phase 3 skipped - using Q4 fallback"
```

---

## Phase 4: F16 Parallelism Tuning

Choose one of three tuning options based on your needs.

### Option 1: Moderate Tuning (+20-30%, Recommended)

```bash
# Update F16 settings in .env
# Find and replace existing LLAMACPP_F16_PARALLEL, BATCH_SIZE, UBATCH_SIZE

# Using sed (Mac-compatible):
sed -i.bak 's/^LLAMACPP_F16_PARALLEL=.*/LLAMACPP_F16_PARALLEL=6/' .env
sed -i.bak 's/^LLAMACPP_F16_BATCH_SIZE=.*/LLAMACPP_F16_BATCH_SIZE=8192/' .env
sed -i.bak 's/^LLAMACPP_F16_UBATCH_SIZE=.*/LLAMACPP_F16_UBATCH_SIZE=2048/' .env
sed -i.bak 's/^LLAMACPP_F16_THREADS=.*/LLAMACPP_F16_THREADS=24/' .env

echo "✓ Phase 4 configuration: Moderate tuning applied"
```

### Option 2: Maximum Tuning (+30-40%)

```bash
# For high concurrent workloads
sed -i.bak 's/^LLAMACPP_F16_PARALLEL=.*/LLAMACPP_F16_PARALLEL=8/' .env
sed -i.bak 's/^LLAMACPP_F16_BATCH_SIZE=.*/LLAMACPP_F16_BATCH_SIZE=12288/' .env
sed -i.bak 's/^LLAMACPP_F16_UBATCH_SIZE=.*/LLAMACPP_F16_UBATCH_SIZE=3072/' .env
sed -i.bak 's/^LLAMACPP_F16_THREADS=.*/LLAMACPP_F16_THREADS=24/' .env

echo "✓ Phase 4 configuration: Maximum tuning applied"
```

### Option 3: Skip F16 Tuning (Use Baseline)

```bash
# No changes needed - use existing configuration
echo "✓ Phase 4 skipped - using baseline F16 settings"
```

---

## Deploy and Test

### Step 1: Start Services

```bash
cd ~/KITT

# Start llama.cpp + all services
./ops/scripts/start-kitty.sh

# This will:
# 1. Start llama-server instances (Q4, F16, CODER, Q4B if configured)
# 2. Start Docker services (brain, mem0-mcp, gateway, etc.)
# 3. Wait for services to be healthy
```

**Expected startup time:**
- llama.cpp servers: ~30-60 seconds (model loading)
- Docker services: ~60-90 seconds (image build + startup)
- Total: ~2-3 minutes

### Step 2: Verify Services

```bash
# Check llama.cpp servers
curl -s http://localhost:8083/health | jq .  # Q4
curl -s http://localhost:8082/health | jq .  # F16
curl -s http://localhost:8085/health | jq .  # CODER (if configured)
curl -s http://localhost:8084/health | jq .  # Q4B (if configured)

# Check Docker services
docker ps | grep -E 'brain|mem0-mcp|gateway'

# Check service logs for errors
docker logs compose-brain-1 --tail 50
docker logs compose-mem0-mcp-1 --tail 50
```

### Step 3: Run Integration Tests

```bash
cd ~/KITT

# Test Phase 1: CODER
./tests/integration/test_coder_integration.sh

# Test Phase 2: Memory Enhancement
./tests/integration/test_memory_enhancement.sh

# Test Phase 3: Diversity Seat
./tests/integration/test_diversity_seat.sh

# Comprehensive smoke test (all phases)
./tests/integration/test_high_impact_additions_smoke.sh
```

**Expected output:**
```
High-Impact Additions - Comprehensive Smoke Test
=========================================
Testing all 4 phases:
  Phase 1: CODER Model Support
  Phase 2: Memory Enhancement (BGE + Reranker)
  Phase 3: Diversity Seat (Q4B)
  Phase 4: F16 Parallelism (Configuration Check)
=========================================

PHASE 1: CODER Model Support
----------------------------------------
Test 1.1: Gateway health check... PASS
Test 1.2: Code generation task via collective... PASS
Test 1.3: CODER model configuration... PASS

PHASE 2: Memory Enhancement (BGE + Reranker)
----------------------------------------
Test 2.1: mem0-mcp health check... PASS
Test 2.2: BGE embedding model check... PASS
  Model: BAAI/bge-small-en-v1.5
Test 2.3: Reranker status... PASS - Reranker enabled
  Model: BAAI/bge-reranker-base
Test 2.4: Semantic search test... PASS - Semantic search working

PHASE 3: Diversity Seat (Q4B)
----------------------------------------
Test 3.1: Council pattern (k=3) test... PASS
Test 3.2: Q4B diversity seat configuration... PASS - Q4B configured
Test 3.3: Extended council (k=5) diversity test... PASS

PHASE 4: F16 Parallelism Configuration
----------------------------------------
Test 4.1: F16 parallelism settings...
  PARALLEL: 6 (baseline: 4, optimal: 6-8)
  BATCH_SIZE: 8192 (baseline: 4096, optimal: 8192-12288)
  UBATCH_SIZE: 2048 (baseline: 1024, optimal: 2048-3072)
  ✓ F16 tuning applied
Test 4.2: F16 judge model test... PASS - F16 judge responding

=========================================
Test Summary
=========================================
Passed:   18
Failed:   0
Warnings: 0

✓ All critical tests passed!
```

---

## Performance Validation

### Baseline Measurement

Before tuning, measure baseline performance:

```bash
# Measure council k=3 (uses F16 judge)
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare PETG vs ABS for outdoor furniture","pattern":"council","k":3}' > /dev/null

# Record time: ____ seconds
```

### Post-Tuning Measurement

After applying F16 tuning, run same test:

```bash
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Compare PETG vs ABS for outdoor furniture","pattern":"council","k":3}' > /dev/null

# Record time: ____ seconds
# Calculate improvement: (baseline - new) / baseline * 100
```

**Expected improvements:**
- Option 1 (Moderate): 20-30% faster
- Option 2 (Maximum): 30-40% faster

### Concurrent Workload Test

Test parallel council execution:

```bash
# Terminal 1
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Task 1: Best print settings for PLA","pattern":"council","k":3}' &

# Terminal 2 (immediately after)
time curl -s -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Task 2: Troubleshoot first layer adhesion","pattern":"council","k":3}' &

# Wait for both
wait

# Baseline: Second request waits for first (sequential)
# Tuned: Both run in parallel (much faster total time)
```

---

## Monitoring and Observability

### RAM Usage

```bash
# Monitor llama-server RAM usage
top -pid $(pgrep llama-server)

# Expected RAM usage:
# - Baseline: ~160GB (Q4 + F16)
# - With CODER: ~180GB (Q4 + F16 + CODER)
# - With F16 tuning: +10-20GB
# - Total: ~190-200GB peak (within 192GB is tight!)
```

⚠️ **RAM WARNING**: If you enable all features (CODER + Q4B + F16 Maximum tuning), you may exceed 192GB. Monitor closely and scale back if needed.

### GPU Utilization (Metal)

```bash
# Monitor GPU usage on M3 Ultra
sudo powermetrics --samplers gpu_power -i 1000 | grep -A5 "GPU"

# Look for:
# - GPU busy %: Should be >80% during collective operations
# - GPU power: Should be 40-60W during inference
```

### Service Logs

```bash
# llama.cpp logs
tail -f .logs/llamacpp-q4.log
tail -f .logs/llamacpp-f16.log
tail -f .logs/llamacpp-coder.log

# Docker service logs
docker logs -f compose-brain-1
docker logs -f compose-mem0-mcp-1
```

### Prometheus Metrics

```bash
# Open Grafana
open http://localhost:3000

# Import dashboard: KITTY Collective Meta-Agent
# Metrics to watch:
# - collective_council_duration_seconds
# - collective_proposals_generated_total
# - llm_client_requests_total{model="kitty-coder"}
# - memory_search_duration_seconds
```

---

## Troubleshooting

### Issue 1: CODER model not loading

**Symptoms:**
- `llama-server` crashes on startup
- "Failed to load model" in logs

**Fix:**
```bash
# Check model file exists and is readable
ls -lh /Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/*.gguf

# Check .env path is correct
grep LLAMACPP_CODER_MODEL .env

# Verify Metal acceleration available
system_profiler SPDisplaysDataType | grep "Metal"
```

### Issue 2: mem0-mcp fails to start

**Symptoms:**
- "Failed to load reranker" in logs
- mem0-mcp container exits

**Fix:**
```bash
# Check mem0-mcp logs
docker logs compose-mem0-mcp-1

# If reranker fails to load, disable it temporarily:
sed -i.bak 's/^RERANKER_MODEL=.*/RERANKER_MODEL=/' .env

# Restart service
docker compose restart mem0-mcp
```

### Issue 3: OOM (Out of Memory)

**Symptoms:**
- `llama-server` crashes with "failed to allocate"
- System becomes unresponsive
- "Killed: 9" in logs

**Fix:**
```bash
# Reduce memory footprint - choose one:

# Option A: Disable CODER (saves ~20GB)
# Comment out LLAMACPP_CODER_BASE in .env

# Option B: Reduce F16 parallelism
sed -i.bak 's/^LLAMACPP_F16_PARALLEL=.*/LLAMACPP_F16_PARALLEL=4/' .env
sed -i.bak 's/^LLAMACPP_F16_BATCH_SIZE=.*/LLAMACPP_F16_BATCH_SIZE=4096/' .env

# Option C: Disable Q4B (saves ~4GB)
# Comment out LLAMACPP_Q4B_BASE in .env

# Restart services
./ops/scripts/stop-kitty.sh
./ops/scripts/start-kitty.sh
```

### Issue 4: Slow collective responses

**Symptoms:**
- Council k=3 takes >120 seconds
- Timeouts in tests

**Possible Causes:**
1. **F16 tuning too aggressive**: Reduce PARALLEL to 4-5
2. **CPU thermal throttling**: Check temperatures with `sudo powermetrics --samplers smc`
3. **Other processes competing**: Check `top` for memory-hungry processes

**Fix:**
```bash
# Revert to baseline F16 settings
sed -i.bak 's/^LLAMACPP_F16_PARALLEL=.*/LLAMACPP_F16_PARALLEL=4/' .env
./ops/scripts/stop-kitty.sh
./ops/scripts/start-kitty.sh
```

---

## Rollback Plan

If you encounter issues and need to revert:

### Full Rollback

```bash
cd ~/KITT

# Stop services
./ops/scripts/stop-kitty.sh

# Restore backup .env
cp .env.backup.$(date +%Y%m%d) .env

# Or manually remove High-Impact Additions sections from .env
nano .env
# Delete sections:
# - HIGH-IMPACT ADDITIONS (Phase 1: CODER)
# - HIGH-IMPACT ADDITIONS (Phase 2: Memory)
# - HIGH-IMPACT ADDITIONS (Phase 3: Diversity)
# - And revert F16 settings to baseline

# Restart with baseline configuration
./ops/scripts/start-kitty.sh
```

### Partial Rollback (One Phase at a Time)

```bash
# Rollback Phase 1 (CODER):
sed -i.bak '/LLAMACPP_CODER/d' .env

# Rollback Phase 2 (Memory):
sed -i.bak 's/^EMBEDDING_MODEL=.*/EMBEDDING_MODEL=sentence-transformers\/all-MiniLM-L6-v2/' .env
sed -i.bak 's/^RERANKER_MODEL=.*/RERANKER_MODEL=/' .env

# Rollback Phase 3 (Q4B):
sed -i.bak '/LLAMACPP_Q4B/d' .env

# Rollback Phase 4 (F16 tuning):
sed -i.bak 's/^LLAMACPP_F16_PARALLEL=.*/LLAMACPP_F16_PARALLEL=4/' .env
sed -i.bak 's/^LLAMACPP_F16_BATCH_SIZE=.*/LLAMACPP_F16_BATCH_SIZE=4096/' .env
sed -i.bak 's/^LLAMACPP_F16_UBATCH_SIZE=.*/LLAMACPP_F16_UBATCH_SIZE=1024/' .env

# Restart services
./ops/scripts/stop-kitty.sh
./ops/scripts/start-kitty.sh
```

---

## Success Criteria

Your deployment is successful when:

✅ All integration tests pass (18+ tests)
✅ No OOM errors in logs
✅ RAM usage stays <190GB peak
✅ Council k=3 completes in <90 seconds
✅ Code generation tasks produce valid Python syntax
✅ Memory search returns relevant results
✅ F16 tuning shows measurable throughput improvement

---

## Next Steps After Deployment

1. **Benchmark Performance**: Run performance tests and record metrics
2. **Update Documentation**: Document any workstation-specific quirks in CLAUDE.md
3. **Create Memories**: Add memories about this deployment to mem0-mcp
4. **Monitor for 24 Hours**: Watch for stability issues, OOM, or performance regressions
5. **Iterate on F16 Tuning**: If Option 1 works well, try Option 2 for more throughput

---

## Reference Links

- Implementation plan: `docs/HIGH_IMPACT_ADDITIONS_IMPLEMENTATION_PLAN.md`
- F16 tuning guide: `docs/F16_PARALLELISM_TUNING_GUIDE.md`
- Unit tests: `tests/unit/test_llm_client.py`
- Integration tests: `tests/integration/test_*_integration.sh`
- Smoke test: `tests/integration/test_high_impact_additions_smoke.sh`

---

## Support

If you encounter issues not covered in this guide:

1. Check service logs: `docker logs compose-<service>-1`
2. Review llama.cpp logs: `tail -f .logs/llamacpp-*.log`
3. Check system resources: `top`, `vm_stat`
4. Consult troubleshooting section above
5. Review git history: `git log --oneline` for recent changes

---

**Status**: Ready for deployment
**Last Updated**: 2025-11-12
**Branch**: `claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL`
