# Phase 1 Testing Guide - Research Session Infrastructure

**Version:** 1.0
**Created:** 2025-01-16
**Purpose:** Verify Phase 1 implementation on workstation

---

## Overview

This document provides step-by-step instructions to test the autonomous research session infrastructure (Phase 1: State Management & Checkpointing).

**What Phase 1 Provides:**
- PostgreSQL-backed state persistence with LangGraph checkpointing
- Research session lifecycle management (create/pause/resume/cancel)
- REST API endpoints for session operations
- Fault-tolerant checkpoint recovery (for future graph execution)

**What's NOT in Phase 1:**
- Actual research graph execution (Phase 5)
- Tool orchestration (Phase 2)
- Model coordination (Phase 3)
- Quality metrics computation (Phase 4)

---

## Prerequisites

### Required
- PostgreSQL 12+ running and accessible
- Python 3.11+
- Git repository cloned at `/path/to/KITT`
- Terminal access to workstation

### Optional
- `curl` or `httpx` for API testing
- PostgreSQL client (`psql`) for database inspection
- `jq` for JSON formatting

---

## Test Plan

### Step 1: Verify Repository State

```bash
cd /path/to/KITT
git fetch origin
git checkout claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB
git pull origin claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB
```

**Expected files to exist:**
```bash
services/brain/migrations/006_research_checkpoints.sql
services/brain/migrations/README.md
services/brain/src/brain/research/__init__.py
services/brain/src/brain/research/checkpoint.py
services/brain/src/brain/research/session_manager.py
services/brain/src/brain/research/routes.py
```

**Verification:**
```bash
ls -l services/brain/migrations/006_research_checkpoints.sql
ls -l services/brain/src/brain/research/*.py
```

✅ **Pass:** All files exist
❌ **Fail:** Missing files - re-pull repository

---

### Step 2: Configure Database Connection

**2.1 Check PostgreSQL is Running**

```bash
# Method 1: Direct connection test
psql -h localhost -U your_user -d postgres -c "SELECT version();"

# Method 2: Docker (if PostgreSQL in container)
docker ps | grep postgres
```

✅ **Pass:** PostgreSQL version displayed
❌ **Fail:** Connection error - start PostgreSQL

**2.2 Create Database (if needed)**

```bash
# Connect to PostgreSQL
psql -h localhost -U your_user -d postgres

# Create database (if it doesn't exist)
CREATE DATABASE kitt;

# Verify
\l kitt

# Exit
\q
```

✅ **Pass:** Database `kitt` exists
❌ **Fail:** Permission error - check user privileges

**2.3 Set DATABASE_URL**

```bash
# Set environment variable (adjust credentials)
export DATABASE_URL="postgresql://your_user:your_password@localhost:5432/kitt"

# Verify it's set
echo $DATABASE_URL
```

✅ **Pass:** DATABASE_URL displayed
❌ **Fail:** Empty output - re-export variable

---

### Step 3: Run Database Migration

**3.1 Execute Migration**

```bash
cd /path/to/KITT/services/brain

# Run migration
psql $DATABASE_URL -f migrations/006_research_checkpoints.sql
```

**Expected output (partial):**
```
CREATE TABLE
CREATE INDEX
CREATE TABLE
...
CREATE FUNCTION
CREATE VIEW
NOTICE: Migration 006 completed successfully: Research session checkpointing and state management tables created
```

✅ **Pass:** "Migration 006 completed successfully" message
❌ **Fail:** ERROR messages - check error log (common issues below)

**3.2 Verify Tables Created**

```bash
# List research tables
psql $DATABASE_URL -c "\dt research*"

# List checkpoint tables
psql $DATABASE_URL -c "\dt checkpoint*"

# List quality metrics tables
psql $DATABASE_URL -c "\dt quality* saturation* confidence* knowledge* model*"

# List views
psql $DATABASE_URL -c "\dv v_*"

# Count total tables
psql $DATABASE_URL -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE 'research%' OR table_name LIKE 'checkpoint%' OR table_name LIKE 'quality%' OR table_name LIKE 'model%';"
```

**Expected counts:**
- 3 checkpoint tables (checkpoints, checkpoint_blobs, checkpoint_writes)
- 2 research tables (research_sessions, research_findings)
- 4 quality tables (quality_metrics, knowledge_gaps, saturation_tracking, confidence_scores)
- 1 model table (model_calls)
- 3 views (v_active_research_sessions, v_session_quality_summary, v_model_usage_stats)

✅ **Pass:** 10+ tables, 3 views exist
❌ **Fail:** Missing tables - check migration errors

**3.3 Verify Functions Created**

```bash
psql $DATABASE_URL -c "\df update_research_session_timestamp"
psql $DATABASE_URL -c "\df calculate_session_stats"
psql $DATABASE_URL -c "\df archive_old_sessions"
```

