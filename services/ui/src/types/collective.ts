/**
 * TypeScript types for Collective Meta-Agent API
 */

export type CollectivePattern = 'council' | 'debate' | 'pipeline';

export type ProviderType = 'local' | 'openai' | 'anthropic' | 'perplexity' | 'gemini';

/**
 * Specialist configuration for collective deliberation
 */
export interface SpecialistConfig {
  id: string;              // "openai_gpt4o_mini" or "local_q4"
  displayName: string;     // "GPT-4o-mini (OpenAI)"
  provider: ProviderType;  // Provider type for routing
  model: string;           // Model identifier
  description: string;     // What this specialist is good at
  costPer1mIn: number;     // Cost per 1M input tokens (USD)
  costPer1mOut: number;    // Cost per 1M output tokens (USD)
  isAvailable: boolean;    // API key present?
}

/**
 * Response from /api/collective/specialists endpoint
 */
export interface SpecialistsListResponse {
  specialists: SpecialistConfig[];
  localCount: number;
  cloudCount: number;
  availableCount: number;
}

/**
 * Cost estimate response
 */
export interface CostEstimateResponse {
  specialistIds: string[];
  estimatedCostUsd: number;
  tokensPerProposal: number;
}

export interface CollectiveProposal {
  role: string;
  text: string;
  model?: string;
  provider?: ProviderType;
  temperature?: number;
  label?: string;
  costUsd?: number;
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
  enableSearchPhase?: boolean;
  selectedSpecialists?: string[];  // List of specialist IDs (overrides k)
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
  | 'cancelled'
  // Search phase events (two-phase proposal generation)
  | 'search_phase_start'
  | 'phase1_start'
  | 'phase1_complete'
  | 'search_requests_collected'
  | 'search_execution_start'
  | 'search_executing'
  | 'search_complete'
  | 'search_phase_complete'
  | 'proposal_phase_start';

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
  // Provider info (multi-provider mode)
  provider?: ProviderType;
  cost_usd?: number;
  specialists?: Array<{
    id: string;
    display_name: string;
    provider: ProviderType;
    model: string;
  }>;
  // Search phase fields
  phase?: number;
  specialist_id?: string;
  search_request_count?: number;
  confidence_without_search?: number;
  queries?: string[];
  total_requests?: number;
  unique_queries?: number;
  duplicates_removed?: number;
  total?: number;
  query?: string;
  success?: boolean;
  result_count?: number;
  total_results?: number;
  successful_queries?: number;
  enable_search_phase?: boolean;
  two_phase?: boolean;
  has_search_results?: boolean;
  search_results_used?: number;
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
