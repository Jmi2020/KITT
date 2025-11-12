# LangGraph Operations Runbook

## Overview

This runbook provides troubleshooting procedures for LangGraph-enhanced routing alerts in KITTY Brain. Use this guide to diagnose and resolve production incidents related to multi-agent reasoning, tool orchestration, and memory retrieval.

## General Diagnostics

### Quick Health Check

```bash
# Check if brain service is running
docker ps | grep brain

# Check brain logs for errors
docker logs brain --tail 100 --follow

# Check llama.cpp servers
curl http://localhost:8082/health  # F16 server
curl http://localhost:8083/health  # Q4 server

# Check Prometheus metrics endpoint
curl http://localhost:8000/metrics | grep brain_graph

# Check current rollout percentage
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent
```

### Access Dashboards

- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Brain API Docs**: http://localhost:8080/docs

---

## Alert: Q4LatencyDegradation

**Severity**: Warning
**SLO**: Q4 P95 latency < 2s
**Trigger**: P95 > 2s for 3+ minutes

### Symptoms

- Slow response times for simple queries
- Users reporting delays in conversational responses
- Router graph taking longer than expected

### Diagnosis

```bash
# Check Q4 llama.cpp server load
curl http://localhost:8083/health
# Look for: model_loaded: true, n_ctx_used/n_ctx

# Check if Q4 server is being throttled
top -p $(pgrep -f "llama-server.*8083")

# Check graph node durations in Prometheus
# Graph: brain_graph_node_duration_seconds{graph="router_graph"}

# Check if complexity analysis is slow
docker logs brain --tail 100 | grep "complexity_analysis"
```

### Resolution Steps

1. **Check Q4 Server Resources**:
   ```bash
   # Check CPU/GPU utilization
   top -p $(pgrep -f "llama-server.*8083")

   # For Mac M3 Ultra, check Metal utilization
   sudo powermetrics --samplers gpu_power -i 1000 -n 1
   ```

2. **Restart Q4 Server** (if hung):
   ```bash
   # Find Q4 server process
   ps aux | grep "llama-server.*8083"

   # Kill and restart via start script
   ./ops/scripts/stop-kitty.sh
   ./ops/scripts/start-kitty.sh
   ```

3. **Reduce Rollout Percentage** (if LangGraph overhead is high):
   ```bash
   # Temporarily reduce rollout to 0%
   # Edit .env: BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0
   docker compose restart brain
   ```

4. **Check for Memory Leaks**:
   ```bash
   docker stats brain
   # Look for increasing memory usage
   ```

### Prevention

- Monitor Q4 server context usage (n_ctx_used should be < 80% of n_ctx)
- Ensure Q4 model is properly quantized (q4_k_m recommended)
- Consider increasing Q4 server --n-parallel if concurrent requests spike

---

## Alert: Q4LatencyCritical

**Severity**: Critical
**SLO**: Q4 P95 latency < 2s
**Trigger**: P95 > 5s for 2+ minutes

### Immediate Actions

1. **Disable LangGraph Routing**:
   ```bash
   # Emergency rollback to traditional router
   curl -X POST http://localhost:8000/admin/langgraph/disable \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. **Check for Server Crash**:
   ```bash
   # Check if Q4 server is responding
   curl http://localhost:8083/health --max-time 5

   # If timeout, restart immediately
   pkill -f "llama-server.*8083"
   ./ops/scripts/start-kitty.sh
   ```

3. **Page Team Lead**:
   - Critical SLO breach requires escalation
   - Document incident timeline

---

## Alert: F16LatencyDegradation

**Severity**: Warning
**SLO**: F16 P95 latency < 10s
**Trigger**: P95 > 10s for 3+ minutes

### Symptoms

- Complex queries taking too long
- F16 deep reasoner timing out
- High escalation fallback rate

### Diagnosis

```bash
# Check F16 llama.cpp server
curl http://localhost:8082/health

# Check deep reasoner graph node durations
# Graph: brain_graph_node_duration_seconds{graph="deep_reasoner_graph"}

# Check reasoning step counts
# Graph: brain_reasoning_steps

