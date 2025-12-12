/**
 * Types for IO Control / Feature Flag management
 */

export interface Feature {
  id: string;
  name: string;
  description: string;
  category: string;
  env_var: string;
  default_value: boolean | string;
  current_value: boolean | string;
  restart_scope: 'none' | 'service' | 'stack' | 'llamacpp';
  requires: string[];
  enables: string[];
  conflicts_with: string[];
  validation_message?: string;
  setup_instructions?: string;
  docs_url?: string;
  can_enable: boolean;
  can_disable: boolean;
  dependencies_met: boolean;
}

export interface Preset {
  id: string;
  name: string;
  description: string;
  features: Record<string, boolean | string>;
  cost_estimate: Record<string, unknown>;
}

export interface PreviewChanges {
  dependencies: Record<string, string[]>;
  costs: Record<string, unknown>;
  restarts: Record<string, string[]>;
  conflicts: Record<string, string[]>;
  health_warnings: Record<string, string>;
}

export interface IOControlState {
  tool_availability: Record<string, boolean>;
  enabled_functions: string[];
  unavailable_message?: string;
  health_warnings: Array<{ feature_name: string; message: string }>;
  restart_impacts: Record<string, string[]>;
  cost_hints: Record<string, string>;
}

export type RestartScope = 'none' | 'service' | 'stack' | 'llamacpp';