✅ **Pass:** All 3 functions listed
❌ **Fail:** Function not found - re-run migration

---

### Step 4: Install Dependencies

**4.1 Install Brain Service**

```bash
cd /path/to/KITT/services/brain

# Install with uv (recommended)
uv pip install -e .

# OR with pip
pip install -e .
```

**Expected output (key packages):**
```
Installing collected packages:
  langgraph-checkpoint-postgres
  psycopg[binary,pool]
  ragas
  datasets
  ...
Successfully installed ...
```

✅ **Pass:** Installation successful, key packages listed
❌ **Fail:** Build errors - check Python version (needs 3.11+)

**4.2 Verify Imports**

```bash
python -c "from brain.research.checkpoint import create_connection_pool; print('✓ checkpoint')"
python -c "from brain.research.session_manager import ResearchSessionManager; print('✓ session_manager')"
python -c "from brain.research.routes import router; print('✓ routes')"
python -c "from langgraph.checkpoint.postgres import PostgresSaver; print('✓ langgraph')"
```

✅ **Pass:** All 4 imports succeed with ✓ marks
❌ **Fail:** ImportError - check dependencies installed

---

### Step 5: Start Brain Service

**5.1 Launch Service**

```bash
cd /path/to/KITT/services/brain

# Ensure DATABASE_URL is set
export DATABASE_URL="postgresql://your_user:your_password@localhost:5432/kitt"

# Start with uvicorn
uv run uvicorn brain.app:app --reload --port 8080 --host 0.0.0.0
```

**Expected startup logs:**
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Brain service starting up
INFO:     Initializing research infrastructure
INFO:     PostgreSQL connection pool created
INFO:     PostgreSQL checkpointer initialized
INFO:     Research session manager initialized
INFO:     Autonomous mode disabled (AUTONOMOUS_ENABLED=false)
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

✅ **Pass:** "Research session manager initialized" in logs
❌ **Fail:** Error in logs - check common issues below

**5.2 Health Check**

```bash
# In a new terminal
curl http://localhost:8080/health
```

**Expected response:**
```json
{"status":"ok"}
```

✅ **Pass:** 200 OK with status
❌ **Fail:** Connection refused - check service is running

**5.3 Research Health Check**

```bash
curl http://localhost:8080/api/research/health
```

**Expected response:**
```json
{
  "service": "autonomous_research",
  "status": "healthy",
  "version": "0.1.0"
}
```

✅ **Pass:** Research service healthy
❌ **Fail:** 503 error - DATABASE_URL not configured

---

### Step 6: Test REST API Endpoints

**6.1 Create Research Session**

```bash
# Create test session
curl -X POST http://localhost:8080/api/research/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Test autonomous research infrastructure - Phase 1 validation",
    "user_id": "test-user-001",
    "config": {
      "max_iterations": 10,
      "max_cost_usd": 1.5,
      "max_external_calls": 5
    }
  }' | jq .
```

**Expected response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "message": "Research session created successfully",
  "thread_id": "research_550e8400-e29b-41d4-a716-446655440000"
}
```

✅ **Pass:** 201 Created, session_id returned
❌ **Fail:** 500 error - check database connection

**Save session_id for next tests:**
```bash
export SESSION_ID="<paste-session-id-here>"
```

**6.2 Get Session Details**

```bash
curl http://localhost:8080/api/research/sessions/$SESSION_ID | jq .
```

**Expected response:**
```json
{
  "session_id": "550e8400-...",
  "user_id": "test-user-001",
  "query": "Test autonomous research infrastructure - Phase 1 validation",
  "status": "active",
  "created_at": "2025-01-16T12:00:00",
  "updated_at": "2025-01-16T12:00:00",
  "completed_at": null,
  "thread_id": "research_550e8400-...",
  "config": {
    "max_iterations": 10,
    "max_cost_usd": 1.5,
    "max_external_calls": 5
  },
  "metadata": {},
  "total_iterations": 0,
  "total_findings": 0,
  "total_sources": 0,
  "total_cost_usd": 0.0,
  "external_calls_used": 0,
  "completeness_score": null,
  "confidence_score": null,
  "saturation_status": null
}
```

✅ **Pass:** Full session details returned
❌ **Fail:** 404 - session not found in database

**6.3 List User Sessions**

```bash
curl "http://localhost:8080/api/research/sessions?user_id=test-user-001" | jq .
```

**Expected response:**
```json
{
  "sessions": [
    {
      "session_id": "550e8400-...",
      "user_id": "test-user-001",
      "query": "Test autonomous research infrastructure - Phase 1 validation",
      "status": "active",
      ...
    }
  ],
  "total": 1
}
```

✅ **Pass:** Array with 1 session
❌ **Fail:** Empty array - check user_id matches

**6.4 Filter by Status**

```bash
curl "http://localhost:8080/api/research/sessions?user_id=test-user-001&status=active" | jq .
```

✅ **Pass:** Sessions with status=active only
❌ **Fail:** 400 error - invalid status value

**6.5 Pause Session**

```bash
curl -X POST http://localhost:8080/api/research/sessions/$SESSION_ID/pause | jq .
```

**Expected response:**
```json
{
  "success": true,
  "message": "Session 550e8400-... paused successfully"
}
```

✅ **Pass:** Success message
❌ **Fail:** 404 - session not active

**Verify status changed:**
```bash
curl http://localhost:8080/api/research/sessions/$SESSION_ID | jq '.status'
```

**Expected:** `"paused"`

**6.6 Resume Session**

```bash
curl -X POST http://localhost:8080/api/research/sessions/$SESSION_ID/resume \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

