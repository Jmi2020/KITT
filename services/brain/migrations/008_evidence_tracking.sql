-- Migration 008: Evidence-First Claim Tracking
-- Adds structured claims and evidence tables for verifiable research output
-- Date: 2025-11-17
-- Dependencies: 007_research_results.sql

-- ============================================================================
-- CLAIMS TABLE
-- ============================================================================
-- Stores atomic claims extracted from research with verification scores
CREATE TABLE IF NOT EXISTS research_claims (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    sub_question_id TEXT,  -- NULL for flat research, set for hierarchical
    claim_text TEXT NOT NULL,
    entailment_score REAL NOT NULL DEFAULT 0.0,  -- NLI verification 0-1
    provenance_score REAL NOT NULL DEFAULT 0.0,  -- Quote coverage 0-1
    dedupe_fingerprint TEXT NOT NULL,            -- For clustering duplicates
    confidence REAL NOT NULL DEFAULT 0.0,        -- Overall confidence 0-1
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    iteration INTEGER DEFAULT 0                   -- Which research iteration produced this
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_claims_session ON research_claims(session_id);
CREATE INDEX IF NOT EXISTS idx_claims_sub_question ON research_claims(sub_question_id);
CREATE INDEX IF NOT EXISTS idx_claims_fingerprint ON research_claims(dedupe_fingerprint);
CREATE INDEX IF NOT EXISTS idx_claims_confidence ON research_claims(session_id, confidence DESC);

-- ============================================================================
-- EVIDENCE TABLE
-- ============================================================================
-- Stores verbatim quotes and their source attribution for claims
CREATE TABLE IF NOT EXISTS research_evidence (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,  -- Links to source in research_findings.sources JSONB
    url TEXT NOT NULL,
    title TEXT,
    quote TEXT NOT NULL,      -- Exact verbatim text from source
    char_start INTEGER,       -- Character offset where quote begins (optional)
    char_end INTEGER,         -- Character offset where quote ends (optional)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for evidence lookups
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON research_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON research_evidence(source_id);

-- ============================================================================
-- VIEWS FOR CONVENIENCE
-- ============================================================================

-- View: Claims with evidence count
CREATE OR REPLACE VIEW vw_claims_with_evidence AS
SELECT
    c.id,
    c.session_id,
    c.sub_question_id,
    c.claim_text,
    c.entailment_score,
    c.provenance_score,
    c.confidence,
    c.iteration,
    COUNT(e.id) as evidence_count,
    COUNT(DISTINCT e.url) as unique_sources
FROM research_claims c
LEFT JOIN research_evidence e ON c.id = e.claim_id
GROUP BY c.id, c.session_id, c.sub_question_id, c.claim_text,
         c.entailment_score, c.provenance_score, c.confidence, c.iteration;

-- View: Session claim summary
CREATE OR REPLACE VIEW vw_session_claim_summary AS
SELECT
    session_id,
    COUNT(*) as total_claims,
    AVG(entailment_score) as avg_entailment,
    AVG(provenance_score) as avg_provenance,
    AVG(confidence) as avg_confidence,
    COUNT(DISTINCT dedupe_fingerprint) as unique_claim_clusters,
    MIN(confidence) as min_confidence,
    MAX(confidence) as max_confidence
FROM research_claims
GROUP BY session_id;

-- ============================================================================
-- BACKWARD COMPATIBILITY
-- ============================================================================
-- research_findings table remains unchanged - we keep both systems during transition
-- Claims are OPTIONAL - old sessions without claims still work
-- New sessions can have claims, findings, or both

-- Add comment explaining the relationship
COMMENT ON TABLE research_claims IS
'Structured atomic claims with evidence attribution. Replaces unstructured text in research_findings for evidence-first research. Both tables coexist during transition.';

COMMENT ON TABLE research_evidence IS
'Verbatim quotes supporting claims, with source attribution and optional character offsets for precise reference.';

-- ============================================================================
-- MIGRATION VALIDATION
-- ============================================================================

-- Verify tables exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'research_claims') THEN
        RAISE EXCEPTION 'Migration failed: research_claims table not created';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'research_evidence') THEN
        RAISE EXCEPTION 'Migration failed: research_evidence table not created';
    END IF;

    RAISE NOTICE 'Migration 008 completed successfully: evidence tracking tables created';
END $$;
