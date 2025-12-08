# Parallel Agent Orchestration Testing Plan

## Overview

This document outlines a comprehensive testing strategy for KITTY's parallel agent orchestration system. Tests progress from basic infrastructure verification through complex multi-agent scenarios.

---

## Prerequisites

Before testing, verify infrastructure is ready:

```bash
# Check llama.cpp servers are running
lsof -nP -iTCP:8083 -sTCP:LISTEN  # Q4 (6 slots)
lsof -nP -iTCP:8084 -sTCP:LISTEN  # Summary (4 slots)
lsof -nP -iTCP:8086 -sTCP:LISTEN  # Vision (4 slots)
lsof -nP -iTCP:8087 -sTCP:LISTEN  # Coder (4 slots)

# Check Ollama is running
curl http://localhost:11434/api/tags

# Verify parallel is enabled
docker-compose -f infra/compose/docker-compose.yml exec brain python3 -c \
  "from brain.agents.parallel.integration import get_parallel_integration; \
   pi = get_parallel_integration(); \
   print(f'Enabled: {pi.enabled}, Rollout: {pi.rollout_percent}%')"
```

---

## Phase 1: Unit Tests (Isolated Components)

### 1.1 Types & Registry

```bash
# Run from KITT root
PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
  services/brain/tests/agents/parallel/test_types.py -v
```

**Test cases:**
- [ ] `ModelTier` enum has all 5 tiers
- [ ] `TaskStatus` transitions (PENDING → IN_PROGRESS → COMPLETED/FAILED)
- [ ] `KittyTask` initialization and mark_* methods
- [ ] `AgentExecutionMetrics` latency calculation

### 1.2 Slot Manager

```bash
PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
  services/brain/tests/agents/parallel/test_slot_manager.py -v
```

**Test cases:**
- [ ] Acquire slot on available endpoint
- [ ] Release slot correctly decrements count
- [ ] Fallback to secondary tier when primary exhausted
- [ ] Slot exhaustion returns None (no infinite loop)
- [ ] Concurrent acquire stress test (8+ simultaneous)

### 1.3 Complexity Estimation

```bash
PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
  services/brain/tests/agents/parallel/test_integration.py::test_complexity -v
```

**Test cases:**
- [ ] Simple queries score < 0.6 ("What is Python?")
- [ ] Complex queries score >= 0.6 ("Research and compare React vs Vue, then design a component library")
- [ ] Multi-question prompts get complexity boost
- [ ] Keyword triggers work ("comprehensive", "in-depth", "step by step")

---

## Phase 2: Integration Tests (Component Interactions)

### 2.1 LLM Adapter

```bash
PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
  services/brain/tests/agents/parallel/test_llm_adapter.py -v
```

**Test cases:**
- [ ] Generate with Q4 tier succeeds
- [ ] Generate with GPTOSS tier succeeds
- [ ] Slot exhaustion gracefully fails
- [ ] generate_for_agent() uses correct tier

### 2.2 Task Decomposition

**Manual test:**
```python
import asyncio
from brain.agents.parallel.parallel_manager import ParallelTaskManager

async def test_decompose():
    manager = ParallelTaskManager()
    tasks = await manager.decompose_goal(
        "Research the best 3D printing materials for outdoor use, "
        "design a birdhouse model, and prepare slicing instructions"
    )
    print(f"Decomposed into {len(tasks)} tasks:")
    for t in tasks:
        print(f"  - [{t.agent_type}] {t.description}")
    return tasks

asyncio.run(test_decompose())
```

**Expected:** 3-5 tasks assigned to researcher, cad_designer, fabricator

### 2.3 Parallel Execution

**Test dependency resolution:**
```python
import asyncio
from brain.agents.parallel.parallel_manager import ParallelTaskManager
from brain.agents.parallel.types import KittyTask, TaskStatus

async def test_parallel_execution():
    manager = ParallelTaskManager()

    # Create tasks with dependencies
    tasks = [
        KittyTask(id="1", description="Research topic", agent_type="researcher"),
        KittyTask(id="2", description="Analyze findings", agent_type="analyst", depends_on=["1"]),
        KittyTask(id="3", description="Generate code", agent_type="coder"),  # Independent
    ]

    results = await manager.execute_parallel(tasks)

    # Task 1 and 3 should run in parallel, task 2 after task 1
    print(f"Results: {len(results)} completed")
    return results

asyncio.run(test_parallel_execution())
```