# Check tool execution latencies (may be blocking F16)
# Graph: brain_tool_execution_duration_seconds
```

### Resolution Steps

1. **Check F16 Server Resources**:
   ```bash
   # F16 uses more VRAM and compute
   top -p $(pgrep -f "llama-server.*8082")

   # Check for GPU throttling
   sudo powermetrics --samplers gpu_power -i 1000 -n 1
   ```

2. **Reduce Reasoning Steps** (if excessive):
   ```python
   # In deep_reasoner_graph.py, check max_reasoning_steps
   # Default: 5, reduce to 3 if latency is critical
   ```

3. **Check Tool Latencies**:
   - F16 often triggers tool refinement
   - Slow tools (CAD, fabrication) may block F16 response
   - Check tool_orchestrator logs for retries

4. **Temporarily Increase Escalation Threshold**:
   ```python
   # In router_graph.py, increase confidence threshold
   # Default: confidence < 0.75 triggers escalation
   # Temporarily: confidence < 0.60 to reduce F16 load
   ```

---

## Alert: F16LatencyCritical

**Severity**: Critical
**SLO**: F16 P95 latency < 10s
**Trigger**: P95 > 20s for 2+ minutes

### Immediate Actions

1. **Disable F16 Escalation**:
   ```bash
   # Emergency: Route all queries via Q4 only
   curl -X POST http://localhost:8000/admin/langgraph/disable-escalation \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. **Restart F16 Server**:
   ```bash
   pkill -f "llama-server.*8082"
   ./ops/scripts/start-kitty.sh
   ```

3. **Check for Infinite Loops**:
   ```bash
   # Check if reasoning retry loops are stuck
   docker logs brain --tail 200 | grep "retry_count"

   # If retry_count is high, restart brain service
   docker compose restart brain
   ```

---

## Alert: HighEscalationFailureRate

**Severity**: Warning
**SLO**: Escalation success rate > 90%
**Trigger**: Failure rate > 10% for 5+ minutes

### Symptoms

- F16 escalations frequently falling back to Q4
- Low self-evaluation scores
- Errors in deep_reasoner_graph logs

### Diagnosis

```bash
# Check escalation reasons
# Graph: brain_escalation_total by reason

# Check escalation status
# Graph: brain_escalation_status_total{status="fallback"}

# Check F16 server errors
curl http://localhost:8082/health
docker logs brain | grep "deep_reasoner" | grep -i error
```

### Resolution Steps

1. **Check F16 Server Health**:
   ```bash
   # Test F16 inference directly
   curl http://localhost:8082/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "kitty-f16",
       "messages": [{"role": "user", "content": "Test"}],
       "max_tokens": 50
     }'
   ```

2. **Review Recent Escalation Failures**:
   ```bash
   # Check logs for specific errors
   docker logs brain --tail 500 | grep "Escalation failed"
   ```

3. **Validate Memory Retrieval**:
   - F16 relies on memory context
   - Check `brain_memory_sufficiency_score`
   - If low, memory MCP server may be down

4. **Check Tool Availability**:
   - F16 often uses tool refinement
   - Verify MCP client connectivity
   - Check `brain_tool_execution_total{status="failed"}`

---

## Alert: CriticalEscalationFailureRate

**Severity**: Critical
**SLO**: Escalation success rate > 90%
**Trigger**: Failure rate > 25% for 3+ minutes

### Immediate Actions

1. **Disable F16 Escalation** (fallback to Q4):
   ```bash
   curl -X POST http://localhost:8000/admin/langgraph/disable-escalation \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. **Restart Brain Service**:
   ```bash
   docker compose restart brain
   ```

3. **Verify F16 Server**:
   ```bash
   # If F16 is down, queries will fail
   curl http://localhost:8082/health --max-time 5 || {
     echo "F16 server down, restarting..."
     ./ops/scripts/stop-kitty.sh
     ./ops/scripts/start-kitty.sh
   }
   ```

---

## Alert: HighToolFailureRate

**Severity**: Warning
**SLO**: Tool success rate > 80%
**Trigger**: Failure rate > 20% for 5+ minutes

### Symptoms

- CAD generation failures
- Fabrication commands failing
- Tool timeout errors

### Diagnosis

```bash
# Check tool execution status
# Graph: brain_tool_execution_total by tool, status

# Check specific tool failures
# Graph: brain_tool_execution_total{status="failed"} by tool

# Check MCP client connectivity
docker logs brain | grep "MCP" | grep -i error