**Expected response:**
```json
{
  "success": true,
  "message": "Session 550e8400-... resumed successfully"
}
```

✅ **Pass:** Success message
❌ **Fail:** 404 - session not paused

**6.7 Cancel Session**

```bash
curl -X DELETE http://localhost:8080/api/research/sessions/$SESSION_ID | jq .
```

**Expected response:**
```json
{
  "success": true,
  "message": "Session 550e8400-... cancelled successfully"
}
```

✅ **Pass:** Success message
❌ **Fail:** 404 - session not found

**Verify status changed:**
```bash
curl http://localhost:8080/api/research/sessions/$SESSION_ID | jq '.status'
```

**Expected:** `"failed"` (cancelled sessions marked as failed)

---

### Step 7: Verify Database State

**7.1 Check Session in Database**

```bash
psql $DATABASE_URL -c "SELECT session_id, user_id, query, status, created_at FROM research_sessions ORDER BY created_at DESC LIMIT 5;"
```

✅ **Pass:** Test session visible with correct status
❌ **Fail:** No rows - session creation failed

**7.2 Check Checkpoints Created**

```bash
psql $DATABASE_URL -c "SELECT thread_id, checkpoint_id, checkpoint->>'ts' as timestamp FROM checkpoints ORDER BY checkpoint->>'ts' DESC LIMIT 3;"
```

**Note:** Checkpoints only created during graph execution (Phase 5). In Phase 1, this table will be empty.

✅ **Pass:** Table exists (empty is OK)
❌ **Fail:** Table not found - migration issue

**7.3 Test View**

```bash
psql $DATABASE_URL -c "SELECT session_id, status, total_iterations, duration_minutes FROM v_active_research_sessions LIMIT 5;"
```

✅ **Pass:** View returns data
❌ **Fail:** View not found - check migration

**7.4 Test Function**

```bash
psql $DATABASE_URL -c "SELECT * FROM calculate_session_stats('$SESSION_ID');"
```

✅ **Pass:** Function returns stats (likely all zeros)
❌ **Fail:** Function error - check migration

---

### Step 8: Load Testing (Optional)

**8.1 Create Multiple Sessions**

```bash
for i in {1..10}; do
  curl -X POST http://localhost:8080/api/research/sessions \
    -H "Content-Type: application/json" \
    -d "{
      \"query\": \"Load test session $i\",
      \"user_id\": \"load-test-user\",
      \"config\": {\"max_iterations\": 5}
    }" > /dev/null 2>&1 &
done

wait
echo "Created 10 sessions"
```

**8.2 Verify All Created**

```bash
curl "http://localhost:8080/api/research/sessions?user_id=load-test-user" | jq '.total'
```

**Expected:** `10`

✅ **Pass:** All 10 sessions created
❌ **Fail:** Missing sessions - check connection pool size

**8.3 Check Database Load**

```bash
psql $DATABASE_URL -c "SELECT COUNT(*) FROM research_sessions;"
psql $DATABASE_URL -c "SELECT pg_size_pretty(pg_database_size('kitt'));"
```

✅ **Pass:** Count matches, database size reasonable
❌ **Fail:** Connection pool exhausted - increase pool size

---

## Cleanup

**Remove Test Data:**
```bash
# Delete test sessions
psql $DATABASE_URL -c "DELETE FROM research_sessions WHERE user_id LIKE 'test-%' OR user_id LIKE 'load-%';"

# Verify cleanup
psql $DATABASE_URL -c "SELECT COUNT(*) FROM research_sessions;"
```

**Stop Service:**
```bash
# Ctrl+C in terminal running uvicorn
```

---

## Common Issues & Solutions

### Issue 1: "relation already exists"
**Cause:** Migration already ran
**Solution:** Migration is idempotent, ignore warning

### Issue 2: "permission denied for schema public"
**Cause:** User lacks CREATE privileges
**Solution:**
```sql
GRANT CREATE ON SCHEMA public TO your_user;
GRANT ALL PRIVILEGES ON DATABASE kitt TO your_user;
```