---

## Phase 3: End-to-End Tests (Full Pipeline)

### 3.1 Simple Complexity Bypass

**Test:** Simple queries should NOT trigger parallel orchestration.

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the capital of France?", "conversation_id": "test-simple"}' \
  | jq '.metadata.parallel_execution // "not parallel"'
```

**Expected:** `"not parallel"` (falls through to traditional routing)

### 3.2 Complex Query Triggers Parallel

**Test:** Complex multi-step goals should trigger parallel.

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Research the best materials for 3D printing drone frames, then design a simple quadcopter frame, and provide slicing recommendations for optimal strength",
    "conversation_id": "test-parallel-1"
  }' | jq '{
    parallel: .metadata.parallel_execution,
    tasks_count: .metadata.tasks_count,
    latency_ms: .metadata.parallel_metrics.total_latency_ms
  }'
```

**Expected:**
```json
{
  "parallel": true,
  "tasks_count": 3,
  "latency_ms": <15000
}
```

### 3.3 Multi-Agent Coordination

**Test:** Verify all 8 agent types can be invoked.

| Query | Expected Agents |
|-------|-----------------|
| "Research quantum computing advances in 2025" | researcher |
| "Analyze the pros and cons of microservices" | reasoner |
| "Design a phone stand with cable management" | cad_designer |
| "Prepare this model for the Bamboo H2D printer" | fabricator |
| "Write a Python script to parse JSON logs" | coder |
| "Describe what you see in this image" + image | vision_analyst |
| "Search my memories for PLA settings" | analyst |
| "Summarize this long document briefly" | summarizer |

### 3.4 Slot Exhaustion & Recovery

**Test:** System handles slot exhaustion gracefully.

```bash
# Launch 10 parallel complex queries simultaneously
for i in {1..10}; do
  curl -X POST http://localhost:8080/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"Research topic $i and analyze comprehensively\", \"conversation_id\": \"stress-$i\"}" &
done
wait
```

**Expected:** All complete (some may queue/wait), no crashes

### 3.5 Fallback on Failure

**Test:** If parallel execution fails, falls back to traditional routing.

```bash
# Temporarily stop a critical server
./ops/scripts/llama/stop.sh

# Send complex query
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Research and analyze parallel computing trends"}' \
  | jq '.output | length'

# Restart servers
./ops/scripts/llama/start.sh
```

**Expected:** Response still generated (via traditional routing fallback)

---

## Phase 4: Performance Benchmarks

### 4.1 Latency Comparison

**Methodology:** Same complex query, parallel vs sequential (disable parallel with `ENABLE_PARALLEL_AGENTS=false`)

```bash
# Benchmark query
QUERY="Research the history of 3D printing, analyze current market trends, design a simple phone holder, and provide material recommendations"

# Run 5x with parallel enabled, record avg latency
# Run 5x with parallel disabled, record avg latency
```

**Expected Improvement:** 2.5-3.5x faster with parallel

### 4.2 Throughput Test

**Test:** Concurrent request handling.

```bash
# Using Apache Bench or similar
ab -n 20 -c 5 -p query.json -T application/json \
  http://localhost:8080/api/chat
```

**Metrics to capture:**
- Requests/second
- Mean response time
- 95th percentile latency
- Failed requests

### 4.3 Resource Utilization

**Monitor during load test:**
```bash
# GPU utilization (Metal doesn't have nvidia-smi, use Activity Monitor or powermetrics)
sudo powermetrics --samplers gpu_power -i 1000

# CPU/Memory
top -l 5 -stats pid,command,cpu,mem | grep llama

# Slot usage (add endpoint to expose)
curl http://localhost:8000/api/parallel/status
```

**Target:** >50% GPU utilization during parallel execution

---

