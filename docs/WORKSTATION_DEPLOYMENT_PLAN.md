# Workstation Deployment Plan - Quality-First LangGraph

**Target Environment**: Mac Studio M3 Ultra (192 GB RAM)
**Deployment Time**: ~30 minutes
**Goal**: Enable Quality-First mode with adaptive monitoring

---

## Pre-Deployment Checklist

**Verify Prerequisites**:
```bash
# 1. Check system resources
system_profiler SPHardwareDataType | grep "Memory:"
# Expected: 192 GB

# 2. Check Docker
docker --version
docker compose version

# 3. Check llama.cpp models
ls -lh /Users/Shared/Coding/models/
# Expected: Athene-V2-Agent-Q4_K_M.gguf, Llama-3.3-70B-Instruct-F16.gguf

# 4. Verify current git status
cd /Users/Shared/Coding/KITT
git status
git branch
```

**Expected State**:
- Branch: `claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL`
- Working tree clean
- All commits pulled

---

## Phase 1: Pull Latest Code (5 minutes)

### Step 1.1: Fetch and Pull

```bash
cd /Users/Shared/Coding/KITT

# Fetch latest
git fetch origin

# Check branch
git branch
# Should show: * claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL

# Pull latest commits
git pull origin claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL

# Verify latest commit
git log --oneline -5
# Should show: 4406053 feat(monitoring): Add Quality-First mode...
```

### Step 1.2: Verify New Files

```bash
# Check monitoring scripts exist
ls -l ops/scripts/monitor-inference.sh
ls -l ops/scripts/check-inference-active.sh

# Check documentation
ls -l docs/QUALITY_FIRST_MODE.md
ls -l .env.quality-first-example

# All should exist and be executable (scripts)
```

---

## Phase 2: Configure Quality-First Mode (10 minutes)

### Step 2.1: Backup Current .env

```bash
# Create timestamped backup
cp .env .env.backup.$(date +%Y%m%d-%H%M%S)

# Verify backup
ls -lh .env.backup.*
```

### Step 2.2: Apply Quality-First Settings

**Option A: Merge example config**:
```bash
# Review example first
cat .env.quality-first-example

# Add to existing .env (appends to end)
cat .env.quality-first-example >> .env

# IMPORTANT: Remove duplicate entries
# Edit .env and remove old BRAIN_USE_LANGGRAPH, BRAIN_LANGGRAPH_ROLLOUT_PERCENT
nano .env  # or vim/code
```

**Option B: Manual configuration** (recommended for control):
```bash
# Edit .env
nano .env

# Add/update these critical settings:
BRAIN_USE_LANGGRAPH=true
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100

# Extended timeouts
BRAIN_REQUEST_TIMEOUT=600
LLAMACPP_TIMEOUT=300
LLAMACPP_Q4_TIMEOUT=180
LLAMACPP_F16_TIMEOUT=600
TOOL_EXECUTION_TIMEOUT=300

# Deep reasoning
MAX_REASONING_STEPS=10
MAX_TOOL_RETRIES=5
ENABLE_TOOL_REFINEMENT=true

# Memory depth
MEMORY_INITIAL_LIMIT=5
MEMORY_DEEP_LIMIT=10
MEMORY_DEEP_THRESHOLD=0.50

# Save and exit (Ctrl+X, Y, Enter in nano)
```

### Step 2.3: Verify Configuration

```bash
# Check LangGraph settings
grep BRAIN_USE_LANGGRAPH .env
grep BRAIN_LANGGRAPH_ROLLOUT_PERCENT .env

# Should show:
# BRAIN_USE_LANGGRAPH=true
# BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100

# Check timeouts
grep TIMEOUT .env | grep -E "(BRAIN|LLAMACPP)"

# Should show values of 180-600 seconds
```

---

## Phase 3: Restart Services (10 minutes)

### Step 3.1: Stop All Services

```bash
# Use existing stop script
./ops/scripts/stop-kitty.sh

# Verify all stopped
docker compose ps
# Should show nothing running

ps aux | grep llama-server
# Should show no processes
```

### Step 3.2: Start llama.cpp Servers

```bash
# Start all llama.cpp servers (Q4, F16, Summary, Vision)
./ops/scripts/start-llamacpp-dual.sh

# Wait for models to load (~5 minutes)
# Monitor progress
tail -f .logs/llamacpp-q4.log
# Look for: "HTTP server listening"

# In another terminal:
tail -f .logs/llamacpp-f16.log
# Look for: "HTTP server listening"
```

