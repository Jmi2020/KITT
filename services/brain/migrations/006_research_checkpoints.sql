-- Migration 006: Research Session Checkpointing & State Management
-- Created: 2025-01-16
-- Purpose: Enable persistent, recoverable research sessions with LangGraph checkpointing

-- ============================================================================
-- LangGraph Checkpoint Tables (auto-created by PostgresSaver, but explicit for clarity)
-- ============================================================================

-- Main checkpoints table: stores full workflow state as JSONB
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ts
    ON checkpoints(thread_id, checkpoint_ns, (checkpoint->>'ts') DESC);

CREATE INDEX IF NOT EXISTS idx_checkpoints_parent
    ON checkpoints(parent_checkpoint_id);

-- Checkpoint blobs table: stores large data separately
CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_blobs_thread
    ON checkpoint_blobs(thread_id, checkpoint_ns);

-- Checkpoint writes table: tracks pending writes from failed nodes
CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread
    ON checkpoint_writes(thread_id, checkpoint_ns, checkpoint_id);

-- ============================================================================
-- Research Session Tables
-- ============================================================================

-- Research sessions: tracks lifecycle and metadata
CREATE TABLE IF NOT EXISTS research_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'active',  -- active, paused, completed, failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    thread_id TEXT,
    config JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}',

    -- Session statistics
    total_iterations INTEGER DEFAULT 0,
    total_findings INTEGER DEFAULT 0,
    total_sources INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10, 4) DEFAULT 0.0,
    external_calls_used INTEGER DEFAULT 0,

    -- Quality metrics
    completeness_score DECIMAL(3, 2),
    confidence_score DECIMAL(3, 2),
    saturation_status JSONB,

    CONSTRAINT valid_status CHECK (status IN ('active', 'paused', 'completed', 'failed')),
    CONSTRAINT valid_scores CHECK (
        completeness_score IS NULL OR (completeness_score >= 0 AND completeness_score <= 1)
    ),
    CONSTRAINT valid_confidence CHECK (
        confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)
    )
);

-- Indexes for research sessions
CREATE INDEX IF NOT EXISTS idx_research_sessions_user ON research_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_research_sessions_status ON research_sessions(status);
CREATE INDEX IF NOT EXISTS idx_research_sessions_created ON research_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_sessions_thread ON research_sessions(thread_id);

-- Foreign key to checkpoints (optional, for referential integrity)
ALTER TABLE research_sessions
    ADD CONSTRAINT fk_research_sessions_thread
    FOREIGN KEY (thread_id) REFERENCES checkpoints(thread_id)
    ON DELETE SET NULL;

-- Research findings: structured storage of findings
CREATE TABLE IF NOT EXISTS research_findings (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    finding_type TEXT,  -- material, property, supplier, cost, design, etc.
    content TEXT NOT NULL,
    confidence DECIMAL(3, 2),
    sources JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    iteration INTEGER,

    CONSTRAINT valid_finding_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

-- Indexes for research findings
CREATE INDEX IF NOT EXISTS idx_research_findings_session ON research_findings(session_id);
CREATE INDEX IF NOT EXISTS idx_research_findings_type ON research_findings(finding_type);
CREATE INDEX IF NOT EXISTS idx_research_findings_created ON research_findings(created_at DESC);

-- ============================================================================
-- Quality Metrics Tables
-- ============================================================================

-- Quality metrics: tracks RAGAS and other quality scores over time
CREATE TABLE IF NOT EXISTS quality_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    metric_type VARCHAR(50) NOT NULL,  -- faithfulness, relevancy, precision, recall, etc.
    metric_value DECIMAL(5, 4) NOT NULL,
    calculated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',

    CONSTRAINT valid_metric_value CHECK (metric_value >= 0 AND metric_value <= 1)
);

-- Indexes for quality metrics
CREATE INDEX IF NOT EXISTS idx_quality_metrics_session ON quality_metrics(session_id);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_type ON quality_metrics(metric_type);
CREATE INDEX IF NOT EXISTS idx_quality_metrics_calculated ON quality_metrics(calculated_at DESC);

-- Knowledge gaps: tracks missing topics and shallow coverage
CREATE TABLE IF NOT EXISTS knowledge_gaps (
    gap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    gap_type VARCHAR(50) NOT NULL,  -- coverage, depth, consistency
    severity DECIMAL(3, 2) NOT NULL,
    description TEXT,
    details JSONB DEFAULT '{}',
    resolved BOOLEAN DEFAULT FALSE,
    identified_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,

    CONSTRAINT valid_severity CHECK (severity >= 0 AND severity <= 1)
);

