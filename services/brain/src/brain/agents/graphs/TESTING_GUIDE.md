# LangGraph Routing Testing Guide

**Purpose**: Validate Phase 1 + Phase 2 implementation with real llama.cpp servers
**Prerequisites**: Q4 server (port 8083) and F16 server (port 8082) running
**Estimated Time**: 2-3 hours for complete validation

---

## Test Environment Setup

### 1. Start llama.cpp Servers

```bash
# Terminal 1: Start Q4 server (Tool Orchestrator)
llama-server \
  --model /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-Q4_K_M.gguf \
  --port 8083 \
  --ctx-size 8192 \
  --n-gpu-layers 35 \
  --threads 24 \
  --alias kitty-q4

# Terminal 2: Start F16 server (Reasoning Engine)
llama-server \
  --model /Users/Shared/Coding/models/Llama-3.3-70B-Instruct-F16.gguf \
  --port 8082 \
  --ctx-size 8192 \
  --n-gpu-layers 35 \
  --threads 24 \
  --alias kitty-f16
```

### 2. Configure Environment

```bash
# Enable LangGraph routing
export BRAIN_USE_LANGGRAPH=true
export BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100

# Ensure multi-server configuration
export LLAMACPP_Q4_HOST=http://localhost:8083
export LLAMACPP_Q4_ALIAS=kitty-q4
export LLAMACPP_F16_HOST=http://localhost:8082
export LLAMACPP_F16_ALIAS=kitty-f16
```

### 3. Start KITTY Services

```bash
# Start all services
./ops/scripts/start-kitty.sh

# Verify Brain service is running
curl http://localhost:8080/health
```

---

## Testing Order & Procedures

### Phase 1: Unit Tests (No Servers Required)

**Purpose**: Validate logic without llama.cpp
**Duration**: 5 minutes

```bash
cd /home/user/KITT

# Test 1: ComplexityAnalyzer scoring
pytest tests/unit/test_complexity_analyzer.py -v

# Expected: All 230 assertions pass
# Validates: Token count, technical density, multi-step detection,
#            ambiguity scoring, tool count estimation, routing recommendations

# Test 2: RouterGraph workflow
pytest tests/unit/test_router_graph.py -v

# Expected: All 70+ assertions pass
# Validates: Node execution, state transitions, conditional edges,
#            error handling, metadata collection
```

**✓ Success Criteria**:
- All tests pass with 0 failures
- No import errors
- Mock clients work correctly

---

### Phase 2: Integration Tests (Requires Servers)

**Purpose**: Validate with real llama.cpp servers
**Duration**: 30 minutes

#### Test 2.1: Q4 Simple Query (No Escalation)

```bash
# Test via CLI
kitty-cli say "Hello KITTY, how are you today?"

# Monitor logs
tail -f .logs/reasoning.log

# Expected behavior:
# - LangGraph routing enabled message
# - Intake → Memory → Complexity → Response nodes executed
# - Complexity score < 0.3 (simple query)
# - Q4 model used (LOCAL tier)
# - No F16 escalation
# - Response returned quickly (< 2s)
# - Confidence > 0.8
```

**✓ Success Criteria**:
- Response makes sense and is friendly
- Logs show: `"Using LangGraph routing for this request"`
- Logs show: `"Q4 response sufficient, no F16 escalation needed"`
- Latency < 2 seconds
- Tier: LOCAL

---

#### Test 2.2: Q4 Medium Complexity (No Escalation)

```bash
kitty-cli say "Design a simple bracket for a 10mm bolt"

# Expected behavior:
# - Complexity score 0.4-0.6 (medium)
# - Tool selection node executed
# - Q4 handles response
# - Confidence > 0.75 (no escalation)
# - Response includes design considerations
```

**✓ Success Criteria**:
- Response discusses bracket design
- Tools considered (coding.generate or cad.generate_model)
- No F16 escalation
- Confidence ≥ 0.75

---

#### Test 2.3: Q4 → F16 Escalation (Low Confidence)

