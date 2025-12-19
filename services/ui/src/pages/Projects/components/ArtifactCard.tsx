/**
 * ArtifactCard - Individual artifact card with actions
 */

import type { UnifiedArtifact } from '../types';
import { ARTIFACT_TYPE_INFO, CATEGORY_INFO } from '../types';

interface ArtifactCardProps {
  artifact: UnifiedArtifact;
  onPreview?: (artifact: UnifiedArtifact) => void;
  onDownload: (artifact: UnifiedArtifact) => void;
  onSendToFabrication?: (artifact: UnifiedArtifact) => void;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatRelativeDate(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours === 0) {
      const diffMins = Math.floor(diffMs / (1000 * 60));
      return diffMins <= 1 ? 'Just now' : `${diffMins}m ago`;
    }
    return `${diffHours}h ago`;
  }
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString();
}

// Types that can be previewed in 3D viewer
const PREVIEWABLE_TYPES = ['glb', 'stl', '3mf'];

// Types that can be sent to fabrication
const FABRICATION_TYPES = ['stl', 'glb', '3mf', 'gcode'];

export function ArtifactCard({
  artifact,
  onPreview,
  onDownload,
  onSendToFabrication,
}: ArtifactCardProps) {
  const typeInfo = ARTIFACT_TYPE_INFO[artifact.artifactType] || {
    icon: '📄',
    color: '#6b7280',
    label: artifact.artifactType.toUpperCase(),
  };

  const categoryInfo = CATEGORY_INFO[artifact.category] || {
    label: artifact.category,
    color: '#6b7280',
  };

  const canPreview = PREVIEWABLE_TYPES.includes(artifact.artifactType);
  const canFabricate = FABRICATION_TYPES.includes(artifact.artifactType);

  const handleCardClick = () => {
    if (canPreview && onPreview) {
      onPreview(artifact);
    }
  };

  return (
    <article
      className={`artifact-card ${canPreview ? 'previewable' : ''}`}
      onClick={handleCardClick}
    >
      <div className="artifact-card-header">
        <span className="artifact-icon">{typeInfo.icon}</span>
        <span
          className="artifact-type-badge"
          style={{ borderColor: typeInfo.color, color: typeInfo.color }}
        >
          {typeInfo.label}
        </span>
      </div>

      <div className="artifact-card-body">
        <h4 className="artifact-name" title={artifact.filename}>
          {artifact.filename.length > 28
            ? artifact.filename.substring(0, 25) + '...'
            : artifact.filename}
        </h4>

        <div className="artifact-meta">
          {artifact.sizeBytes !== undefined && (
            <span className="artifact-size">{formatBytes(artifact.sizeBytes)}</span>
          )}
          <span className="artifact-date">{formatRelativeDate(artifact.modifiedAt)}</span>
        </div>

        {artifact.source === 'database' && artifact.projectTitle && (
          <span className="artifact-project">From: {artifact.projectTitle}</span>
        )}

        {artifact.source === 'filesystem' && artifact.parentDir && (
          <span className="artifact-job">Job: {artifact.parentDir.substring(0, 8)}...</span>
        )}

        <div className="artifact-source-badge">
          <span className={`source-indicator source-${artifact.source}`}>
            {artifact.source === 'filesystem' ? 'Local' : 'Project'}
          </span>
          <span
            className="category-indicator"
            style={{ backgroundColor: categoryInfo.color }}
            title={categoryInfo.label}
          >
            {categoryInfo.label}
          </span>
        </div>
      </div>

      <div className="artifact-card-actions">
        {canPreview && onPreview && (
          <button
            className="btn-action btn-preview"
            onClick={(e) => {
              e.stopPropagation();
              onPreview(artifact);
            }}
            title="Preview in 3D viewer"
          >
            👁️
          </button>
        )}

        <button
          className="btn-action btn-download"
          onClick={(e) => {
            e.stopPropagation();
            onDownload(artifact);
          }}
          title="Download"
        >
          ⬇️
        </button>

        {canFabricate && onSendToFabrication && (
          <button
            className="btn-action btn-fabricate"
            onClick={(e) => {
              e.stopPropagation();
              onSendToFabrication(artifact);
            }}
            title="Send to Fabrication Console"
          >
            🖨️
          </button>
        )}
      </div>
    </article>
  );
}

export default ArtifactCard;
