/**
 * Active Sessions Tab - WebSocket Streaming Progress
 * Displays real-time progress for active research sessions
 */

import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { ResearchSession, ProgressUpdate } from '../../../types/research';

interface ActiveSessionsProps {
  api: UseResearchApiReturn;
  activeSession: ResearchSession | null;
  progressLogs: ProgressUpdate[];
  currentProgress: {
    iteration: number;
    findingsCount: number;
    sourcesCount: number;
    budgetRemaining: number;
    saturation: { threshold_met?: boolean; novel_findings_last_n?: number } | null;
  };
  onClearSession: () => void;
  onProgressUpdate: (update: ProgressUpdate) => void;
}

const ActiveSessions = ({
  api,
  activeSession,
  progressLogs,
  currentProgress,
  onClearSession,
}: ActiveSessionsProps) => {
  const handlePause = async () => {
    if (!activeSession) return;
    const success = await api.pauseSession(activeSession.session_id);
    if (success) {
      api.disconnectWebSocket();
      api.loadSessionDetails(activeSession.session_id);
    }
  };

  const handleResume = async () => {
    if (!activeSession) return;
    const success = await api.resumeSession(activeSession.session_id);
    if (success) {
      api.connectWebSocket(activeSession.session_id, (update) => {
        // This will be handled by parent
      });
    }
  };

  const handleCancel = async () => {
    if (!activeSession) return;
    if (!confirm('Are you sure you want to cancel this session?')) return;

    const success = await api.cancelSession(activeSession.session_id);
    if (success) {
      api.disconnectWebSocket();
      onClearSession();
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
        return 'status-active';
      case 'completed':
        return 'status-completed';
      case 'paused':
        return 'status-paused';
      case 'failed':
        return 'status-failed';
      default:
        return '';
    }
  };

  if (!activeSession) {
    return (
      <div className="active-sessions-tab">
        <div className="empty-state">
          <h3>No Active Session</h3>
          <p>Start a new research query or select an active session from the sidebar.</p>
        </div>
      </div>
    );
  }

  const maxIterations = activeSession.config?.max_iterations || 10;
  const maxCost = activeSession.config?.max_cost_usd || 2;

  return (
    <div className="active-sessions-tab">
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
          <button className="btn-warning" onClick={handlePause}>
            Pause
          </button>
        )}
        {activeSession.status === 'paused' && (
          <button className="btn-success" onClick={handleResume}>
            Resume
          </button>
        )}
        <button className="btn-danger" onClick={handleCancel}>
          Cancel
        </button>
        <button className="btn-secondary" onClick={onClearSession}>
          Back
        </button>
      </div>

      {/* Real-time Progress */}
      {api.isConnected && (
        <div className="live-indicator">
          <span className="pulse"></span>
          Live Streaming
        </div>
      )}

      <div className="progress-stats">
        <div className="stat-card">
          <div className="stat-label">Iteration</div>
          <div className="stat-value">
            {currentProgress.iteration} / {maxIterations}
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${(currentProgress.iteration / maxIterations) * 100}%`,
              }}
            ></div>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Findings</div>
          <div className="stat-value">
            {currentProgress.findingsCount || activeSession.total_findings}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Sources</div>
          <div className="stat-value">
            {currentProgress.sourcesCount || activeSession.total_sources}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Budget Remaining</div>
          <div className="stat-value">
            ${(currentProgress.budgetRemaining || 0).toFixed(2)} / ${maxCost}
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill budget"
              style={{
                width: `${(currentProgress.budgetRemaining / maxCost) * 100}%`,
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

          {currentProgress.saturation && (
            <div className="metric-card">
              <div className="metric-label">Saturation</div>
              <div className="metric-value">
                {currentProgress.saturation.threshold_met ? 'Met' : 'Searching'}
              </div>
              <small>
                Novel findings (last 3): {currentProgress.saturation.novel_findings_last_n || 0}
              </small>
            </div>
          )}
        </div>
      </div>

      {/* Progress Logs */}
      {progressLogs.length > 0 && (
        <div className="progress-logs">
          <h3>Progress Log</h3>
          <div className="log-container">
            {progressLogs
              .slice()
              .reverse()
              .map((log, idx) => (
                <div key={idx} className={`log-entry log-${log.type}`}>
                  <span className="log-time">
                    {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : ''}
                  </span>
                  <span className="log-type">[{log.type}]</span>
                  {log.node && <span className="log-node">{log.node}</span>}
                  {log.message && <span className="log-message">{log.message}</span>}
                  {log.error && <span className="log-error">{log.error}</span>}
                  {log.stopping_decision?.should_stop && (
                    <span className="log-stop">Stop: {log.stopping_decision.reason}</span>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ActiveSessions;
