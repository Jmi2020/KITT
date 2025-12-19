/**
 * Research Hub Types
 * Shared interfaces for Research, Results, and Schedule components
 */

export interface ResearchSession {
  session_id: string;
  user_id: string;
  query: string;
  status: 'active' | 'completed' | 'paused' | 'failed' | 'pending';
  created_at: string;
  updated_at: string;
  completed_at?: string;
  thread_id?: string;
  config?: ResearchConfig;
  total_iterations: number;
  total_findings: number;
  total_sources: number;
  total_cost_usd: number;
  external_calls_used: number;
  completeness_score?: number;
  confidence_score?: number;
  saturation_status?: {
    threshold_met: boolean;
    novel_findings_last_n: number;
  };
}

export interface ResearchConfig {
  strategy?: string;
  max_iterations?: number;
  max_cost_usd?: number;
  base_priority?: number;
  enable_hierarchical?: boolean;
  max_sub_questions?: number;
  min_sub_questions?: number;
  sub_question_min_iterations?: number;
  sub_question_max_iterations?: number;
}

export interface ResearchTemplate {
  type: string;
  name: string;
  description: string;
  strategy: string;
  max_iterations: number;
  min_sources: number;
  min_confidence: number;
  use_debate: boolean;
}

// Research event types matching backend events.py
export type ResearchEventType =
  // Session lifecycle
  | 'connection'
  | 'session_started'
  | 'session_complete'
  | 'session_error'
  | 'session_paused'
  | 'session_resumed'
  // Iteration lifecycle
  | 'iteration_start'
  | 'iteration_complete'
  // Search events (fine-grained)
  | 'search_phase_start'
  | 'search_query_start'
  | 'search_query_complete'
  | 'search_cache_hit'
  | 'search_phase_complete'
  // Finding extraction events
  | 'extraction_start'
  | 'finding_extracted'
  | 'extraction_complete'
  // Validation events
  | 'validation_start'
  | 'validation_complete'
  // Quality/stopping events
  | 'quality_check'
  | 'saturation_check'
  | 'stopping_decision'
  // Synthesis events
  | 'synthesis_start'
  | 'synthesis_chunk'
  | 'synthesis_complete'
  // Legacy events for backward compatibility
  | 'progress'
  | 'complete'
  | 'error'
  | 'heartbeat';

export interface ResearchEvent {
  type: ResearchEventType;
  session_id: string;
  timestamp?: string;

  // Session events
  query?: string;
  config?: ResearchConfig;
  max_iterations?: number;
  max_cost_usd?: number;
  total_iterations?: number;
  total_findings?: number;
  total_sources?: number;
  total_cost_usd?: number;
  completeness_score?: number;
  confidence_score?: number;
  has_synthesis?: boolean;

  // Error events
  error?: string;
  error_type?: string;
  recoverable?: boolean;

  // Iteration events
  iteration?: number;
  strategy?: string;
  pending_queries?: string[];
  new_findings?: number;
  new_sources?: number;
  cost_this_iteration?: number;
  cumulative_findings?: number;
  cumulative_sources?: number;
  cumulative_cost?: number;

  // Search events
  query_count?: number;
  providers?: string[];
  query_index?: number;
  total_queries?: number;
  search_query?: string;
  provider?: string;
  results_count?: number;
  success?: boolean;
  cached?: boolean;
  latency_ms?: number;
  cache_age_seconds?: number;
  successful_queries?: number;
  cached_queries?: number;
  total_results?: number;
  dedup_saved?: number;

  // Finding extraction events
  sources_to_process?: number;
  finding_index?: number;
  finding_type?: string;
  content_preview?: string;
  confidence?: number;
  source_url?: string;
  source_title?: string;
  findings_extracted?: number;
  sources_processed?: number;

  // Validation events
  claims_to_validate?: number;
  claims_validated?: number;
  claims_rejected?: number;
  avg_confidence?: number;

  // Quality events
  ragas_score?: number;
  meets_threshold?: boolean;

  // Saturation events
  novel_findings_last_n?: number;
  saturation_threshold?: number;
  threshold_met?: boolean;
  novelty_rate?: number;

  // Stopping decision events
  should_stop?: boolean;
  reason?: string;
  criteria_met?: string[];
  criteria_not_met?: string[];

  // Synthesis events
  findings_count?: number;
  sources_count?: number;
  model?: string;
  chunk?: string;
  chunk_index?: number;
  synthesis_length?: number;
  model_used?: string;
  cost_usd?: number;

  // Connection events
  message?: string;

  // Heartbeat events
  status?: string;
  uptime_seconds?: number;

  // Legacy fields for backward compatibility
  node?: string;
  budget_remaining?: number;
  saturation?: {
    threshold_met?: boolean;
    novel_findings_last_n?: number;
  };
  stopping_decision?: {
    should_stop?: boolean;
    reason?: string;
  };
}

// Alias for backward compatibility
export type ProgressUpdate = ResearchEvent;

export interface SessionResults {
  session_id: string;
  query: string;
  status: string;
  final_synthesis: string | null;
  synthesis_model: string | null;
  findings: Finding[];
  total_findings: number;
  total_sources: number;
  total_cost_usd: number;
  completeness_score: number | null;
  confidence_score: number | null;
}

export interface Finding {
  id: number;
  finding_type: string;
  content: string;
  confidence: number;
  sources: FindingSource[];
  iteration: number;
  created_at: string;
}

export interface FindingSource {
  url: string;
  title?: string;
}

export interface Schedule {
  id: string;
  user_id: string;
  job_type: string;
  job_name: string;
  description?: string;
  natural_language_schedule?: string;
  cron_expression: string;
  timezone: string;
  enabled: boolean;
  budget_limit_usd?: number;
  priority: number;
  tags?: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  last_execution_at?: string;
  next_execution_at?: string;
}

export interface ScheduleExecution {
  id: string;
  job_name: string;
  status: 'success' | 'failed' | 'running';
  budget_spent_usd?: number;
  execution_time: string;
  error_message?: string;
}

export type ResearchHubTab = 'new' | 'active' | 'results' | 'schedule';
