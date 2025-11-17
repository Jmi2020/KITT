/**
 * Research Page - Autonomous Research Pipeline UI
 *
 * Features:
 * - Research query input with strategy selection
 * - Real-time WebSocket streaming with progress bars
 * - Iteration counter, findings list, saturation visualization
 * - Budget tracking display (spent/remaining)
 * - Quality metrics dashboard (RAGAS, confidence, novelty)
 * - Session history browser
 */

import { useState, useEffect, useRef } from 'react';
import './Research.css';

interface ResearchSession {
  session_id: string;
  user_id: string;
  query: string;
  status: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  thread_id?: string;
  config?: {
    max_iterations?: number;
    max_cost_usd?: number;
  };
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

interface ProgressUpdate {
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

interface ResearchTemplate {
  type: string;
  name: string;
  description: string;
  strategy: string;
  max_iterations: number;
  min_sources: number;
  min_confidence: number;
  use_debate: boolean;
}

const Research = () => {
  // State
  const [query, setQuery] = useState('');
  const [userId, setUserId] = useState('demo-user');
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [templates, setTemplates] = useState<ResearchTemplate[]>([]);
  const [maxIterations, setMaxIterations] = useState(10);
  const [maxCost, setMaxCost] = useState(2.0);
  const [strategy, setStrategy] = useState('hybrid');
  const [enablePaidTools, setEnablePaidTools] = useState(false);
  const [activeSession, setActiveSession] = useState<ResearchSession | null>(null);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Real-time streaming state
  const [connected, setConnected] = useState(false);
  const [currentIteration, setCurrentIteration] = useState(0);
  const [findingsCount, setFindingsCount] = useState(0);
  const [sourcesCount, setSourcesCount] = useState(0);
  const [budgetRemaining, setBudgetRemaining] = useState(0);
  const [saturation, setSaturation] = useState<any>(null);
  const [progressLogs, setProgressLogs] = useState<ProgressUpdate[]>([]);

  // WebSocket ref
  const wsRef = useRef<WebSocket | null>(null);

  // Load templates and sessions on mount
  useEffect(() => {
    loadTemplates();
    loadSessions();
  }, [userId]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await fetch('/api/research/templates');
      if (!response.ok) throw new Error('Failed to load templates');
      const data = await response.json();
      setTemplates(data.templates || []);
    } catch (err: any) {
      console.error('Error loading templates:', err);
    }
  };

  const loadSessions = async () => {
    try {
      const response = await fetch(
        `/api/research/sessions?user_id=${encodeURIComponent(userId)}&limit=20`
      );
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err: any) {
      console.error('Error loading sessions:', err);
      setError(err.message);
    }
  };

