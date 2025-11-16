# KITT Data Flow Analysis - Executive Summary

## Overview
KITT is a distributed AI orchestration system with:
- **14 services** communicating via HTTP, MQTT, PostgreSQL, Redis, and Qdrant
- **4 async autonomous job schedules** running every 15 minutes to daily
- **5 state storage layers** with critical consistency gaps
- **No message queue** - relying on HTTP for critical async operations

---

## Critical Issues (Must Fix)

### 1. Conversation State Lost on Service Restart
**Severity:** CRITICAL | **Impact:** Double execution of hazard operations

- Pending confirmations stored in-memory only
- On brain restart: all confirmation state evaporates
- User says "unlock" → treated as new request → double confirmation issued
- **Fix:** Persist to PostgreSQL, warm cache on startup (2-3 days)

### 2. Unbounded Semantic Cache
**Severity:** CRITICAL | **Impact:** Stale responses served indefinitely

- Redis Streams grow without bound (no TTL, no eviction)
- After 100K requests: 10MB stream, O(N) lookup time
- Cache invalidation: never happens
- **Fix:** Add TTL, implement proper cache hit ratio, add invalidation endpoints (1 day)

### 3. Autonomous Jobs Not Persisted
**Severity:** CRITICAL | **Impact:** Job schedules lost on restart

- APScheduler uses in-process memory (no persistent job store)
- If brain crashes: weekly_research_cycle, daily health checks all forgotten
- No observability: can't tell if jobs are running
- **Fix:** Use PostgreSQL job store or Kubernetes CronJobs (1-3 days)

### 4. No Distributed Locking
**Severity:** CRITICAL | **Impact:** Race conditions and inconsistent state

- Multiple jobs access same tables: projects, tasks, goals
- task_execution_cycle (every 15 min) + project_generation_cycle = race condition
- PostgreSQL isolation=read_committed insufficient
- **Fix:** Add database locks or Redis mutex (1-2 days)

### 5. Database Writes Without Await (Silent Failures)
**Severity:** CRITICAL | **Impact:** Data loss, incomplete audit trail

```python
try:
    record_conversation_message(...)  # ← NOT AWAITED!
except Exception:
    pass  # ← Silently ignored
```
- Audit trail incomplete
- Messages lost on network partition
- **Fix:** Await all writes or explicit 202 Accepted pattern (2 hours)

---

## High-Priority Issues

### 6. Brain Service Startup Bottleneck (5-10 seconds)
- Sequential initialization of PostgreSQL, Redis, MCP servers, research graph
- Kubernetes liveness probe may timeout
- **Fix:** Parallel initialization, deferred initialization (Medium complexity)

### 7. Task Execution is Blocking and Sequential
- Every 15 minutes, tasks execute one-by-one
- If one service is slow: all others blocked
- No timeout, no retry, no observability
- **Fix:** Make concurrent with asyncio.gather, add timeouts (2-3 days)

### 8. Gateway is Single Point of Failure
- All client requests → single gateway:8080
- No load balancer visible
- **Fix:** Add load balancer, scale horizontally (1 day)

### 9. PostgreSQL Connection Pool Too Small
- Default: 5 + 10 overflow = 15 total connections
- At 20+ concurrent requests: connection queue forms
- **Fix:** Increase pool_size to 20, max_overflow to 40 (30 min)

### 10. Memory MCP Latency
- Embedding model runs on every query (100-500ms)
- Called 2x per request (search memories, store memories)
- **Fix:** Cache embeddings, use smaller model, conditional search (3-5 days)

---

## Architecture Findings

### Request Flow (Good)
```
CLI/UI → Gateway (8080) → Brain (8000) → Services
├─ Memory search (Qdrant)
├─ Routing decision (local/MCP/frontier)
└─ Response recording (PostgreSQL async)
```

