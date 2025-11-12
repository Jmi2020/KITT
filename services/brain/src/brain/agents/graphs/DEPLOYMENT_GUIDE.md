# LangGraph Deployment & Testing Guide

## Overview

This guide provides step-by-step instructions for deploying and testing the LangGraph-enhanced routing system in KITTY Brain. Follow these procedures in order to ensure a successful rollout.

**Total Time**: ~3 hours for full deployment and initial testing
**Prerequisites**: Mac Studio M3 Ultra with 192 GB RAM, Docker, llama.cpp servers

---

## Phase 1: Environment Setup (30 minutes)

### Step 1.1: Configure Environment Variables

```bash
# Navigate to KITT repository
cd /home/user/KITT

# Backup existing .env
cp .env .env.backup.$(date +%Y%m%d)

# Add LangGraph configuration to .env
cat >> .env <<'EOF'

# ==================================================
# LangGraph Enhanced Routing Configuration
# ==================================================

# Feature Flags
BRAIN_USE_LANGGRAPH=false                    # Start disabled for safety
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0            # Gradual rollout 0-100%

# Multi-Server llama.cpp Configuration
LLAMACPP_Q4_HOST=http://localhost:8083       # Fast Q4 server
LLAMACPP_Q4_ALIAS=kitty-q4
LLAMACPP_F16_HOST=http://localhost:8082      # Precision F16 server
LLAMACPP_F16_ALIAS=kitty-f16

# Optional: Override existing model aliases if needed
# LOCAL_MODEL_PRIMARY=kitty-q4
# LOCAL_MODEL_CODER=kitty-f16
EOF

# Verify configuration
grep "BRAIN_USE_LANGGRAPH" .env
grep "LLAMACPP_Q4_HOST" .env
grep "LLAMACPP_F16_HOST" .env
```

**Expected Output**:
```
BRAIN_USE_LANGGRAPH=false
LLAMACPP_Q4_HOST=http://localhost:8083
LLAMACPP_F16_HOST=http://localhost:8082
```

### Step 1.2: Start llama.cpp Servers

**Q4 Server (Port 8083) - Fast Routing**:
```bash
# Start Q4 server for fast routing
llama-server \
  --model /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 \
  --port 8083 \
  --n-gpu-layers 999 \
  --ctx-size 8192 \
  --n-parallel 4 \
  --batch-size 512 \
  --threads 8 \
  --alias kitty-q4 \
  > .logs/llamacpp-q4.log 2>&1 &

echo "Q4 server PID: $!"
```

**F16 Server (Port 8082) - Deep Reasoning**:
```bash
# Start F16 server for deep reasoning
llama-server \
  --model /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-f16.gguf \
  --host 0.0.0.0 \
  --port 8082 \
  --n-gpu-layers 999 \
  --ctx-size 8192 \
  --n-parallel 2 \
  --batch-size 512 \
  --threads 12 \
  --alias kitty-f16 \
  > .logs/llamacpp-f16.log 2>&1 &

echo "F16 server PID: $!"
```

**Wait for Model Loading** (~5 minutes):
```bash
# Monitor Q4 server logs
tail -f .logs/llamacpp-q4.log
# Look for: "HTTP server listening" and "model loaded = true"

# Monitor F16 server logs (in separate terminal)
tail -f .logs/llamacpp-f16.log
# Look for: "HTTP server listening" and "model loaded = true"
```

**Verify Server Health**:
```bash
# Test Q4 server
curl http://localhost:8083/health | jq '.'
# Expected: {"status": "ok", "model_loaded": true}

# Test F16 server
curl http://localhost:8082/health | jq '.'
# Expected: {"status": "ok", "model_loaded": true}

# Test Q4 inference
curl http://localhost:8083/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kitty-q4",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }' | jq '.choices[0].message.content'

# Test F16 inference
curl http://localhost:8082/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "kitty-f16",
    "messages": [{"role": "user", "content": "Hello"}],
    "max_tokens": 10
  }' | jq '.choices[0].message.content'
```

