/**
 * TypeScript types for Service Manager API
 * Matches backend: services/common/src/common/service_manager/types.py
 */

export type ServiceType = 'native_process' | 'docker_service' | 'docker_infra';

export interface HealthStatus {
  service_name: string;
  is_healthy: boolean;
  checked_at: string;
  latency_ms: number | null;
  status_code: number | null;
  error: string | null;
  details: Record<string, unknown> | null;
}

export interface ServiceStatus {
  name: string;
  display_name: string;
  type: ServiceType;
  port: number;
  base_url: string;
  is_running: boolean;
  is_healthy: boolean;
  health: HealthStatus | null;
  pid: number | null;
  container_id: string | null;
  uptime_seconds: number | null;
  last_started_at: string | null;
  auto_start_enabled: boolean;
}

export interface ServiceListResponse {
  total: number;
  services: string[];
  native_processes: string[];
  docker_services: string[];
  infrastructure: string[];
  auto_startable: string[];
}

export interface ServiceSummaryResponse {
  healthy: string[];
  unhealthy: string[];
  total: number;
  healthy_count: number;
  unhealthy_count: number;
}

export interface ServiceActionResponse {
  success: boolean;
  service: string;
  message: string | null;
}

export type ServiceCategory = 'all' | 'native' | 'docker' | 'infrastructure';
