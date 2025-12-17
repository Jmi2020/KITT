/**
 * Collective Meta-Agent Page
 * Multi-agent deliberation system for complex decision-making
 */

import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useCollectiveApi } from '../../hooks/useCollectiveApi';
import type { CollectivePattern, CollectiveSession, CollectiveProposal, SpecialistConfig } from '../../types/collective';
import './Collective.css';

type TabType = 'run' | 'history';

interface PatternOption {
  value: CollectivePattern;
  label: string;
  description: string;
  icon: string;
}

const PATTERNS: PatternOption[] = [
  {
    value: 'council',
    label: 'Council',
    description: 'Multiple specialists provide independent proposals, then a judge synthesizes the best ideas',
    icon: 'users',
  },
  {
    value: 'debate',
    label: 'Debate',
    description: 'PRO and CON perspectives argue their cases, then a judge weighs both sides',
    icon: 'scale',
  },
  {
    value: 'pipeline',
    label: 'Pipeline',
    description: 'Sequential workflow for code generation (coming soon)',
    icon: 'workflow',
  },
];

function PatternCard({
  pattern,
  selected,
  onSelect,
}: {
  pattern: PatternOption;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`pattern-card ${selected ? 'selected' : ''} ${pattern.value === 'pipeline' ? 'disabled' : ''}`}
      onClick={onSelect}
      disabled={pattern.value === 'pipeline'}
    >
      <div className="pattern-icon">{pattern.icon === 'users' ? '👥' : pattern.icon === 'scale' ? '⚖️' : '🔄'}</div>
      <div className="pattern-info">
        <h4>{pattern.label}</h4>
        <p>{pattern.description}</p>
      </div>
      {selected && <div className="pattern-check">✓</div>}
    </button>
  );
}