### Step 1.3: Start Docker Compose Services

```bash
# Start all services
docker compose up -d --build

# Wait for services to start (~2 minutes)
docker compose ps

# Check brain service logs
docker logs brain --tail 50

# Expected in logs:
# - "LangGraph integration disabled" (BRAIN_USE_LANGGRAPH=false)
# - "BrainRouter initialized"
# - "Server started on port 8000"
```

### Step 1.4: Verify Prometheus Metrics Endpoint

```bash
# Check if brain service exposes metrics
curl http://localhost:8000/metrics | grep brain_

# Expected metrics (should see 0 counts since LangGraph is disabled):
# brain_langgraph_routing_total 0
# brain_tier_routing_total{tier="local"} 0
# brain_graph_execution_total 0
```

**✅ Checkpoint**: Both llama.cpp servers running, Docker services up, metrics endpoint accessible

---

## Phase 2: Grafana Dashboard Import (15 minutes)

### Step 2.1: Access Grafana

```bash
# Open Grafana in browser
open http://localhost:3000

# Default credentials (if not changed):
# Username: admin
# Password: admin (or check .env for GRAFANA_ADMIN_PASSWORD)
```

### Step 2.2: Configure Prometheus Data Source

1. Navigate to **Configuration → Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. Configure:
   - **Name**: `Prometheus` (or keep default)
   - **URL**: `http://prometheus:9090` (Docker internal) or `http://localhost:9090` (external)
   - **Access**: `Server` (default)
5. Click **Save & Test**
6. Expected: "Data source is working"

### Step 2.3: Import LangGraph Dashboards

**Dashboard 1: Routing Overview**
1. Navigate to **Dashboards → Import**
2. Click **Upload JSON file**
3. Select: `infra/grafana/dashboards/langgraph-routing-overview.json`
4. Configure:
   - **Name**: `LangGraph Routing Overview`
   - **Folder**: `KITTY Brain` (create if needed)
   - **UID**: `langgraph-routing-overview` (auto-filled)
   - **Prometheus**: Select configured data source
5. Click **Import**

**Dashboard 2: Quality Metrics**
1. Repeat import process for: `langgraph-quality-metrics.json`
2. Name: `LangGraph Quality Metrics`

**Dashboard 3: Tool Performance**
1. Repeat import process for: `langgraph-tool-performance.json`
2. Name: `LangGraph Tool Performance`

**Dashboard 4: Memory Performance**
1. Repeat import process for: `langgraph-memory-performance.json`
2. Name: `LangGraph Memory Performance`

### Step 2.4: Validate Dashboard Panels

**Open each dashboard and verify**:
- All panels display correctly (no errors)
- Time range: Last 1 hour
- Refresh interval: 10 seconds
- All metrics show "No data" (expected, LangGraph is disabled)

**✅ Checkpoint**: 4 Grafana dashboards imported and displaying correctly

---

## Phase 3: Prometheus Alerting Setup (15 minutes)

### Step 3.1: Add Alert Rules to Prometheus

```bash
# Verify alert file exists
ls -lh infra/prometheus/alerts/langgraph-alerts.yml

# Check Prometheus configuration
cat infra/prometheus/prometheus.yml | grep rule_files -A 5

# If rule_files section missing, add it:
cat >> infra/prometheus/prometheus.yml <<'EOF'

rule_files:
  - /etc/prometheus/alerts/*.yml
EOF
```

### Step 3.2: Reload Prometheus Configuration

```bash
# Hot reload Prometheus (no restart needed)
curl -X POST http://localhost:9090/-/reload

# Or restart Prometheus if reload not enabled
docker compose restart prometheus

# Verify alerts loaded
curl http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name=="langgraph_routing_slos")'
```

### Step 3.3: Verify Alerts in Prometheus UI

```bash
# Open Prometheus alerts page
open http://localhost:9090/alerts

# Expected: 14 alerts in "langgraph_routing_slos" group
# State: "Inactive" (no data yet)
```

