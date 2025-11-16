# P0 Batch Testing Guide

**Branch**: `claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB`
**Purpose**: Test all 5 critical P0 fixes after deployment
**Test Duration**: ~15-20 minutes
**Prerequisites**: PostgreSQL, Redis, brain service deployed

---

## Pre-Deployment: Run Migrations

All P0 fixes require database schema changes. Run migrations before testing:

```bash
cd /home/user/KITT/services/common
alembic upgrade head
```

**Verify migrations applied:**
```bash
psql $DATABASE_URL -c "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 5;"
```

**Expected output (should include)**:
- `f7g8h9i0j1k2` - Conversation state persistence
- `k1l2m3n4o5p6` - APScheduler job persistence

**Verify tables created:**
```bash
psql $DATABASE_URL -c "\dt" | grep -E "conversation_sessions|apscheduler_jobs"
```

**Expected:**
```
 public | conversation_sessions | table | ...
 public | apscheduler_jobs      | table | ...
```

---

## P0 #1: Research Graph Wiring (Real Tool Execution)

### What Changed
Research graph nodes now use real infrastructure components instead of simulated data:
- Real tool executor (Perplexity API, DuckDuckGo)
- Real permission gate (I/O Control, budget checks)
- Real model coordinator (AI synthesis)

### Test Steps

1. **Start brain service and check logs:**
```bash
docker-compose restart brain
docker-compose logs brain | grep "Research components registered"
```

**Expected:**
```
INFO: Research components registered: {'fully_wired': True, 'tool_executor': True, 'permission_gate': True, 'model_coordinator': True, ...}
```

2. **Trigger a research session** (via API or research endpoint):
```bash
curl -X POST http://localhost:8000/api/research/start \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is quantum computing?",
    "max_iterations": 2
  }'
```

3. **Check brain logs for real execution:**
```bash
docker-compose logs brain | grep -E "Executing.*tasks with real tool executor|Task.*executed with"
```

**Expected (NOT seeing "simulated execution"):**
```
INFO: Executing 3 tasks with real tool executor
INFO: Task task_1 executed with web_search: cost=$0.00
INFO: Task task_2 executed with research_deep: cost=$0.05
```

**✅ PASS**: Logs show "real tool executor", not "simulated execution"
**❌ FAIL**: Logs show "Tool executor not available, using simulated execution"

### Troubleshooting
If using simulated execution:
- Check `get_global_components()` returns non-None
- Verify `set_global_components()` was called in app.py startup
- Check brain service logs for component registration errors

---

## P0 #2: Persistent Conversation State

### What Changed
Conversation state (including hazard confirmations) now persists to PostgreSQL, preventing double-execution of dangerous operations after restart.

### Test Steps

1. **Create a conversation with pending confirmation:**
```python
from brain.conversation import SyncPersistentStateManager
from brain.app import app

# Get state manager
state_manager = app.state.conversation_state_manager

# Create conversation
state = state_manager.get_or_create("test-conv-123", user_id="test-user")

# Set pending confirmation (simulates hazard operation)
state.set_pending_confirmation(
    tool_name="delete_all_files",
    tool_args={"path": "/critical/data"},
    confirmation_phrase="DELETE ALL DATA",
    hazard_class="high",
    reason="Irreversible data deletion"
)

print("✅ Pending confirmation set")
```

2. **Verify persistence to database:**
```bash
psql $DATABASE_URL -c "
SELECT id, user_id, pending_confirmation
FROM conversation_sessions
WHERE id = 'test-conv-123';
"
```

**Expected:**
```
        id        |  user_id  |              pending_confirmation
------------------+-----------+--------------------------------------------------
 test-conv-123    | test-user | {"tool_name": "delete_all_files", "hazard_class": "high", ...}
```

3. **Restart brain service:**
```bash
docker-compose restart brain
sleep 5
```

4. **Retrieve conversation and verify pending confirmation survived:**
```python
from brain.conversation import SyncPersistentStateManager
from brain.app import app

state_manager = app.state.conversation_state_manager
state = state_manager.get("test-conv-123")

assert state is not None, "State should exist after restart"
assert state.pending_confirmation is not None, "Pending confirmation should be preserved"
assert state.pending_confirmation["tool_name"] == "delete_all_files"

print("✅ Pending confirmation survived restart")
```

