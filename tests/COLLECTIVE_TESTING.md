# Collective Meta-Agent Testing Guide

## Overview

This directory contains comprehensive tests for the Collective Meta-Agent integration.

## Test Files

### 1. Unit Tests (`unit/test_collective_graph.py`)

Tests the LangGraph state machine in isolation with mocked LLM calls.

**Test Coverage**:
- Individual node functions (n_plan, n_propose_council, n_propose_debate, n_judge)
- Graph construction and routing
- Full graph execution for all patterns (council, debate, pipeline)
- State accumulation across nodes
- Boundary conditions (k=2, k=7, empty tasks)
- Invalid pattern handling

**Run Unit Tests**:
```bash
# From repository root
pytest tests/unit/test_collective_graph.py -v

# With coverage
pytest tests/unit/test_collective_graph.py --cov=services/brain/src/brain/agents/collective
```

**Expected Results**:
- All tests should pass without requiring running services
- Fast execution (< 5 seconds total)
- 100% code coverage of graph nodes

---

### 2. Integration Tests (`integration/test_collective_api.py`)

Tests the API endpoints with live services (brain + gateway + llama.cpp).

**Test Coverage**:
- Brain API endpoint (`/api/collective/run`)
- Gateway proxy endpoint (`/api/collective/run`)
- All three patterns (council, debate, pipeline)
- Validation errors (invalid pattern, k out of range, missing task)
- Default parameters
- Boundary values
- Error forwarding through gateway

**Prerequisites**:
- Brain service running on port 8000
- Gateway service running on port 8080
- llama.cpp Q4 server running on port 8083
- llama.cpp F16 server running on port 8082

**Run Integration Tests**:
```bash
# Start services first
./ops/scripts/start-all.sh

# Run integration tests (fast tests only)
pytest tests/integration/test_collective_api.py -v -m "integration and not slow"

# Run all tests including slow Quality-First tests
pytest tests/integration/test_collective_api.py -v -m integration

# Run specific test class
pytest tests/integration/test_collective_api.py::TestCollectiveBrainAPI -v
```

**Expected Results**:
- Fast tests: < 2 minutes total (with Quality-First mode)
- Slow tests: 5-10 minutes (complex k=5 council, detailed debate)
- All status codes as expected (200 for success, 422 for validation errors)

---

### 3. Smoke Test (`smoke_test_collective.sh`)

Quick validation script for deployment verification.

**Test Coverage**:
- Health checks (brain + gateway)
- Council pattern (k=2)
- Debate pattern
- Validation errors (4 tests)
- Direct brain API access

**Run Smoke Test**:
```bash
# From repository root
./tests/smoke_test_collective.sh

# With custom endpoints
GATEWAY_BASE=http://localhost:8080 ./tests/smoke_test_collective.sh
```

**Expected Output**:
```
=========================================
Collective Meta-Agent Smoke Test
=========================================

1. Health Checks
Testing: Brain Health... PASS (HTTP 200)
Testing: Gateway Health... PASS (HTTP 200)

2. Council Pattern (k=2)
Testing: Council k=2... PASS (HTTP 200)

3. Debate Pattern
Testing: Debate... PASS (HTTP 200)

4. Validation Tests
Testing: Invalid pattern... PASS (HTTP 422)
Testing: k too low... PASS (HTTP 422)
Testing: k too high... PASS (HTTP 422)
Testing: Missing task... PASS (HTTP 422)

5. Direct Brain API
Testing: Brain Direct... PASS (HTTP 200)

=========================================
Test Summary: 9 passed, 0 failed
=========================================
All tests passed! ✓
```

**Execution Time**: 30-60 seconds (Quality-First mode)

---

## Test Markers

Tests are marked for selective execution:

- `@pytest.mark.integration` - Requires running services
- `@pytest.mark.slow` - Takes > 2 minutes (Quality-First complex queries)

**Examples**:
```bash
# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "integration and not slow"

# Run only slow tests
pytest -m slow
```

---

## Continuous Integration

For CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Unit Tests
  run: pytest tests/unit/test_collective_graph.py -v

- name: Start Services
  run: ./ops/scripts/start-all.sh

- name: Wait for Health
  run: |
    timeout 300 bash -c 'until curl -f http://localhost:8000/healthz; do sleep 5; done'
    timeout 300 bash -c 'until curl -f http://localhost:8080/healthz; do sleep 5; done'

- name: Integration Tests (Fast)
  run: pytest tests/integration/test_collective_api.py -v -m "integration and not slow" --timeout=180

- name: Smoke Test
  run: ./tests/smoke_test_collective.sh
```

---

## Troubleshooting

### Tests Fail with Connection Errors

**Symptom**: `ConnectionError: Connection refused`

**Solution**:
```bash
# Check services are running
curl http://localhost:8000/healthz
curl http://localhost:8080/healthz

# Check llama.cpp servers
curl http://localhost:8083/health
curl http://localhost:8082/health