### Step 3.3: Verify llama.cpp Health

```bash
# Wait for all servers to be ready
sleep 300  # 5 minutes for model loading

# Test Q4 server
curl http://localhost:8083/health
# Expected: {"status":"ok","model_loaded":true}

# Test F16 server
curl http://localhost:8082/health
# Expected: {"status":"ok","model_loaded":true}

# Test inference
curl http://localhost:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kitty-q4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }'
# Should return JSON with response
```

### Step 3.4: Start Docker Services

```bash
# Start all Docker services
docker compose up -d --build

# Wait for startup
sleep 30

# Check status
docker compose ps
# All services should be "Up"

# Check brain service logs
docker logs compose-brain-1 --tail 50 | grep -i langgraph

# Expected to see:
# "LangGraph routing enabled"
# "Rollout percentage: 100"
```

### Step 3.5: Verify Brain Health

```bash
# Check brain API
curl http://localhost:8000/health

# Check metrics endpoint
curl http://localhost:8000/metrics | grep brain_langgraph

# Should see metrics like:
# brain_langgraph_routing_total
# brain_langgraph_rollout_percent 100
```

---

## Phase 4: Initial Testing (5 minutes)

### Step 4.1: Simple Query Test

```bash
# Test simple query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is 2 + 2?",
    "userId": "test-user",
    "conversationId": "deployment-test-001"
  }'

# Should return response with answer "4"
# Check latency in response
```

### Step 4.2: Start Monitoring

```bash
# Terminal 1: Start inference monitoring
./ops/scripts/monitor-inference.sh 5

# Leave running to watch system activity
```

### Step 4.3: Complex Query Test

```bash
# Terminal 2: Test complex query
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain the thermodynamic principles of heat exchangers with detailed analysis",
    "userId": "test-user",
    "conversationId": "deployment-test-002"
  }'

# Watch Terminal 1 for:
# - "⚡ INFERENCE IN PROGRESS"
# - High CPU usage on F16 server
# - Active connections

# This query should trigger F16 escalation
# Latency: 2-5 minutes (Quality-First mode)
```

### Step 4.4: Verify Metrics in Grafana

```bash
# Open Grafana
open http://localhost:3000

# Login: admin / admin (or your password)

# Navigate to "LangGraph Routing Overview" dashboard

# Should see:
# - Routing rate > 0
# - Q4 usage or F16 escalation
# - Latency graphs showing data
# - Rollout percentage: 100%
```

---

## Phase 5: Monitoring Setup (Optional but Recommended)

### Step 5.1: Create Monitoring Session

```bash
# Install tmux if not already
brew install tmux

# Create monitoring session
tmux new-session -s kitty-monitor

# Split panes (Ctrl+B, then %)
# Pane 1: Inference monitoring
./ops/scripts/monitor-inference.sh 5

# Ctrl+B, then " (split horizontally)
# Pane 2: Brain logs
docker logs -f compose-brain-1

# Ctrl+B, then " (split again)
# Pane 3: Q4 logs
tail -f .logs/llamacpp-q4.log

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t kitty-monitor
```

### Step 5.2: Set Up Log Rotation (Optional)

```bash
# Create logrotate config
sudo tee /etc/logrotate.d/kitty-llama <<EOF
/Users/Shared/Coding/KITT/.logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $(whoami) staff
}
EOF
```

---

## Validation Checklist

After deployment, verify:

**✓ Services Running**:
- [ ] Q4 llama.cpp server (port 8083) - `curl http://localhost:8083/health`
- [ ] F16 llama.cpp server (port 8082) - `curl http://localhost:8082/health`
- [ ] Brain service - `docker logs compose-brain-1 | grep "Server started"`
- [ ] All Docker services - `docker compose ps | grep Up`

**✓ Configuration Applied**:
- [ ] `BRAIN_USE_LANGGRAPH=true` - `grep BRAIN_USE_LANGGRAPH .env`
- [ ] `ROLLOUT_PERCENT=100` - `grep ROLLOUT_PERCENT .env`
- [ ] Timeouts extended - `grep TIMEOUT .env | grep 600`

**✓ LangGraph Active**:
- [ ] Metrics endpoint shows LangGraph metrics - `curl localhost:8000/metrics | grep langgraph`
- [ ] Brain logs show "LangGraph routing enabled" - `docker logs compose-brain-1 | grep LangGraph`
- [ ] Test query returns response - Use curl test above

