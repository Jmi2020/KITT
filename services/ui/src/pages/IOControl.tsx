/**
 * I/O Control Dashboard - Feature Flag Management UI
 *
 * Features:
 * - Feature toggle switches with dependency visualization
 * - Real-time state display (Redis-backed)
 * - Restart scope indicators (NONE, SERVICE, STACK, LLAMACPP)
 * - Category grouping (AUTONOMOUS, SECURITY, PRINTING, etc.)
 * - Change preview before applying
 * - Preset configurations
 * - Dependency conflict warnings
 */

import { useState, useEffect } from 'react';
import './IOControl.css';

interface Feature {
  id: string;
  name: string;
  description: string;
  category: string;
  env_var: string;
  default_value: boolean | string;
  current_value: boolean | string;
  restart_scope: string;
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

interface Preset {
  id: string;
  name: string;
  description: string;
  features: Record<string, boolean | string>;
  cost_estimate: Record<string, any>;
}

interface PreviewChanges {
  dependencies: Record<string, string[]>;
  costs: Record<string, any>;
  restarts: Record<string, any>;
  conflicts: Record<string, string[]>;
  health_warnings: Record<string, string>;
}

const IOControl = () => {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [restartScopeFilter, setRestartScopeFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingChanges, setPendingChanges] = useState<Record<string, boolean | string>>({});
  const [previewData, setPreviewData] = useState<PreviewChanges | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  // Load features/state on mount
  useEffect(() => {
    loadFeatures();
    loadPresets();
    loadState();
  }, []);

  const [toolAvailability, setToolAvailability] = useState<Record<string, boolean>>({});
  const [enabledFunctions, setEnabledFunctions] = useState<string[]>([]);
  const [unavailableMessage, setUnavailableMessage] = useState<string | undefined>();
  const [healthWarnings, setHealthWarnings] = useState<any[]>([]);
  const [restartImpacts, setRestartImpacts] = useState<Record<string, string[]>>({});
  const [costHints, setCostHints] = useState<Record<string, string>>({});

  const loadFeatures = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/io-control/features');
      if (!response.ok) throw new Error('Failed to load features');
      const data: Feature[] = await response.json();
      setFeatures(data);
    } catch (err: any) {
      console.error('Error loading features:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadPresets = async () => {
    try {
      const response = await fetch('/api/io-control/presets');
      if (!response.ok) throw new Error('Failed to load presets');
      const data = await response.json();
      setPresets(data.presets || []);
    } catch (err: any) {
      console.error('Error loading presets:', err);
    }
  };

  const loadState = async () => {
    try {
      const response = await fetch('/api/io-control/state');
      if (!response.ok) throw new Error('Failed to load state');
      const data = await response.json();
      setToolAvailability(data.tool_availability || {});
      setEnabledFunctions(data.enabled_functions || []);
      setUnavailableMessage(data.unavailable_message);
      setHealthWarnings(data.health_warnings || []);
      setRestartImpacts(data.restart_impacts || {});
      setCostHints(data.cost_hints || {});
    } catch (err: any) {
      console.warn('Error loading state:', err);
    }
  };

  const toggleFeature = async (featureId: string, newValue: boolean | string) => {
    // Add to pending changes
    setPendingChanges((prev) => ({ ...prev, [featureId]: newValue }));
  };

  const previewChanges = async () => {
    if (Object.keys(pendingChanges).length === 0) return;

    try {
      const response = await fetch('/api/io-control/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ changes: pendingChanges }),
      });

      if (!response.ok) throw new Error('Failed to preview changes');
      const data = await response.json();
      setPreviewData(data);
      setShowPreview(true);
    } catch (err: any) {
      console.error('Error previewing changes:', err);
      setError(err.message);
    }
  };

