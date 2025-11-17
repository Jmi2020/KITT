-- Migration: Add Research Results Display Support
-- Adds columns for final synthesis storage and follow-up lineage tracking

-- Add final_synthesis column to store AI-generated answers
ALTER TABLE research_sessions
ADD COLUMN IF NOT EXISTS final_synthesis TEXT;

-- Add parent_session_id for follow-up lineage
ALTER TABLE research_sessions
ADD COLUMN IF NOT EXISTS parent_session_id TEXT REFERENCES research_sessions(session_id) ON DELETE SET NULL;

-- Add synthesis metadata for tracking cost and model used
ALTER TABLE research_sessions
ADD COLUMN IF NOT EXISTS synthesis_model TEXT;

ALTER TABLE research_sessions
ADD COLUMN IF NOT EXISTS synthesis_cost_usd NUMERIC(10,4) DEFAULT 0.0;

-- Create index for efficient parent session lookups
CREATE INDEX IF NOT EXISTS idx_research_sessions_parent ON research_sessions(parent_session_id);

-- Add comment explaining follow-up chain
COMMENT ON COLUMN research_sessions.parent_session_id IS 'Reference to parent session for follow-up research chains';
COMMENT ON COLUMN research_sessions.final_synthesis IS 'AI-generated synthesis of all findings into coherent answer';
COMMENT ON COLUMN research_sessions.synthesis_model IS 'Model ID used to generate synthesis (e.g., claude-3-sonnet)';
COMMENT ON COLUMN research_sessions.synthesis_cost_usd IS 'Cost of generating synthesis';