```bash
kitty-cli say "Explain the detailed thermodynamic principles of heat exchangers with comprehensive analysis"

# Expected behavior:
# - Complexity score > 0.7 (high complexity)
# - Q4 generates initial response
# - Q4 confidence < 0.75 OR complexity triggers escalation
# - F16 escalation node executed
# - Deep reasoner workflow: decomposition → reasoning → synthesis
# - F16 response replaces Q4 response
# - Final confidence > 0.8
# - Latency 5-10 seconds (F16 processing)
```

**✓ Success Criteria**:
- Logs show: `"Escalating to F16 deep reasoner"`
- Logs show: `"Decomposed into X sub-problems"`
- Logs show: `"Completed reasoning step X/5"`
- Logs show: `"F16 escalation complete: confidence=0.XX"`
- Response is detailed and comprehensive
- Tier: FRONTIER
- Metadata includes: f16_reasoning_steps, f16_sub_problems

---

#### Test 2.4: Q4 → F16 Escalation (Explicit Deep Reasoning)

```bash
kitty-cli say "Provide a detailed analysis of quantum entanglement with step-by-step reasoning"

# Expected behavior:
# - Query contains "detailed analysis" and "step-by-step reasoning"
# - Complexity analyzer flags requires_deep_reasoning=true
# - Automatic F16 escalation regardless of Q4 confidence
# - F16 shows explicit reasoning steps in response
```

**✓ Success Criteria**:
- F16 escalation occurs immediately after complexity analysis
- Response includes numbered reasoning steps
- High confidence (> 0.85)

---

#### Test 2.5: F16 Fallback on Failure

```bash
# Manually stop F16 server to test fallback
# Terminal 2: Ctrl+C to stop F16 server

kitty-cli say "Explain quantum mechanics in great detail"

# Expected behavior:
# - Q4 generates response
# - Escalation attempted to F16
# - F16 connection fails
# - Fallback to Q4 response
# - Warning logged but request succeeds
```

**✓ Success Criteria**:
- Logs show: `"F16 escalation failed: ..."`
- Logs show: `"escalation_reason": "F16 escalation error: ..."`
- Q4 response returned (not error)
- Request completes successfully
- escalated_to_f16 = false

**Cleanup**: Restart F16 server for remaining tests

---

### Phase 3: A/B Testing Validation

**Purpose**: Verify gradual rollout works
**Duration**: 15 minutes

#### Test 3.1: 0% Rollout (Disabled)

```bash
export BRAIN_LANGGRAPH_ROLLOUT_PERCENT=0

# Restart Brain service
docker compose restart brain-api

# Send 10 queries
for i in {1..10}; do
  kitty-cli say "Query $i: Hello KITTY"
done

# Expected: All use traditional router (not LangGraph)
```

**✓ Success Criteria**:
- Logs show: `"BrainOrchestrator initialized with traditional routing"`
- No LangGraph routing messages
- All queries use BrainRouter

---

#### Test 3.2: 50% Rollout (A/B Testing)

```bash
export BRAIN_LANGGRAPH_ROLLOUT_PERCENT=50

# Restart Brain service
docker compose restart brain-api

# Send 20 queries with different conversation IDs
# (Hash-based routing ensures consistency per conversation_id)

python3 << 'EOF'
import requests
import hashlib

for i in range(20):
    conv_id = f"test_conv_{i}"
    hash_val = hash(conv_id) % 100

    response = requests.post(
        "http://localhost:8080/api/query",
        json={
            "conversation_id": conv_id,
            "request_id": f"req_{i}",
            "prompt": f"Hello KITTY {i}",
            "user_id": "test_user"
        }
    )

    # Check if LangGraph was used
    result = response.json()
    used_langgraph = result.get("metadata", {}).get("langgraph", False)

    print(f"Conv {i}: hash={hash_val}, langgraph={used_langgraph}")
EOF

# Expected: ~50% use LangGraph, ~50% use traditional router
```

**✓ Success Criteria**:
- Approximately 50% of requests use LangGraph
- Same conversation_id always routes to same method (consistent)
- No errors or failures

---

#### Test 3.3: 100% Rollout (Full Deployment)

```bash
export BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100

# Restart Brain service
docker compose restart brain-api

# Send multiple queries
for i in {1..5}; do
  kitty-cli say "Test query $i"
done

# Expected: All use LangGraph
```