**Alert List** (should see all 14):
1. Q4LatencyDegradation
2. Q4LatencyCritical
3. F16LatencyDegradation
4. F16LatencyCritical
5. HighEscalationFailureRate
6. CriticalEscalationFailureRate
7. HighToolFailureRate
8. CriticalToolFailureRate
9. LowConfidenceRate
10. MemoryRetrievalSlow
11. GraphExecutionFailures
12. CriticalToolDown
13. LowSelfEvaluationScores
14. LowMemorySufficiency

### Step 3.4: (Optional) Configure Alertmanager

```bash
# If Alertmanager is configured, add routing for LangGraph alerts
cat >> infra/alertmanager/alertmanager.yml <<'EOF'

routes:
  - match:
      component: langgraph
    receiver: langgraph-team
    continue: true

receivers:
  - name: langgraph-team
    slack_configs:
      - api_url: YOUR_SLACK_WEBHOOK_URL
        channel: '#kitty-alerts'
        title: 'LangGraph Alert: {{ .GroupLabels.alertname }}'
        text: '{{ .Annotations.description }}'
EOF

# Reload Alertmanager
docker compose restart alertmanager
```

**✅ Checkpoint**: Prometheus alerts loaded, visible in UI, Alertmanager configured (optional)

---

## Phase 4: Initial Testing (1 hour)

### Step 4.1: Run Unit Tests (5 minutes)

```bash
# From repository root
cd /home/user/KITT

# Install test dependencies (if not already installed)
pip install pytest pytest-asyncio pytest-mock

# Run complexity analyzer tests
pytest tests/unit/test_complexity_analyzer.py -v

# Expected: 15 test classes, 230 assertions, all pass

# Run router graph tests
pytest tests/unit/test_router_graph.py -v

# Expected: 14 test classes, 70+ assertions, all pass
```

**If tests fail**:
- Check if `services/common` is importable
- Ensure all dependencies installed: `pip install -e services/brain/`
- Check mocks are properly configured

### Step 4.2: Enable LangGraph with 0% Rollout (10 minutes)

This step enables LangGraph infrastructure but routes 0% traffic (for metrics testing).

```bash
# Update .env
sed -i.bak 's/BRAIN_USE_LANGGRAPH=false/BRAIN_USE_LANGGRAPH=true/' .env
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0/' .env

# Restart brain service
docker compose restart brain

# Wait for restart
sleep 10

# Check logs for LangGraph initialization
docker logs brain --tail 50 | grep -i langgraph

# Expected:
# "LangGraph integration initialized"
# "Rollout percentage: 0%"
# "LangGraph routing available but disabled for all conversations"
```

**Test Query with 0% Rollout**:
```bash
# Should use traditional router (A/B test sends 0% to LangGraph)
kitty-cli say "Hello KITTY"

# Check metrics
curl http://localhost:8000/metrics | grep brain_langgraph_routing_total

# Expected: brain_langgraph_routing_total{enabled="false"} 1
```

**Verify Metrics in Grafana**:
- Open `LangGraph Routing Overview` dashboard
- Should see: "Rollout Percentage: 0%"
- Should see: "LangGraph Requests/sec: 0" (no traffic routed)

### Step 4.3: Test Simple Queries (Q4 Routing) (15 minutes)

Enable 100% rollout for testing:

```bash
# Enable 100% rollout for testing
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100/' .env
docker compose restart brain
sleep 10

# Verify rollout
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent
# Expected: brain_langgraph_rollout_percent 100
```

**Test Case 1: Simple Greeting**
```bash
kitty-cli say "Hello KITTY, how are you?"

# Expected behavior:
# - Complexity score < 0.3
# - Q4 handles response
# - No F16 escalation
# - Response latency ~1-2 seconds
```

**Test Case 2: Device Status Query**
```bash
kitty-cli say "What's the printer status?"

# Expected behavior:
# - Complexity score < 0.4
# - Q4 handles response
# - May invoke tool: get_printer_status
# - Response latency ~1-3 seconds
```

