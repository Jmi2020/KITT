# Database Migration - Research Sessions

This document provides instructions for running the research session database migration.

## Prerequisites

- PostgreSQL 12+ installed and running
- Database connection string (DATABASE_URL)
- `psql` command-line tool

## Migration File

`migrations/006_research_checkpoints.sql`

## What This Migration Creates

### LangGraph Checkpoint Tables (3 tables)
- `checkpoints` - Full workflow state storage
- `checkpoint_blobs` - Large data storage
- `checkpoint_writes` - Pending writes tracking

### Research Session Tables (2 tables)
- `research_sessions` - Session lifecycle and metadata
- `research_findings` - Structured findings storage

### Quality Metrics Tables (4 tables)
- `quality_metrics` - RAGAS scores
- `knowledge_gaps` - Coverage/depth/consistency gaps
- `saturation_tracking` - Novelty rate monitoring
- `confidence_scores` - Multi-factor confidence tracking

### Model Usage Tracking (1 table)
- `model_calls` - Per-model costs, latency, tier usage

### Helper Functions (3 functions)
- `update_research_session_timestamp()` - Auto-update timestamps
- `calculate_session_stats()` - Aggregate statistics
- `archive_old_sessions()` - Data retention

### Monitoring Views (3 views)
- `v_active_research_sessions` - Real-time session monitoring
- `v_session_quality_summary` - Quality metrics overview
- `v_model_usage_stats` - Model performance analytics

## Running the Migration

### Option 1: Using psql directly

```bash
# Set your DATABASE_URL
export DATABASE_URL="postgresql://user:password@localhost:5432/kitt"

# Run migration
cd services/brain
psql $DATABASE_URL -f migrations/006_research_checkpoints.sql
```

### Option 2: Using psql with separate parameters

```bash
psql -h localhost -U your_user -d kitt -f services/brain/migrations/006_research_checkpoints.sql
```

### Option 3: From Docker (if database is in container)

```bash
# Copy migration to container
docker cp services/brain/migrations/006_research_checkpoints.sql postgres_container:/tmp/

# Execute migration
docker exec -i postgres_container psql -U your_user -d kitt -f /tmp/006_research_checkpoints.sql
```

## Verification

After running the migration, verify the tables were created:

```sql
-- Connect to database
psql $DATABASE_URL

-- List all research-related tables
\dt research*
\dt checkpoint*
\dt quality*
\dt saturation*
\dt confidence*
\dt knowledge*
\dt model*

-- Check table counts
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename LIKE 'research%'
   OR tablename LIKE 'checkpoint%'
   OR tablename LIKE 'quality%'
   OR tablename LIKE 'model%'
ORDER BY tablename;

-- Verify views
\dv v_*

-- Verify functions
\df update_research_session_timestamp
\df calculate_session_stats
\df archive_old_sessions
```

Expected output should show:
- 9 tables created
- 3 views created
- 3 functions created
- All tables empty (0 rows)

## Testing the Migration

Create a test session to verify everything works:

```sql
-- Insert test session
INSERT INTO research_sessions (
    session_id, user_id, query, status, thread_id
) VALUES (
    'test-session-001',
    'test-user',
    'Test research query',
    'active',
    'research_test-session-001'
);

-- Verify insert
SELECT session_id, user_id, query, status, created_at
FROM research_sessions
WHERE session_id = 'test-session-001';

-- Test view
SELECT * FROM v_active_research_sessions
WHERE session_id = 'test-session-001';

-- Cleanup test data
DELETE FROM research_sessions WHERE session_id = 'test-session-001';
```

## Rollback (if needed)

If you need to rollback the migration:

```sql
-- WARNING: This will delete all research data!

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS model_calls CASCADE;
DROP TABLE IF EXISTS confidence_scores CASCADE;
DROP TABLE IF EXISTS saturation_tracking CASCADE;
DROP TABLE IF EXISTS knowledge_gaps CASCADE;
DROP TABLE IF EXISTS quality_metrics CASCADE;
DROP TABLE IF EXISTS research_findings CASCADE;
DROP TABLE IF EXISTS research_sessions CASCADE;
DROP TABLE IF EXISTS research_sessions_archive CASCADE;
DROP TABLE IF EXISTS checkpoint_writes CASCADE;
DROP TABLE IF EXISTS checkpoint_blobs CASCADE;
DROP TABLE IF EXISTS checkpoints CASCADE;

-- Drop views
DROP VIEW IF EXISTS v_model_usage_stats;
DROP VIEW IF EXISTS v_session_quality_summary;
DROP VIEW IF EXISTS v_active_research_sessions;

-- Drop functions
DROP FUNCTION IF EXISTS archive_old_sessions(INTEGER);
DROP FUNCTION IF EXISTS calculate_session_stats(TEXT);
DROP FUNCTION IF EXISTS update_research_session_timestamp();
```

## Common Issues

### Issue: "relation already exists"
**Solution:** Tables already created. Migration is idempotent, safe to re-run.

### Issue: "permission denied"
**Solution:** Ensure database user has CREATE TABLE privileges:
```sql
GRANT CREATE ON SCHEMA public TO your_user;
```

### Issue: "extension uuid-ossp not found"
**Solution:** The migration uses `gen_random_uuid()` which requires PostgreSQL 13+.
For PostgreSQL 12, install extension:
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

## Next Steps

After successful migration:

1. **Configure DATABASE_URL** environment variable
2. **Start brain service** - it will auto-initialize checkpointer
3. **Test API** - create a research session via REST API
4. **Monitor** - check Grafana dashboards (when Phase 6 complete)

## Environment Configuration

Add to `.env` or environment:

```bash
# Required for research infrastructure
DATABASE_URL=postgresql://user:password@localhost:5432/kitt

# Optional research configuration
RESEARCH_MAX_ITERATIONS=15
RESEARCH_BASE_SIZE=10
RESEARCH_SATURATION_THRESHOLD=0.05
MAX_EXTERNAL_CALLS_PER_SESSION=10
MAX_COST_PER_SESSION_USD=2.00
```

## Monitoring

After migration, monitor database size:

```sql
-- Check database size
SELECT pg_size_pretty(pg_database_size('kitt'));

-- Check checkpoint table size (can grow large)
SELECT
    pg_size_pretty(pg_total_relation_size('checkpoints')) as checkpoints_size,
    COUNT(*) as checkpoint_count
FROM checkpoints;

-- Monitor active sessions
SELECT COUNT(*) FROM research_sessions WHERE status = 'active';
```

## Maintenance

Set up periodic cleanup:

```sql
-- Archive sessions older than 90 days
SELECT archive_old_sessions(90);

-- Cleanup old checkpoints (keep last 50 per thread)
-- This will be implemented in CheckpointManager.cleanup_old_checkpoints()
```