**✅ PASS**: Pending confirmation exists after restart
**❌ FAIL**: `state.pending_confirmation` is None after restart

### Troubleshooting
If state not persisting:
- Check migration `f7g8h9i0j1k2` was applied
- Verify `conversation_sessions` table has `pending_confirmation` column
- Check brain logs for "Persisted conversation state" messages
- Ensure `auto_setup=True` in PostgreSQL pool config

---

## P0 #3: Database Write Safety (Graceful Shutdown)

### What Changed
Brain service now waits up to 30 seconds for in-flight database writes to complete before shutting down, preventing data loss.

### Test Steps

1. **Start a research session** (long-running):
```bash
curl -X POST http://localhost:8000/api/research/start \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Comprehensive analysis of renewable energy trends",
    "max_iterations": 10
  }' &
```

2. **Immediately restart brain service** (while research is running):
```bash
sleep 2
docker-compose restart brain
```

3. **Check shutdown logs for graceful shutdown:**
```bash
docker-compose logs brain | grep -E "Initiating graceful shutdown|Session manager shutdown"
```

**Expected:**
```
INFO: Initiating graceful shutdown for research session manager
INFO: Session manager shutdown: {'completed': 1, 'timeout': 0, 'failed': 0, 'duration_seconds': 2.3}
```

4. **Verify research session was persisted:**
```bash
psql $DATABASE_URL -c "
SELECT session_id, status, checkpoints_count
FROM research_sessions
ORDER BY created_at DESC
LIMIT 1;
"
```

**Expected:**
```
    session_id    | status    | checkpoints_count
------------------+-----------+------------------
 <session-id>     | completed | 3
```

**✅ PASS**: `shutdown` shows `completed > 0, timeout = 0`, session persisted
**❌ FAIL**: `timeout > 0`, or session not in database

### Troubleshooting
If writes timing out:
- Check PostgreSQL connection pool is healthy
- Verify network connectivity to database
- Increase timeout: modify `graceful_shutdown(timeout_seconds=60)`
- Check for database locks: `SELECT * FROM pg_stat_activity WHERE state = 'active';`

---

## P0 #4: Semantic Cache TTL & Size Limits

### What Changed
Semantic cache now has 12-hour TTL and 10,000 entry limit to prevent unbounded growth.

### Test Steps

1. **Check cache initialization logs:**
```bash
docker-compose logs brain | grep "SemanticCache initialized"
```

**Expected:**
```
INFO: SemanticCache initialized: TTL=43200s, max_entries=10000
```

2. **Add entries to cache:**
```python
from common.cache import SemanticCache, CacheRecord

cache = SemanticCache()

# Add 100 entries
for i in range(100):
    cache.store(CacheRecord(
        key=f"test_key_{i}",
        prompt=f"What is {i}?",
        response=f"Answer for {i}",
        confidence=0.9
    ))

print("✅ Added 100 entries")
```

3. **Check cache stats:**
```python
stats = cache.get_stats()
print(f"""
Cache Statistics:
- Entries: {stats.entry_count} / {stats.max_entries}
- Size: ~{stats.size_bytes / 1024:.1f} KB
- Hit rate: {stats.hit_rate:.2%}
- TTL: {stats.ttl_seconds / 3600:.1f} hours
""")
```

**Expected:**
```
Cache Statistics:
- Entries: 100 / 10000
- Size: ~50.0 KB
- Hit rate: 0.00%
- TTL: 12.0 hours
```

4. **Verify TTL is set on Redis:**
```bash
redis-cli TTL kitty:semantic-cache
```

**Expected:** Integer between `1` and `43200` (seconds remaining until expiration)

5. **Test max entries trimming** (add more than limit):
```python
cache = SemanticCache(max_entries=10)

# Add 20 entries
for i in range(20):
    cache.store(CacheRecord(key=f"k{i}", prompt="Q", response="A", confidence=0.9))

stats = cache.get_stats()
assert stats.entry_count <= 12, f"Cache should be trimmed to ~10, got {stats.entry_count}"
print(f"✅ Cache trimmed: {stats.entry_count} entries (max 10)")
```

**✅ PASS**: Cache has TTL set, entries trimmed to max_entries
**❌ FAIL**: TTL is `-1` (no expiration), or entries exceed max significantly

