# LangGraph Multi-Agent System Testing Plan

## Overview

This testing plan validates the LangGraph multi-agent deployment for KITTY Brain, focusing on Q4/F16 routing intelligence, complexity analysis, tool orchestration, and system performance.

**Test Duration**: ~20-30 minutes
**Prerequisites**: All llama.cpp servers running, Docker services healthy
**Test Script**: `./tests/langgraph_system_test.sh`

---

## Quick Start

```bash
# From repository root
cd /Users/Shared/Coding/KITT

# Make test script executable
chmod +x tests/langgraph_system_test.sh

# Run full test suite
./tests/langgraph_system_test.sh

# Results saved to: ./test-results/langgraph-YYYYMMDD-HHMMSS/
```

---

## Test Categories

### 1. Simple Query Routing (Q4 Expected)

**Objective**: Verify fast-path routing for low-complexity queries

**Test Cases**:
- Simple math: "What is 2 + 2?"
- General knowledge: "What is the capital of France?"
- Status check: "Hello KITTY, how are you?"

**Expected Behavior**:
- Complexity score < 0.3
- Routed to Q4 (Athene-V2-Agent on port 8083)
- Response time < 5 seconds
- No F16 escalation

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Response received
- ✓ Model = kitty-q4 or routing_tier = local
- ✓ Latency within SLO

**Validation Commands**:
```bash
# Check Q4 server logs for recent activity
tail -50 /Users/Shared/Coding/KITT/.logs/llamacpp-q4.log

# Verify metrics
curl -s http://localhost:8000/metrics | grep brain_langgraph
```

---

### 2. Complex Query Routing (F16 Expected)

**Objective**: Verify deep reasoning escalation for high-complexity queries

**Test Cases**:
- Multi-step reasoning: "Explain supervised vs unsupervised ML with examples"
- Technical explanation: "Describe how a 3D printer's stepper motor control works"
- Comparative analysis: "Compare FDM and SLA printing technologies"

**Expected Behavior**:
- Complexity score > 0.7
- Routed to F16 (Llama-3.3-70B on port 8082)
- Response time < 30 seconds
- Detailed, structured response

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Response shows reasoning depth
- ✓ Model = kitty-f16 or escalation logged
- ✓ Latency acceptable for complex query

**Validation Commands**:
```bash
# Check F16 server logs
tail -50 /Users/Shared/Coding/KITT/.logs/llamacpp-f16.log

# Check for escalation events in brain logs
docker logs compose-brain-1 --tail 100 | grep -i "escalat\|f16"
```

---

### 3. CAD Tool Execution

**Objective**: Verify tool orchestration for CAD generation requests

**Test Cases**:
- Simple bracket: "Design a mounting bracket for Raspberry Pi 4"
- Parametric design: "Create a parametric phone stand with adjustable angle"
- Multi-part assembly: "Design a 3-part enclosure for Arduino Uno"

**Expected Behavior**:
- Complexity score > 0.6
- Tools invoked: `cad_generate` or similar
- CAD artifact returned (STEP/STL)
- MinIO storage URI provided

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Tools executed > 0
- ✓ Artifact metadata present
- ✓ File stored in MinIO

**Validation Commands**:
```bash
# Check CAD service logs
docker logs compose-cad-1 --tail 50

# Verify MinIO storage
curl -s http://localhost:9000/minio/health/live
```

---

### 4. Fabrication Tool Execution

**Objective**: Verify printer status and fabrication workflow tools

**Test Cases**:
- Printer status: "What 3D printers are currently online?"
- Printer selection: "Which printer is best for a 6-hour print?"
- Queue job: "Queue this STL to the fastest available printer"

**Expected Behavior**:
- Tools invoked: `printer_status`, `queue_print`
- Real-time printer state retrieved
- Intelligent printer selection based on status

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Printer list returned
- ✓ Status includes: online/offline, current job, capabilities
- ✓ Tool execution successful

**Validation Commands**:
```bash
# Check fabrication service
docker logs compose-fabrication-1 --tail 50

# Verify MQTT messages (if mosquitto accessible)
docker logs compose-mosquitto-1 --tail 30
```

---

### 5. Device Discovery Tools

**Objective**: Verify network device scanning and discovery

**Test Cases**:
- Network scan: "Scan for network devices"
- Device filter: "Show me all Raspberry Pi devices on the network"
- Device details: "Get details for device at 192.168.1.50"

**Expected Behavior**:
- Tools invoked: `network_scan`, `device_info`
- mDNS/SSDP/UDP discovery protocols used
- Device registry updated

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Devices discovered (count > 0 or "none found")
- ✓ Device metadata: IP, hostname, type, services

**Validation Commands**:
```bash
# Check discovery service
docker logs compose-discovery-1 --tail 50

# Verify discovered devices
curl -s http://localhost:8500/api/discovery/devices | jq .
```

---

### 6. Memory Integration

**Objective**: Verify conversation memory retrieval and context

**Test Cases**:
- Follow-up query: Ask "What did we just discuss?" after a CAD query
- Context recall: "Based on our earlier conversation, modify the design"
- User preference: "Remember I prefer PETG filament"

**Expected Behavior**:
- Memory retrieval from Qdrant vector store
- Context enriched with past conversation
- Coherent multi-turn dialogue