function ProposalCard({
  proposal,
  index,
  isActive,
}: {
  proposal: CollectiveProposal;
  index: number;
  isActive: boolean;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className={`proposal-card ${isActive ? 'active' : ''}`}>
      <div className="proposal-header" onClick={() => setExpanded(!expanded)}>
        <div className="proposal-role">
          <span className="proposal-index">{index + 1}</span>
          <span className="proposal-role-name">{proposal.role}</span>
          {proposal.model && <span className="proposal-model">{proposal.model}</span>}
        </div>
        <button className="expand-btn">{expanded ? '−' : '+'}</button>
      </div>
      {expanded && (
        <div className="proposal-content">
          <div className="proposal-text markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {proposal.text}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

function VerdictPanel({ verdict }: { verdict: string }) {
  return (
    <div className="verdict-panel">
      <div className="verdict-header">
        <span className="verdict-icon">⚖️</span>
        <h3>Judge Verdict</h3>
      </div>
      <div className="verdict-content">
        <div className="verdict-text markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {verdict}
          </ReactMarkdown>
        </div>
      </div>
      <div className="verdict-actions">
        <button
          className="btn-copy"
          onClick={() => navigator.clipboard.writeText(verdict)}
        >
          Copy to Clipboard
        </button>
      </div>
    </div>
  );
}

function PhaseIndicator({
  phase,
  pattern,
  k,
  activeIndex,
  hasSearchPhase,
}: {
  phase: string;
  pattern: CollectivePattern;
  k: number;
  activeIndex: number;
  hasSearchPhase?: boolean;
}) {
  const phases = hasSearchPhase
    ? [
        { id: 'planning', label: 'Planning' },
        { id: 'searching', label: 'Searching' },
        { id: 'proposing', label: pattern === 'debate' ? 'Debating' : 'Proposing' },
        { id: 'judging', label: 'Judging' },
        { id: 'complete', label: 'Complete' },
      ]
    : [
        { id: 'planning', label: 'Planning' },
        { id: 'proposing', label: pattern === 'debate' ? 'Debating' : 'Proposing' },
        { id: 'judging', label: 'Judging' },
        { id: 'complete', label: 'Complete' },
      ];

  const currentIndex = phases.findIndex(p => p.id === phase);

  return (
    <div className="phase-indicator">
      {phases.map((p, i) => (
        <div
          key={p.id}
          className={`phase-step ${i < currentIndex ? 'done' : ''} ${i === currentIndex ? 'active' : ''}`}
        >
          <div className="phase-dot">
            {i < currentIndex ? '✓' : i === currentIndex && phase === 'proposing' ? `${activeIndex + 1}/${k}` : i + 1}
          </div>
          <div className="phase-label">{p.label}</div>
        </div>
      ))}
    </div>
  );
}

function SessionListItem({
  session,
  onSelect,
}: {
  session: CollectiveSession;
  onSelect: () => void;
}) {
  const statusColors: Record<string, string> = {
    completed: 'green',
    error: 'red',
    running: 'blue',
    pending: 'gray',
  };

  return (
    <div className="session-item" onClick={onSelect}>
      <div className="session-task">{session.task.slice(0, 60)}...</div>
      <div className="session-meta">
        <span className={`session-status status-${statusColors[session.status]}`}>
          {session.status}
        </span>
        <span className="session-pattern">{session.pattern}</span>
        <span className="session-time">
          {new Date(session.created_at).toLocaleString()}
        </span>
      </div>
    </div>
  );
}

export default function Collective() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (searchParams.get('tab') as TabType) || 'run';

  const [task, setTask] = useState('');
  const [pattern, setPattern] = useState<CollectivePattern>('council');
  const [k, setK] = useState(3);
  const [enableSearchPhase, setEnableSearchPhase] = useState(false);
  const [selectedSession, setSelectedSession] = useState<CollectiveSession | null>(null);
  const [selectedSpecialists, setSelectedSpecialists] = useState<string[]>(['local_q4']);
  const [useCustomSpecialists, setUseCustomSpecialists] = useState(false);
  const [estimatedCost, setEstimatedCost] = useState(0);

  const {
    loading,
    error,
    clearError,
    currentSession,
    proposals,
    verdict,
    phase,
    activeProposalIndex,
    searchPhaseInfo,
    sessions,
    loadSessions,
    loadSessionDetails,
    specialists,
    specialistsLoading,
    fetchSpecialists,
    estimateCost,
    startStreaming,
    cancelStreaming,
    isConnected,
  } = useCollectiveApi();

  // Load specialists on mount
  useEffect(() => {
    fetchSpecialists();
  }, [fetchSpecialists]);

  // Load sessions on tab change
  useEffect(() => {
    if (tab === 'history') {
      loadSessions();
    }
  }, [tab, loadSessions]);

  // Update cost estimate when specialists change
  useEffect(() => {
    if (useCustomSpecialists && selectedSpecialists.length > 0) {
      estimateCost(selectedSpecialists).then(setEstimatedCost);
    } else {
      setEstimatedCost(0);
    }
  }, [selectedSpecialists, useCustomSpecialists, estimateCost]);

  const setTab = useCallback((newTab: TabType) => {
    setSearchParams({ tab: newTab });
  }, [setSearchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!task.trim()) return;

    clearError();
    await startStreaming({
      task: task.trim(),
      pattern,
      k,
      enableSearchPhase,
      selectedSpecialists: useCustomSpecialists && selectedSpecialists.length >= 2
        ? selectedSpecialists
        : undefined,
    });
  };

  const handleSpecialistToggle = (specialistId: string) => {
    setSelectedSpecialists(prev => {
      if (prev.includes(specialistId)) {
        return prev.filter(id => id !== specialistId);
      } else {
        return [...prev, specialistId];
      }
    });
  };

  const localSpecialists = specialists.filter(s => s.provider === 'local');
  const cloudSpecialists = specialists.filter(s => s.provider !== 'local');

  const handleCancel = () => {
    cancelStreaming();
  };

  const handleSessionSelect = async (session: CollectiveSession) => {
    const details = await loadSessionDetails(session.session_id);
    if (details) {
      setSelectedSession(details);
    }
  };

  const isRunning = phase !== 'idle' && phase !== 'complete' && phase !== 'error';
  const isSearching = phase === 'searching' || (searchPhaseInfo.isActive && phase !== 'complete');

  return (
    <div className="collective-page">
      <div className="collective-header">
        <h1>Collective Intelligence</h1>
        <p className="collective-subtitle">
          Multi-agent deliberation for better decisions
        </p>
      </div>

      <div className="collective-tabs">
        <button
          className={`tab-btn ${tab === 'run' ? 'active' : ''}`}
          onClick={() => setTab('run')}
        >
          Run Collective
        </button>
        <button
          className={`tab-btn ${tab === 'history' ? 'active' : ''}`}
          onClick={() => setTab('history')}
        >
          History
        </button>
      </div>

      {tab === 'run' && (
        <div className="collective-run">
          {/* Input Form */}
          {phase === 'idle' && (
            <form className="collective-form" onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="task">Task / Question</label>
                <textarea
                  id="task"
                  value={task}
                  onChange={(e) => setTask(e.target.value)}
                  placeholder="Describe what you want the specialists to deliberate on..."
                  rows={4}
                  required
                />
              </div>

              <div className="form-group">
                <label>Deliberation Pattern</label>
                <div className="pattern-options">
                  {PATTERNS.map((p) => (
                    <PatternCard
                      key={p.value}
                      pattern={p}
                      selected={pattern === p.value}
                      onSelect={() => setPattern(p.value)}
                    />
                  ))}
                </div>
              </div>

              {pattern === 'council' && (
                <div className="form-group">
                  <div className="specialist-mode-toggle">
                    <label className="checkbox-label">
                      <input
                        type="checkbox"
                        checked={useCustomSpecialists}
                        onChange={(e) => setUseCustomSpecialists(e.target.checked)}
                      />
                      <span className="checkbox-text">
                        Select specific specialists
                        <span className="checkbox-hint">
                          Mix local and cloud providers for diverse perspectives
                        </span>
                      </span>
                    </label>
                  </div>

                  {!useCustomSpecialists ? (
                    <>
                      <label htmlFor="k">Number of Specialists: {k}</label>
                      <input
                        type="range"
                        id="k"
                        min={2}
                        max={7}
                        value={k}
                        onChange={(e) => setK(parseInt(e.target.value))}
                        className="k-slider"
                      />
                      <div className="k-labels">
                        <span>2</span>
                        <span>7</span>
                      </div>
                    </>
                  ) : (
                    <div className="specialist-selector">
                      {specialistsLoading ? (
                        <div className="loading-specialists">Loading specialists...</div>
                      ) : (
                        <>
                          <div className="specialist-group">
                            <h4>Local Models (Free)</h4>
                            {localSpecialists.map(spec => (
                              <label
                                key={spec.id}
                                className={`specialist-option ${!spec.isAvailable ? 'unavailable' : ''}`}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedSpecialists.includes(spec.id)}
                                  onChange={() => handleSpecialistToggle(spec.id)}
                                  disabled={!spec.isAvailable}
                                />
                                <span className="specialist-info">
                                  <span className="specialist-name">{spec.displayName}</span>
                                  <span className="specialist-desc">{spec.description}</span>
                                </span>
                              </label>
                            ))}
                          </div>

                          <div className="specialist-group">
                            <h4>Cloud Providers</h4>
                            {cloudSpecialists.map(spec => (
                              <label
                                key={spec.id}
                                className={`specialist-option ${!spec.isAvailable ? 'unavailable' : ''}`}
                              >
                                <input
                                  type="checkbox"
                                  checked={selectedSpecialists.includes(spec.id)}
                                  onChange={() => handleSpecialistToggle(spec.id)}
                                  disabled={!spec.isAvailable}
                                />
                                <span className="specialist-info">
                                  <span className="specialist-name">
                                    {spec.displayName}
                                    {spec.isAvailable ? (
                                      <span className="api-key-badge available">API Key Set</span>
                                    ) : (
                                      <span className="api-key-badge missing">No API Key</span>
                                    )}
                                  </span>
                                  <span className="specialist-desc">{spec.description}</span>
                                </span>
                              </label>
                            ))}
                          </div>

                          <div className="specialist-summary">
                            <span>Selected: {selectedSpecialists.length} specialists</span>
                            {estimatedCost > 0 && (
                              <span className="cost-estimate">
                                Est. cost: ${estimatedCost.toFixed(4)}
                              </span>
                            )}
                            {selectedSpecialists.length < 2 && (
                              <span className="min-warning">Minimum 2 required</span>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div className="form-group checkbox-group">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={enableSearchPhase}
                    onChange={(e) => setEnableSearchPhase(e.target.checked)}
                  />
                  <span className="checkbox-text">
                    Enable Web Search
                    <span className="checkbox-hint">
                      Specialists will search the web for information before generating proposals
                    </span>
                  </span>
                </label>
              </div>

              <button
                type="submit"
                className="submit-btn"
                disabled={
                  loading ||
                  !task.trim() ||
                  (useCustomSpecialists && selectedSpecialists.length < 2)
                }
              >
                {loading ? 'Starting...' : 'Start Deliberation'}
              </button>
            </form>
          )}

          {/* Progress View */}
          {isRunning && (
            <div className="collective-progress">
              <PhaseIndicator
                phase={phase}
                pattern={pattern}
                k={pattern === 'debate' ? 2 : k}
                activeIndex={activeProposalIndex}
                hasSearchPhase={enableSearchPhase || searchPhaseInfo.isActive}
              />

              <div className="progress-info">
                <p>Task: {currentSession?.task}</p>
                <button className="cancel-btn" onClick={handleCancel}>
                  Cancel
                </button>
              </div>

              {/* Search Phase Progress */}
              {isSearching && (
                <div className="search-progress">
                  <div className="search-progress-header">
                    <span className="search-icon">🔍</span>
                    <h4>
                      {searchPhaseInfo.currentPhase === 1
                        ? 'Phase 1: Analyzing Search Needs'
                        : 'Executing Web Searches'}
                    </h4>
                  </div>
                  <div className="search-progress-message">
                    {searchPhaseInfo.message}
                  </div>
                  {searchPhaseInfo.totalSearches > 0 && (
                    <div className="search-progress-bar-container">
                      <div
                        className="search-progress-bar"
                        style={{
                          width: `${(searchPhaseInfo.completedSearches / searchPhaseInfo.totalSearches) * 100}%`,
                        }}
                      />
                      <span className="search-progress-count">
                        {searchPhaseInfo.completedSearches}/{searchPhaseInfo.totalSearches}
                      </span>
                    </div>
                  )}
                  {searchPhaseInfo.searchQueries.length > 0 && (
                    <div className="search-queries-list">
                      <span className="queries-label">Queries:</span>
                      <div className="queries-chips">
                        {searchPhaseInfo.searchQueries.slice(0, 5).map((query, i) => (
                          <span
                            key={i}
                            className={`query-chip ${i < searchPhaseInfo.completedSearches ? 'done' : i === searchPhaseInfo.currentSearchIndex ? 'active' : ''}`}
                          >
                            {query.length > 30 ? query.slice(0, 30) + '...' : query}
                          </span>
                        ))}
                        {searchPhaseInfo.searchQueries.length > 5 && (
                          <span className="query-chip more">+{searchPhaseInfo.searchQueries.length - 5} more</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {proposals.length > 0 && (
                <div className="proposals-section">
                  <h3>Proposals</h3>
                  <div className="proposals-list">
                    {proposals.map((prop, i) => (
                      <ProposalCard
                        key={i}
                        proposal={prop}
                        index={i}
                        isActive={i === activeProposalIndex && phase === 'proposing'}
                      />
                    ))}
                  </div>
                </div>
              )}

              {phase === 'judging' && (
                <div className="judging-indicator">
                  <div className="judging-spinner" />
                  <p>Judge is synthesizing proposals...</p>
                </div>
              )}
            </div>
          )}

          {/* Results View */}
          {phase === 'complete' && (
            <div className="collective-results">
              <div className="results-header">
                <h2>Deliberation Complete</h2>
                <button className="new-run-btn" onClick={() => window.location.reload()}>
                  New Run
                </button>
              </div>

              <div className="results-task">
                <strong>Task:</strong> {currentSession?.task}
              </div>

              <div className="proposals-section">
                <h3>Proposals ({proposals.length})</h3>
                <div className="proposals-list">
                  {proposals.map((prop, i) => (
                    <ProposalCard
                      key={i}
                      proposal={prop}
                      index={i}
                      isActive={false}
                    />
                  ))}
                </div>
              </div>

              {verdict && <VerdictPanel verdict={verdict} />}
            </div>
          )}

          {/* Error View */}
          {phase === 'error' && (
            <div className="collective-error">
              <h3>Error</h3>
              <p>{error}</p>
              <button className="retry-btn" onClick={() => window.location.reload()}>
                Try Again
              </button>
            </div>
          )}

          {error && phase === 'idle' && (
            <div className="error-message">{error}</div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="collective-history">
          {sessions.length === 0 ? (
            <div className="empty-state">
              <p>No previous deliberations found.</p>
              <button className="btn-primary" onClick={() => setTab('run')}>
                Start a Deliberation
              </button>
            </div>
          ) : (
            <div className="sessions-grid">
              <div className="sessions-list">
                <h3>Recent Sessions</h3>
                {sessions.map((session) => (
                  <SessionListItem
                    key={session.session_id}
                    session={session}
                    onSelect={() => handleSessionSelect(session)}
                  />
                ))}
              </div>

              {selectedSession && (
                <div className="session-detail">
                  <h3>Session Details</h3>
                  <div className="detail-task">{selectedSession.task}</div>
                  <div className="detail-meta">
                    <span>Pattern: {selectedSession.pattern}</span>
                    <span>Specialists: {selectedSession.k}</span>
                    <span>Status: {selectedSession.status}</span>
                  </div>

                  {/* Judge Verdict first - the final synthesized decision */}
                  {selectedSession.verdict && (
                    <VerdictPanel verdict={selectedSession.verdict} />
                  )}

                  {/* Specialist proposals below - supporting opinions */}
                  {selectedSession.proposals?.length > 0 && (
                    <div className="proposals-section">
                      <h4>Specialist Opinions ({selectedSession.proposals.length})</h4>
                      {selectedSession.proposals.map((prop, i) => (
                        <ProposalCard
                          key={i}
                          proposal={prop}
                          index={i}
                          isActive={false}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