### Troubleshooting
If cache not evicting:
- Check Redis version: `redis-cli INFO server | grep redis_version` (needs 5.0+)
- Verify `EXPIRE` command works: `redis-cli EXPIRE kitty:semantic-cache 3600`
- Check MAXLEN is being used: add logging to `cache.store()`
- Manual trim: `cache.trim(max_entries=100)`

---

## P0 #5: Persistent APScheduler Jobs

### What Changed
APScheduler jobs now persist to PostgreSQL, surviving service restarts. All 7 autonomous jobs preserved.

### Test Steps

1. **Start brain service with autonomous mode enabled:**
```bash
export AUTONOMOUS_ENABLED=true
docker-compose restart brain
```

2. **Check scheduler startup logs:**
```bash
docker-compose logs brain | grep "Autonomous scheduler started"
```

**Expected (first start):**
```
INFO: Autonomous scheduler started: 7 new jobs registered, 0 restored from database, 7 total active jobs
```

3. **Verify jobs in database:**
```bash
psql $DATABASE_URL -c "SELECT id, next_run_time FROM apscheduler_jobs ORDER BY id;"
```

**Expected (7 jobs):**
```
            id             |  next_run_time
---------------------------+----------------
 daily_health_check        | 1705420800.0
 knowledge_base_update     | 1705416000.0
 outcome_measurement_cycle | 1705420800.0
 printer_fleet_health_check| 1705412400.0
 project_generation_cycle  | 1705416600.0
 task_execution_cycle      | 1705413000.0
 weekly_research_cycle     | 1705413000.0
```

4. **Restart brain service:**
```bash
docker-compose restart brain
sleep 5
```

5. **Check jobs were restored (NOT re-registered):**
```bash
docker-compose logs brain | grep "Autonomous scheduler started"
```

**Expected (after restart):**
```
INFO: Autonomous scheduler started: 0 new jobs registered, 7 restored from database, 7 total active jobs
```

6. **Verify no duplicate jobs:**
```bash
psql $DATABASE_URL -c "SELECT id, COUNT(*) FROM apscheduler_jobs GROUP BY id HAVING COUNT(*) > 1;"
```

**Expected:** `(0 rows)` - No duplicates

**✅ PASS**: 7 jobs restored from database, no duplicates
**❌ FAIL**: "7 new jobs" after restart (indicates re-registration, not restoration)

### Troubleshooting
If jobs not persisting:
- Check migration `k1l2m3n4o5p6` was applied
- Verify `apscheduler_jobs` table exists
- Check scheduler initialization: `get_scheduler()` should use `database_url`
- Clear duplicates: `DELETE FROM apscheduler_jobs; docker-compose restart brain`

If jobs duplicating:
- Verify `app.py` checks `existing_job_ids` before adding jobs
- Check for multiple scheduler instances (should be singleton)

---

## Full Integration Test (All P0s Together)

This test verifies all 5 P0 fixes work together in a realistic workflow.

### Test Scenario

1. **Start brain service** with all systems enabled:
```bash
export AUTONOMOUS_ENABLED=true
docker-compose up -d brain redis postgres
sleep 10
```

