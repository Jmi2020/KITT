# Phase 1 Test Fixes - Workstation Instructions

## Summary of Issues Found

Three issues were identified during Phase 1 testing:

1. **Migration SQL FK Constraint Error**: Foreign key on `research_sessions.thread_id` referenced `checkpoints(thread_id)` which is not unique (composite PK)
2. **Migration SQL View Error**: `MAX(st.saturated)` tried to aggregate a boolean field
3. **Async Pool Error**: `ResearchSessionManager` used sync `ConnectionPool` with `async with` context manager

## Files Modified

- `services/brain/migrations/006_research_checkpoints.sql` - Fixed FK and view issues
- `services/brain/src/brain/research/checkpoint.py` - Changed to async pool and checkpointer
- `services/brain/src/brain/app.py` - Added await to init_checkpointer call

## Step-by-Step Instructions

### 1. Pull Latest Changes

```bash
cd /home/user/KITT
git pull origin claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB
```

### 2. Re-run Migration (Fresh Start)

The migration SQL has been fixed. Drop existing tables and re-run:

```bash
# Connect to database (via docker)
docker exec -i compose-postgres-1 psql -U kitty -d kitty << 'EOF'
-- Drop all research tables (clean slate)
DROP TABLE IF EXISTS model_calls CASCADE;
DROP TABLE IF EXISTS confidence_scores CASCADE;
DROP TABLE IF EXISTS saturation_tracking CASCADE;
DROP TABLE IF EXISTS knowledge_gaps CASCADE;
DROP TABLE IF EXISTS quality_metrics CASCADE;
DROP TABLE IF EXISTS research_findings CASCADE;
DROP TABLE IF EXISTS research_sessions CASCADE;
DROP TABLE IF EXISTS checkpoint_writes CASCADE;
DROP TABLE IF EXISTS checkpoint_blobs CASCADE;
DROP TABLE IF EXISTS checkpoints CASCADE;

-- Drop views
DROP VIEW IF EXISTS v_model_usage_stats CASCADE;
DROP VIEW IF EXISTS v_session_quality_summary CASCADE;
DROP VIEW IF EXISTS v_active_research_sessions CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS archive_old_sessions(INTEGER);
DROP FUNCTION IF EXISTS calculate_session_stats(TEXT);
DROP FUNCTION IF EXISTS update_research_session_timestamp();
EOF

# Re-run migration with fixes
cat services/brain/migrations/006_research_checkpoints.sql | docker exec -i compose-postgres-1 psql -U kitty -d kitty
```

### 3. Verify Migration Success

```bash
docker exec -i compose-postgres-1 psql -U kitty -d kitty << 'EOF'
-- Verify all tables created
\dt research*
\dt checkpoint*
\dt quality*
\dt saturation*
\dt confidence*
\dt knowledge*
\dt model*

-- Verify all views created (should see 3 views)
\dv v_*

-- Verify functions created
\df update_research_session_timestamp
\df calculate_session_stats
\df archive_old_sessions

-- Should see no errors
EOF
```

**Expected Output:**
- 10 tables (checkpoints, checkpoint_blobs, checkpoint_writes, research_sessions, research_findings, quality_metrics, knowledge_gaps, saturation_tracking, confidence_scores, model_calls)
- 3 views (v_active_research_sessions, v_session_quality_summary, v_model_usage_stats)
- 3 functions

### 4. Verify Python Changes

The code has been updated to use async connection pools. Verify imports work:

```bash
cd /home/user/KITT
source .venv/bin/activate  # Use root .venv

python << 'EOF'
import sys
sys.path.insert(0, '/home/user/KITT/services/brain/src')
sys.path.insert(0, '/home/user/KITT/services/common/src')

# Test imports
print("Testing checkpoint module...")
from brain.research.checkpoint import create_connection_pool, init_checkpointer
print("✓ Checkpoint imports successful")

print("\nTesting session manager...")
from brain.research.session_manager import ResearchSessionManager
print("✓ Session manager imports successful")

print("\nAll imports passed!")
EOF
```

### 5. Test Brain Service Startup