**✓ Success Criteria**:
- All queries show: `"Using LangGraph routing for this request"`
- No traditional router usage
- All queries complete successfully

---

### Phase 4: Performance Benchmarking

**Purpose**: Measure latency, token usage, cost
**Duration**: 30 minutes

#### Test 4.1: Q4 Latency Baseline

```bash
# Send 10 simple queries (Q4 only, no escalation)
python3 << 'EOF'
import requests
import time

latencies = []

for i in range(10):
    start = time.time()

    response = requests.post(
        "http://localhost:8080/api/query",
        json={
            "conversation_id": f"latency_test_{i}",
            "request_id": f"req_{i}",
            "prompt": "Hello KITTY",
            "user_id": "test_user"
        }
    )

    end = time.time()
    latency = (end - start) * 1000
    latencies.append(latency)

    print(f"Query {i}: {latency:.0f}ms")

import statistics
print(f"\nQ4 Latency Statistics:")
print(f"  Mean: {statistics.mean(latencies):.0f}ms")
print(f"  P50: {statistics.median(latencies):.0f}ms")
print(f"  P95: {sorted(latencies)[int(len(latencies) * 0.95)]:.0f}ms")
print(f"  Max: {max(latencies):.0f}ms")
EOF
```

**✓ Success Criteria**:
- P95 latency < 1500ms
- Mean latency < 1000ms
- Consistent performance across runs

---

#### Test 4.2: F16 Latency Measurement

```bash
# Send 5 complex queries (F16 escalation)
python3 << 'EOF'
import requests
import time

latencies = []
complex_prompt = "Explain the detailed thermodynamic principles of heat exchangers with comprehensive multi-step analysis"

for i in range(5):
    start = time.time()

    response = requests.post(
        "http://localhost:8080/api/query",
        json={
            "conversation_id": f"f16_test_{i}",
            "request_id": f"req_{i}",
            "prompt": complex_prompt,
            "user_id": "test_user"
        }
    )

    end = time.time()
    latency = (end - start) * 1000
    latencies.append(latency)

    result = response.json()
    escalated = result.get("metadata", {}).get("escalated_to_f16", False)
    reasoning_steps = result.get("metadata", {}).get("f16_reasoning_steps", 0)

    print(f"Query {i}: {latency:.0f}ms, escalated={escalated}, steps={reasoning_steps}")

import statistics
print(f"\nF16 Latency Statistics:")
print(f"  Mean: {statistics.mean(latencies):.0f}ms")
print(f"  P95: {sorted(latencies)[int(len(latencies) * 0.95)]:.0f}ms")
print(f"  Max: {max(latencies):.0f}ms")
EOF
```

**✓ Success Criteria**:
- P95 latency < 10000ms (10 seconds)
- Mean latency 5000-8000ms
- All queries escalated to F16
- Reasoning steps = 3-5

---

#### Test 4.3: Cost Analysis (Token Usage)

```bash
# Monitor token usage from logs
grep "total_tokens" .logs/reasoning.log | tail -20

# Calculate approximate cost
# Q4: $0.0001 per query (local, free)
# F16: $0.0001 per query (local, free)
# vs Cloud API: $0.002-0.06 per query

# Expected savings: 100% (all local)
```

**✓ Success Criteria**:
- Zero cloud API costs
- All queries served locally
- Token counts logged for analysis

---

### Phase 5: Stress Testing

**Purpose**: Validate under load
**Duration**: 20 minutes

#### Test 5.1: Concurrent Queries (Q4)

```bash
# Send 20 concurrent simple queries
python3 << 'EOF'
import requests
import concurrent.futures
import time

def send_query(i):
    start = time.time()
    try:
        response = requests.post(
            "http://localhost:8080/api/query",
            json={
                "conversation_id": f"stress_q4_{i}",
                "request_id": f"req_{i}",
                "prompt": f"Hello KITTY {i}",
                "user_id": "test_user"
            },
            timeout=30
        )
        latency = (time.time() - start) * 1000
        return {"success": True, "latency": latency, "status": response.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)}

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
    results = list(executor.map(send_query, range(20)))

success_count = sum(1 for r in results if r["success"])
latencies = [r["latency"] for r in results if r["success"]]

print(f"Success rate: {success_count}/20 ({success_count/20*100:.1f}%)")
print(f"Mean latency: {sum(latencies)/len(latencies):.0f}ms")
print(f"Max latency: {max(latencies):.0f}ms")
EOF
```