### Autonomous Operations (Fragile)
```
APScheduler (in-process memory)
├─ daily_health_check (12:00 UTC)
├─ weekly_research_cycle (Mon 13:00 UTC) ← jobs lost on restart
├─ project_generation_cycle (12:30 UTC) ← race condition
├─ task_execution_cycle (every 15 min) ← blocking, sequential
└─ outcome_measurement_cycle (14:00 UTC) ← no recovery
```

### State Management (Fragmented)
```
In-Memory       ← Fast, ephemeral (CRITICAL: lost on restart)
  ↓ (fire-and-forget)
MQTT Retained   ← Unreliable (lost if Mosquitto restarts)
  ↓ (async)
PostgreSQL      ← Durable but slow, write lag 100ms+
  ↓ (cache layer)
Redis Streams   ← Unbounded growth, no TTL, stale cache
  ↓ (vector search)
Qdrant          ← Vector DB, single insert only
```

### Communication (No Message Queue)
- HTTP: Request/response (blocking)
- MQTT: Pub/sub (unreliable for critical messages)
- Missing: Kafka, RabbitMQ, or Redis Streams for task queue
- Result: No guaranteed delivery for autonomous operations

---

## Performance Bottlenecks

| Bottleneck | Severity | P99 Latency Impact | Fix |
|-----------|----------|------------------|-----|
| Brain startup | HIGH | 5-10s | Medium |
| Semantic cache lookup | MEDIUM | 50-500ms | Medium |
| Memory MCP embedding | MEDIUM | 100-500ms | Hard |
| MQTT context publish | MEDIUM | 50-100ms | Easy |
| Task execution | HIGH | 30-60s per task | Hard |
| PostgreSQL pool | LOW | 100ms+ queue | Easy |

**Estimated P99 Latency:** ~2150ms
- Routing: 1500ms (50% of latency)
- Overhead: 650ms (memory search 300ms, MQTT publish 100ms, etc.)

---

## Recommendations (Priority Order)

### Phase 1: Fix Data Loss Issues (1-2 weeks)
1. Persist conversation state to PostgreSQL ✓ Fixes #1
2. Implement cache TTL and invalidation ✓ Fixes #2
3. Migrate to persistent job store ✓ Fixes #3
4. Add distributed locking ✓ Fixes #4
5. Await all database writes ✓ Fixes #5

### Phase 2: Improve Observability (1 week)
1. Add distributed tracing (Jaeger/Tempo)
2. Add health checks for job schedules
3. Add metrics for cache hit rate, memory growth
4. Add slow query logging
5. Add task execution observability

### Phase 3: Performance (2-3 weeks)
1. Parallel brain startup
2. Concurrent task execution with asyncio.gather
3. Smaller/faster embedding model
4. Batch memory operations
5. Add request deduplication

### Phase 4: Architecture (Medium-term)
1. Add message queue (Kafka or Redis Streams)
2. Implement event sourcing for audit trail
3. Add distributed consensus for autonomy coordination
4. Migrate from in-process scheduler to Kubernetes CronJobs
5. Add load balancer and scale gateway horizontally

---

## Key Files Analyzed

**Brain Service:**
- app.py (lifespan initialization)
- orchestrator.py (request orchestration)
- routes/query.py (API endpoint)
- routing/router.py (routing decision)
- conversation/state.py (state management)
- autonomous/scheduler.py (job scheduling)
- autonomous/jobs.py (7 scheduled jobs)

**Supporting Services:**
- gateway/app.py (request proxy)
- broker/app.py (command broker)
- common/cache.py (semantic cache)
- common/db/models.py (data models)

**Infrastructure:**
- infra/compose/docker-compose.yml (14 services)

---

## Conclusion

KITT has a **well-designed request flow** but **fragile state management and autonomy orchestration**. The system will lose critical state on service restarts and has race conditions in autonomous operations.

**Estimated effort to fix critical issues:** 5-10 days
**Estimated effort for full refactor:** 3-4 weeks

Start with #1-5 (data loss), then move to observability and performance improvements.

---

See KITT_DATA_FLOW_ANALYSIS.md for complete technical details with ASCII diagrams.