# Check tool retry counts
# Graph: brain_tool_retry_total
```

### Resolution Steps

1. **Identify Failing Tools**:
   ```promql
   # Query Prometheus for top failing tools
   topk(5, sum by (tool) (rate(brain_tool_execution_total{status="failed"}[5m])))
   ```

2. **Check MCP Server**:
   ```bash
   # CAD and fabrication tools use MCP
   docker logs mcp-server --tail 100

   # Restart if needed
   docker compose restart mcp-server
   ```

3. **Check Tool Dependencies**:
   - **CAD tools**: Zoo API, Tripo API, MinIO
   - **Fabrication tools**: MQTT broker, printer connectivity
   - **Coding tools**: Sandbox execution environment

4. **Verify API Keys**:
   ```bash
   # Check .env for missing/expired keys
   grep -E "(ZOO_API_KEY|TRIPO_API_KEY)" .env
   ```

---

## Alert: CriticalToolFailureRate

**Severity**: Critical
**SLO**: Tool success rate > 80%
**Trigger**: Failure rate > 40% for 3+ minutes

### Immediate Actions

1. **Disable Tool Orchestration** (graceful degradation):
   ```bash
   # Temporary: Disable parallel tool execution
   curl -X POST http://localhost:8000/admin/tools/disable-orchestration \
     -H "Authorization: Bearer $ADMIN_TOKEN"
   ```

2. **Check External Dependencies**:
   ```bash
   # MinIO (CAD artifact storage)
   curl http://localhost:9000/minio/health/live

   # MQTT (fabrication commands)
   docker logs mosquitto --tail 50

   # MCP server (tool provider)
   curl http://localhost:8500/health
   ```

3. **Restart Dependent Services**:
   ```bash
   docker compose restart mcp-server mosquitto minio
   ```

---

## Alert: LowConfidenceRate

**Severity**: Warning
**SLO**: ≥ 70% of queries with confidence ≥ 0.6
**Trigger**: > 30% of queries with confidence ≤ 0.6 for 10+ minutes

### Symptoms

- Many low-confidence responses
- Q4 frequently triggering escalation
- Users reporting inaccurate or uncertain responses

### Diagnosis

```bash
# Check confidence distribution
# Graph: brain_confidence_distribution by tier

# Check query complexity
# Graph: brain_complexity_score

# Check memory sufficiency
# Graph: brain_memory_sufficiency_score
```

### Resolution Steps

1. **Review Complexity Analyzer**:
   - May be over-estimating complexity
   - Check if simple queries are being marked complex

2. **Check Memory Retrieval**:
   ```bash
   # Low memory sufficiency can reduce confidence
   # Graph: brain_memory_hit_total

   # Verify memory MCP server
   docker logs memory-mcp-server --tail 100
   ```

3. **Validate Q4 Model**:
   ```bash
   # Ensure Q4 model is properly loaded
   curl http://localhost:8083/health | jq '.model_loaded'

   # Check if correct model alias is set
   curl http://localhost:8083/v1/models
   ```

4. **Check for Prompt Drift**:
   - Review system prompts in `prompts.py`
   - Ensure prompts still align with Q4 model training

---

## Alert: MemoryRetrievalSlow

**Severity**: Warning
**SLO**: Memory retrieval P95 < 1s
**Trigger**: P95 > 1s for 5+ minutes

### Symptoms

- Slow initial search and deep search
- High latency for memory-augmented queries
- Excessive deep search rate

### Diagnosis

```bash
# Check memory retrieval duration
# Graph: brain_memory_retrieval_duration_seconds by search_type

# Check deep search rate
# Graph: brain_memory_hit_total{search_type="deep"} / brain_memory_hit_total

# Check memory MCP server
docker logs memory-mcp-server --tail 100

# Check PostgreSQL (if memory uses DB)
docker exec -it postgres psql -U postgres -c "SELECT count(*) FROM memories;"
```

### Resolution Steps

1. **Check Memory MCP Server**:
   ```bash
   # Restart if slow
   docker compose restart memory-mcp-server
   ```

2. **Optimize Memory Index**:
   ```bash
   # If using PostgreSQL vector extension
   docker exec -it postgres psql -U postgres -c "REINDEX TABLE memories;"
   ```

3. **Reduce Deep Search Threshold**:
   ```python
   # In memory_graph.py, adjust deep_search_threshold
   # Default: 0.60, increase to 0.65 to reduce deep search frequency
   ```

4. **Check Network Latency**:
   ```bash
   # Memory MCP server network latency
   ping memory-mcp-server
   ```

---

## Alert: GraphExecutionFailures

**Severity**: Warning
**SLO**: Graph success rate > 95%
**Trigger**: Failure rate > 5% for 5+ minutes

### Symptoms

- Graph execution exceptions
- Error responses to users
- LangGraph state errors

### Diagnosis

```bash
# Check graph execution status
# Graph: brain_graph_execution_total{status="failed"}