2. **Trigger research session** (tests P0 #1, #2, #3):
```bash
RESEARCH_SESSION_ID=$(curl -s -X POST http://localhost:8000/api/research/start \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Latest developments in AI safety",
    "max_iterations": 3
  }' | jq -r '.session_id')

echo "Research session: $RESEARCH_SESSION_ID"
```

3. **Set hazard confirmation** (tests P0 #2):
```python
state = state_manager.get_or_create(RESEARCH_SESSION_ID, "test-user")
state.set_pending_confirmation(
    tool_name="publish_paper",
    tool_args={"title": "AI Safety Research"},
    confirmation_phrase="PUBLISH",
    hazard_class="medium",
    reason="Public paper publication"
)
```

4. **Wait for cache population** (tests P0 #4):
```bash
sleep 5
redis-cli XLEN kitty:semantic-cache
# Should show entries > 0
```

5. **Restart brain service immediately** (tests P0 #2, #3, #5):
```bash
docker-compose restart brain
sleep 10
```

6. **Verify all systems survived restart:**

```bash
# P0 #1: Research components wired
docker-compose logs brain | grep "Research components registered: {'fully_wired': True"

# P0 #2: Conversation state persisted
psql $DATABASE_URL -c "SELECT pending_confirmation FROM conversation_sessions WHERE id = '$RESEARCH_SESSION_ID';"
# Should show pending confirmation

# P0 #3: Research session completed gracefully
docker-compose logs brain | grep "Session manager shutdown: {'completed':"

# P0 #4: Cache has TTL
redis-cli TTL kitty:semantic-cache
# Should be 1-43200 seconds

# P0 #5: Jobs restored
docker-compose logs brain | grep "7 restored from database"
```

**✅ PASS**: All 5 checks succeed
**❌ FAIL**: Any check fails - see individual P0 troubleshooting sections

---

## Expected Log Output (Healthy System)

When all P0 fixes are working correctly, brain service startup should show:

```
INFO: Brain service starting up
INFO: Initializing PostgreSQL connection pool
INFO: Connection pool ready (size: 20)

# P0 #2: Persistent conversation state
INFO: PersistentConversationStateManager initialized

# P0 #1: Research graph wiring
INFO: Research components registered: {'fully_wired': True, 'tool_executor': True, 'permission_gate': True, ...}

# P0 #5: APScheduler jobs
INFO: Starting autonomous scheduler with persistent job store
INFO: Autonomous scheduler started - 7 existing jobs restored from database
INFO: Autonomous scheduler started: 0 new jobs registered, 7 restored from database, 7 total active jobs

# P0 #4: Semantic cache
INFO: SemanticCache initialized: TTL=43200s, max_entries=10000

INFO: Brain service startup complete
```

**On shutdown:**
```
INFO: Brain service shutting down

# P0 #3: Graceful shutdown
INFO: Initiating graceful shutdown for research session manager
INFO: Session manager shutdown: {'completed': 2, 'timeout': 0, 'failed': 0, 'duration_seconds': 1.8}

INFO: Stopping autonomous scheduler
INFO: Autonomous scheduler stopped
INFO: Closing PostgreSQL connection pool
INFO: Brain service shutdown complete
```

---

## Quick Verification Checklist

After deployment, verify these 5 log patterns:

- [ ] `Research components registered: {'fully_wired': True, ...}` (P0 #1)
- [ ] `PersistentConversationStateManager initialized` (P0 #2)
- [ ] `Session manager shutdown: {'completed': N, 'timeout': 0, ...}` (P0 #3)
- [ ] `SemanticCache initialized: TTL=43200s, max_entries=10000` (P0 #4)
- [ ] `Autonomous scheduler started: 0 new, 7 restored, 7 total` (P0 #5, after restart)

---

## Rollback Procedure

If any P0 fix causes issues, rollback:

```bash
# Checkout previous branch
git checkout main  # or previous stable branch

# Downgrade migrations
cd services/common
alembic downgrade -2  # Rolls back 2 migrations (f7g8h9i0j1k2, k1l2m3n4o5p6)

# Restart services
docker-compose restart brain

# Verify rollback
docker-compose logs brain | grep "Brain service startup complete"
```

**Note**: Rollback will lose:
- Persisted conversation states (hazard confirmations reset)
- Persisted APScheduler jobs (must re-register on startup)

---

## Success Criteria

All P0 fixes are working if:

1. ✅ Research graph uses real tools (not simulated)
2. ✅ Conversation state survives restart (pending confirmations preserved)
3. ✅ Database writes complete before shutdown (no timeouts)
4. ✅ Semantic cache stays bounded (≤10k entries, 12hr TTL)
5. ✅ Scheduled jobs survive restart (7 jobs restored, no duplicates)

**Estimated Impact**:
- **Data Safety**: Hazard operations cannot double-execute (P0 #2)
- **Reliability**: Jobs don't disappear on restart (P0 #5)
- **Memory**: Cache won't grow unbounded (P0 #4)
- **Functionality**: Research uses real APIs (P0 #1)
- **Stability**: Clean shutdown prevents data loss (P0 #3)

---

## Contact & Support

If issues arise during testing:
- Check individual troubleshooting sections above
- Review detailed testing guide: `Research/TestingGuide.md`
- Check system analysis: `KITT_SYSTEM_ANALYSIS_MASTER.md`
- Review commit history for P0 fixes:
  - `649d0b1` - Research graph wiring
  - `475d79b` - Persistent conversation state
  - `d08242a` - Database write safety
  - `cd0ca9e` - Semantic cache TTL
  - `0fe71f8` - Persistent job store