**Test Case 3: Simple CAD Request**
```bash
kitty-cli say "Create a simple 10mm cube"

# Expected behavior:
# - Complexity score ~0.4-0.6
# - Q4 handles response
# - May invoke tool: generate_cad
# - Response latency ~2-5 seconds
```

**Verify in Grafana**:
- Open `LangGraph Routing Overview`
- Should see: Q4 usage ~100%
- Should see: Escalation rate ~0%
- Open `LangGraph Quality Metrics`
- Should see: Q4 confidence scores (likely 0.7-0.9)

### Step 4.4: Test Complex Queries (F16 Escalation) (15 minutes)

**Test Case 4: High Complexity Query**
```bash
kitty-cli say "Explain the detailed thermodynamic principles of heat exchangers with comprehensive multi-step analysis and parametric design considerations"

# Expected behavior:
# - Complexity score > 0.7
# - Q4 generates initial response
# - Escalates to F16 (high complexity trigger)
# - F16 runs 7-node workflow
# - Response latency ~7-12 seconds
```

**Test Case 5: Low Confidence Escalation**
```bash
kitty-cli say "Design an aerodynamically optimized bracket with stress analysis for aerospace applications using advanced parametric modeling"

# Expected behavior:
# - Q4 generates initial response
# - Q4 confidence < 0.75 (likely)
# - Escalates to F16 (low confidence trigger)
# - F16 provides detailed response
# - Response latency ~8-15 seconds
```

**Test Case 6: Explicit Deep Reasoning**
```bash
kitty-cli say "I need a deep analysis of CAD generation approaches with step-by-step reasoning about parametric vs mesh-based modeling"

# Expected behavior:
# - Keywords: "deep analysis", "step-by-step reasoning"
# - Escalates to F16 (explicit trigger)
# - F16 problem decomposition visible in response
# - Response latency ~10-15 seconds
```

**Verify in Grafana**:
- Open `LangGraph Routing Overview`
- Should see: Escalation rate ~30-50% (depends on queries)
- Should see: F16 usage increasing
- Open `LangGraph Quality Metrics`
- Should see: F16 confidence scores (likely 0.8-0.95)
- Should see: F16 reasoning steps (3-5 steps typical)

### Step 4.5: Test Memory Integration (10 minutes)

**Test Case 7: Memory Storage**
```bash
# Establish context
kitty-cli say "My favorite bolt size is 10mm"

# Check logs for memory storage
docker logs brain | grep "memory" | tail -20

# Expected: "Storing memory: User's favorite bolt size is 10mm"
```

**Test Case 8: Memory Retrieval**
```bash
# Query using stored context
kitty-cli say "Design a bracket for my favorite bolt size"

# Expected behavior:
# - Memory retrieval finds "favorite bolt size is 10mm"
# - Response includes 10mm specification
# - Check Grafana: Memory hit count increases
```

**Verify in Grafana**:
- Open `LangGraph Memory Performance`
- Should see: Memory hit counts increasing
- Should see: Memory sufficiency scores (likely 0.6-0.8)
- Should see: Initial search vs deep search distribution

### Step 4.6: Validate Metrics Collection (5 minutes)

**Check Prometheus Metrics**:
```bash
# Graph execution metrics
curl -s http://localhost:8000/metrics | grep brain_graph_execution_total

# Expected: brain_graph_execution_total{graph="router_graph",status="completed"} > 0

# Routing tier metrics
curl -s http://localhost:8000/metrics | grep brain_tier_routing_total

# Expected:
# brain_tier_routing_total{tier="local"} > 0  (Q4 queries)
# brain_tier_routing_total{tier="frontier"} > 0  (F16 queries, if escalated)

# Escalation metrics
curl -s http://localhost:8000/metrics | grep brain_escalation_total

# Expected: brain_escalation_total{reason="high_complexity"} > 0

# Tool metrics
curl -s http://localhost:8000/metrics | grep brain_tool_execution_total

# Expected: brain_tool_execution_total{tool="...",status="completed"} > 0
```