  const createSession = async () => {
    if (!query.trim() || query.length < 10) {
      setError('Query must be at least 10 characters');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const requestBody: any = {
        query: query.trim(),
        user_id: userId,
        config: {
          strategy: strategy,
          max_iterations: maxIterations,
          max_cost_usd: maxCost,
        },
      };

      // Add base_priority if paid tools enabled (triggers Perplexity usage)
      if (enablePaidTools) {
        requestBody.config.base_priority = 0.7;
      }

      // Include template if selected
      if (selectedTemplate) {
        requestBody.template = selectedTemplate;
      }

      const response = await fetch('/api/research/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create session');
      }

      const data = await response.json();

      // Get full session details
      const sessionResponse = await fetch(`/api/research/sessions/${data.session_id}`);
      const sessionData = await sessionResponse.json();

      setActiveSession(sessionData);

      // Connect to WebSocket for streaming
      connectWebSocket(data.session_id);

      // Reload sessions list
      loadSessions();
    } catch (err: any) {
      console.error('Error creating session:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const connectWebSocket = (sessionId: string) => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Construct WebSocket URL (use wss:// for production)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/research/sessions/${sessionId}/stream`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const update: ProgressUpdate = JSON.parse(event.data);

        // Add to progress logs
        setProgressLogs((prev) => [...prev, update]);

        // Update UI state based on message type
        if (update.type === 'progress') {
          setCurrentIteration(update.iteration || 0);
          setFindingsCount(update.findings_count || 0);
          setSourcesCount(update.sources_count || 0);
          setBudgetRemaining(update.budget_remaining || 0);
          setSaturation(update.saturation);
        } else if (update.type === 'complete') {
          console.log('Research completed');
          setConnected(false);
          // Reload session details
          if (activeSession) {
            loadSessionDetails(activeSession.session_id);
          }
          loadSessions();
        } else if (update.type === 'error') {
          console.error('WebSocket error:', update.error);
          setError(update.error || 'Unknown error');
          setConnected(false);
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('WebSocket connection error');
      setConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      setConnected(false);
    };

    wsRef.current = ws;
  };

  const loadSessionDetails = async (sessionId: string) => {
    try {
      const response = await fetch(`/api/research/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session details');
      const data = await response.json();
      setActiveSession(data);
    } catch (err: any) {
      console.error('Error loading session details:', err);
    }
  };

  const pauseSession = async () => {
    if (!activeSession) return;

    try {
      const response = await fetch(`/api/research/sessions/${activeSession.session_id}/pause`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to pause session');

      // Disconnect WebSocket
      if (wsRef.current) {
        wsRef.current.close();
      }

      loadSessionDetails(activeSession.session_id);
      loadSessions();
    } catch (err: any) {
      console.error('Error pausing session:', err);
      setError(err.message);
    }
  };

  const resumeSession = async () => {
    if (!activeSession) return;

    try {
      const response = await fetch(`/api/research/sessions/${activeSession.session_id}/resume`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to resume session');

      // Reconnect WebSocket
      connectWebSocket(activeSession.session_id);

      loadSessionDetails(activeSession.session_id);
      loadSessions();
    } catch (err: any) {
      console.error('Error resuming session:', err);
      setError(err.message);
    }
  };

  const cancelSession = async () => {
    if (!activeSession) return;
    if (!confirm('Are you sure you want to cancel this session?')) return;

    try {
      const response = await fetch(`/api/research/sessions/${activeSession.session_id}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to cancel session');

      // Disconnect WebSocket
      if (wsRef.current) {
        wsRef.current.close();
      }

      setActiveSession(null);
      setProgressLogs([]);
      loadSessions();
    } catch (err: any) {
      console.error('Error cancelling session:', err);
      setError(err.message);
    }
  };

  const selectSession = (session: ResearchSession) => {
    setActiveSession(session);
    setQuery(session.query);
    setProgressLogs([]);

    // If session is active, connect to stream
    if (session.status === 'active') {
      connectWebSocket(session.session_id);
    }
  };

  const selectTemplateHandler = (templateType: string) => {
    setSelectedTemplate(templateType);

    // Auto-fill settings based on template
    const template = templates.find(t => t.type === templateType);
    if (template) {
      setMaxIterations(template.max_iterations);
      // Keep max cost user-defined, just update iterations
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'status-active';
      case 'completed': return 'status-completed';
      case 'paused': return 'status-paused';
      case 'failed': return 'status-failed';
      default: return '';
    }
  };

  return (
    <div className="research-page">
      <div className="research-header">
        <h1>🔬 Autonomous Research Pipeline</h1>
        <p className="subtitle">
          Multi-phase research with LangGraph streaming, budget tracking, and quality metrics
        </p>
      </div>

      {error && (
        <div className="error-banner">
          <strong>Error:</strong> {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="research-container">
        {/* Left Panel: New Research / Active Session */}
        <div className="research-main">
          {!activeSession ? (
            <div className="research-form">
              <h2>Start New Research</h2>

              <div className="form-group">
                <label htmlFor="template">Research Template</label>
                <select
                  id="template"
                  value={selectedTemplate}
                  onChange={(e) => selectTemplateHandler(e.target.value)}
                  disabled={loading}
                >
                  <option value="">Auto-detect (recommended)</option>
                  {templates.map((template) => (
                    <option key={template.type} value={template.type}>
                      {template.name} - {template.description}
                    </option>
                  ))}
                </select>
                <small>
                  {selectedTemplate
                    ? `Using ${templates.find(t => t.type === selectedTemplate)?.name} template`
                    : 'Template will be auto-detected from your query'}
                </small>
              </div>

              <div className="form-group">
                <label htmlFor="query">Research Query</label>
                <textarea
                  id="query"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="What would you like to research? (min. 10 characters)"
                  rows={4}
                  disabled={loading}
                />
                <small>{query.length}/10 characters minimum</small>
              </div>

              <div className="form-group">
                <label htmlFor="strategy">Research Strategy</label>
                <select
                  id="strategy"
                  value={strategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  disabled={loading}
                >
                  <option value="hybrid">Hybrid (Recommended)</option>
                  <option value="breadth_first">Breadth First - Wide coverage</option>
                  <option value="depth_first">Depth First - Deep dive</option>
                  <option value="task_decomposition">Task Decomposition - Break down complex queries</option>
                </select>
                <small>Strategy determines how research is conducted</small>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label htmlFor="maxIterations">Max Iterations</label>
                  <input
                    type="number"
                    id="maxIterations"
                    value={maxIterations}
                    onChange={(e) => setMaxIterations(parseInt(e.target.value) || 10)}
                    min={1}
                    max={50}
                    disabled={loading}
                  />
                  <small>Research depth (1-50)</small>
                </div>

                <div className="form-group">
                  <label htmlFor="maxCost">Max Cost (USD)</label>
                  <input
                    type="number"
                    id="maxCost"
                    value={maxCost}
                    onChange={(e) => setMaxCost(parseFloat(e.target.value) || 2.0)}
                    min={0.1}
                    max={10}
                    step={0.1}
                    disabled={loading}
                  />
                  <small>Budget limit ($0.10-$10.00)</small>
                </div>
              </div>

              <div className="form-group checkbox-group">
                <label htmlFor="enablePaidTools">
                  <input
                    type="checkbox"
                    id="enablePaidTools"
                    checked={enablePaidTools}
                    onChange={(e) => setEnablePaidTools(e.target.checked)}
                    disabled={loading}
                  />
                  <span>Enable paid tools (Perplexity for deep research)</span>
                </label>
                <small>
                  {enablePaidTools
                    ? '⚠️ Research will use Perplexity API when beneficial (higher cost but better quality)'
                    : 'Using free tools only (Brave Search, SearXNG, Jina Reader)'}
                </small>
              </div>

              <button
                className="btn-primary"
                onClick={createSession}
                disabled={loading || query.length < 10}
              >
                {loading ? 'Creating Session...' : '🚀 Start Research'}
              </button>
            </div>
          ) : (
            <div className="active-session">
              <div className="session-header">
                <h2>Active Session</h2>
                <span className={`status-badge ${getStatusColor(activeSession.status)}`}>
                  {activeSession.status}
                </span>
              </div>

              <div className="session-query">
                <strong>Query:</strong> {activeSession.query}
              </div>

              <div className="session-controls">
                {activeSession.status === 'active' && (
                  <button className="btn-warning" onClick={pauseSession}>
                    ⏸️ Pause
                  </button>
                )}
                {activeSession.status === 'paused' && (
                  <button className="btn-success" onClick={resumeSession}>
                    ▶️ Resume
                  </button>
                )}
                <button className="btn-danger" onClick={cancelSession}>
                  🛑 Cancel
                </button>
                <button className="btn-secondary" onClick={() => setActiveSession(null)}>
                  ← Back
                </button>
              </div>

              {/* Real-time Progress */}
              {connected && (
                <div className="live-indicator">
                  <span className="pulse"></span>
                  Live Streaming
                </div>
              )}

              <div className="progress-stats">
                <div className="stat-card">
                  <div className="stat-label">Iteration</div>
                  <div className="stat-value">{currentIteration} / {activeSession.config?.max_iterations || '?'}</div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${(currentIteration / (activeSession.config?.max_iterations || 10)) * 100}%`
                      }}
                    ></div>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-label">Findings</div>
                  <div className="stat-value">{findingsCount || activeSession.total_findings}</div>
                </div>

                <div className="stat-card">
                  <div className="stat-label">Sources</div>
                  <div className="stat-value">{sourcesCount || activeSession.total_sources}</div>
                </div>

                <div className="stat-card">
                  <div className="stat-label">Budget Remaining</div>
                  <div className="stat-value">
                    ${(budgetRemaining || 0).toFixed(2)} / ${activeSession.config?.max_cost_usd || 0}
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill budget"
                      style={{
                        width: `${((budgetRemaining / (activeSession.config?.max_cost_usd || 2)) * 100)}%`
                      }}
                    ></div>
                  </div>
                </div>

                <div className="stat-card">
                  <div className="stat-label">Cost Spent</div>
                  <div className="stat-value">${activeSession.total_cost_usd.toFixed(4)}</div>
                </div>

                <div className="stat-card">
                  <div className="stat-label">External Calls</div>
                  <div className="stat-value">{activeSession.external_calls_used}</div>
                </div>
              </div>

              {/* Quality Metrics */}
              <div className="quality-metrics">
                <h3>Quality Metrics</h3>
                <div className="metrics-grid">
                  {activeSession.completeness_score !== undefined && (
                    <div className="metric-card">
                      <div className="metric-label">Completeness</div>
                      <div className="metric-value">
                        {(activeSession.completeness_score * 100).toFixed(1)}%
                      </div>
                      <div className="metric-bar">
                        <div
                          className="metric-fill completeness"
                          style={{ width: `${activeSession.completeness_score * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {activeSession.confidence_score !== undefined && (
                    <div className="metric-card">
                      <div className="metric-label">Confidence</div>
                      <div className="metric-value">
                        {(activeSession.confidence_score * 100).toFixed(1)}%
                      </div>
                      <div className="metric-bar">
                        <div
                          className="metric-fill confidence"
                          style={{ width: `${activeSession.confidence_score * 100}%` }}
                        ></div>
                      </div>
                    </div>
                  )}

                  {saturation && (
                    <div className="metric-card">
                      <div className="metric-label">Saturation</div>
                      <div className="metric-value">
                        {saturation.threshold_met ? '✓ Met' : '○ Searching'}
                      </div>
                      <small>Novel findings (last 3): {saturation.novel_findings_last_n || 0}</small>
                    </div>
                  )}
                </div>
              </div>

              {/* Progress Logs */}
              {progressLogs.length > 0 && (
                <div className="progress-logs">
                  <h3>Progress Log</h3>
                  <div className="log-container">
                    {progressLogs.slice().reverse().map((log, idx) => (
                      <div key={idx} className={`log-entry log-${log.type}`}>
                        <span className="log-time">
                          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}
                        </span>
                        <span className="log-type">[{log.type}]</span>
                        {log.node && <span className="log-node">{log.node}</span>}
                        {log.message && <span className="log-message">{log.message}</span>}
                        {log.error && <span className="log-error">{log.error}</span>}
                        {log.stopping_decision?.should_stop && (
                          <span className="log-stop">
                            Stop: {log.stopping_decision.reason}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right Panel: Session History */}
        <div className="research-sidebar">
          <div className="sidebar-header">
            <h3>Session History</h3>
            <button className="btn-small" onClick={loadSessions}>
              🔄 Refresh
            </button>
          </div>

          <div className="session-list">
            {sessions.length === 0 ? (
              <p className="empty-state">No sessions yet</p>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.session_id}
                  className={`session-card ${activeSession?.session_id === session.session_id ? 'active' : ''}`}
                  onClick={() => selectSession(session)}
                >
                  <div className="session-card-header">
                    <span className={`status-dot ${getStatusColor(session.status)}`}></span>
                    <span className="session-status">{session.status}</span>
                    <span className="session-date">
                      {new Date(session.created_at).toLocaleDateString()}
                    </span>
                  </div>

                  <div className="session-card-query">
                    {session.query.substring(0, 80)}
                    {session.query.length > 80 && '...'}
                  </div>

                  <div className="session-card-stats">
                    <span>📊 {session.total_findings} findings</span>
                    <span>🔗 {session.total_sources} sources</span>
                    <span>💰 ${session.total_cost_usd.toFixed(2)}</span>
                  </div>

                  {session.completeness_score !== undefined && (
                    <div className="session-card-quality">
                      <small>
                        Quality: {(session.completeness_score * 100).toFixed(0)}%
                      </small>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Research;
