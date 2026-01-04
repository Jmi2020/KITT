/**
 * ArtifactBrowser - Browse and select artifacts from storage
 *
 * Lists all generated artifacts with filtering and selection capabilities.
 */

import { useState, useEffect, useCallback } from 'react';
import './ArtifactBrowser.css';

interface ArtifactInfo {
  filename: string;
  type: string;
  path: string;
  download_url: string;
  size_bytes: number;
  created_at: string;
  modified_at: string;
}

interface ArtifactListResponse {
  artifacts: ArtifactInfo[];
  total: number;
  type_filter: string | null;
}

interface ArtifactStats {
  total_files: number;
  total_size_bytes: number;
  by_type: Record<string, { count: number; size_bytes: number }>;
}

type ArtifactType = 'all' | 'glb' | 'stl' | '3mf' | 'gcode' | 'step' | 'gltf';

interface ArtifactBrowserProps {
  onSelectArtifact?: (artifactPath: string, artifactType: string) => void;
  onRefresh?: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

const TYPE_ICONS: Record<string, string> = {
  glb: '🎨',
  stl: '📐',
  '3mf': '📦',
  gcode: '🖨️',
  step: '⚙️',
  gltf: '🎬',
};

export function ArtifactBrowser({ onSelectArtifact, onRefresh }: ArtifactBrowserProps) {
  const [artifacts, setArtifacts] = useState<ArtifactInfo[]>([]);
  const [stats, setStats] = useState<ArtifactStats | null>(null);
  const [typeFilter, setTypeFilter] = useState<ArtifactType>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [deletingPath, setDeletingPath] = useState<string | null>(null);

  const fetchArtifacts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [listRes, statsRes] = await Promise.all([
        fetch(`/api/cad/artifacts/list?type=${typeFilter}`),
        fetch('/api/cad/artifacts/stats'),
      ]);

      if (!listRes.ok) throw new Error('Failed to fetch artifacts');
      if (!statsRes.ok) throw new Error('Failed to fetch stats');

      const listData: ArtifactListResponse = await listRes.json();
      const statsData: ArtifactStats = await statsRes.json();

      setArtifacts(listData.artifacts);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [typeFilter]);

  useEffect(() => {
    fetchArtifacts();
  }, [fetchArtifacts]);

  const handleSelect = (artifact: ArtifactInfo) => {
    setSelectedPath(artifact.path);
    if (onSelectArtifact) {
      onSelectArtifact(artifact.path, artifact.type);
    }
  };

  const handleDelete = async (artifact: ArtifactInfo, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Delete ${artifact.filename}?`)) return;

    setDeletingPath(artifact.path);
    try {
      const res = await fetch(`/api/cad/artifacts/${artifact.type}/${artifact.filename}`, {
        method: 'DELETE',
      });
      if (!res.ok) throw new Error('Failed to delete artifact');
      await fetchArtifacts();
      if (selectedPath === artifact.path) {
        setSelectedPath(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeletingPath(null);
    }
  };

  const handleRefresh = () => {
    fetchArtifacts();
    if (onRefresh) onRefresh();
  };

  return (
    <div className="artifact-browser">
      {/* Header with stats */}
      <div className="artifact-browser__header">
        <div className="artifact-browser__stats">
          <span className="artifact-browser__stat">
            <strong>{stats?.total_files ?? 0}</strong> files
          </span>
          <span className="artifact-browser__stat">
            <strong>{formatBytes(stats?.total_size_bytes ?? 0)}</strong> total
          </span>
        </div>
        <button
          type="button"
          className="artifact-browser__refresh-btn"
          onClick={handleRefresh}
          disabled={loading}
          title="Refresh"
        >
          <svg viewBox="0 0 24 24" className={`artifact-browser__refresh-icon ${loading ? 'spinning' : ''}`}>
            <path d="M23 4v6h-6M1 20v-6h6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      {/* Type filter tabs */}
      <div className="artifact-browser__filters">
        {(['all', 'glb', 'stl', '3mf', 'gcode', 'step', 'gltf'] as ArtifactType[]).map((type) => {
          const count = type === 'all'
            ? stats?.total_files ?? 0
            : stats?.by_type[type]?.count ?? 0;
          return (
            <button
              key={type}
              type="button"
              className={`artifact-browser__filter-btn ${typeFilter === type ? 'artifact-browser__filter-btn--active' : ''}`}
              onClick={() => setTypeFilter(type)}
              disabled={type !== 'all' && count === 0}
            >
              {type === 'all' ? 'All' : (
                <>
                  <span className="artifact-browser__type-icon">{TYPE_ICONS[type]}</span>
                  {type.toUpperCase()}
                </>
              )}
              <span className="artifact-browser__filter-count">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Error display */}
      {error && (
        <div className="artifact-browser__error">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Loading state */}
      {loading && artifacts.length === 0 && (
        <div className="artifact-browser__loading">
          <span className="artifact-browser__spinner" />
          <span>Loading artifacts...</span>
        </div>
      )}

      {/* Empty state */}
      {!loading && artifacts.length === 0 && (
        <div className="artifact-browser__empty">
          <svg viewBox="0 0 24 24" className="artifact-browser__empty-icon">
            <path d="M3 3h18v18H3V3z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M3 9h18M9 21V9" fill="none" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
          <span className="artifact-browser__empty-text">
            {typeFilter === 'all' ? 'No artifacts in storage' : `No ${typeFilter.toUpperCase()} files`}
          </span>
          <span className="artifact-browser__empty-hint">
            Generate a model or import a file to get started
          </span>
        </div>
      )}

      {/* Artifact list */}
      {artifacts.length > 0 && (
        <ul className="artifact-browser__list">
          {artifacts.map((artifact) => (
            <li
              key={artifact.path}
              className={`artifact-browser__item ${selectedPath === artifact.path ? 'artifact-browser__item--selected' : ''}`}
              onClick={() => handleSelect(artifact)}
            >
              <div className="artifact-browser__item-icon">
                {TYPE_ICONS[artifact.type] || '📄'}
              </div>
              <div className="artifact-browser__item-info">
                <span className="artifact-browser__item-name" title={artifact.filename}>
                  {artifact.filename}
                </span>
                <span className="artifact-browser__item-meta">
                  <span className="artifact-browser__item-type">{artifact.type.toUpperCase()}</span>
                  <span className="artifact-browser__item-size">{formatBytes(artifact.size_bytes)}</span>
                  <span className="artifact-browser__item-date">{formatDate(artifact.modified_at)}</span>
                </span>
              </div>
              <div className="artifact-browser__item-actions">
                <a
                  href={artifact.download_url}
                  download
                  className="artifact-browser__download-btn"
                  onClick={(e) => e.stopPropagation()}
                  title="Download"
                >
                  <svg viewBox="0 0 24 24">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </a>
                <button
                  type="button"
                  className="artifact-browser__delete-btn"
                  onClick={(e) => handleDelete(artifact, e)}
                  disabled={deletingPath === artifact.path}
                  title="Delete"
                >
                  {deletingPath === artifact.path ? (
                    <span className="artifact-browser__spinner artifact-browser__spinner--small" />
                  ) : (
                    <svg viewBox="0 0 24 24">
                      <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ArtifactBrowser;