**Query Prometheus Directly**:
```bash
# Open Prometheus UI
open http://localhost:9090/graph

# Run queries:
# 1. Escalation rate (last 5 minutes)
rate(brain_escalation_total[5m])

# 2. Q4 vs F16 routing distribution
sum by (tier) (rate(brain_tier_routing_total[5m]))

# 3. Average confidence by tier
avg(brain_confidence_score) by (tier)

# 4. P95 Q4 latency
histogram_quantile(0.95,
  sum by (le) (rate(brain_graph_node_duration_seconds_bucket{graph="router_graph"}[5m]))
)
```

**✅ Checkpoint**: All test cases passed, metrics collecting correctly, dashboards showing data

---

## Phase 5: Gradual Rollout (4-5 weeks)

### Week 1: 10% Rollout (Monitor for 48 hours)

**Enable 10% Rollout**:
```bash
# Update .env
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=10/' .env
docker compose restart brain

# Verify rollout
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent
# Expected: brain_langgraph_rollout_percent 10
```

**Monitoring Checklist** (Check every 12 hours):
- [ ] Q4 P95 latency < 2s (SLO compliance)
- [ ] F16 P95 latency < 10s (SLO compliance)
- [ ] Escalation success rate > 90%
- [ ] Tool success rate > 80%
- [ ] No critical alerts firing
- [ ] Graph execution success rate > 95%

**If SLO Violations Occur**:
1. Check runbook: `ops/runbooks/langgraph-troubleshooting.md`
2. Follow diagnosis and resolution steps
3. If unresolvable, rollback: `BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0`

**After 48 Hours**:
- Review Grafana dashboards for trends
- Check error logs: `docker logs brain | grep -i error`
- If stable, proceed to Week 2

### Week 2: 25% Rollout (Monitor for 48 hours)

```bash
# Increase rollout
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=10/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=25/' .env
docker compose restart brain
```

Repeat monitoring checklist from Week 1.

### Week 3: 50% Rollout (Monitor for 48 hours)

```bash
# Increase rollout
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=25/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=50/' .env
docker compose restart brain
```

Repeat monitoring checklist from Week 1.

### Week 4: 75% Rollout (Monitor for 48 hours)

```bash
# Increase rollout
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=50/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=75/' .env
docker compose restart brain
```

Repeat monitoring checklist from Week 1.

### Week 5: 100% Rollout (Full Deployment)

```bash
# Full deployment
sed -i.bak 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=75/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100/' .env
docker compose restart brain

# Verify
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent
# Expected: brain_langgraph_rollout_percent 100
```

**Post-Deployment Monitoring** (30 days):
- Daily SLO compliance review
- Weekly capacity utilization review
- Monthly performance report (see `CAPACITY_PLANNING.md`)

**✅ Checkpoint**: 100% rollout successful, all SLOs met, system stable

---

## Troubleshooting Common Issues

### Issue: Q4 Server Not Responding

**Symptoms**: `curl http://localhost:8083/health` times out

**Diagnosis**:
```bash
# Check if process is running
ps aux | grep "llama-server.*8083"

# Check logs
tail -50 .logs/llamacpp-q4.log

# Check port binding
lsof -i :8083
```

**Resolution**:
```bash
# Kill stuck process
pkill -f "llama-server.*8083"

# Restart Q4 server (see Step 1.2)
```

### Issue: F16 Server Out of Memory

**Symptoms**: F16 server crashes, OOM errors in logs

**Diagnosis**:
```bash
# Check memory usage
top -p $(pgrep -f "llama-server.*8082")

# Check logs
tail -100 .logs/llamacpp-f16.log | grep -i "memory\|oom"
```

**Resolution**:
```bash
# Option 1: Use quantized model instead of FP16
# Replace F16 model with q8_0 (saves ~70 GB)

# Option 2: Reduce context size
# Restart F16 with --ctx-size 4096 instead of 8192

# Option 3: Reduce parallel requests
# Restart F16 with --n-parallel 1 instead of 2
```

### Issue: No Metrics in Grafana

**Symptoms**: Grafana dashboards show "No data"