# Restart services
./ops/scripts/stop-all.sh
./ops/scripts/start-all.sh
```

### Tests Timeout

**Symptom**: `ReadTimeout: Request timed out`

**Causes**:
1. Quality-First mode has 600s timeouts - tests may be slow
2. llama.cpp servers under heavy load
3. First query after model load is slow (warm-up)

**Solutions**:
```bash
# Monitor llama.cpp inference
tail -f .logs/llamacpp-q4.log .logs/llamacpp-f16.log

# Check GPU/CPU utilization
./ops/scripts/monitor/inference.sh 5

# Increase test timeout
pytest tests/integration/test_collective_api.py --timeout=300
```

### Tests Pass but Responses are Low Quality

**Symptom**: Tests pass but proposals are generic or verdict is brief

**Causes**:
1. Not in Quality-First mode (using Speed-First defaults)
2. Model not fully loaded
3. Context size too small

**Solutions**:
```bash
# Verify Quality-First configuration
grep -E "(BRAIN_REQUEST_TIMEOUT|MAX_REASONING_STEPS|VERBOSITY)" .env

# Check context sizes
curl http://localhost:8083/v1/models  # Should show 32K for Q4
curl http://localhost:8082/v1/models  # Should show 65K for F16

# Restart with Quality-First mode
cp .env.quality-first-example .env
./ops/scripts/stop-all.sh
./ops/scripts/start-all.sh
```

### Validation Tests Fail (Wrong Status Code)

**Symptom**: Expected 422, got 200

**Cause**: Pydantic validation not enforcing constraints

**Solution**:
```bash
# Check Pydantic version
pip show pydantic

# Verify router validation
curl -X POST http://localhost:8080/api/collective/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"Test","pattern":"invalid","k":3}' -v

# Should return 422 with validation error details
```

---

## Performance Benchmarks

**Quality-First Mode** (BRAIN_REQUEST_TIMEOUT=600, MAX_REASONING_STEPS=10):

| Test | Pattern | k | Expected Time | Actual Time (M3 Ultra) |
|------|---------|---|---------------|------------------------|
| Smoke (k=2) | council | 2 | 30-60s | ~45s |
| Integration (k=3) | council | 3 | 60-150s | ~90s |
| Integration (debate) | debate | 2 | 50-120s | ~75s |
| Slow (k=5 complex) | council | 5 | 120-300s | ~180s |

**Hardware**: Mac Studio M3 Ultra, 192 GB RAM, Metal GPU

**Variables Affecting Performance**:
- First query after model load: +30-60s (warm-up)
- Concurrent requests: Linear slowdown (no batching yet)
- Verbosity level: VERBOSITY=5 adds ~10-20% latency
- Context size: 32K Q4 / 65K F16 vs 2K default

---

## Future Test Enhancements

1. **Async Performance Tests**
   - Measure parallelization speedup when async nodes implemented
   - Benchmark concurrent council proposals

2. **Quality Metrics**
   - Add assertions on verdict length (> 100 chars for complex queries)
   - Validate proposal diversity (proposals should differ)
   - Check for hallucinations (invalid printer names, materials)

3. **Load Testing**
   - Test concurrent collective requests
   - Measure throughput (requests/minute)
   - Identify bottlenecks (Q4 vs F16 capacity)

4. **Regression Testing**
   - Store "golden" responses for specific prompts
   - Detect quality degradation after model changes
   - Track latency regressions

5. **End-to-End Workflows**
   - CLI integration tests
   - UI component tests
   - Tool registry validation

---

## Test Data

### Sample Tasks for Manual Testing

**Council Pattern**:
```json
{
  "task": "Compare PETG vs ABS vs ASA for outdoor furniture. Consider UV resistance, temperature range (-20°C to 50°C), and ease of printing on Voron 2.4.",
  "pattern": "council",
  "k": 3
}
```

**Debate Pattern**:
```json
{
  "task": "For a large functional bracket (250mm), should I prioritize layer adhesion (0.3mm layers, 260°C) or dimensional accuracy (0.15mm layers, 240°C)? Consider strength requirements and warping risk.",
  "pattern": "debate"
}
```

**Pipeline Pattern** (future):
```json
{
  "task": "Generate a Python script to analyze STL file dimensions and recommend optimal printer orientation",
  "pattern": "pipeline"
}
```

---

## Reporting Issues

When reporting test failures, include:

1. **Test command**: Exact pytest command run
2. **Environment**: OS, Python version, Docker version
3. **Service logs**:
   ```bash
   docker logs compose-brain-1 > brain.log
   docker logs compose-gateway-1 > gateway.log
   tail -100 .logs/llamacpp-q4.log > q4.log
   tail -100 .logs/llamacpp-f16.log > f16.log
   ```
4. **Test output**: Full pytest output with `-vv` flag
5. **Configuration**: Relevant .env variables
6. **System state**: Output of `./ops/scripts/monitor/inference.sh 1`

---

**Last Updated**: November 12, 2025
**Maintainer**: KITTY Development Team
