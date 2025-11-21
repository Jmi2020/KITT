/**
 * Results Page - Research Results Browser
 *
 * Displays completed research sessions with ability to view detailed results
 */

import { useState, useEffect } from 'react';
import { getWebUserId } from '../utils/user';
import './Results.css';

interface ResearchSession {
  session_id: string;
  user_id: string;
  query: string;
  status: string;
  created_at: string;
  updated_at: string;
  completed_at?: string;
  total_iterations: number;
  total_findings: number;
  total_sources: number;
  total_cost_usd: number;
  completeness_score?: number;
  confidence_score?: number;
}

interface SessionResults {
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

interface Finding {
  id: number;
  finding_type: string;
  content: string;
  confidence: number;
  sources: any[];
  iteration: number;
  created_at: string;
}

const Results = () => {
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  const [results, setResults] = useState<SessionResults | null>(null);
  const [loading, setLoading] = useState(false);
  const [generatingSynthesis, setGeneratingSynthesis] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userId] = useState<string>(() => getWebUserId());
  const [showModal, setShowModal] = useState(false);

  // Load completed sessions
  useEffect(() => {
    loadSessions();
  }, [userId]);

  const loadSessions = async () => {
    try {
      const response = await fetch(
        `/api/research/sessions?user_id=${encodeURIComponent(userId)}&status=completed&limit=50`
      );
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err: any) {
      console.error('Error loading sessions:', err);
      setError(err.message);
    }
  };

  const loadResults = async (sessionId: string) => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/research/sessions/${sessionId}/results`);
      if (!response.ok) throw new Error('Failed to load results');
      const data = await response.json();
      setResults(data);
      setSelectedSession(sessionId);
      setShowModal(true);
    } catch (err: any) {
      console.error('Error loading results:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedSession(null);
    setResults(null);
  };

  const generateSynthesis = async (sessionId: string) => {
    setGeneratingSynthesis(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/research/sessions/${sessionId}/generate-synthesis`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to generate synthesis');
      const data = await response.json();

      // Update results with new synthesis
      if (results) {
        setResults({
          ...results,
          final_synthesis: data.synthesis,
          synthesis_model: data.model
        });
      }
    } catch (err: any) {
      console.error('Error generating synthesis:', err);
      setError(err.message);
    } finally {
      setGeneratingSynthesis(false);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.7) return '#28a745';
    if (confidence >= 0.5) return '#ffc107';
    return '#dc3545';
  };

  return (
    <div className="results-page">
      <div className="results-header">
        <h1>Research Results</h1>
        <p className="subtitle">Browse and explore completed research sessions</p>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <div className="sessions-grid">
        {sessions.length === 0 ? (
          <div className="empty-state">
            <p>No completed research sessions found</p>
            <p>Start a new research query from the Research tab</p>
          </div>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              className="session-card"
              onClick={() => loadResults(session.session_id)}
            >
              <div className="session-card-header">
                <span className="session-status">{session.status}</span>
                <span className="session-date">{formatDate(session.completed_at || session.updated_at)}</span>
              </div>
              <div className="session-card-query">
                {session.query.length > 150 ? session.query.substring(0, 150) + '...' : session.query}
              </div>
              <div className="session-card-stats">
                <span>📊 {session.total_findings} findings</span>
                <span>🔗 {session.total_sources} sources</span>
                <span>🔁 {session.total_iterations} iterations</span>
              </div>
              {session.completeness_score && (
                <div className="session-card-quality">
                  <small>Quality: {(session.completeness_score * 100).toFixed(0)}%</small>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Results Modal */}
      {showModal && results && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Research Results</h2>
              <button className="modal-close" onClick={closeModal}>×</button>
            </div>

            <div className="modal-body">
              {/* Query */}
              <div className="results-query">
                <strong>Query:</strong> {results.query}
              </div>

              {/* Stats */}
              <div className="results-stats">
                <div className="stat-item">
                  <span className="stat-label">Findings</span>
                  <span className="stat-value">{results.total_findings}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Sources</span>
                  <span className="stat-value">{results.total_sources}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Cost</span>
                  <span className="stat-value">${results.total_cost_usd.toFixed(2)}</span>
                </div>
              </div>

              {/* Synthesis */}
              {results.final_synthesis ? (
                <div className="results-synthesis">
                  <h3>Synthesis</h3>
                  <div className="synthesis-content">
                    {results.final_synthesis}
                  </div>
                  {results.synthesis_model && (
                    <p className="synthesis-model">Generated by: {results.synthesis_model}</p>
                  )}
                </div>
              ) : (
                <div className="results-synthesis">
                  <h3>Synthesis</h3>
                  <p className="info-message">
                    No synthesis available for this session. Generate a cohesive analysis from the findings?
                  </p>
                  <button
                    className="generate-synthesis-btn"
                    onClick={() => generateSynthesis(results.session_id)}
                    disabled={generatingSynthesis}
                  >
                    {generatingSynthesis ? '🔄 Generating...' : '✨ Generate Synthesis'}
                  </button>
                </div>
              )}

              {/* Findings List */}
              <div className="findings-section">
                <h3>Findings ({results.findings.length})</h3>
                <div className="findings-list">
                  {results.findings.map((finding) => (
                    <div key={finding.id} className="finding-card">
                      <div className="finding-header">
                        <span className="finding-type">{finding.finding_type}</span>
                        <span className="finding-iteration">Iteration {finding.iteration}</span>
                        <span
                          className="finding-confidence"
                          style={{ color: getConfidenceColor(finding.confidence) }}
                        >
                          {(finding.confidence * 100).toFixed(0)}% confidence
                        </span>
                      </div>
                      <div className="finding-content">
                        {finding.content}
                      </div>
                      {finding.sources && finding.sources.length > 0 && (
                        <div className="finding-sources">
                          <strong>Sources:</strong>
                          <ul>
                            {finding.sources.map((source: any, idx: number) => (
                              <li key={idx}>
                                {typeof source === 'string' ? (
                                  <a href={source} target="_blank" rel="noopener noreferrer">{source}</a>
                                ) : (
                                  <a href={source.url} target="_blank" rel="noopener noreferrer">
                                    {source.title || source.url}
                                  </a>
                                )}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {loading && (
        <div className="loading-overlay">
          <div className="loading-spinner">Loading results...</div>
        </div>
      )}
    </div>
  );
};

export default Results;