```bash
cd /home/user/KITT

# Set environment
export DATABASE_URL="postgresql://kitty:changeme@localhost:5432/kitty"
export AUTONOMOUS_ENABLED=false

# Start service on port 18100 (8080 is in use)
cd services/brain
uvicorn brain.app:app --host 0.0.0.0 --port 18100 --log-level info > /tmp/brain_service_test.log 2>&1 &
BRAIN_PID=$!

# Wait for startup
sleep 3

# Check logs for successful init
tail -20 /tmp/brain_service_test.log | grep -E "(PostgreSQL|Research|initialized)"
```

**Expected Log Lines:**
```
Initializing research infrastructure
PostgreSQL connection pool created
PostgreSQL checkpointer initialized
Research session manager initialized
```

### 6. Test Research Session API

```bash
# Health check
curl http://localhost:18100/api/research/health

# Create session (this previously failed with async context manager error)
curl -X POST http://localhost:18100/api/research/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test-user",
    "query": "What are the latest advances in 3D printing materials?",
    "config": {
      "max_iterations": 5
    }
  }' | jq '.'
```

**Expected Response:**
```json
{
  "session_id": "...",
  "user_id": "test-user",
  "query": "What are the latest advances in 3D printing materials?",
  "status": "active",
  "created_at": "2025-..."
}
```

Save the session_id from the response for next tests.

### 7. Test Other Session Operations

```bash
# Replace SESSION_ID with actual ID from step 6
SESSION_ID="your-session-id-here"

# Get session
curl http://localhost:18100/api/research/sessions/${SESSION_ID} | jq '.'

# List all sessions
curl http://localhost:18100/api/research/sessions | jq '.'

# Pause session
curl -X POST http://localhost:18100/api/research/sessions/${SESSION_ID}/pause | jq '.'

# Resume session
curl -X POST http://localhost:18100/api/research/sessions/${SESSION_ID}/resume | jq '.'

# Cancel session
curl -X DELETE http://localhost:18100/api/research/sessions/${SESSION_ID} | jq '.'
```

### 8. Verify Database Records

```bash
docker exec -i compose-postgres-1 psql -U kitty -d kitty << 'EOF'
-- Check sessions created
SELECT session_id, user_id, status, query FROM research_sessions;

-- Check checkpoints created (should have at least 1 per session)
SELECT thread_id, checkpoint_id, type FROM checkpoints LIMIT 5;

-- Verify views work
SELECT * FROM v_active_research_sessions;
SELECT * FROM v_model_usage_stats;
SELECT * FROM v_session_quality_summary;
EOF
```

### 9. Cleanup Test Service

```bash
# Kill test brain service
kill $BRAIN_PID 2>/dev/null || pkill -f "uvicorn brain.app"

# Logs are saved in /tmp/brain_service_test.log for review
```

### 10. Cleanup Test Data (Optional)

```bash
docker exec -i compose-postgres-1 psql -U kitty -d kitty << 'EOF'
-- Clean test sessions
DELETE FROM research_sessions WHERE user_id = 'test-user';
EOF
```

## Success Criteria

All of the following should pass:

- [ ] Migration runs without errors
- [ ] All 10 tables created
- [ ] All 3 views created (including v_session_quality_summary)
- [ ] All 3 functions created
- [ ] Python imports work
- [ ] Brain service starts with "Research session manager initialized" log
- [ ] POST /api/research/sessions returns 201 with session_id (not 500)
- [ ] GET /api/research/sessions/{id} returns session details
- [ ] Session record visible in database
- [ ] Checkpoint record created for session

## Common Issues

### Issue: "relation already exists"

**Solution:** Tables already exist from previous run. Use the DROP statements in Step 2 to start fresh.

### Issue: "module 'langgraph.checkpoint.postgres' has no attribute 'aio'"

**Solution:** Upgrade langgraph-checkpoint-postgres:
```bash
cd /home/user/KITT
source .venv/bin/activate
pip install --upgrade langgraph-checkpoint-postgres
```

### Issue: "AsyncConnectionPool object has no attribute 'open'"

**Solution:** The pool is lazily initialized. This is expected - the pool will open connections on first use.

### Issue: Service starts but /api/research/sessions fails with different error

**Solution:** Check `/tmp/brain_service_test.log` for the full traceback. Common issues:
- Wrong DATABASE_URL format
- PostgreSQL not accessible
- Missing tables (re-run migration)

## Contact

If any issues persist after following these steps, provide:
1. Output of Step 3 (migration verification)
2. Output of Step 6 (session creation)
3. Last 50 lines of `/tmp/brain_service_test.log`
4. Any error tracebacks