**Success Criteria**:
- ✓ HTTP 200 status
- ✓ Response references prior context
- ✓ Memory sufficiency score > 0.5
- ✓ No hallucinated context

**Validation Commands**:
```bash
# Check Qdrant for stored memories
curl -s http://localhost:6333/collections | jq .

# Check mem0-mcp service
docker logs compose-mem0-mcp-1 --tail 30
```

---

### 7. End-to-End Workflow

**Objective**: Test complete multi-step workflow with multiple tools

**Test Case**:
"Design a simple phone stand, convert it to STL, analyze for printability, and queue it to the best available printer"

**Expected Behavior**:
1. CAD tool: Generate phone stand design
2. Conversion tool: STEP → STL conversion
3. Analysis tool: Printability check (overhangs, supports needed)
4. Fabrication tool: Printer selection + queue job
5. All steps orchestrated by LangGraph workflow

**Success Criteria**:
- ✓ All 4 tool calls successful
- ✓ Data flows between tools (STL from CAD → Analysis)
- ✓ Final job queued to printer
- ✓ Total workflow time < 2 minutes

---

## Metrics Validation

After running tests, verify these metrics are being collected:

```bash
# Check brain metrics endpoint
curl -s http://localhost:8000/metrics | grep brain_langgraph

# Expected metrics:
# - brain_langgraph_routing_total (increments with each query)
# - brain_langgraph_rollout_percent (should be 100)
# - brain_graph_node_duration_seconds (histogram of node execution times)
# - brain_graph_execution_total (total graph executions)
```

**Grafana Dashboard Verification**:
1. Open http://localhost:3000
2. Login: admin / admin
3. Navigate to "LangGraph Routing Overview" dashboard
4. Verify panels show data:
   - Routing decisions (Q4 vs F16 split)
   - Request rate and latency
   - Tool execution counts
   - Complexity score distribution

---

## Log Analysis Checklist

After test run, review logs for these key indicators:

**✓ LangGraph Initialization** (brain logs):
```
INFO: LangGraph routing enabled (rollout: 100%)
INFO: Registered Q4 client: kitty-q4 @ http://host.docker.internal:8083
INFO: Registered F16 client: kitty-f16 @ http://host.docker.internal:8082
```

**✓ Complexity Analysis** (brain logs):
```
DEBUG: Complexity analysis result: score=0.45, factors={...}
DEBUG: Routing recommendation: tier=local, model=q4
```

**✓ Tool Execution** (brain logs):
```
INFO: Executing tool: cad_generate with params={...}
INFO: Tool execution successful: artifact_id=abc123
```

**✓ F16 Escalation** (brain logs):
```
INFO: Escalating to F16: complexity=0.85, confidence_low=true
INFO: F16 response generated: tokens=896, latency=72s
```

---

## Troubleshooting

### Issue: All queries timeout (no response)

**Check**:
```bash
# Verify llama.cpp servers
curl http://localhost:8083/health  # Q4
curl http://localhost:8082/health  # F16

# Check brain service health
curl http://localhost:8000/health

# Review brain logs for errors
docker logs compose-brain-1 --tail 100 | grep -i error
```

**Fix**: Restart llama.cpp servers if unhealthy

---

### Issue: Tools not executing

**Check**:
```bash
# Verify tool-related services
docker ps | grep -E "cad|fabrication|discovery"

# Check tool registry initialization
docker logs compose-brain-1 | grep "Loaded.*tools"
```

**Fix**: Ensure all dependent services are running

---

### Issue: No LangGraph metrics

**Check**:
```bash
# Verify rollout percentage
docker exec compose-brain-1 printenv BRAIN_LANGGRAPH_ROLLOUT_PERCENT

# Check feature flag
docker exec compose-brain-1 printenv BRAIN_USE_LANGGRAPH
```

**Fix**: Should be `BRAIN_USE_LANGGRAPH=true` and `ROLLOUT_PERCENT=100`

---

## Success Criteria Summary

**System is healthy if**:
- ✓ 80%+ of test queries return HTTP 200
- ✓ Q4 handles simple queries (< 5s latency)
- ✓ F16 handles complex queries (< 30s latency)
- ✓ At least 1 tool executes successfully
- ✓ LangGraph metrics are being collected
- ✓ No critical errors in brain logs

**Deployment is successful if**:
- ✓ All 4 llama.cpp servers healthy
- ✓ Grafana dashboards showing data
- ✓ Prometheus scraping brain metrics
- ✓ 16 alert rules loaded
- ✓ Test script passes with 0 failures

---

## Next Steps After Testing

1. **Review Results**: Check `./test-results/langgraph-*/` directory
2. **Monitor Dashboards**: Open Grafana and watch real-time routing
3. **Use Web UI**: Test interactively at http://localhost:4173
4. **Iterate**: If issues found, adjust complexity thresholds in `.env`

---

## Contact / Support

**Troubleshooting Runbook**: `ops/runbooks/langgraph-troubleshooting.md`
**Architecture Docs**: `services/brain/src/brain/agents/graphs/ARCHITECTURE.md`
**Deployment Guide**: `services/brain/src/brain/agents/graphs/DEPLOYMENT_GUIDE.md`

---

**Test Plan Version**: 1.0
**Last Updated**: 2025-11-12
**Compatible with**: LangGraph Multi-Agent v1.0 (Phase 1-5 complete)
