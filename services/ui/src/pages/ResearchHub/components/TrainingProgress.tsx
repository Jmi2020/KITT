/**
 * TrainingProgress - Fine-tuning progress overlay
 *
 * Shows real-time progress for the training pipeline:
 * Prepare -> Train -> Fuse -> Convert
 */

import type { FinetuneJob, TrainingProgressEvent } from '../../../types/research';
import './TrainingProgress.css';

// Training phases
const PHASES = [
  { id: 'preparing', label: 'Prepare Data', icon: '1' },
  { id: 'training', label: 'Train LoRA', icon: '2' },
  { id: 'fusing', label: 'Fuse Weights', icon: '3' },
  { id: 'converting', label: 'Export GGUF', icon: '4' },
] as const;

interface TrainingProgressProps {
  job?: FinetuneJob;
  progress: TrainingProgressEvent | null;
  onClose: () => void;
}

const TrainingProgress = ({ job, progress, onClose }: TrainingProgressProps) => {
  const currentPhase = progress?.phase || 'preparing';
  const hasError = !!progress?.error;
  const isComplete = currentPhase === 'converting' && !hasError;

  // Calculate phase status
  const getPhaseStatus = (phaseId: string): 'completed' | 'active' | 'pending' => {
    const phaseOrder = ['preparing', 'training', 'fusing', 'converting'];
    const currentIndex = phaseOrder.indexOf(currentPhase);
    const phaseIndex = phaseOrder.indexOf(phaseId);

    if (phaseIndex < currentIndex) return 'completed';
    if (phaseIndex === currentIndex) return 'active';
    return 'pending';
  };

  // Format ETA
  const formatEta = (seconds?: number) => {
    if (!seconds) return '--';
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  return (
    <div className="training-progress-overlay">
      <div className="training-progress-modal">
        {/* Header */}
        <div className="training-header">
          <h3>
            {hasError ? 'Training Error' : isComplete ? 'Training Complete' : 'Training Model'}
          </h3>
          <button className="close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        {/* Topic */}
        {job && (
          <div className="training-topic">
            <strong>{job.topic_name}</strong>
            <span className="job-id">Job: {job.job_id.slice(0, 8)}</span>
          </div>
        )}

        {/* Phase Pipeline */}
        <div className="training-pipeline">
          {PHASES.map((phase, index) => {
            const status = getPhaseStatus(phase.id);
            return (
              <div key={phase.id} className={`training-phase ${status}`}>
                <div className="phase-icon">
                  {status === 'completed' ? '✓' : phase.icon}
                </div>
                <div className="phase-label">{phase.label}</div>
                {index < PHASES.length - 1 && <div className="phase-connector" />}
              </div>
            );
          })}
        </div>

        {/* Progress Metrics */}
        {progress && currentPhase === 'training' && (
          <div className="training-metrics">
            <div className="metric-row">
              <div className="training-metric">
                <span className="metric-label">Epoch</span>
                <span className="metric-value">
                  {progress.epoch} / {job?.config.epochs || '?'}
                </span>
              </div>
              <div className="training-metric">
                <span className="metric-label">Step</span>
                <span className="metric-value">{progress.step}</span>
              </div>
              <div className="training-metric">
                <span className="metric-label">Loss</span>
                <span className={`metric-value ${progress.loss < 1 ? 'good' : ''}`}>
                  {progress.loss.toFixed(4)}
                </span>
              </div>
            </div>

            <div className="metric-row">
              <div className="training-metric">
                <span className="metric-label">Speed</span>
                <span className="metric-value">{progress.tokens_per_second.toFixed(1)} tok/s</span>
              </div>
              <div className="training-metric">
                <span className="metric-label">ETA</span>
                <span className="metric-value">{formatEta(progress.eta_seconds)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Loss Graph Placeholder */}
        {progress && currentPhase === 'training' && (
          <div className="loss-graph">
            <div className="graph-label">Training Loss</div>
            <div className="graph-value">{progress.loss.toFixed(4)}</div>
            <div className="loss-indicator">
              <div
                className="loss-bar"
                style={{
                  width: `${Math.max(5, 100 - progress.loss * 20)}%`,
                }}
              />
            </div>
          </div>
        )}

        {/* Progress Bar */}
        {progress && !hasError && job && (
          <div className="training-progress-bar">
            <div
              className="training-progress-fill"
              style={{
                width: `${
                  job.config.epochs > 0
                    ? ((progress.epoch - 1 + progress.step / (progress.step * 100 || 1)) /
                        job.config.epochs) *
                      100
                    : 0
                }%`,
              }}
            />
          </div>
        )}

        {/* Phase Status Messages */}
        {progress && !hasError && (
          <div className="phase-status-message">
            {currentPhase === 'preparing' && 'Loading dataset and initializing model...'}
            {currentPhase === 'training' && `Training epoch ${progress.epoch}...`}
            {currentPhase === 'fusing' && 'Merging LoRA weights into base model...'}
            {currentPhase === 'converting' && 'Converting to GGUF format...'}
          </div>
        )}

        {/* Error Message */}
        {hasError && (
          <div className="training-error">
            <span className="error-icon">⚠️</span>
            <span className="error-message">{progress?.error}</span>
          </div>
        )}

        {/* Complete Message */}
        {isComplete && (
          <div className="training-complete">
            <span className="complete-icon">🎉</span>
            <span className="complete-message">
              Expert model ready! Check the Experts tab to activate it.
            </span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="training-actions">
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

export default TrainingProgress;