# Check brain logs for exceptions
docker logs brain --tail 200 | grep -i "exception\|error"

# Check state validation errors
docker logs brain | grep "state validation"
```

### Resolution Steps

1. **Review Recent Graph Errors**:
   ```bash
   # Look for specific node failures
   docker logs brain --tail 500 | grep "node failed"
   ```

2. **Check State Serialization**:
   - LangGraph requires JSON-serializable state
   - Check for non-serializable objects in states.py

3. **Validate Graph Construction**:
   ```python
   # In router_graph.py or deep_reasoner_graph.py
   # Ensure all conditional edges are properly defined
   # Ensure all nodes are reachable
   ```

4. **Restart Brain Service**:
   ```bash
   docker compose restart brain
   ```

---

## Alert: CriticalToolDown

**Severity**: Critical
**Trigger**: Specific tool failure rate > 80% for 3+ minutes

### Immediate Actions

1. **Identify Critical Tool**:
   ```bash
   # Check alert labels for tool name
   # Example: tool="generate_cad"
   ```

2. **Check Tool Provider**:
   - **generate_cad**: CAD service (port 8200), Zoo API, Tripo API
   - **slice_model**: Fabrication service (port 8300)
   - **coding.generate**: Coder-agent service (port 8092)
   - **web_search**: MCP client, Perplexity API

3. **Restart Tool Provider**:
   ```bash
   # Example for CAD tool
   docker compose restart cad

   # Example for fabrication tool
   docker compose restart fabrication
   ```

4. **Disable Tool Temporarily**:
   ```bash
   # If tool is broken, disable in tool registry
   curl -X POST http://localhost:8000/admin/tools/disable \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"tool": "generate_cad"}'
   ```

---

## Alert: LowSelfEvaluationScores

**Severity**: Warning
**Trigger**: F16 median self-evaluation < 0.5 for 10+ minutes

### Symptoms

- F16 producing low-quality reasoning
- Self-evaluation scores consistently low
- Users reporting poor F16 responses

### Diagnosis

```bash
# Check self-evaluation distribution
# Graph: brain_self_evaluation_score

# Check reasoning step counts
# Graph: brain_reasoning_steps

# Check F16 model health
curl http://localhost:8082/health
```

### Resolution Steps

1. **Review F16 Prompts**:
   - Check `prompts.py` for self-evaluation prompt
   - Ensure prompt aligns with F16 model training

2. **Check Reasoning Step Quality**:
   ```bash
   # Look for reasoning loops or poor decomposition
   docker logs brain | grep "reasoning_steps" -A 10
   ```

3. **Validate F16 Model**:
   ```bash
   # Ensure F16 model is FP16, not quantized
   curl http://localhost:8082/v1/models
   ```

4. **Increase Max Reasoning Steps**:
   ```python
   # In deep_reasoner_graph.py, increase max_reasoning_steps
   # Default: 5, try 7 for more thorough reasoning
   ```

---

## Alert: LowMemorySufficiency

**Severity**: Warning
**Trigger**: Median memory sufficiency < 0.5 for 15+ minutes

### Symptoms

- Insufficient memory context for queries
- High deep search rate
- Responses lacking relevant context

### Diagnosis

```bash
# Check memory sufficiency scores
# Graph: brain_memory_sufficiency_score

# Check memory hit counts
# Graph: brain_memory_hit_total

# Check fact extraction rate
# Graph: brain_fact_extraction_total
```

### Resolution Steps

1. **Increase Fact Extraction**:
   - More facts → better future retrieval
   - Check if fact extraction is running

2. **Adjust Sufficiency Threshold**:
   ```python
   # In memory_graph.py, reduce sufficiency_threshold
   # Default: 0.75, reduce to 0.60 to trigger deep search less
   ```

3. **Check Memory MCP Server**:
   ```bash
   # Verify memory storage is working
   docker logs memory-mcp-server | grep "store memory"
   ```

4. **Review Memory Search Quality**:
   - Check if search embeddings are accurate
   - Verify semantic similarity scoring

---

## Alert: ExcessiveDeepSearchRate

**Severity**: Info
**Trigger**: Deep search rate > 50% for 15+ minutes

### Symptoms

- Most queries requiring deep search
- Initial search not finding relevant memories
- Slower overall memory retrieval

### Diagnosis

```bash
# Check deep search rate
# Graph: brain_memory_hit_total{search_type="deep"} / brain_memory_hit_total

