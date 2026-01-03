/**
 * HarvestProgress - Paper harvesting progress overlay
 *
 * Shows real-time progress for the harvesting pipeline:
 * Harvest -> Extract -> Build
 */

import type { ResearchTopic, HarvestProgressEvent } from '../../../types/research';
import './HarvestProgress.css';

// Harvest phases
const PHASES = [
  { id: 'harvesting', label: 'Harvest Papers', icon: '1' },
  { id: 'extracting', label: 'Extract Claims', icon: '2' },
  { id: 'building', label: 'Build Dataset', icon: '3' },
] as const;

interface HarvestProgressProps {
  topic?: ResearchTopic;
  progress: HarvestProgressEvent | null;
  onClose: () => void;
}

const HarvestProgress = ({ topic, progress, onClose }: HarvestProgressProps) => {
  const currentPhase = progress?.phase || 'harvesting';
  const hasError = !!progress?.error;
  const isComplete = currentPhase === 'building' && !hasError;

  // Calculate phase status
  const getPhaseStatus = (phaseId: string): 'completed' | 'active' | 'pending' => {
    const phaseOrder = ['harvesting', 'extracting', 'building'];
    const currentIndex = phaseOrder.indexOf(currentPhase);
    const phaseIndex = phaseOrder.indexOf(phaseId);

    if (phaseIndex < currentIndex) return 'completed';
    if (phaseIndex === currentIndex) return 'active';
    return 'pending';
  };

  return (
    <div className="harvest-progress-overlay">
      <div className="harvest-progress-modal">
        {/* Header */}
        <div className="harvest-header">
          <h3>
            {hasError ? 'Harvest Error' : isComplete ? 'Harvest Complete' : 'Harvesting Papers'}
          </h3>
          <button className="close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        {/* Topic Name */}
        {topic && (
          <div className="harvest-topic">
            <strong>{topic.name}</strong>
          </div>
        )}

        {/* Phase Pipeline */}
        <div className="harvest-pipeline">
          {PHASES.map((phase, index) => {
            const status = getPhaseStatus(phase.id);
            return (
              <div key={phase.id} className={`harvest-phase ${status}`}>
                <div className="phase-icon">
                  {status === 'completed' ? '✓' : phase.icon}
                </div>
                <div className="phase-label">{phase.label}</div>
                {index < PHASES.length - 1 && <div className="phase-connector" />}
              </div>
            );
          })}
        </div>

        {/* Progress Stats */}
        {progress && (
          <div className="harvest-stats">
            <div className="harvest-stat">
              <span className="stat-icon">📄</span>
              <span className="stat-value">{progress.papers_found}</span>
              <span className="stat-label">Papers Found</span>
            </div>
            <div className="harvest-stat">
              <span className="stat-icon">📥</span>
              <span className="stat-value">{progress.papers_processed}</span>
              <span className="stat-label">Processed</span>
            </div>
            <div className="harvest-stat">
              <span className="stat-icon">💡</span>
              <span className="stat-value">{progress.claims_extracted}</span>
              <span className="stat-label">Claims</span>
            </div>
            <div className="harvest-stat">
              <span className="stat-icon">📝</span>
              <span className="stat-value">{progress.entries_created}</span>
              <span className="stat-label">Entries</span>
            </div>
          </div>
        )}

        {/* Current Paper */}
        {progress?.current_paper && (
          <div className="harvest-current">
            <span className="current-label">Processing:</span>
            <span className="current-paper" title={progress.current_paper}>
              {progress.current_paper.length > 60
                ? progress.current_paper.slice(0, 60) + '...'
                : progress.current_paper}
            </span>
          </div>
        )}

        {/* Source */}
        {progress?.source && (
          <div className="harvest-source">
            <span className="source-label">Source:</span>
            <span className="source-badge">{progress.source}</span>
          </div>
        )}

        {/* Progress Bar */}
        {progress && !hasError && (
          <div className="harvest-progress-bar">
            <div
              className="harvest-progress-fill"
              style={{
                width: `${
                  progress.papers_found > 0
                    ? (progress.papers_processed / progress.papers_found) * 100
                    : 0
                }%`,
              }}
            />
          </div>
        )}

        {/* Error Message */}
        {hasError && (
          <div className="harvest-error">
            <span className="error-icon">⚠️</span>
            <span className="error-message">{progress?.error}</span>
          </div>
        )}

        {/* Complete Message */}
        {isComplete && (
          <div className="harvest-complete">
            <span className="complete-icon">🎉</span>
            <span className="complete-message">
              Dataset ready with {progress?.entries_created || 0} training entries!
            </span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="harvest-actions">
          {(hasError || isComplete) && (
            <button className="btn-primary" onClick={onClose}>
              {hasError ? 'Close' : 'Done'}
            </button>
          )}
          {!hasError && !isComplete && (
            <button className="btn-secondary" onClick={onClose}>
              Run in Background
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default HarvestProgress;
