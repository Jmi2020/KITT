/**
 * Runtime Tab - Service Lifecycle Management
 * Real-time monitoring and control of all KITTY services
 */

import { useState, useMemo } from 'react';
import { useServiceManager } from '../../../hooks/useServiceManager';
import type { ServiceStatus, ServiceCategory } from '../../../types/services';
import './RuntimeTab.css';

const POLL_OPTIONS = [
  { label: '2s', value: 2000 },
  { label: '5s', value: 5000 },
  { label: '10s', value: 10000 },
  { label: '30s', value: 30000 },
  { label: 'Paused', value: 0 },
];

function formatUptime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d`;
}

function formatLatency(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1) return '<1ms';
  return `${Math.round(ms)}ms`;
}

interface ServiceCardProps {
  service: ServiceStatus;
  isActionLoading: boolean;
  onStart: () => void;
  onStop: () => void;
  onRestart: () => void;
}

function ServiceCard({
  service,
  isActionLoading,
  onStart,
  onStop,
  onRestart,
}: ServiceCardProps) {
  const [expanded, setExpanded] = useState(false);

  const getTypeBadgeClass = (type: string) => {
    switch (type) {
      case 'native_process':
        return 'type-native';
      case 'docker_service':
        return 'type-docker';
      case 'docker_infra':
        return 'type-infra';
      default:
        return '';
    }
  };

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'native_process':
        return 'Native';
      case 'docker_service':
        return 'Docker';
      case 'docker_infra':
        return 'Infra';
      default:
        return type;
    }
  };

  return (
    <div className={`service-card ${service.is_healthy ? 'healthy' : 'unhealthy'}`}>
      <div className="service-card-header">
        <div className="service-info">
          <div className={`health-dot ${service.is_healthy ? 'healthy' : 'unhealthy'}`} />
          <div className="service-name-group">
            <span className="service-name">{service.display_name}</span>
            <span className={`service-type-badge ${getTypeBadgeClass(service.type)}`}>
              {getTypeLabel(service.type)}
            </span>
          </div>
        </div>
        <button
          className="expand-button"
          onClick={() => setExpanded(!expanded)}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? '▲' : '▼'}
        </button>
      </div>

      <div className="service-metrics">
        <span className="metric">
          <span className="metric-label">Port:</span>
          <span className="metric-value">{service.port}</span>
        </span>
        {service.is_running && service.uptime_seconds !== null && (
          <span className="metric">
            <span className="metric-label">Uptime:</span>
            <span className="metric-value">{formatUptime(service.uptime_seconds)}</span>
          </span>
        )}
        {service.health?.latency_ms !== null && service.health?.latency_ms !== undefined && (
          <span className="metric">
            <span className="metric-label">Latency:</span>
            <span className="metric-value">{formatLatency(service.health.latency_ms)}</span>
          </span>
        )}
        <span className={`status-badge ${service.is_running ? 'running' : 'stopped'}`}>
          {service.is_running ? 'Running' : 'Stopped'}
        </span>
      </div>

      <div className="service-actions">
        <button
          className="btn btn-sm btn-start"
          onClick={onStart}
          disabled={isActionLoading || service.is_running}
          title={service.is_running ? 'Already running' : 'Start service'}
        >
          {isActionLoading ? '...' : 'Start'}
        </button>
        <button
          className="btn btn-sm btn-stop"
          onClick={onStop}
          disabled={isActionLoading || !service.is_running}
          title={!service.is_running ? 'Already stopped' : 'Stop service'}
        >
          {isActionLoading ? '...' : 'Stop'}
        </button>
        <button
          className="btn btn-sm btn-restart"
          onClick={onRestart}
          disabled={isActionLoading}
          title="Restart service"
        >
          {isActionLoading ? '...' : 'Restart'}
        </button>
      </div>

      {expanded && (
        <div className="service-details">
          <div className="detail-row">
            <span className="detail-label">Name:</span>
            <span className="detail-value">{service.name}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">URL:</span>
            <span className="detail-value">{service.base_url}</span>
          </div>
          {service.pid && (
            <div className="detail-row">
              <span className="detail-label">PID:</span>
              <span className="detail-value">{service.pid}</span>
            </div>
          )}
          {service.container_id && (
            <div className="detail-row">
              <span className="detail-label">Container:</span>
              <span className="detail-value">{service.container_id.slice(0, 12)}</span>
            </div>
          )}
          <div className="detail-row">
            <span className="detail-label">Auto-start:</span>
            <span className="detail-value">{service.auto_start_enabled ? 'Yes' : 'No'}</span>
          </div>
          {service.health?.error && (
            <div className="detail-row error">
              <span className="detail-label">Error:</span>
              <span className="detail-value">{service.health.error}</span>
            </div>
          )}
          {service.last_started_at && (
            <div className="detail-row">
              <span className="detail-label">Started:</span>
              <span className="detail-value">
                {new Date(service.last_started_at).toLocaleString()}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function RuntimeTab() {
  const serviceManager = useServiceManager({ pollInterval: 5000 });
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<ServiceCategory>('all');
  const [pollInterval, setPollInterval] = useState(5000);

  // Filter and search services
  const filteredServices = useMemo(() => {
    let services = serviceManager.filterByCategory(selectedCategory);
    if (searchQuery.trim()) {
      const lower = searchQuery.toLowerCase();
      services = services.filter(
        (s) =>
          s.name.toLowerCase().includes(lower) ||
          s.display_name.toLowerCase().includes(lower)
      );
    }
    // Sort: running first, then by name
    return services.sort((a, b) => {
      if (a.is_running !== b.is_running) return a.is_running ? -1 : 1;
      return a.display_name.localeCompare(b.display_name);
    });
  }, [serviceManager, selectedCategory, searchQuery]);

  const handlePollIntervalChange = (value: number) => {
    setPollInterval(value);
    if (value === 0) {
      serviceManager.pausePolling();
    } else {
      serviceManager.resumePolling();
      serviceManager.setPollInterval(value);
    }
  };

  return (
    <div className="runtime-tab">
      {/* Stats Grid */}
      <div className="runtime-stats-grid">
        <div className="runtime-stat-card">
          <div className="stat-label">Total Services</div>
          <div className="stat-value">{serviceManager.totalCount || '—'}</div>
          <div className="stat-hint">Registered in manager</div>
        </div>
        <div className="runtime-stat-card healthy">
          <div className="stat-label">Healthy</div>
          <div className="stat-value">{serviceManager.healthyCount}</div>
          <div className="stat-hint">Running & responding</div>
        </div>
        <div className="runtime-stat-card unhealthy">
          <div className="stat-label">Unhealthy</div>
          <div className="stat-value">{serviceManager.unhealthyCount}</div>
          <div className="stat-hint">Stopped or failing</div>
        </div>
        <div className="runtime-stat-card">
          <div className="stat-label">Last Updated</div>
          <div className="stat-value stat-time">
            {serviceManager.lastUpdated
              ? serviceManager.lastUpdated.toLocaleTimeString()
              : '—'}
          </div>
          <div className="stat-hint">
            {serviceManager.isPaused ? 'Polling paused' : `Auto-refresh ${pollInterval / 1000}s`}
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {serviceManager.error && (
        <div className="error-banner">
          <span>{serviceManager.error}</span>
          <button onClick={serviceManager.clearError}>×</button>
        </div>
      )}

      {/* Toolbar */}
      <div className="runtime-toolbar">
        <div className="toolbar-left">
          <input
            type="text"
            className="search-input"
            placeholder="Search services..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <select
            className="category-select"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value as ServiceCategory)}
          >
            <option value="all">All Types</option>
            <option value="native">Native ({serviceManager.byCategory.native.length})</option>
            <option value="docker">Docker ({serviceManager.byCategory.docker.length})</option>
            <option value="infrastructure">
              Infrastructure ({serviceManager.byCategory.infrastructure.length})
            </option>
          </select>
        </div>
        <div className="toolbar-right">
          <select
            className="poll-select"
            value={pollInterval}
            onChange={(e) => handlePollIntervalChange(Number(e.target.value))}
          >
            {POLL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            className="btn btn-sm btn-refresh"
            onClick={serviceManager.refreshAll}
            disabled={serviceManager.loading}
          >
            {serviceManager.loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Services Grid */}
      {serviceManager.loading && serviceManager.totalCount === 0 ? (
        <div className="loading-state">
          <div className="loading-spinner" />
          <p>Loading services...</p>
        </div>
      ) : filteredServices.length === 0 ? (
        <div className="empty-state">
          <p>No services found matching your filters.</p>
        </div>
      ) : (
        <div className="services-grid">
          {filteredServices.map((service) => (
            <ServiceCard
              key={service.name}
              service={service}
              isActionLoading={serviceManager.actionLoading[service.name] || false}
              onStart={() => serviceManager.startService(service.name)}
              onStop={() => serviceManager.stopService(service.name)}
              onRestart={() => serviceManager.restartService(service.name)}
            />
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="runtime-legend">
        <div className="legend-item">
          <span className="health-dot healthy" /> Healthy
        </div>
        <div className="legend-item">
          <span className="health-dot unhealthy" /> Unhealthy
        </div>
        <span className="legend-separator">|</span>
        <div className="legend-item">
          <span className="service-type-badge type-native">Native</span> Host process
        </div>
        <div className="legend-item">
          <span className="service-type-badge type-docker">Docker</span> Container service
        </div>
        <div className="legend-item">
          <span className="service-type-badge type-infra">Infra</span> Infrastructure
        </div>
      </div>
    </div>
  );
}