**✓ Success Criteria**:
- Success rate ≥ 95%
- Mean latency < 3000ms
- No crashes or errors

---

#### Test 5.2: Concurrent Queries (Mixed Q4/F16)

```bash
# Send 10 concurrent queries (mix of simple and complex)
python3 << 'EOF'
import requests
import concurrent.futures
import time

queries = [
    "Hello KITTY",  # Simple (Q4)
    "Explain quantum entanglement in detail",  # Complex (F16)
    "Design a bracket",  # Medium (Q4)
    "Provide comprehensive analysis of thermodynamics",  # Complex (F16)
    "What time is it?",  # Simple (Q4)
] * 2  # Repeat twice = 10 queries

def send_query(i, prompt):
    start = time.time()
    try:
        response = requests.post(
            "http://localhost:8080/api/query",
            json={
                "conversation_id": f"stress_mixed_{i}",
                "request_id": f"req_{i}",
                "prompt": prompt,
                "user_id": "test_user"
            },
            timeout=30
        )
        latency = (time.time() - start) * 1000
        result = response.json()
        escalated = result.get("metadata", {}).get("escalated_to_f16", False)
        return {"success": True, "latency": latency, "escalated": escalated}
    except Exception as e:
        return {"success": False, "error": str(e)}

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(lambda x: send_query(x[0], x[1]), enumerate(queries)))

success_count = sum(1 for r in results if r["success"])
escalated_count = sum(1 for r in results if r.get("escalated", False))

print(f"Success rate: {success_count}/10 ({success_count/10*100:.1f}%)")
print(f"Escalated to F16: {escalated_count}/10")
EOF
```

**✓ Success Criteria**:
- Success rate ≥ 90%
- Complex queries escalate to F16
- No server crashes

---

### Phase 6: Edge Cases & Error Handling

**Purpose**: Validate robustness
**Duration**: 20 minutes

#### Test 6.1: Empty Query

```bash
kitty-cli say ""

# Expected: Handled gracefully with error message
```

**✓ Success Criteria**:
- No crash
- Appropriate error response
- Complexity score = 0.0

---

#### Test 6.2: Very Long Query

```bash
# Generate 1000-word query
python3 -c "print('Design a bracket ' * 500)" | kitty-cli say "$(cat)"

# Expected: Handled, may escalate to F16 due to high token count
```

**✓ Success Criteria**:
- Query processed successfully
- High complexity score (> 0.8)
- Likely escalates to F16

---

#### Test 6.3: Unicode and Special Characters

```bash
kitty-cli say "设计一个支架 🔧 with émojis and spëcial çharacters"

# Expected: Handled correctly
```

**✓ Success Criteria**:
- No parsing errors
- Response makes sense

---

#### Test 6.4: Rapid Sequential Queries (Same Conversation)

```bash
# Send 5 queries rapidly in same conversation
for i in {1..5}; do
  kitty-cli say "Query $i in conversation" &
done
wait

# Expected: All queries processed, memory context accumulates
```

**✓ Success Criteria**:
- All queries complete
- Conversation state maintained
- Memory stores all interactions

---

### Phase 7: Memory Integration

**Purpose**: Validate memory retrieval in reasoning
**Duration**: 15 minutes

#### Test 7.1: Memory Context in Q4

```bash
# First query: Establish context
kitty-cli say "My favorite bolt size is 10mm"

# Second query: Reference context
kitty-cli say "Design a bracket for my favorite bolt size"

# Expected: Q4 retrieves memory, uses 10mm in response
```

**✓ Success Criteria**:
- Second response mentions 10mm
- Logs show: `"Retrieved X memories"`
- Memory context included in prompt

---

#### Test 7.2: Memory Context in F16

