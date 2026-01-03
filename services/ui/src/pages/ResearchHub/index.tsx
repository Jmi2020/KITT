/**
 * Research Hub - Consolidated Research Interface
 *
 * Combines:
 * - New Research (query form)
 * - Active Sessions (WebSocket streaming)
 * - Results (completed research browser)
 * - Datasets (topic management & paper harvesting)
 * - Fine-Tuning (training job management)
 * - Experts (expert model browser)
 * - Schedule (autonomy calendar)
 */

import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useResearchApi } from '../../hooks/useResearchApi';
import type { ResearchHubTab, ResearchSession, ProgressUpdate } from '../../types/research';
import NewResearch from './tabs/NewResearch';
import ActiveSessions from './tabs/ActiveSessions';
import Results from './tabs/Results';
import DatasetsTab from './tabs/Datasets';
import FineTuningTab from './tabs/FineTuning';
import ExpertsTab from './tabs/Experts';
import Schedule from './tabs/Schedule';
import ResourcesPanel from './components/ResourcesPanel';
import './ResearchHub.css';

const ResearchHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as ResearchHubTab | null;
  const [activeTab, setActiveTab] = useState<ResearchHubTab>(tabParam || 'new');

  // Shared API hook
  const api = useResearchApi();

  // Active session state (shared between New and Active tabs)
  const [activeSession, setActiveSession] = useState<ResearchSession | null>(null);
  const [progressLogs, setProgressLogs] = useState<ProgressUpdate[]>([]);
  const [currentProgress, setCurrentProgress] = useState({
    iteration: 0,
    findingsCount: 0,
    sourcesCount: 0,
    budgetRemaining: 0,
    saturation: null as { threshold_met?: boolean; novel_findings_last_n?: number } | null,
  });

  // Load initial data
  useEffect(() => {
    api.loadTemplates();
    api.loadSessions();
  }, []);

  // Sync tab with URL
  useEffect(() => {
    if (tabParam && tabParam !== activeTab) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const handleTabChange = (tab: ResearchHubTab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  // Handle WebSocket updates
  const handleProgressUpdate = (update: ProgressUpdate) => {
    setProgressLogs((prev) => [...prev, update]);

    if (update.type === 'progress') {
      setCurrentProgress({
        iteration: update.iteration || 0,
        findingsCount: update.findings_count || 0,
        sourcesCount: update.sources_count || 0,
        budgetRemaining: update.budget_remaining || 0,
        saturation: update.saturation || null,
      });
    } else if (update.type === 'complete') {
      // Refresh session details and list
      if (activeSession) {
        api.loadSessionDetails(activeSession.session_id).then((session) => {
          if (session) setActiveSession(session);
        });
      }
      api.loadSessions();
    } else if (update.type === 'error') {
      api.loadSessions();
    }
  };

  // Session creation callback
  const handleSessionCreated = (session: ResearchSession) => {
    setActiveSession(session);
    setProgressLogs([]);
    setCurrentProgress({
      iteration: 0,
      findingsCount: 0,
      sourcesCount: 0,
      budgetRemaining: session.config?.max_cost_usd || 0,
      saturation: null,
    });

    // Connect WebSocket
    api.connectWebSocket(session.session_id, handleProgressUpdate);

    // Switch to active tab
    handleTabChange('active');
  };

  // Session selection (from sidebar)
  const handleSelectSession = (session: ResearchSession) => {
    setActiveSession(session);
    setProgressLogs([]);

    if (session.status === 'active') {
      api.connectWebSocket(session.session_id, handleProgressUpdate);
      handleTabChange('active');
    } else if (session.status === 'completed') {
      handleTabChange('results');
    }
  };

  // Clear active session
  const handleClearSession = () => {
    api.disconnectWebSocket();
    setActiveSession(null);
    setProgressLogs([]);
    handleTabChange('new');
  };

  const tabs: { id: ResearchHubTab; label: string; icon: string }[] = [
    { id: 'new', label: 'New Research', icon: '🔬' },
    { id: 'active', label: 'Active', icon: '📡' },
    { id: 'results', label: 'Results', icon: '📊' },
    { id: 'datasets', label: 'Datasets', icon: '📚' },
    { id: 'finetune', label: 'Fine-Tuning', icon: '🧠' },
    { id: 'experts', label: 'Experts', icon: '🎓' },
    { id: 'schedule', label: 'Schedule', icon: '📅' },
  ];

  return (
    <div className="research-hub">
      <div className="research-hub-header">
        <h1>Research Hub</h1>
        <p className="subtitle">
          Autonomous research pipeline with real-time streaming, results browser, and scheduling
        </p>
      </div>

      {api.error && (
        <div className="error-banner">
          <strong>Error:</strong> {api.error}
          <button onClick={api.clearError}>×</button>
        </div>
      )}

      <div className="research-hub-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.id === 'active' && activeSession?.status === 'active' && (
              <span className="tab-badge pulse">Live</span>
            )}
          </button>
        ))}
      </div>

      <div className="research-hub-content">
        <div className="research-hub-main">
          {activeTab === 'new' && (
            <NewResearch
              api={api}
              onSessionCreated={handleSessionCreated}
            />
          )}

          {activeTab === 'active' && (
            <ActiveSessions
              api={api}
              activeSession={activeSession}
              progressLogs={progressLogs}
              currentProgress={currentProgress}
              onClearSession={handleClearSession}
              onProgressUpdate={handleProgressUpdate}
            />
          )}

          {activeTab === 'results' && (
            <Results
              api={api}
              initialSessionId={activeSession?.status === 'completed' ? activeSession.session_id : undefined}
            />
          )}

          {activeTab === 'datasets' && (
            <DatasetsTab api={api} />
          )}

          {activeTab === 'finetune' && (
            <FineTuningTab api={api} />
          )}

          {activeTab === 'experts' && (
            <ExpertsTab api={api} />
          )}

          {activeTab === 'schedule' && (
            <Schedule api={api} />
          )}
        </div>

        {/* Right Sidebar - Resources Panel for datasets/finetune/experts, Sessions otherwise */}
        <div className="research-hub-sidebar">
          {['datasets', 'finetune', 'experts'].includes(activeTab) ? (
            <ResourcesPanel api={api} />
          ) : (
            <>
              <div className="sidebar-header">
                <h3>Recent Sessions</h3>
                <button className="btn-small" onClick={() => api.loadSessions()}>
                  🔄
                </button>
              </div>

              <div className="session-list">
                {api.sessions.length === 0 ? (
                  <p className="empty-state">No sessions yet</p>
                ) : (
                  api.sessions.slice(0, 10).map((session) => (
                    <div
                      key={session.session_id}
                      className={`session-card ${activeSession?.session_id === session.session_id ? 'selected' : ''}`}
                      onClick={() => handleSelectSession(session)}
                    >
                      <div className="session-card-header">
                        <span className={`status-dot status-${session.status}`}></span>
                        <span className="session-status">{session.status}</span>
                        <span className="session-date">
                          {new Date(session.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      <div className="session-card-query">
                        {session.query.substring(0, 60)}
                        {session.query.length > 60 && '...'}
                      </div>

                      <div className="session-card-stats">
                        <span>📊 {session.total_findings}</span>
                        <span>🔗 {session.total_sources}</span>
                        <span>💰 ${session.total_cost_usd.toFixed(2)}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ResearchHub;