-- Indexes for knowledge gaps
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_session ON knowledge_gaps(session_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_type ON knowledge_gaps(gap_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_resolved ON knowledge_gaps(resolved);

-- Saturation tracking: tracks novelty rate and saturation detection
CREATE TABLE IF NOT EXISTS saturation_tracking (
    tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    sources_processed INTEGER NOT NULL,
    unique_themes_count INTEGER NOT NULL,
    novelty_rate DECIMAL(5, 4) NOT NULL,
    consecutive_low_novelty INTEGER DEFAULT 0,
    saturated BOOLEAN DEFAULT FALSE,
    checked_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_novelty_rate CHECK (novelty_rate >= 0 AND novelty_rate <= 1)
);

-- Indexes for saturation tracking
CREATE INDEX IF NOT EXISTS idx_saturation_tracking_session ON saturation_tracking(session_id);
CREATE INDEX IF NOT EXISTS idx_saturation_tracking_checked ON saturation_tracking(checked_at DESC);

-- Confidence scores: multi-factor confidence tracking
CREATE TABLE IF NOT EXISTS confidence_scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    finding_id INTEGER REFERENCES research_findings(id) ON DELETE CASCADE,
    overall_confidence DECIMAL(3, 2) NOT NULL,
    source_quality_score DECIMAL(3, 2),
    consensus_score DECIMAL(3, 2),
    recency_score DECIMAL(3, 2),
    evidence_strength_score DECIMAL(3, 2),
    verification_score DECIMAL(3, 2),
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_overall_confidence CHECK (overall_confidence >= 0 AND overall_confidence <= 1),
    CONSTRAINT valid_component_scores CHECK (
        (source_quality_score IS NULL OR (source_quality_score >= 0 AND source_quality_score <= 1)) AND
        (consensus_score IS NULL OR (consensus_score >= 0 AND consensus_score <= 1)) AND
        (recency_score IS NULL OR (recency_score >= 0 AND recency_score <= 1)) AND
        (evidence_strength_score IS NULL OR (evidence_strength_score >= 0 AND evidence_strength_score <= 1)) AND
        (verification_score IS NULL OR (verification_score >= 0 AND verification_score <= 1))
    )
);

-- Indexes for confidence scores
CREATE INDEX IF NOT EXISTS idx_confidence_scores_session ON confidence_scores(session_id);
CREATE INDEX IF NOT EXISTS idx_confidence_scores_finding ON confidence_scores(finding_id);
CREATE INDEX IF NOT EXISTS idx_confidence_scores_created ON confidence_scores(created_at DESC);

-- ============================================================================
-- Model Usage Tracking
-- ============================================================================

-- Model calls: track which models were used and their costs
CREATE TABLE IF NOT EXISTS model_calls (
    call_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    model_id VARCHAR(100) NOT NULL,  -- llama-3.1-8b-q4, gpt-4o, etc.
    model_family VARCHAR(50),        -- llama, gemma, openai, anthropic
    decision_type VARCHAR(100),      -- tool_selection, material_selection, etc.
    tier VARCHAR(20),                -- trivial, low, medium, high, critical
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd DECIMAL(10, 6) DEFAULT 0.0,
    latency_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    called_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes for model calls
CREATE INDEX IF NOT EXISTS idx_model_calls_session ON model_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_model ON model_calls(model_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_tier ON model_calls(tier);
CREATE INDEX IF NOT EXISTS idx_model_calls_called ON model_calls(called_at DESC);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to update research_sessions.updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_research_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on research_sessions
CREATE TRIGGER trigger_update_research_session_timestamp
    BEFORE UPDATE ON research_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_research_session_timestamp();

-- Function to calculate session statistics
CREATE OR REPLACE FUNCTION calculate_session_stats(p_session_id TEXT)
RETURNS TABLE(
    total_findings BIGINT,
    total_sources BIGINT,
    avg_confidence DECIMAL,
    latest_completeness DECIMAL,
    total_cost DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT rf.id)::BIGINT,
        COUNT(DISTINCT jsonb_array_elements(rf.sources))::BIGINT,
        AVG(rf.confidence)::DECIMAL(3,2),
        (SELECT completeness_score FROM research_sessions WHERE session_id = p_session_id),
        (SELECT SUM(cost_usd) FROM model_calls WHERE session_id = p_session_id)::DECIMAL(10,4)
    FROM research_findings rf
    WHERE rf.session_id = p_session_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Views for Monitoring
-- ============================================================================

-- View: Active research sessions with statistics
CREATE OR REPLACE VIEW v_active_research_sessions AS
SELECT
    rs.session_id,
    rs.user_id,
    rs.query,
    rs.status,
    rs.created_at,
    rs.updated_at,
    rs.total_iterations,
    rs.total_findings,
    rs.total_sources,
    rs.total_cost_usd,
    rs.external_calls_used,
    rs.completeness_score,
    rs.confidence_score,
    EXTRACT(EPOCH FROM (NOW() - rs.created_at)) / 60 AS duration_minutes,
    (
        SELECT COUNT(*)
        FROM quality_metrics qm
        WHERE qm.session_id = rs.session_id
        AND qm.metric_type = 'faithfulness'
        AND qm.metric_value >= 0.85
    ) AS high_quality_findings
FROM research_sessions rs
WHERE rs.status IN ('active', 'paused')
ORDER BY rs.updated_at DESC;

-- View: Session quality summary
CREATE OR REPLACE VIEW v_session_quality_summary AS
SELECT
    rs.session_id,
    rs.user_id,
    rs.status,
    AVG(CASE WHEN qm.metric_type = 'faithfulness' THEN qm.metric_value END) AS avg_faithfulness,
    AVG(CASE WHEN qm.metric_type = 'answer_relevancy' THEN qm.metric_value END) AS avg_relevancy,
    AVG(CASE WHEN qm.metric_type = 'context_precision' THEN qm.metric_value END) AS avg_precision,
    AVG(CASE WHEN qm.metric_type = 'context_recall' THEN qm.metric_value END) AS avg_recall,
    COUNT(DISTINCT kg.gap_id) AS total_gaps,
    COUNT(DISTINCT CASE WHEN kg.resolved THEN kg.gap_id END) AS resolved_gaps,
    MAX(st.saturated) AS is_saturated,
    MAX(st.novelty_rate) AS latest_novelty_rate
FROM research_sessions rs
LEFT JOIN quality_metrics qm ON rs.session_id = qm.session_id
LEFT JOIN knowledge_gaps kg ON rs.session_id = kg.session_id
LEFT JOIN saturation_tracking st ON rs.session_id = st.session_id
GROUP BY rs.session_id, rs.user_id, rs.status;

-- View: Model usage statistics
CREATE OR REPLACE VIEW v_model_usage_stats AS
SELECT
    model_id,
    model_family,
    tier,
    COUNT(*) AS total_calls,
    SUM(CASE WHEN success THEN 1 ELSE 0 END) AS successful_calls,
    ROUND(100.0 * SUM(CASE WHEN success THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate,
    SUM(cost_usd) AS total_cost_usd,
    AVG(latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
    SUM(input_tokens) AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens
FROM model_calls
GROUP BY model_id, model_family, tier
ORDER BY total_calls DESC;

-- ============================================================================
-- Data Retention Policy (Optional)
-- ============================================================================

-- Function to archive completed sessions older than 90 days
CREATE OR REPLACE FUNCTION archive_old_sessions(days_old INTEGER DEFAULT 90)
RETURNS INTEGER AS $$
DECLARE
    archived_count INTEGER;
BEGIN
    -- Archive to archive table (create if needed)
    CREATE TABLE IF NOT EXISTS research_sessions_archive (LIKE research_sessions INCLUDING ALL);

    WITH archived AS (
        DELETE FROM research_sessions
        WHERE status IN ('completed', 'failed')
        AND completed_at < NOW() - INTERVAL '1 day' * days_old
        RETURNING *
    )
    INSERT INTO research_sessions_archive
    SELECT * FROM archived;

    GET DIAGNOSTICS archived_count = ROW_COUNT;
    RETURN archived_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE checkpoints IS 'LangGraph checkpoint storage for fault-tolerant workflow execution';
COMMENT ON TABLE research_sessions IS 'Tracks autonomous research session lifecycle and statistics';
COMMENT ON TABLE research_findings IS 'Structured storage of research findings with confidence scores';
COMMENT ON TABLE quality_metrics IS 'RAGAS and other quality metrics tracked over time';
COMMENT ON TABLE knowledge_gaps IS 'Tracks coverage, depth, and consistency gaps in research';
COMMENT ON TABLE saturation_tracking IS 'Monitors novelty rate and data saturation for stopping criteria';
COMMENT ON TABLE confidence_scores IS 'Multi-factor confidence scoring for research findings';
COMMENT ON TABLE model_calls IS 'Tracks model usage, costs, and performance metrics';

COMMENT ON COLUMN research_sessions.status IS 'Session status: active (running), paused (user paused), completed (finished successfully), failed (error occurred)';
COMMENT ON COLUMN research_sessions.total_cost_usd IS 'Running total cost in USD from external API calls';
COMMENT ON COLUMN research_sessions.external_calls_used IS 'Count of external model API calls (GPT-4o, Claude, etc.)';

-- ============================================================================
-- Initial Data / Seed (if needed)
-- ============================================================================

-- No seed data required for this migration

-- ============================================================================
-- Migration Complete
-- ============================================================================

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 006 completed successfully: Research session checkpointing and state management tables created';
END $$;