```bash
# First query: Complex context
kitty-cli say "I'm working on a heat exchanger project with aluminum materials"

# Second query: Complex query referencing context
kitty-cli say "Provide detailed analysis of thermal conductivity considerations for my project"

# Expected: F16 escalation with memory context included
```

**✓ Success Criteria**:
- F16 response references aluminum and heat exchanger
- Memory context passed to deep reasoner
- Contextually accurate response

---

## Test Results Template

**Copy this template to record results**:

```markdown
# LangGraph Testing Results

**Date**: YYYY-MM-DD
**Tester**: [Your Name]
**Environment**:
- Q4 Model: [Model name and quant]
- F16 Model: [Model name and quant]
- Q4 Port: 8083
- F16 Port: 8082

## Phase 1: Unit Tests
- [ ] test_complexity_analyzer.py: PASS / FAIL
- [ ] test_router_graph.py: PASS / FAIL

## Phase 2: Integration Tests
- [ ] Test 2.1 (Q4 Simple): PASS / FAIL - Latency: ___ms
- [ ] Test 2.2 (Q4 Medium): PASS / FAIL - Latency: ___ms
- [ ] Test 2.3 (Q4→F16 Escalation): PASS / FAIL - Latency: ___ms
- [ ] Test 2.4 (Explicit Deep Reasoning): PASS / FAIL - Latency: ___ms
- [ ] Test 2.5 (F16 Fallback): PASS / FAIL

## Phase 3: A/B Testing
- [ ] Test 3.1 (0% Rollout): PASS / FAIL
- [ ] Test 3.2 (50% Rollout): PASS / FAIL - LangGraph usage: ___%
- [ ] Test 3.3 (100% Rollout): PASS / FAIL

## Phase 4: Performance
- [ ] Test 4.1 (Q4 Latency): P95: ___ms, Mean: ___ms
- [ ] Test 4.2 (F16 Latency): P95: ___ms, Mean: ___ms
- [ ] Test 4.3 (Cost Analysis): Cloud cost: $0 (all local)

## Phase 5: Stress Testing
- [ ] Test 5.1 (20 Concurrent Q4): Success: __%
- [ ] Test 5.2 (10 Mixed Q4/F16): Success: __%

## Phase 6: Edge Cases
- [ ] Test 6.1 (Empty Query): PASS / FAIL
- [ ] Test 6.2 (Long Query): PASS / FAIL
- [ ] Test 6.3 (Unicode): PASS / FAIL
- [ ] Test 6.4 (Rapid Sequential): PASS / FAIL

## Phase 7: Memory Integration
- [ ] Test 7.1 (Memory in Q4): PASS / FAIL
- [ ] Test 7.2 (Memory in F16): PASS / FAIL

## Issues Found
1. [Issue description]
2. [Issue description]

## Overall Assessment
- Ready for production: YES / NO / PARTIAL
- Recommended rollout: __%
- Notes: [Additional observations]
```

---

## Troubleshooting

### Issue: LangGraph not routing

**Check**:
```bash
echo $BRAIN_USE_LANGGRAPH  # Should be "true"
docker compose logs brain-api | grep "LangGraph"
```

**Fix**: Ensure environment variables are set and Brain service restarted.

---

### Issue: F16 not escalating

**Check**:
```bash
# Verify F16 server is running
curl http://localhost:8082/health

# Check escalation logs
grep "Escalating to F16" .logs/reasoning.log
```

**Fix**: Ensure F16 server is running, check enable_deep_reasoner=true in router_graph.

---

### Issue: High latency

**Check**:
- GPU layers: `n-gpu-layers` should be 35+ for M3 Ultra
- Context size: `ctx-size` should be 8192+
- Threads: `threads` should be 24 for M3 Ultra

**Fix**: Adjust llama-server parameters for optimal performance.

---

## Next Steps After Testing

1. **If all tests pass**: Proceed with gradual production rollout
2. **If issues found**: Document in GitHub issue, fix, re-test
3. **Performance concerns**: Adjust model parameters, consider quantization
4. **Ready for Phase 3**: Begin memory-augmented conversation graph

---

**Questions or Issues?**: Document in `test-results-YYYY-MM-DD.md` and review with team.