**Diagnosis**:
```bash
# Check if Prometheus is scraping brain service
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="brain")'

# Check if brain exposes metrics
curl http://localhost:8000/metrics | head -20

# Check LangGraph is enabled
grep BRAIN_USE_LANGGRAPH .env
```

**Resolution**:
```bash
# Ensure LangGraph is enabled
sed -i 's/BRAIN_USE_LANGGRAPH=false/BRAIN_USE_LANGGRAPH=true/' .env
docker compose restart brain

# Verify Prometheus scrape config
cat infra/prometheus/prometheus.yml | grep -A 5 "job_name: 'brain'"
```

### Issue: High F16 Latency

**Symptoms**: F16 queries take > 20 seconds

**Diagnosis**:
```bash
# Check F16 server load
curl http://localhost:8082/health | jq '.slots'

# Check GPU utilization (Metal)
sudo powermetrics --samplers gpu_power -i 1000 -n 1

# Check Prometheus metrics
curl -s http://localhost:9090/api/v1/query?query=histogram_quantile\(0.95,brain_graph_node_duration_seconds_bucket{graph=\"deep_reasoner_graph\"}\)
```

**Resolution**:
```bash
# See ops/runbooks/langgraph-troubleshooting.md
# Section: "Alert: F16LatencyDegradation"
```

---

## Rollback Procedures

### Emergency Disable (0% Rollout)

```bash
# Immediate rollback to 0% LangGraph traffic
sed -i 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=[0-9]*/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0/' .env
docker compose restart brain

# Verify
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent
# Expected: brain_langgraph_rollout_percent 0
```

### Full Disable (Traditional Router Only)

```bash
# Disable LangGraph completely
sed -i 's/BRAIN_USE_LANGGRAPH=true/BRAIN_USE_LANGGRAPH=false/' .env
docker compose restart brain

# Verify
docker logs brain | grep "LangGraph integration disabled"
```

### Restore from Backup

```bash
# Restore .env from backup
cp .env.backup.YYYYMMDD .env
docker compose restart brain
```

---

## Success Criteria Checklist

### Deployment Phase
- [ ] Both llama.cpp servers running and healthy
- [ ] Docker Compose services started successfully
- [ ] Grafana dashboards imported and displaying
- [ ] Prometheus alerts loaded and visible
- [ ] Unit tests pass (300+ assertions)

### Testing Phase
- [ ] Simple queries route to Q4 only
- [ ] Complex queries escalate to F16
- [ ] Memory integration works (storage and retrieval)
- [ ] All metrics collecting correctly
- [ ] Dashboards show real-time data

### Rollout Phase
- [ ] 10% rollout stable for 48 hours
- [ ] 25% rollout stable for 48 hours
- [ ] 50% rollout stable for 48 hours
- [ ] 75% rollout stable for 48 hours
- [ ] 100% rollout stable for 7+ days
- [ ] All SLOs met consistently
- [ ] No critical alerts during rollout

---

## Next Steps After Deployment

1. **Team Training**: Share documentation with team
2. **Monitoring Review**: Daily SLO compliance checks
3. **Capacity Planning**: Monitor usage trends (see `CAPACITY_PLANNING.md`)
4. **Optimization**: Apply vertical scaling optimizations if needed
5. **Feedback Loop**: Collect user feedback on response quality

---

## Related Documentation

- **Architecture**: `ARCHITECTURE.md` - Design principles
- **Testing Guide**: `TESTING_GUIDE.md` - 7-phase validation with real servers
- **Implementation Summary**: `IMPLEMENTATION_SUMMARY.md` - Complete feature overview
- **SLO Definitions**: `SLO_DEFINITIONS.md` - Service level objectives
- **Capacity Planning**: `CAPACITY_PLANNING.md` - Scaling strategies
- **Troubleshooting**: `/ops/runbooks/langgraph-troubleshooting.md` - Operations runbook

---

**Document Version**: 1.0
**Last Updated**: 2025-11-12
**Estimated Deployment Time**: 3 hours (setup + testing) + 4-5 weeks (gradual rollout)