  const applyChanges = async () => {
    if (Object.keys(pendingChanges).length === 0) return;

    setLoading(true);
    try {
      const response = await fetch('/api/io-control/features/bulk-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ changes: pendingChanges, persist: true }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to apply changes');
      }

      // Reload features and clear pending changes
      await loadFeatures();
      setPendingChanges({});
      setShowPreview(false);
      setPreviewData(null);
    } catch (err: any) {
      console.error('Error applying changes:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = async (presetId: string) => {
    if (!confirm(`Apply preset "${presetId}"? This will change multiple feature flags.`)) return;

    setLoading(true);
    try {
      const response = await fetch(`/api/io-control/presets/${presetId}/apply`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to apply preset');

      // Reload features
      await loadFeatures();
      setPendingChanges({});
    } catch (err: any) {
      console.error('Error applying preset:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const cancelChanges = () => {
    setPendingChanges({});
    setShowPreview(false);
    setPreviewData(null);
  };

  // Get unique categories
  const categories = ['all', ...Array.from(new Set(features.map((f) => f.category)))];

  // Filter features
  const filteredFeatures = features.filter((feature) => {
    if (selectedCategory !== 'all' && feature.category !== selectedCategory) return false;
    if (searchQuery && !feature.name.toLowerCase().includes(searchQuery.toLowerCase()) &&
        !feature.description.toLowerCase().includes(searchQuery.toLowerCase())) {
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
      case 'none': return 'scope-none';
      case 'service': return 'scope-service';
      case 'stack': return 'scope-stack';
      case 'llamacpp': return 'scope-llamacpp';
      default: return '';
    }
  };

  const getRestartScopeIcon = (scope: string) => {
    switch (scope) {
      case 'none': return '🟢';
      case 'service': return '🟡';
      case 'stack': return '🔴';
      case 'llamacpp': return '🟠';
      default: return '';
    }
  };

  const getFeatureValue = (feature: Feature): boolean | string => {
    if (pendingChanges.hasOwnProperty(feature.id)) {
      return pendingChanges[feature.id];
    }
    return feature.current_value;
  };

  const hasPendingChange = (featureId: string): boolean => {
    return pendingChanges.hasOwnProperty(featureId);
  };

  const copyCommand = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
    } catch (e) {
      window.prompt('Copy command', command);
    }
  };

  const totalFeatures = features.length;
  const enabledFeatures = features.filter((f) => Boolean(f.current_value)).length;
  const pendingCount = Object.keys(pendingChanges).length;
  const restartSummary = features.reduce<Record<string, number>>((acc, f) => {
    acc[f.restart_scope] = (acc[f.restart_scope] || 0) + 1;
    return acc;
  }, {});

  const [toolAvailability, setToolAvailability] = useState<Record<string, boolean>>({});
  const [enabledFunctions, setEnabledFunctions] = useState<string[]>([]);
  const [unavailableMessage, setUnavailableMessage] = useState<string | undefined>();
  const [healthWarnings, setHealthWarnings] = useState<any[]>([]);
  const [restartImpacts, setRestartImpacts] = useState<Record<string, string[]>>({});
  const [costHints, setCostHints] = useState<Record<string, string>>({});

  const matchesRestartScope = (feature: Feature) => {
    if (restartScopeFilter === 'all') return true;
    return feature.restart_scope === restartScopeFilter;
  };

  return (
    <div className="iocontrol-page">
      <div className="iocontrol-header">
        <h1>⚙️ I/O Control Dashboard</h1>
        <p className="subtitle">
          Manage external device integrations and feature flags with dependency validation
        </p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Pending Changes</div>
          <div className="stat-value">{pendingCount}</div>
          <div className="stat-hint">Preview before applying</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Features Enabled</div>
          <div className="stat-value">
            {enabledFeatures}/{totalFeatures || '—'}
          </div>
          <div className="stat-hint">Current on/off state</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Restart Scopes</div>
          <div className="stat-legend">
            <span className="legend-item scope-none">🟢 none ({restartSummary['none'] || 0})</span>
            <span className="legend-item scope-service">🟡 service ({restartSummary['service'] || 0})</span>
            <span className="legend-item scope-llamacpp">🟠 llama.cpp ({restartSummary['llamacpp'] || 0})</span>
            <span className="legend-item scope-stack">🔴 stack ({restartSummary['stack'] || 0})</span>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Quick Links</div>
          <div className="stat-links">
            <span className="link-pill" onClick={() => copyCommand('kitty-launcher run')}>Access-All Console</span>
            <span className="link-pill" onClick={() => copyCommand('kitty-cli shell')}>CLI Shell</span>
            <span className="link-pill" onClick={() => window.open('http://localhost:4173', '_blank')}>Web UI</span>
          </div>
        </div>
      </div>

      {/* Tool Availability Snapshot */}
      <div className="card availability-card">
        <div className="card-header">
          <h3>Tool Availability</h3>
          <small>Derived from providers, offline mode, and cloud routing</small>
        </div>
        <div className="availability-grid">
          {Object.entries(toolAvailability).map(([tool, enabled]) => (
            <div key={tool} className={`availability-item ${enabled ? 'ok' : 'off'}`}>
              <span className="dot" aria-hidden /> {tool} {costHints[tool] ? `— ${costHints[tool]}` : ''}
            </div>
          ))}
        </div>
        {enabledFunctions.length > 0 && (
          <div className="enabled-functions">
            <strong>Enabled functions:</strong> {enabledFunctions.join(', ')}
          </div>
        )}
        {unavailableMessage && (
          <div className="unavailable-message">
            {unavailableMessage}
          </div>
        )}
        {healthWarnings && healthWarnings.length > 0 && (
          <div className="health-warnings">
            <strong>Health warnings:</strong>
            <ul>
              {healthWarnings.map((hw, i) => (
                <li key={i}>{hw.feature_name}: {hw.message}</li>
              ))}
            </ul>
          </div>
        )}
        {restartImpacts && Object.keys(restartImpacts).length > 0 && (
          <div className="restart-impacts">
            <strong>Restart impacts:</strong>
            <ul>
              {Object.entries(restartImpacts).map(([scope, services]) => (
                <li key={scope}>{scope}: {services.join(', ')}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {error && (
        <div className="error-banner">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="iocontrol-toolbar">
        <div className="toolbar-left">
          <input
            type="text"
            className="search-input"
            placeholder="Search features..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <select
            className="category-select"
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
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
              <button className="btn-secondary" onClick={cancelChanges}>
                Cancel
              </button>
              <button className="btn-warning" onClick={previewChanges}>
                Preview Changes
              </button>
              <button className="btn-primary" onClick={applyChanges} disabled={loading}>
                Apply Changes
              </button>
            </>
          )}

          <button className="btn-small" onClick={loadFeatures}>
            🔄 Refresh
          </button>
        </div>
      </div>

      {/* Presets */}
      {presets.length > 0 && (
        <div className="presets-section">
          <h3>Quick Presets</h3>
          <div className="presets-grid">
            {presets.map((preset) => (
              <button
                key={preset.id}
                className="preset-card"
                onClick={() => applyPreset(preset.id)}
                disabled={loading}
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
        {Object.entries(featuresByCategory).map(([category, categoryFeatures]) => {
          const scoped = categoryFeatures.filter(matchesRestartScope);
          if (scoped.length === 0) return null;
          return (
            <div key={category} className="feature-category">
              <h2 className="category-title">
                {category.replace(/_/g, ' ').toUpperCase()}
                <span className="feature-count">({scoped.length})</span>
              </h2>

              <div className="features-list">
                {scoped.map((feature) => {
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
                          <span className={`restart-badge ${getRestartScopeColor(feature.restart_scope)}`}>
                            {getRestartScopeIcon(feature.restart_scope)} {feature.restart_scope}
                          </span>
                        </div>

                        <div className="feature-toggle">
                          {isBoolean ? (
                            <label className="toggle-switch">
                              <input
                                type="checkbox"
                                checked={currentValue as boolean}
                                onChange={(e) => toggleFeature(feature.id, e.target.checked)}
                                disabled={
                                  (currentValue && !feature.can_disable) ||
                                  (!currentValue && !feature.can_enable)
                                }
                              />
                              <span className="toggle-slider"></span>
                            </label>
                          ) : (
                            <input
                              type="text"
                              value={currentValue as string}
                              onChange={(e) => toggleFeature(feature.id, e.target.value)}
                              className="feature-input"
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
                            const reqFeature = features.find((f) => f.id === reqId);
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
                            const enableFeature = features.find((f) => f.id === enableId);
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
                            const conflictFeature = features.find((f) => f.id === conflictId);
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
                          <a href={feature.docs_url} target="_blank" rel="noopener noreferrer" className="docs-link">
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
          );
        })}
      </div>

      {/* Preview Modal */}
      {showPreview && previewData && (
        <div className="modal-overlay" onClick={() => setShowPreview(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Preview Changes</h2>
              <button className="modal-close" onClick={() => setShowPreview(false)}>
                ×
              </button>
            </div>

            <div className="modal-body">
              {Object.keys(previewData.conflicts).length > 0 && (
                <div className="preview-section conflicts">
                  <h3>⚠️ Conflicts Detected</h3>
                  {Object.entries(previewData.conflicts).map(([featureId, conflicts]) => (
                    <div key={featureId} className="conflict-item">
                      <strong>{featureId}</strong> conflicts with: {conflicts.join(', ')}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(previewData.health_warnings).length > 0 && (
                <div className="preview-section warnings">
                  <h3>⚠️ Health Warnings</h3>
                  {Object.entries(previewData.health_warnings).map(([featureId, warning]) => (
                    <div key={featureId} className="warning-item">
                      <strong>{featureId}:</strong> {warning}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(previewData.dependencies).length > 0 && (
                <div className="preview-section dependencies">
                  <h3>📋 Dependencies</h3>
                  {Object.entries(previewData.dependencies).map(([featureId, deps]) => (
                    <div key={featureId} className="dependency-item">
                      <strong>{featureId}</strong> will enable: {deps.join(', ')}
                    </div>
                  ))}
                </div>
              )}

              {previewData.restarts && Object.keys(previewData.restarts).length > 0 && (
                <div className="preview-section restarts">
                  <h3>🔄 Restarts Required</h3>
                  {Object.entries(previewData.restarts).map(([scope, services]: [string, any]) => (
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
                onClick={applyChanges}
                disabled={loading || Object.keys(previewData.conflicts).length > 0}
              >
                Apply Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && <div className="loading-overlay">Loading...</div>}
    </div>
  );
};

export default IOControl;
