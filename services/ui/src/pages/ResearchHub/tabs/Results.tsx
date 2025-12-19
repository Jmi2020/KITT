/**
 * Results Tab - Research Results Browser
 * Displays completed research sessions with detailed findings
 */

import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { SessionResults, Finding } from '../../../types/research';
import {
  exportMarkdown,
  exportJSON,
  exportPDF,
  copyToClipboard,
} from '../utils/export';

interface ResultsProps {
  api: UseResearchApiReturn;
  initialSessionId?: string;
}

const Results = ({ api, initialSessionId }: ResultsProps) => {
  const [results, setResults] = useState<SessionResults | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(initialSessionId || null);
  const [showModal, setShowModal] = useState(false);
  const [generatingSynthesis, setGeneratingSynthesis] = useState(false);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [exportingPDF, setExportingPDF] = useState(false);

  // Load completed sessions on mount
  useEffect(() => {
    api.loadSessions('completed', 50);
  }, []);

  // Auto-load results if initialSessionId provided
  useEffect(() => {
    if (initialSessionId) {
      loadResults(initialSessionId);
    }
  }, [initialSessionId]);

  const loadResults = async (sessionId: string) => {
    const data = await api.loadResults(sessionId);
    if (data) {
      setResults(data);
      setSelectedSessionId(sessionId);
      setShowModal(true);
    }
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedSessionId(null);
    setResults(null);
  };

  const handleGenerateSynthesis = async () => {
    if (!results) return;

    setGeneratingSynthesis(true);
    const data = await api.generateSynthesis(results.session_id);

    if (data) {
      setResults({
        ...results,
        final_synthesis: data.synthesis,
        synthesis_model: data.model,
      });
    }
    setGeneratingSynthesis(false);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.7) return 'var(--color-success)';
    if (confidence >= 0.5) return 'var(--color-warning)';
    return 'var(--color-error)';
  };

  const handleCopy = async () => {
    if (!results) return;
    const success = await copyToClipboard(results);
    setCopyFeedback(success ? 'Copied!' : 'Failed to copy');
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const handleExportPDF = async () => {
    if (!results) return;
    setExportingPDF(true);
    try {
      await exportPDF(results);
    } catch (error) {
      console.error('PDF export failed:', error);
    }
    setExportingPDF(false);
  };

  const completedSessions = api.sessions.filter((s) => s.status === 'completed');

  return (
    <div className="results-tab">
      <h2>Research Results</h2>
      <p className="subtitle">Browse and explore completed research sessions</p>

      <div className="sessions-grid">
        {completedSessions.length === 0 ? (
          <div className="empty-state">
            <p>No completed research sessions found</p>
            <p>Start a new research query from the New Research tab</p>
          </div>
        ) : (
          completedSessions.map((session) => (
            <div
              key={session.session_id}
              className={`result-card ${selectedSessionId === session.session_id ? 'selected' : ''}`}
              onClick={() => loadResults(session.session_id)}
            >
              <div className="result-card-header">
                <span className="result-status">{session.status}</span>
                <span className="result-date">
                  {formatDate(session.completed_at || session.updated_at)}
                </span>
              </div>
              <div className="result-card-query">
                {session.query.length > 150
                  ? session.query.substring(0, 150) + '...'
                  : session.query}
              </div>
              <div className="result-card-stats">
                <span>📊 {session.total_findings} findings</span>
                <span>🔗 {session.total_sources} sources</span>
                <span>🔁 {session.total_iterations} iterations</span>
              </div>
              {session.completeness_score && (
                <div className="result-card-quality">
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
              <button className="modal-close" onClick={closeModal}>
                ×
              </button>
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

              {/* Export Actions */}
              <div className="export-actions">
                <span className="export-label">Export:</span>
                <button
                  className="btn-export"
                  onClick={handleCopy}
                  title="Copy as Markdown to clipboard"
                >
                  {copyFeedback || '📋 Copy'}
                </button>
                <button
                  className="btn-export"
                  onClick={() => results && exportMarkdown(results)}
                  title="Download as Markdown file"
                >
                  📝 Markdown
                </button>
                <button
                  className="btn-export"
                  onClick={() => results && exportJSON(results)}
                  title="Download as JSON file"
                >
                  📦 JSON
                </button>
                <button
                  className="btn-export"
                  onClick={handleExportPDF}
                  disabled={exportingPDF}
                  title="Download as PDF file"
                >
                  {exportingPDF ? '⏳ Generating...' : '📄 PDF'}
                </button>
              </div>

              {/* Synthesis */}
              {results.final_synthesis ? (
                <div className="results-synthesis">
                  <h3>Synthesis</h3>
                  <div className="synthesis-content markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {results.final_synthesis}
                    </ReactMarkdown>
                  </div>
                  {results.synthesis_model && (
                    <p className="synthesis-model">Generated by: {results.synthesis_model}</p>
                  )}
                </div>
              ) : (
                <div className="results-synthesis">
                  <h3>Synthesis</h3>
                  <p className="info-message">
                    No synthesis available for this session. Generate a cohesive analysis from the
                    findings?
                  </p>
                  <button
                    className="btn-primary"
                    onClick={handleGenerateSynthesis}
                    disabled={generatingSynthesis || api.loading}
                  >
                    {generatingSynthesis ? 'Generating...' : 'Generate Synthesis'}
                  </button>
                </div>
              )}

              {/* Findings List */}
              <div className="findings-section">
                <h3>Findings ({results.findings.length})</h3>
                <div className="findings-list">
                  {results.findings.map((finding: Finding) => (
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
                      <div className="finding-content">{finding.content}</div>
                      {finding.sources && finding.sources.length > 0 && (
                        <div className="finding-sources">
                          <strong>Sources:</strong>
                          <ul>
                            {finding.sources.map((source, idx) => (
                              <li key={idx}>
                                {typeof source === 'string' ? (
                                  <a href={source} target="_blank" rel="noopener noreferrer">
                                    {source}
                                  </a>
                                ) : (
                                  <a
                                    href={source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
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

      {api.loading && (
        <div className="loading-overlay">
          <div className="loading-spinner">Loading results...</div>
        </div>
      )}
    </div>
  );
};

export default Results;
