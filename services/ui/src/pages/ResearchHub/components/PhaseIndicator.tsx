/**
 * PhaseIndicator - Visual progress indicator for research phases
 *
 * Shows the current phase of research with a pipeline visualization:
 * Initialize -> Search -> Extract -> Validate -> Synthesize
 *
 * Pattern inspired by Collective Intelligence phase indicator.
 */

import { useMemo } from 'react';
import type { ResearchEvent } from '../../../types/research';
import './PhaseIndicator.css';

// Research phases in order
const PHASES = [
  { id: 'initialize', label: 'Initialize', icon: '1' },
  { id: 'search', label: 'Search', icon: '2' },
  { id: 'extract', label: 'Extract', icon: '3' },
  { id: 'validate', label: 'Validate', icon: '4' },
  { id: 'synthesize', label: 'Synthesize', icon: '5' },
] as const;

type PhaseId = (typeof PHASES)[number]['id'];

interface PhaseIndicatorProps {
  /** Current phase being executed */
  currentPhase: PhaseId;
  /** Current iteration number */
  iteration: number;
  /** Maximum iterations */
  maxIterations: number;
  /** Number of searches completed in current iteration */
  searchesCompleted?: number;
  /** Total searches planned for current iteration */
  totalSearches?: number;
  /** Number of findings extracted */
  findingsExtracted?: number;
  /** Whether synthesis is in progress */
  synthesizing?: boolean;
  /** List of recent events for the log */
  recentEvents?: ResearchEvent[];
  /** Whether to show expanded log */
  showLog?: boolean;
  /** Toggle log visibility */
  onToggleLog?: () => void;
}

function getPhaseFromEvent(event: ResearchEvent): PhaseId {
  const type = event.type;

  if (type === 'session_started' || type === 'iteration_start') {
    return 'initialize';
  }
  if (
    type === 'search_phase_start' ||
    type === 'search_query_start' ||
    type === 'search_query_complete' ||
    type === 'search_cache_hit' ||
    type === 'search_phase_complete'
  ) {
    return 'search';
  }
  if (
    type === 'extraction_start' ||
    type === 'finding_extracted' ||
    type === 'extraction_complete'
  ) {
    return 'extract';
  }
  if (
    type === 'validation_start' ||
    type === 'validation_complete' ||
    type === 'quality_check' ||
    type === 'saturation_check' ||
    type === 'stopping_decision'
  ) {
    return 'validate';
  }
  if (
    type === 'synthesis_start' ||
    type === 'synthesis_chunk' ||
    type === 'synthesis_complete'
  ) {
    return 'synthesize';
  }

  return 'initialize';
}

function getPhaseIndex(phase: PhaseId): number {
  return PHASES.findIndex((p) => p.id === phase);
}

function getPhaseStatus(
  phase: PhaseId,
  currentPhase: PhaseId
): 'completed' | 'active' | 'pending' {
  const phaseIndex = getPhaseIndex(phase);
  const currentIndex = getPhaseIndex(currentPhase);

  if (phaseIndex < currentIndex) return 'completed';
  if (phaseIndex === currentIndex) return 'active';
  return 'pending';
}

