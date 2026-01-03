/**
 * TopicCard - Research topic summary card
 *
 * Displays topic status, progress, and stats with action buttons.
 */

import type { ResearchTopic } from '../../../types/research';
import './TopicCard.css';

interface TopicCardProps {
  topic: ResearchTopic;
  onStartHarvest: () => void;
  isHarvesting: boolean;
  disabled?: boolean;
}

const TopicCard = ({ topic, onStartHarvest, isHarvesting, disabled }: TopicCardProps) => {
  // Status badge styling
  const getStatusBadge = () => {
    switch (topic.status) {
      case 'created':
        return { label: 'Created', className: 'status-created' };
      case 'harvesting':
        return { label: 'Harvesting', className: 'status-harvesting' };
      case 'extracting':
        return { label: 'Extracting', className: 'status-extracting' };
      case 'ready':
        return { label: 'Ready', className: 'status-ready' };
      case 'error':
        return { label: 'Error', className: 'status-error' };
      default:
        return { label: topic.status, className: '' };
    }
  };

  const status = getStatusBadge();
  const isReadyForTraining = topic.dataset_entries >= 5000;
  const maturationPercent = Math.min(100, (topic.maturation_score || 0) * 100);

  return (
    <div className={`topic-card ${status.className}`}>
      {/* Header */}
      <div className="topic-header">
        <h4 className="topic-name">{topic.name}</h4>
        <span className={`topic-status ${status.className}`}>{status.label}</span>
      </div>

      {/* Description */}
      {topic.description && (
        <p className="topic-description">{topic.description}</p>
      )}

      {/* Sources */}
      <div className="topic-sources">
        {topic.sources.map((source) => (
          <span key={source} className="source-badge">
            {source}
          </span>
        ))}
      </div>

      {/* Stats Grid */}
      <div className="topic-stats">
        <div className="topic-stat">
          <span className="stat-value">{topic.papers_harvested}</span>
          <span className="stat-label">Papers</span>
        </div>
        <div className="topic-stat">
          <span className="stat-value">{topic.claims_extracted}</span>
          <span className="stat-label">Claims</span>
        </div>
        <div className="topic-stat">
          <span className="stat-value">{topic.dataset_entries}</span>
          <span className="stat-label">Entries</span>
        </div>
      </div>

      {/* Maturation Progress */}
      {topic.dataset_entries > 0 && (
        <div className="topic-maturation">
          <div className="maturation-header">
            <span className="maturation-label">Dataset Maturation</span>
            <span className="maturation-value">{maturationPercent.toFixed(0)}%</span>
          </div>
          <div className="maturation-bar">
            <div
              className="maturation-fill"
              style={{ width: `${maturationPercent}%` }}
            />
            {/* 5000 threshold marker */}
            <div className="threshold-marker" style={{ left: '50%' }} title="5000 entries (training threshold)" />
          </div>
          {isReadyForTraining && (
            <span className="ready-badge">Ready for Training</span>
          )}
        </div>
      )}

      {/* Error Message */}
      {topic.error_message && (
        <div className="topic-error">
          {topic.error_message}
        </div>
      )}

      {/* Actions */}
      <div className="topic-actions">
        {topic.status === 'created' && (
          <button
            className="btn-primary"
            onClick={onStartHarvest}
            disabled={disabled || isHarvesting}
          >
            {isHarvesting ? 'Harvesting...' : 'Start Harvest'}
          </button>
        )}
        {topic.status === 'ready' && isReadyForTraining && (
          <button className="btn-secondary" disabled={disabled}>
            Fine-Tune Model
          </button>
        )}
        {topic.status === 'error' && (
          <button
            className="btn-primary"
            onClick={onStartHarvest}
            disabled={disabled || isHarvesting}
          >
            Retry Harvest
          </button>
        )}
      </div>

      {/* Timestamps */}
      <div className="topic-timestamps">
        <small>Created: {new Date(topic.created_at).toLocaleDateString()}</small>
        {topic.updated_at !== topic.created_at && (
          <small>Updated: {new Date(topic.updated_at).toLocaleDateString()}</small>
        )}
      </div>
    </div>
  );
};

export default TopicCard;
