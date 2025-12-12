/**
 * System Tab - Feature Flag Management
 * Consolidates IOControl functionality into Settings
 */

import { useEffect, useState } from 'react';
import type { UseIOControlReturn } from '../../../hooks/useIOControl';
import type { Feature } from '../../../types/iocontrol';
import './SystemTab.css';

interface SystemTabProps {
  api: UseIOControlReturn;
}

export default function SystemTab({ api }: SystemTabProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [restartScopeFilter, setRestartScopeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showPreview, setShowPreview] = useState(false);

  useEffect(() => {
    api.loadFeatures();
    api.loadPresets();
    api.loadState();
  }, [api]);

  // Get unique categories
  const categories = ['all', ...Array.from(new Set(api.features.map((f) => f.category)))];

  // Filter features
  const filteredFeatures = api.features.filter((feature) => {
    if (selectedCategory !== 'all' && feature.category !== selectedCategory) return false;
    if (restartScopeFilter !== 'all' && feature.restart_scope !== restartScopeFilter) return false;
    if (
      searchQuery &&
      !feature.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
      !feature.description.toLowerCase().includes(searchQuery.toLowerCase())
    ) {
      return false;
    }
    return true;
  });

  // Group features by category
  const featuresByCategory: Record<string, Feature[]> = {};
  filteredFeatures.forEach((feature) => {
    if (!featuresByCategory[feature.category]) {
      featuresByCategory[feature.category] = [];
    }
    featuresByCategory[feature.category].push(feature);
  });

  const getRestartScopeColor = (scope: string) => {
    switch (scope) {
      case 'none':
        return 'scope-none';
      case 'service':
        return 'scope-service';
      case 'stack':
        return 'scope-stack';
      case 'llamacpp':
        return 'scope-llamacpp';
      default:
        return '';
    }
  };

  const getRestartScopeIcon = (scope: string) => {
    switch (scope) {
      case 'none':
        return '🟢';
      case 'service':
        return '🟡';
      case 'stack':
        return '🔴';
      case 'llamacpp':
        return '🟠';
      default:
        return '';
    }
  };

  const getFeatureValue = (feature: Feature): boolean | string => {
    if (api.pendingChanges.hasOwnProperty(feature.id)) {
      return api.pendingChanges[feature.id];
    }
    return feature.current_value;
  };

  const hasPendingChange = (featureId: string): boolean => {
    return api.pendingChanges.hasOwnProperty(featureId);
  };

  const handlePreviewClick = async () => {
    await api.previewChanges();
    setShowPreview(true);
  };

  const handleApplyClick = async () => {
    const success = await api.applyChanges();
    if (success) {
      setShowPreview(false);
    }
  };

  const handlePresetClick = async (presetId: string) => {
    if (!confirm(`Apply preset "${presetId}"? This will change multiple feature flags.`)) return;
    await api.applyPreset(presetId);
  };

  const pendingCount = Object.keys(api.pendingChanges).length;
  const totalFeatures = api.features.length;
  const enabledFeatures = api.features.filter((f) => Boolean(f.current_value)).length;
  const restartSummary = api.features.reduce<Record<string, number>>((acc, f) => {
    acc[f.restart_scope] = (acc[f.restart_scope] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="system-tab">
      {/* Stats Grid */}
      <div className="system-stats-grid">
        <div className="system-stat-card">
          <div className="stat-label">Pending Changes</div>
          <div className="stat-value">{pendingCount}</div>
          <div className="stat-hint">Preview before applying</div>
        </div>
        <div className="system-stat-card">
          <div className="stat-label">Features Enabled</div>
          <div className="stat-value">
            {enabledFeatures}/{totalFeatures || '—'}
          </div>
          <div className="stat-hint">Current on/off state</div>
        </div>
        <div className="system-stat-card">
          <div className="stat-label">Restart Scopes</div>
          <div className="stat-legend">
            <span className="legend-item scope-none">🟢 none ({restartSummary['none'] || 0})</span>
            <span className="legend-item scope-service">
              🟡 service ({restartSummary['service'] || 0})
            </span>
            <span className="legend-item scope-llamacpp">
              🟠 llama.cpp ({restartSummary['llamacpp'] || 0})
            </span>
            <span className="legend-item scope-stack">🔴 stack ({restartSummary['stack'] || 0})</span>
          </div>
        </div>
      </div>

      {/* Tool Availability */}
      {Object.keys(api.toolAvailability).length > 0 && (
        <div className="system-card availability-card">
          <div className="card-header">
            <h3>Tool Availability</h3>
            <small>Derived from providers, offline mode, and cloud routing</small>
          </div>
          <div className="availability-grid">
            {Object.entries(api.toolAvailability).map(([tool, enabled]) => (
              <div key={tool} className={`availability-item ${enabled ? 'ok' : 'off'}`}>
                <span className="dot" aria-hidden />{' '}
                {tool} {api.costHints[tool] ? `— ${api.costHints[tool]}` : ''}
              </div>
            ))}
          </div>
          {api.enabledFunctions.length > 0 && (
            <div className="enabled-functions">
              <strong>Enabled functions:</strong> {api.enabledFunctions.join(', ')}
            </div>
          )}
          {api.unavailableMessage && (
            <div className="unavailable-message">{api.unavailableMessage}</div>
          )}
          {api.healthWarnings.length > 0 && (
            <div className="health-warnings">
              <strong>Health warnings:</strong>
              <ul>
                {api.healthWarnings.map((hw, i) => (
                  <li key={i}>
                    {hw.feature_name}: {hw.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Error Banner */}
      {api.error && (
        <div className="error-banner">
          <strong>Error:</strong> {api.error}
          <button onClick={api.clearError}>×</button>
        </div>
      )}

      {/* Toolbar */}
      <div className="system-toolbar">
        <div className="toolbar-left">
          <input
            type="text"
            className="search-input"
            placeholder="Search features..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search features"
          />

          <select
            className="category-select"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            aria-label="Filter by category"
          >
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat === 'all' ? 'All Categories' : cat.replace(/_/g, ' ').toUpperCase()}
              </option>
            ))}
          </select>

          <select
            className="category-select"
            value={restartScopeFilter}
            onChange={(e) => setRestartScopeFilter(e.target.value)}
            aria-label="Filter by restart scope"
          >
            <option value="all">All restart scopes</option>
            <option value="none">No restart</option>
            <option value="service">Service restart</option>
            <option value="llamacpp">llama.cpp restart</option>
            <option value="stack">Stack restart</option>
          </select>
        </div>

        <div className="toolbar-right">
          {pendingCount > 0 && (
            <>
              <span className="pending-count">{pendingCount} pending changes</span>
              <button className="btn-secondary" onClick={api.cancelChanges}>
                Cancel
              </button>
              <button className="btn-warning" onClick={handlePreviewClick}>
                Preview Changes
              </button>
              <button className="btn-primary" onClick={handleApplyClick} disabled={api.loading}>
                Apply Changes
              </button>
            </>
          )}

          <button className="btn-small" onClick={api.loadFeatures}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Presets */}
      {api.presets.length > 0 && (
        <div className="presets-section">
          <h3>Quick Presets</h3>
          <div className="presets-grid">
            {api.presets.map((preset) => (
              <button
                key={preset.id}
                className="preset-card"
                onClick={() => handlePresetClick(preset.id)}
                disabled={api.loading}
              >
                <div className="preset-name">{preset.name}</div>
                <div className="preset-description">{preset.description}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Features by Category */}
      <div className="features-container">
        {Object.entries(featuresByCategory).map(([category, categoryFeatures]) => (
          <div key={category} className="feature-category">
            <h2 className="category-title">
              {category.replace(/_/g, ' ').toUpperCase()}
              <span className="feature-count">({categoryFeatures.length})</span>
            </h2>

            <div className="features-list">
              {categoryFeatures.map((feature) => {
                const currentValue = getFeatureValue(feature);
                const isPending = hasPendingChange(feature.id);
                const isBoolean = typeof feature.default_value === 'boolean';

                return (
                  <div
                    key={feature.id}
                    className={`feature-card ${isPending ? 'pending-change' : ''} ${!feature.can_enable && currentValue === false ? 'disabled' : ''}`}
                  >
                    <div className="feature-header">
                      <div className="feature-title-row">
                        <h3 className="feature-name">{feature.name}</h3>
                        <span
                          className={`restart-badge ${getRestartScopeColor(feature.restart_scope)}`}
                        >
                          {getRestartScopeIcon(feature.restart_scope)} {feature.restart_scope}
                        </span>
                      </div>

                      <div className="feature-toggle">
                        {isBoolean ? (
                          <label className="toggle-switch">
                            <input
                              type="checkbox"
                              checked={currentValue as boolean}
                              onChange={(e) => api.toggleFeature(feature.id, e.target.checked)}
                              disabled={
                                (Boolean(currentValue) && !feature.can_disable) ||
                                (!currentValue && !feature.can_enable)
                              }
                              aria-label={`Toggle ${feature.name}`}
                            />
                            <span className="toggle-slider"></span>
                          </label>
                        ) : (
                          <input
                            type="text"
                            value={currentValue as string}
                            onChange={(e) => api.toggleFeature(feature.id, e.target.value)}
                            className="feature-input"
                            aria-label={`Set ${feature.name} value`}
                          />
                        )}
                      </div>
                    </div>

                    <div className="feature-description">{feature.description}</div>

                    {isPending && (
                      <div className="pending-indicator">
                        ⚠️ Pending change: {String(feature.current_value)} → {String(currentValue)}
                      </div>
                    )}

                    {feature.requires.length > 0 && (
                      <div className="feature-dependencies">
                        <strong>Requires:</strong>{' '}
                        {feature.requires.map((reqId) => {
                          const reqFeature = api.features.find((f) => f.id === reqId);
                          const isMetFeature = reqFeature?.current_value;
                          return (
                            <span
                              key={reqId}
                              className={`dependency-tag ${isMetFeature ? 'met' : 'unmet'}`}
                            >
                              {reqFeature?.name || reqId}
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {feature.enables.length > 0 && (
                      <div className="feature-enables">
                        <strong>Enables:</strong>{' '}
                        {feature.enables.map((enableId) => {
                          const enableFeature = api.features.find((f) => f.id === enableId);
                          return (
                            <span key={enableId} className="enable-tag">
                              {enableFeature?.name || enableId}
                            </span>
                          );
                        })}
                      </div>
                    )}

                    {feature.conflicts_with.length > 0 && (
                      <div className="feature-conflicts">
                        <strong>⚠️ Conflicts with:</strong>{' '}
                        {feature.conflicts_with.map((conflictId) => {
                          const conflictFeature = api.features.find((f) => f.id === conflictId);
                          return (
                            <span key={conflictId} className="conflict-tag">
                              {conflictFeature?.name || conflictId}
                            </span>
                          );
                        })}
                      </div>
                    )}

                    <div className="feature-footer">
                      <code className="env-var">{feature.env_var}</code>
                      {feature.docs_url && (
                        <a
                          href={feature.docs_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="docs-link"
                        >
                          📚 Docs
                        </a>
                      )}
                    </div>

                    {!feature.dependencies_met && (
                      <div className="warning-banner">
                        ⚠️ Dependencies not met. Enable required features first.
                      </div>
                    )}

                    {feature.validation_message && currentValue && (
                      <div className="info-banner">{feature.validation_message}</div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Preview Modal */}
      {showPreview && api.previewData && (
        <div className="modal-overlay" onClick={() => setShowPreview(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Preview Changes</h2>
              <button className="modal-close" onClick={() => setShowPreview(false)}>
                ×
              </button>
            </div>

            <div className="modal-body">
              {Object.keys(api.previewData.conflicts).length > 0 && (
                <div className="preview-section conflicts">
                  <h3>⚠️ Conflicts Detected</h3>
                  {Object.entries(api.previewData.conflicts).map(([featureId, conflicts]) => (
                    <div key={featureId} className="conflict-item">
                      <strong>{featureId}</strong> conflicts with: {conflicts.join(', ')}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(api.previewData.health_warnings).length > 0 && (
                <div className="preview-section warnings">
                  <h3>⚠️ Health Warnings</h3>
                  {Object.entries(api.previewData.health_warnings).map(([featureId, warning]) => (
                    <div key={featureId} className="warning-item">
                      <strong>{featureId}:</strong> {warning}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(api.previewData.dependencies).length > 0 && (
                <div className="preview-section dependencies">
                  <h3>📋 Dependencies</h3>
                  {Object.entries(api.previewData.dependencies).map(([featureId, deps]) => (
                    <div key={featureId} className="dependency-item">
                      <strong>{featureId}</strong> will enable: {deps.join(', ')}
                    </div>
                  ))}
                </div>
              )}

              {api.previewData.restarts && Object.keys(api.previewData.restarts).length > 0 && (
                <div className="preview-section restarts">
                  <h3>🔄 Restarts Required</h3>
                  {Object.entries(api.previewData.restarts).map(([scope, services]) => (
                    <div key={scope} className="restart-item">
                      <span className={`restart-badge ${getRestartScopeColor(scope)}`}>
                        {getRestartScopeIcon(scope)} {scope}
                      </span>
                      {Array.isArray(services) && services.length > 0 && (
                        <span>: {services.join(', ')}</span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowPreview(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleApplyClick}
                disabled={
                  api.loading ||
                  (api.previewData && Object.keys(api.previewData.conflicts).length > 0)
                }
              >
                Apply Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {api.loading && <div className="loading-overlay">Loading...</div>}
    </div>
  );
}