## Phase 5: Edge Cases & Error Handling

### 5.1 Empty Task Decomposition

**Test:** Goal that can't be decomposed into sub-tasks.

```bash
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi there!"}'
```

**Expected:** Falls through to traditional routing (complexity < threshold)

### 5.2 Circular Dependencies

**Test:** Malformed dependency graph doesn't cause infinite loop.

*This requires injecting test data or mocking - manual verification*

### 5.3 Partial Task Failure

**Test:** One task fails, others complete, synthesis still works.

*Simulate by killing one llama.cpp server mid-execution*

### 5.4 Timeout Handling

**Test:** Very slow task hits timeout, doesn't block others.

```bash
# Set low timeout for testing
PARALLEL_AGENT_TASK_TIMEOUT_S=5 docker-compose up -d brain

# Send query requiring slow operation
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Research everything about the complete history of computing"}'
```

**Expected:** Partial results with timeout indication

---

## Phase 6: UI/UX Validation

### 6.1 Voice Mode

- [ ] Complex voice query triggers parallel
- [ ] Voice summary is generated and spoken
- [ ] Response feels cohesive (not like stitched fragments)

### 6.2 Shell/Chat Mode

- [ ] Metadata shows parallel execution details
- [ ] Task breakdown visible in verbose mode
- [ ] Streaming works (or graceful fallback to non-streaming)

### 6.3 Research Mode

- [ ] Research pipeline integrates with parallel where appropriate
- [ ] No conflicts between research graph and parallel orchestration

---

## Test Execution Checklist

| Phase | Test | Status | Notes |
|-------|------|--------|-------|
| 1.1 | Types & Registry | ⬜ | |
| 1.2 | Slot Manager | ⬜ | |
| 1.3 | Complexity Estimation | ⬜ | |
| 2.1 | LLM Adapter | ⬜ | |
| 2.2 | Task Decomposition | ⬜ | |
| 2.3 | Parallel Execution | ⬜ | |
| 3.1 | Simple Bypass | ⬜ | |
| 3.2 | Complex Triggers | ⬜ | |
| 3.3 | Multi-Agent | ⬜ | |
| 3.4 | Slot Exhaustion | ⬜ | |
| 3.5 | Fallback | ⬜ | |
| 4.1 | Latency Benchmark | ⬜ | |
| 4.2 | Throughput | ⬜ | |
| 4.3 | Resource Util | ⬜ | |
| 5.1 | Empty Decompose | ⬜ | |
| 5.2 | Circular Deps | ⬜ | |
| 5.3 | Partial Failure | ⬜ | |
| 5.4 | Timeout | ⬜ | |
| 6.1 | Voice Mode | ⬜ | |
| 6.2 | Shell Mode | ⬜ | |
| 6.3 | Research Mode | ⬜ | |

---

## Quick Smoke Test Commands

Run these for a quick health check:

```bash
# 1. Infrastructure check
./ops/scripts/llama/status.sh 2>/dev/null || lsof -nP -iTCP:8083,8084,8086,8087 -sTCP:LISTEN

# 2. Parallel enabled check
curl -s http://localhost:8000/api/health | jq '.parallel_agents // "not exposed"'

# 3. Simple query (should NOT be parallel)
curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}' | jq '.output[:50]'

# 4. Complex query (SHOULD be parallel)
time curl -s -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Research React best practices and compare with Vue, then design a component architecture"}' \
  | jq '{parallel: .metadata.parallel_execution, tasks: .metadata.tasks_count}'
```

---

## Known Limitations (V1)

1. **No nested parallelism** - Agents cannot spawn sub-agents
2. **In-process slot tracking** - Doesn't share across replicas (add Redis later)
3. **Soft tool guidance only** - Tools aren't hard-filtered per agent
4. **No streaming** - Parallel execution returns complete response

---

## Rollback Procedure

If issues arise, disable parallel orchestration:

```bash
# In .env
ENABLE_PARALLEL_AGENTS=false

# Restart
docker-compose -f infra/compose/docker-compose.yml up -d brain
```

System will fall back to traditional sequential routing.