### Issue 3: "ModuleNotFoundError: No module named 'langgraph'"
**Cause:** Dependencies not installed
**Solution:**
```bash
cd services/brain
uv pip install -e .
```

### Issue 4: "503 Service Unavailable" on /api/research/*
**Cause:** DATABASE_URL not set
**Solution:**
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/kitt"
# Restart service
```

### Issue 5: "could not connect to server"
**Cause:** PostgreSQL not running
**Solution:**
```bash
# Start PostgreSQL
sudo systemctl start postgresql
# OR for Docker
docker start postgres_container
```

### Issue 6: "Research session manager initialized" not in logs
**Cause:** Database connection failed
**Solution:** Check DATABASE_URL, verify database exists, check credentials

### Issue 7: ImportError for brain.research modules
**Cause:** Package not installed in editable mode
**Solution:**
```bash
cd services/brain
uv pip install -e .
```

---

## Success Checklist

Phase 1 is **COMPLETE** if all these pass:

- [ ] Database migration runs successfully (9 tables, 3 views, 3 functions)
- [ ] Service starts with "Research session manager initialized" log
- [ ] Health check returns 200 OK
- [ ] Research health check returns 200 OK
- [ ] Create session returns 201 with session_id
- [ ] Get session returns full details
- [ ] List sessions returns array
- [ ] Pause session changes status to "paused"
- [ ] Resume session changes status to "active"
- [ ] Cancel session changes status to "failed"
- [ ] Database contains session records
- [ ] Views return data
- [ ] Functions execute without errors

---

## Next Steps

After Phase 1 testing passes:

1. **Report results** - Provide test output to development team
2. **Phase 2** - Tool Orchestration (wave execution, validation)
3. **Phase 3** - Model Coordination (tiered consultation)
4. **Phase 4** - Quality Metrics (RAGAS, saturation)
5. **Phase 5** - Integration (complete autonomous research graph)

---

## Appendix A: Quick Test Script

Save as `test_phase1.sh`:

```bash
#!/bin/bash
set -e

echo "=== Phase 1 Testing Script ==="

# Configuration
export DATABASE_URL="postgresql://user:pass@localhost:5432/kitt"
BASE_URL="http://localhost:8080"

echo "1. Testing health endpoints..."
curl -sf $BASE_URL/health > /dev/null && echo "✓ General health OK" || echo "✗ General health FAILED"
curl -sf $BASE_URL/api/research/health > /dev/null && echo "✓ Research health OK" || echo "✗ Research health FAILED"

echo "2. Creating test session..."
SESSION_ID=$(curl -sf -X POST $BASE_URL/api/research/sessions \
  -H "Content-Type: application/json" \
  -d '{"query":"Test","user_id":"test"}' | jq -r '.session_id')
echo "✓ Session created: $SESSION_ID"

echo "3. Getting session details..."
curl -sf $BASE_URL/api/research/sessions/$SESSION_ID > /dev/null && echo "✓ Get session OK" || echo "✗ Get session FAILED"

echo "4. Listing sessions..."
COUNT=$(curl -sf "$BASE_URL/api/research/sessions?user_id=test" | jq '.total')
echo "✓ Found $COUNT sessions"

echo "5. Pausing session..."
curl -sf -X POST $BASE_URL/api/research/sessions/$SESSION_ID/pause > /dev/null && echo "✓ Pause OK" || echo "✗ Pause FAILED"

echo "6. Resuming session..."
curl -sf -X POST $BASE_URL/api/research/sessions/$SESSION_ID/resume -H "Content-Type: application/json" -d '{}' > /dev/null && echo "✓ Resume OK" || echo "✗ Resume FAILED"

echo "7. Cancelling session..."
curl -sf -X DELETE $BASE_URL/api/research/sessions/$SESSION_ID > /dev/null && echo "✓ Cancel OK" || echo "✗ Cancel FAILED"

echo "8. Cleaning up..."
psql $DATABASE_URL -c "DELETE FROM research_sessions WHERE user_id = 'test';" > /dev/null
echo "✓ Cleanup complete"

echo "=== All tests passed! ==="
```

Run with: `bash test_phase1.sh`

---

## Appendix B: Database Schema Reference

**Quick reference for manual queries:**

```sql
-- Active sessions
SELECT * FROM v_active_research_sessions;

-- Session quality
SELECT * FROM v_session_quality_summary;

-- Model usage
SELECT * FROM v_model_usage_stats;

-- Session stats
SELECT * FROM calculate_session_stats('session-id-here');

-- Archive old sessions
SELECT archive_old_sessions(90);

-- Checkpoint size
SELECT
  COUNT(*) as checkpoint_count,
  pg_size_pretty(SUM(pg_column_size(checkpoint))) as total_size
FROM checkpoints;
```

---

**End of Testing Guide**
