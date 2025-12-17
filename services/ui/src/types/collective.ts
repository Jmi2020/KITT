/**
 * TypeScript types for Collective Meta-Agent API
 */

export type CollectivePattern = 'council' | 'debate' | 'pipeline';

export interface CollectiveProposal {
  role: string;
  text: string;
  model?: string;
  temperature?: number;
  label?: string;
}

export interface CollectiveSession {
  session_id: string;
  task: string;
  pattern: CollectivePattern;
  k: number;
  status: 'pending' | 'running' | 'completed' | 'error' | 'cancelled';
  created_at: string;
  proposals: CollectiveProposal[];
  verdict: string | null;
  error?: string;
  proposals_count?: number;
  has_verdict?: boolean;
}

export interface CollectiveSessionList {
  sessions: CollectiveSession[];
  total: number;
}

export interface StreamStartRequest {
  task: string;
  pattern: CollectivePattern;
  k: number;
  userId?: string;
}

export interface StreamStartResponse {
  session_id: string;
  status: string;
  message: string;
}

// WebSocket event types
export type CollectiveEventType =
  | 'connection'
  | 'started'
  | 'plan_start'
  | 'plan_complete'
  | 'proposals_start'
  | 'proposal_start'
  | 'proposal_complete'
  | 'judge_start'
  | 'verdict_complete'
  | 'complete'
  | 'error'
  | 'cancelled';

export interface CollectiveEvent {
  type: CollectiveEventType;
  session_id?: string;
  message?: string;
  pattern?: CollectivePattern;
  k?: number;
  task?: string;
  plan?: string;
  count?: number;
  index?: number;
  role?: string;
  text?: string;
  model?: string;
  temperature?: number;
  verdict?: string;
  proposals?: CollectiveProposal[];
}

// Legacy non-streaming API types
export interface RunCollectiveRequest {
  task: string;
  pattern: CollectivePattern;
  k: number;
  max_steps?: number;
  conversationId?: string;
  userId?: string;
}

export interface RunCollectiveResponse {
  pattern: CollectivePattern;
  proposals: CollectiveProposal[];
  verdict: string;
  logs?: string;
  peer_reviews?: unknown[];
  aggregate_rankings?: unknown[];
  peer_review_enabled: boolean;
  aux: Record<string, unknown>;
}
