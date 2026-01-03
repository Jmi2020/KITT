/**
 * FinetuneJobCard - Training job summary card
 *
 * Displays job status, progress, and metrics.
 */

import type { FinetuneJob } from '../../../types/research';
import './FinetuneJobCard.css';

interface FinetuneJobCardProps {
  job: FinetuneJob;
  onViewProgress?: () => void;
}

const FinetuneJobCard = ({ job, onViewProgress }: FinetuneJobCardProps) => {
  // Status badge styling
  const getStatusBadge = () => {
    switch (job.status) {
      case 'pending':
        return { label: 'Pending', className: 'status-pending' };
      case 'preparing':
        return { label: 'Preparing', className: 'status-preparing' };
      case 'training':
        return { label: 'Training', className: 'status-training' };
      case 'fusing':
        return { label: 'Fusing', className: 'status-fusing' };
      case 'converting':
        return { label: 'Converting', className: 'status-converting' };
      case 'completed':
        return { label: 'Completed', className: 'status-completed' };
      case 'failed':
        return { label: 'Failed', className: 'status-failed' };
      default:
        return { label: job.status, className: '' };
    }
  };

  const status = getStatusBadge();
  const isActive = !['completed', 'failed'].includes(job.status);
  const progress = job.progress;

  // Calculate training progress percentage
  const progressPercent = progress?.total_epochs
    ? ((progress.current_epoch - 1 + progress.current_step / progress.total_steps) /
        progress.total_epochs) *
      100
    : 0;

  return (
    <div className={`finetune-job-card ${status.className}`}>
      {/* Header */}
      <div className="job-header">
        <div className="job-info">
          <h4 className="job-topic">{job.topic_name}</h4>
          <span className="job-id">Job: {job.job_id.slice(0, 8)}</span>
        </div>
        <span className={`job-status ${status.className}`}>{status.label}</span>
      </div>

      {/* Config */}
      <div className="job-config">
        <span className="config-item">
          <span className="config-label">Epochs:</span>
          <span className="config-value">{job.config.epochs}</span>
        </span>
        <span className="config-item">
          <span className="config-label">Batch:</span>
          <span className="config-value">{job.config.batch_size}</span>
        </span>
        <span className="config-item">
          <span className="config-label">LR:</span>
          <span className="config-value">{job.config.learning_rate}</span>
        </span>
        <span className="config-item">
          <span className="config-label">Rank:</span>
          <span className="config-value">{job.config.lora_rank}</span>
        </span>
      </div>

      {/* Active Progress */}
      {isActive && progress && (
        <div className="job-progress">
          <div className="progress-header">
            <span className="progress-label">
              Epoch {progress.current_epoch}/{progress.total_epochs}
            </span>
            <span className="progress-stats">
              {progress.tokens_per_second.toFixed(1)} tok/s | Loss: {progress.current_loss.toFixed(4)}
            </span>
          </div>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="progress-steps">
            Step {progress.current_step}/{progress.total_steps}
          </div>
        </div>
      )}

      {/* Completed Metrics */}
      {job.status === 'completed' && job.metrics && (
        <div className="job-metrics">
          <div className="metric">
            <span className="metric-value">{job.metrics.final_loss.toFixed(4)}</span>
            <span className="metric-label">Final Loss</span>
          </div>
          <div className="metric">
            <span className="metric-value">{job.metrics.training_samples.toLocaleString()}</span>
            <span className="metric-label">Samples</span>
          </div>
          <div className="metric">
            <span className="metric-value">
              {(job.metrics.training_duration_seconds / 60).toFixed(1)}m
            </span>
            <span className="metric-label">Duration</span>
          </div>
        </div>
      )}

      {/* Error */}
      {job.error_message && (
        <div className="job-error">{job.error_message}</div>
      )}

      {/* Actions */}
      <div className="job-actions">
        {isActive && onViewProgress && (
          <button className="btn-secondary" onClick={onViewProgress}>
            View Progress
          </button>
        )}
        {job.status === 'completed' && (
          <button className="btn-secondary">View in Experts</button>
        )}
      </div>

      {/* Timestamps */}
      <div className="job-timestamps">
        {job.started_at && (
          <small>Started: {new Date(job.started_at).toLocaleString()}</small>
        )}
        {job.completed_at && (
          <small>Completed: {new Date(job.completed_at).toLocaleString()}</small>
        )}
      </div>
    </div>
  );
};

export default FinetuneJobCard;