# Check initial search threshold
# Default: 0.75, may be too high
```

### Resolution Steps

1. **Increase Initial Search Limit**:
   ```python
   # In memory_graph.py, increase initial_search_limit
   # Default: 3, increase to 5
   ```

2. **Reduce Initial Search Threshold**:
   ```python
   # In memory_graph.py, reduce initial_threshold
   # Default: 0.75, reduce to 0.70
   ```

3. **Optimize Memory Embeddings**:
   - Check if embedding model needs retraining
   - Verify semantic similarity quality

---

## Alert: LangGraphRolloutStalled

**Severity**: Info
**Trigger**: Rollout percentage unchanged for 2+ hours during gradual rollout

### Symptoms

- Rollout percentage stuck (e.g., 50%)
- A/B testing not progressing

### Diagnosis

```bash
# Check current rollout percentage
curl http://localhost:8000/metrics | grep brain_langgraph_rollout_percent

# Check if manual intervention is needed
cat .env | grep BRAIN_LANGGRAPH_ROLLOUT_PERCENT
```

### Resolution Steps

1. **Manual Rollout Progression**:
   ```bash
   # Edit .env to increase rollout
   # Example: 50% → 75%
   sed -i 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=50/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=75/' .env

   # Restart brain service
   docker compose restart brain
   ```

2. **Automated Rollout** (future enhancement):
   - Implement automated rollout based on SLO compliance
   - Increase by 10% every 24h if no SLO violations

---

## Emergency Procedures

### Full LangGraph Disable

```bash
# Disable LangGraph routing completely
curl -X POST http://localhost:8000/admin/langgraph/disable \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# Or edit .env
sed -i 's/BRAIN_USE_LANGGRAPH=true/BRAIN_USE_LANGGRAPH=false/' .env
docker compose restart brain
```

### Full Rollback to Traditional Router

```bash
# Stop brain service
docker compose stop brain

# Edit .env
sed -i 's/BRAIN_USE_LANGGRAPH=true/BRAIN_USE_LANGGRAPH=false/' .env
sed -i 's/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=[0-9]*/BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0/' .env

# Restart brain service
docker compose start brain
```

### Restart All Services

```bash
./ops/scripts/stop-kitty.sh
./ops/scripts/start-kitty.sh
```

---

## Incident Response Template

```markdown
## Incident Report: [Alert Name]

**Date**: YYYY-MM-DD HH:MM UTC
**Severity**: Critical / Warning / Info
**Duration**: X minutes
**Impact**: [Description of user impact]

### Timeline

- HH:MM - Alert triggered
- HH:MM - Investigation started
- HH:MM - Root cause identified
- HH:MM - Mitigation applied
- HH:MM - Alert resolved

### Root Cause

[Detailed description]

### Resolution

[Steps taken to resolve]

### Prevention

[Actions to prevent recurrence]

### Related Alerts

- [List of related alerts]

### Follow-up Actions

- [ ] Update runbook
- [ ] Adjust alert thresholds
- [ ] Implement automated remediation
```

---

## Escalation Contacts

**On-call Engineer**: [PagerDuty rotation]
**Team Lead**: [Slack channel]
**System Architect**: [Email]

**Escalation Criteria**:
- Critical SLO breach > 5 minutes
- Multiple critical alerts firing
- User-facing outage

---

## Related Documentation

- **SLO Definitions**: `/services/brain/src/brain/agents/graphs/SLO_DEFINITIONS.md`
- **Alerting Rules**: `/infra/prometheus/alerts/langgraph-alerts.yml`
- **Architecture**: `/services/brain/src/brain/agents/graphs/ARCHITECTURE.md`
- **Testing Guide**: `/services/brain/src/brain/agents/graphs/TESTING_GUIDE.md`
- **Capacity Planning**: `/services/brain/src/brain/agents/graphs/CAPACITY_PLANNING.md`
