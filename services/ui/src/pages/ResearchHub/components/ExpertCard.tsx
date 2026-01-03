/**
 * ExpertCard - Expert model summary card
 *
 * Displays model information with activate/deactivate/delete actions.
 */

import type { ExpertModel } from '../../../types/research';
import './ExpertCard.css';

interface ExpertCardProps {
  expert: ExpertModel;
  onActivate: () => void;
  onDeactivate: () => void;
  onDelete: () => void;
  disabled?: boolean;
}

const ExpertCard = ({
  expert,
  onActivate,
  onDeactivate,
  onDelete,
  disabled,
}: ExpertCardProps) => {
  const isActive = expert.is_active;
  const hasGguf = !!expert.gguf_path;

  return (
    <div className={`expert-card ${isActive ? 'active' : 'inactive'}`}>
      {/* Header */}
      <div className="expert-header">
        <div className="expert-info">
          <h4 className="expert-topic">{expert.topic_name}</h4>
          <span className="expert-id">ID: {expert.model_id.slice(0, 12)}</span>
        </div>
        <span className={`expert-status ${isActive ? 'active' : 'inactive'}`}>
          {isActive ? 'ACTIVE' : 'INACTIVE'}
        </span>
      </div>

      {/* Stats */}
      <div className="expert-stats">
        <div className="expert-stat">
          <span className="stat-value">{expert.training_samples.toLocaleString()}</span>
          <span className="stat-label">Samples</span>
        </div>
        <div className="expert-stat">
          <span className={`stat-value ${expert.final_loss < 0.5 ? 'good' : ''}`}>
            {expert.final_loss.toFixed(4)}
          </span>
          <span className="stat-label">Final Loss</span>
        </div>
        <div className="expert-stat">
          <span className="stat-value">{hasGguf ? 'Yes' : 'No'}</span>
          <span className="stat-label">GGUF</span>
        </div>
      </div>

      {/* Paths */}
      <div className="expert-paths">
        <div className="path-item">
          <span className="path-label">Adapter:</span>
          <code className="path-value" title={expert.adapter_path}>
            {expert.adapter_path.split('/').pop()}
          </code>
        </div>
        {expert.gguf_path && (
          <div className="path-item">
            <span className="path-label">GGUF:</span>
            <code className="path-value" title={expert.gguf_path}>
              {expert.gguf_path.split('/').pop()}
            </code>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="expert-actions">
        {isActive ? (
          <button
            className="btn-secondary"
            onClick={onDeactivate}
            disabled={disabled}
          >
            Deactivate
          </button>
        ) : (
          <button
            className="btn-primary"
            onClick={onActivate}
            disabled={disabled}
          >
            Activate
          </button>
        )}
        <button
          className="btn-danger"
          onClick={onDelete}
          disabled={disabled || isActive}
          title={isActive ? 'Deactivate before deleting' : 'Delete model'}
        >
          Delete
        </button>
      </div>

      {/* Timestamps */}
      <div className="expert-timestamps">
        <small>Created: {new Date(expert.created_at).toLocaleDateString()}</small>
        {expert.last_used_at && (
          <small>Last used: {new Date(expert.last_used_at).toLocaleDateString()}</small>
        )}
      </div>
    </div>
  );
};

export default ExpertCard;
