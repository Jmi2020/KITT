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

export interface ProgressUpdate {
  type: 'connection' | 'progress' | 'complete' | 'error';
  node?: string;
  iteration?: number;
  status?: string;
  findings_count?: number;
  sources_count?: number;
  budget_remaining?: number;
  saturation?: {
    threshold_met?: boolean;
    novel_findings_last_n?: number;
  };
  stopping_decision?: {
    should_stop?: boolean;
    reason?: string;
  };
  error?: string;
  message?: string;
  timestamp?: string;
}

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