**✓ Monitoring Working**:
- [ ] `monitor-inference.sh` shows live data
- [ ] `check-inference-active.sh q4` returns 0 when inference running
- [ ] Grafana dashboards display metrics

---

## Troubleshooting

### Issue: llama.cpp servers not starting

**Check**:
```bash
# Look for errors in logs
cat .logs/llamacpp-q4.log | grep -i error
cat .logs/llamacpp-f16.log | grep -i error

# Check if ports already in use
lsof -i :8082
lsof -i :8083

# Check model files exist
ls -lh /Users/Shared/Coding/models/*.gguf
```

**Fix**:
```bash
# Kill stuck processes
pkill -f llama-server

# Restart
./ops/scripts/start-llamacpp-dual.sh
```

### Issue: Brain service errors

**Check**:
```bash
# Check full logs
docker logs compose-brain-1 --tail 200

# Check for import errors
docker logs compose-brain-1 | grep -i "importerror\|modulenotfound"

# Check environment variables
docker exec compose-brain-1 printenv | grep LANGGRAPH
```

**Fix**:
```bash
# Rebuild brain service
docker compose build brain
docker compose up -d brain
```

### Issue: No metrics in Grafana

**Check**:
```bash
# Prometheus scraping brain?
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="brain")'

# Brain exposing metrics?
curl http://localhost:8000/metrics | head -20

# Grafana data source configured?
# Open http://localhost:3000 → Configuration → Data Sources
```

**Fix**:
```bash
# Restart Prometheus
docker compose restart prometheus

# Re-import dashboards if needed
# Dashboards → Import → Upload JSON files from infra/grafana/dashboards/
```

---

## Rollback Procedure

If Quality-First mode causes issues:

### Quick Rollback (Disable LangGraph)

```bash
# Edit .env
nano .env

# Set:
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0  # Route 0% traffic to LangGraph

# Or disable completely:
BRAIN_USE_LANGGRAPH=false

# Restart brain
docker compose restart brain

# Verify traditional router active
docker logs compose-brain-1 | grep "LangGraph"
# Should show: "LangGraph routing disabled" or "rollout: 0%"
```

### Full Rollback (Restore .env)

```bash
# Restore from backup
cp .env.backup.20251112-143000 .env  # Use your backup timestamp

# Restart all
./ops/scripts/stop-kitty.sh
./ops/scripts/start-llamacpp-dual.sh
sleep 300  # Wait for models
docker compose up -d
```

---

## Next Steps After Deployment

1. **Run Full Test Suite**:
   ```bash
   ./tests/langgraph_system_test.sh
   # Results in: test-results/langgraph-YYYYMMDD-HHMMSS/
   ```

2. **Monitor for 24 Hours**:
   - Keep `monitor-inference.sh` running
   - Review Grafana dashboards periodically
   - Check for any errors in logs

3. **Adjust Timeouts if Needed**:
   - If queries still timeout, increase further
   - If queries complete too quickly, reduce for efficiency
   - Monitor actual inference times to calibrate

4. **Test Long-Running Workflows**:
   ```bash
   # Deep research query
   kitty-cli say "Comprehensive analysis of HVAC heat exchanger efficiency..."

   # CAD iteration
   kitty-cli say "Design phone stand, iterate until printability > 95%"

   # Multi-tool workflow
   kitty-cli say "Research → Design → Analyze → Queue to printer"
   ```

5. **Review Quality Metrics**:
   - Check self-evaluation scores (target: > 0.9)
   - Check confidence distributions
   - Verify F16 escalation rate (target: 20-30% of queries)

---

## Success Criteria

**Deployment Successful If**:
- ✅ All 4 llama.cpp servers healthy
- ✅ Brain service starts with LangGraph enabled
- ✅ Test queries return responses (no timeouts)
- ✅ Monitoring shows inference activity
- ✅ Grafana dashboards display data
- ✅ Quality-First timeouts applied (600s)

**Ready for Production Use If**:
- ✅ Test suite passes (no failures)
- ✅ Long-running queries complete successfully
- ✅ No critical errors in 24-hour monitoring period
- ✅ Self-evaluation scores > 0.85
- ✅ Tool success rate > 90%

---

**Document Version**: 1.0
**Created**: 2025-11-12
**Target**: Mac Studio M3 Ultra with Quality-First LangGraph configuration
**Estimated Time**: 30 minutes deployment + 24 hours validation
