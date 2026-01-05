/**
 * ArtifactGrid - Grid container for artifact cards
 */

import { ArtifactCard } from './ArtifactCard';
import { EmptyState } from './EmptyState';
import type { UnifiedArtifact } from '../types';

interface ArtifactGridProps {
  artifacts: UnifiedArtifact[];
  loading: boolean;
  error: string | null;
  onPreview?: (artifact: UnifiedArtifact) => void;
  onDownload: (artifact: UnifiedArtifact) => void;
  onSendToFabrication?: (artifact: UnifiedArtifact) => void;
  onRetry?: () => void;
}

/** Skeleton card component for loading state */
function SkeletonCard() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-card-header">
        <div className="skeleton-icon" />
        <div className="skeleton-badge" />
      </div>
      <div className="skeleton-card-body">
        <div className="skeleton-title" />
        <div className="skeleton-meta">
          <div className="skeleton-meta-item" />
          <div className="skeleton-meta-item" />
        </div>
      </div>
      <div className="skeleton-card-actions">
        <div className="skeleton-btn" />
        <div className="skeleton-btn" />
      </div>
    </div>
  );
}

export function ArtifactGrid({
  artifacts,
  loading,
  error,
  onPreview,
  onDownload,
  onSendToFabrication,
  onRetry,
}: ArtifactGridProps) {
  if (loading) {
    return (
      <div className="skeleton-grid">
        {[...Array(6)].map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-banner">
        <strong>Error loading artifacts:</strong> {error}
        {onRetry && (
          <button className="btn-small" onClick={onRetry}>
            Retry
          </button>
        )}
      </div>
    );
  }

  if (artifacts.length === 0) {
    return (
      <EmptyState
        icon="📁"
        title="No Artifacts Found"
        message="Generate models in the Fabrication Console or import files to get started."
      />
    );
  }

  return (
    <div className="artifacts-grid">
      {artifacts.map((artifact) => (
        <ArtifactCard
          key={artifact.id}
          artifact={artifact}
          onPreview={onPreview}
          onDownload={onDownload}
          onSendToFabrication={onSendToFabrication}
        />
      ))}
    </div>
  );
}

export default ArtifactGrid;