const PhaseIndicator = ({
  currentPhase,
  iteration,
  maxIterations,
  searchesCompleted = 0,
  totalSearches = 0,
  findingsExtracted = 0,
  synthesizing = false,
  recentEvents = [],
  showLog = false,
  onToggleLog,
}: PhaseIndicatorProps) => {
  // Calculate progress percentage
  const progress = useMemo(() => {
    const currentIndex = getPhaseIndex(currentPhase);
    const baseProgress = (currentIndex / PHASES.length) * 100;

    // Add sub-progress within current phase
    if (currentPhase === 'search' && totalSearches > 0) {
      const searchProgress = (searchesCompleted / totalSearches) * (100 / PHASES.length);
      return Math.min(baseProgress + searchProgress, 100);
    }

    return baseProgress;
  }, [currentPhase, searchesCompleted, totalSearches]);

  // Format event for log display
  const formatEventLog = (event: ResearchEvent): string => {
    const type = event.type;

    switch (type) {
      case 'session_started':
        return `Session started: "${event.query?.slice(0, 50)}..."`;
      case 'iteration_start':
        return `Starting iteration ${event.iteration} of ${maxIterations}`;
      case 'iteration_complete':
        return `Iteration ${event.iteration} complete: +${event.new_findings || 0} findings`;
      case 'search_query_start':
        return `Searching: "${event.search_query?.slice(0, 40)}..."`;
      case 'search_query_complete':
        return `Search complete: ${event.results_count || 0} results${event.cached ? ' (cached)' : ''}`;
      case 'search_phase_complete':
        return `Search phase done: ${event.successful_queries}/${event.total_queries} queries, ${event.total_results} results`;
      case 'finding_extracted':
        return `Found: "${event.content_preview?.slice(0, 50)}..."`;
      case 'extraction_complete':
        return `Extracted ${event.findings_extracted} findings from ${event.sources_processed} sources`;
      case 'validation_complete':
        return `Validated ${event.claims_validated} claims, rejected ${event.claims_rejected}`;
      case 'quality_check':
        return `Quality: ${((event.completeness_score || 0) * 100).toFixed(0)}% complete, ${((event.confidence_score || 0) * 100).toFixed(0)}% confident`;
      case 'stopping_decision':
        return event.should_stop ? `Stopping: ${event.reason}` : 'Continuing research...';
      case 'synthesis_start':
        return `Synthesizing ${event.findings_count} findings...`;
      case 'synthesis_complete':
        return `Synthesis complete (${event.synthesis_length} chars)`;
      case 'session_complete':
        return `Research complete: ${event.total_findings} findings, $${event.total_cost_usd?.toFixed(4)} cost`;
      case 'session_error':
        return `Error: ${event.error}`;
      default:
        return `${type}`;
    }
  };

  return (
    <div className="phase-indicator">
      {/* Iteration Counter */}
      <div className="phase-iteration">
        <span className="iteration-label">Iteration</span>
        <span className="iteration-value">
          {iteration} / {maxIterations}
        </span>
      </div>

      {/* Phase Pipeline */}
      <div className="phase-pipeline">
        {PHASES.map((phase, index) => {
          const status = getPhaseStatus(phase.id, currentPhase);
          return (
            <div key={phase.id} className={`phase-step ${status}`}>
              <div className="phase-icon">{status === 'completed' ? '✓' : phase.icon}</div>
              <div className="phase-label">{phase.label}</div>
              {index < PHASES.length - 1 && <div className="phase-connector" />}
            </div>
          );
        })}
      </div>

      {/* Progress Bar */}
      <div className="phase-progress-bar">
        <div className="phase-progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Current Phase Stats */}
      <div className="phase-stats">
        {currentPhase === 'search' && totalSearches > 0 && (
          <span className="phase-stat">
            Searches: {searchesCompleted}/{totalSearches}
          </span>
        )}
        {currentPhase === 'extract' && (
          <span className="phase-stat">Findings: {findingsExtracted}</span>
        )}
        {synthesizing && <span className="phase-stat synthesizing">Synthesizing...</span>}
      </div>

      {/* Expandable Event Log */}
      {recentEvents.length > 0 && (
        <div className="phase-log-section">
          <button className="phase-log-toggle" onClick={onToggleLog}>
            {showLog ? 'Hide' : 'Show'} Event Log ({recentEvents.length})
          </button>
          {showLog && (
            <div className="phase-log">
              {recentEvents
                .slice()
                .reverse()
                .slice(0, 20)
                .map((event, idx) => (
                  <div key={idx} className={`phase-log-entry ${event.type}`}>
                    <span className="log-time">
                      {event.timestamp
                        ? new Date(event.timestamp).toLocaleTimeString()
                        : ''}
                    </span>
                    <span className="log-message">{formatEventLog(event)}</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default PhaseIndicator;
export { getPhaseFromEvent, type PhaseId };
