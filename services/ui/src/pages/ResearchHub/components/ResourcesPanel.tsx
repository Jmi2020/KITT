/**
 * ResourcesPanel - Memory mode + disk usage sidebar
 *
 * Displays current memory mode state, loaded models,
 * disk usage, and provides controls for mode switching and data compression.
 */

import { useEffect, useState } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import './ResourcesPanel.css';

interface ResourcesPanelProps {
  api: UseResearchApiReturn;
}

// Memory mode descriptions
const MODE_INFO: Record<string, { label: string; description: string; color: string }> = {
  idle: {
    label: 'IDLE',
    description: 'No models loaded',
    color: '#6b7280',
  },
  research: {
    label: 'RESEARCH',
    description: 'Paper harvesting & extraction',
    color: '#3b82f6',
  },
  collective: {
    label: 'COLLECTIVE',
    description: 'Multi-agent evaluation',
    color: '#f59e0b',
  },
  finetune: {
    label: 'FINETUNE',
    description: 'mlx-lm QLoRA training',
    color: '#8b5cf6',
  },
};

const ResourcesPanel = ({ api }: ResourcesPanelProps) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [compressAgeDays, setCompressAgeDays] = useState(30);
  const [isCompressing, setIsCompressing] = useState(false);

  // Load data on mount and periodically
  useEffect(() => {
    api.loadMemoryMode();
    api.loadDiskUsage();

    const interval = setInterval(() => {
      api.loadMemoryMode();
      api.loadDiskUsage();
    }, 30000); // Refresh every 30s

    return () => clearInterval(interval);
  }, [api.loadMemoryMode, api.loadDiskUsage]);

  const { memoryMode, diskUsage, loading } = api;

  // Handle mode switch
  const handleModeSwitch = async (mode: string) => {
    await api.setMemoryMode(mode);
  };

  // Handle compression
  const handleCompress = async () => {
    setIsCompressing(true);
    await api.compressOldData(compressAgeDays);
    setIsCompressing(false);
  };

  const modeInfo = memoryMode ? MODE_INFO[memoryMode.mode] || MODE_INFO.idle : MODE_INFO.idle;

  // Quota status styling
  const getQuotaStatusColor = () => {
    if (!diskUsage) return '#6b7280';
    switch (diskUsage.quota_status) {
      case 'ok':
        return '#4ade80';
      case 'warning':
        return '#f59e0b';
      case 'critical':
      case 'paused':
        return '#dc2626';
      default:
        return '#6b7280';
    }
  };

  if (isCollapsed) {
    return (
      <div className="resources-panel collapsed">
        <button
          className="expand-btn"
          onClick={() => setIsCollapsed(false)}
          title="Expand Resources Panel"
        >
          ◀
        </button>
        <div className="collapsed-indicator" style={{ borderColor: modeInfo.color }}>
          <span className="mode-badge" style={{ background: modeInfo.color }}>
            {modeInfo.label.charAt(0)}
          </span>
          {diskUsage && (
            <span className="disk-indicator" style={{ color: getQuotaStatusColor() }}>
              {diskUsage.usage_percent.toFixed(0)}%
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="resources-panel">
      <div className="panel-header">
        <h3>Resources</h3>
        <button
          className="collapse-btn"
          onClick={() => setIsCollapsed(true)}
          title="Collapse"
        >
          ▶
        </button>
      </div>

      {/* Memory Mode Section */}
      <div className="panel-section">
        <h4>Memory Mode</h4>

        {memoryMode ? (
          <>
            {/* Current Mode */}
            <div
              className="current-mode"
              style={{ borderColor: modeInfo.color }}
            >
              <span className="mode-badge" style={{ background: modeInfo.color }}>
                {modeInfo.label}
              </span>
              <span className="mode-desc">{modeInfo.description}</span>
            </div>

            {/* Memory Usage */}
            <div className="memory-usage">
              <div className="usage-bar">
                <div
                  className="usage-fill"
                  style={{
                    width: `${(memoryMode.memory_used_gb / (memoryMode.memory_used_gb + memoryMode.memory_available_gb)) * 100}%`,
                    background: modeInfo.color,
                  }}
                />
              </div>
              <div className="usage-text">
                {memoryMode.memory_used_gb.toFixed(1)}GB /{' '}
                {(memoryMode.memory_used_gb + memoryMode.memory_available_gb).toFixed(0)}GB
              </div>
            </div>

            {/* Loaded Models */}
            {memoryMode.models_loaded.length > 0 && (
              <div className="loaded-models">
                <span className="models-label">Loaded:</span>
                <div className="models-list">
                  {memoryMode.models_loaded.map((model) => (
                    <span key={model} className="model-chip">
                      {model}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Mode Switcher */}
            <div className="mode-switcher">
              <span className="switcher-label">Switch to:</span>
              <div className="mode-buttons">
                {Object.entries(MODE_INFO).map(([mode, info]) => (
                  <button
                    key={mode}
                    className={`mode-btn ${memoryMode.mode === mode ? 'current' : ''}`}
                    style={{
                      borderColor: memoryMode.can_transition_to?.includes(mode)
                        ? info.color
                        : 'var(--border-color)',
                    }}
                    onClick={() => handleModeSwitch(mode)}
                    disabled={
                      loading ||
                      memoryMode.mode === mode ||
                      !memoryMode.can_transition_to?.includes(mode)
                    }
                    title={info.description}
                  >
                    {info.label}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="loading-state">Loading memory status...</div>
        )}
      </div>

      {/* Disk Usage Section */}
      <div className="panel-section">
        <h4>Disk Quota</h4>

        {diskUsage ? (
          <>
            {/* Usage Bar */}
            <div className="disk-usage">
              <div className="usage-bar">
                <div
                  className="usage-fill"
                  style={{
                    width: `${diskUsage.usage_percent}%`,
                    background: getQuotaStatusColor(),
                  }}
                />
              </div>
              <div className="usage-text">
                {diskUsage.used_gb.toFixed(1)}GB / {diskUsage.quota_gb}GB
                <span
                  className="quota-status"
                  style={{ color: getQuotaStatusColor() }}
                >
                  ({diskUsage.quota_status.toUpperCase()})
                </span>
              </div>
            </div>

            {/* Breakdown */}
            <div className="disk-breakdown">
              <div className="breakdown-item">
                <span className="breakdown-label">Research Data:</span>
                <span className="breakdown-value">{diskUsage.research_data_gb.toFixed(1)}GB</span>
              </div>
              <div className="breakdown-item">
                <span className="breakdown-label">Expert Models:</span>
                <span className="breakdown-value">{diskUsage.expert_models_gb.toFixed(1)}GB</span>
              </div>
              <div className="breakdown-item">
                <span className="breakdown-label">Temp Files:</span>
                <span className="breakdown-value">{diskUsage.temp_files_gb.toFixed(1)}GB</span>
              </div>
            </div>

            {/* Compression */}
            <div className="compress-section">
              <div className="compress-header">
                <span>Compress files older than:</span>
                <select
                  value={compressAgeDays}
                  onChange={(e) => setCompressAgeDays(parseInt(e.target.value))}
                  disabled={loading || isCompressing}
                >
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={30}>30 days</option>
                  <option value={60}>60 days</option>
                  <option value={90}>90 days</option>
                </select>
              </div>
              <button
                className="btn-compress"
                onClick={handleCompress}
                disabled={loading || isCompressing}
              >
                {isCompressing ? 'Compressing...' : 'Compress Old Data'}
              </button>
            </div>

            {/* Quota Message */}
            {diskUsage.quota_message && (
              <div
                className="quota-message"
                style={{ borderColor: getQuotaStatusColor() }}
              >
                {diskUsage.quota_message}
              </div>
            )}
          </>
        ) : (
          <div className="loading-state">Loading disk status...</div>
        )}
      </div>
    </div>
  );
};

export default ResourcesPanel;
