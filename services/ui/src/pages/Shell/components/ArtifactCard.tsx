/**
 * ArtifactCard - Renders CAD artifacts with download buttons and preview links
 *
 * Displays generated 3D models in the Shell chat with:
 * - Download buttons for each file type (GLB, STL, 3MF)
 * - Clickable links to open files directly
 * - Visual indicators for file types
 */

import './ArtifactCard.css';

interface ArtifactMetadata {
  glb_location?: string;
  stl_location?: string;
  thumbnail?: string;
  [key: string]: string | undefined;
}

export interface CadArtifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata?: ArtifactMetadata;
}

interface ArtifactCardProps {
  artifacts: CadArtifact[];
}

// Translate artifact paths to web-accessible URLs
const translatePath = (location: string): string => {
  const base = '/api/cad/artifacts';
  if (location.startsWith('artifacts/')) {
    return `${base}/${location.replace('artifacts/', '')}`;
  }
  if (location.startsWith('storage/artifacts/')) {
    return `${base}/${location.replace('storage/artifacts/', '')}`;
  }
  if (location.startsWith('/')) {
    return location;
  }
  return `${base}/${location}`;
};

// Get download filename from path
const getFilename = (path: string): string => {
  return path.split('/').pop() || 'model';
};

// File type icons and labels
const FILE_TYPES: Record<string, { icon: string; label: string; desc: string }> = {
  glb: { icon: '🎨', label: 'GLB', desc: 'Preview / AR View' },
  stl: { icon: '🖨️', label: 'STL', desc: 'For slicing' },
  '3mf': { icon: '📦', label: '3MF', desc: 'Print-ready' },
  gcode: { icon: '⚙️', label: 'G-code', desc: 'Printer instructions' },
};

export function ArtifactCard({ artifacts }: ArtifactCardProps) {
  if (!artifacts.length) return null;

  return (
    <div className="artifact-card">
      <div className="artifact-card__header">
        <span className="artifact-card__icon">🎨</span>
        <span className="artifact-card__title">Generated Models</span>
        <span className="artifact-card__count">{artifacts.length}</span>
      </div>

      <div className="artifact-card__list">
        {artifacts.map((artifact, index) => {
          const glbUrl = artifact.metadata?.glb_location
            ? translatePath(artifact.metadata.glb_location)
            : artifact.artifactType === 'glb'
              ? translatePath(artifact.location)
              : null;

          const stlUrl = artifact.metadata?.stl_location
            ? translatePath(artifact.metadata.stl_location)
            : artifact.artifactType === 'stl'
              ? translatePath(artifact.location)
              : null;

          const primaryUrl = translatePath(artifact.location);
          const thumbnailUrl = artifact.metadata?.thumbnail;

          return (
            <div key={index} className="artifact-card__item">
              {/* Thumbnail or placeholder */}
              <div className="artifact-card__preview">
                {thumbnailUrl ? (
                  <img src={thumbnailUrl} alt="Model preview" />
                ) : (
                  <div className="artifact-card__preview-placeholder">
                    <span>{FILE_TYPES[artifact.artifactType.toLowerCase()]?.icon || '📄'}</span>
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="artifact-card__info">
                <span className="artifact-card__provider">{artifact.provider}</span>
                <span className="artifact-card__type">
                  {artifact.artifactType.toUpperCase()}
                </span>
              </div>

              {/* Download buttons */}
              <div className="artifact-card__actions">
                {glbUrl && (
                  <a
                    href={glbUrl}
                    download={getFilename(glbUrl)}
                    className="artifact-card__btn artifact-card__btn--glb"
                    title="Download GLB for preview/AR"
                  >
                    <span className="artifact-card__btn-icon">🎨</span>
                    <span className="artifact-card__btn-label">GLB</span>
                  </a>
                )}

                {stlUrl && (
                  <a
                    href={stlUrl}
                    download={getFilename(stlUrl)}
                    className="artifact-card__btn artifact-card__btn--stl"
                    title="Download STL for slicing"
                  >
                    <span className="artifact-card__btn-icon">🖨️</span>
                    <span className="artifact-card__btn-label">STL</span>
                  </a>
                )}

                {!glbUrl && !stlUrl && (
                  <a
                    href={primaryUrl}
                    download={getFilename(primaryUrl)}
                    className="artifact-card__btn artifact-card__btn--primary"
                    title={`Download ${artifact.artifactType.toUpperCase()}`}
                  >
                    <span className="artifact-card__btn-icon">⬇️</span>
                    <span className="artifact-card__btn-label">Download</span>
                  </a>
                )}

                {/* View in Fabrication Console link */}
                <a
                  href="/fabrication"
                  className="artifact-card__btn artifact-card__btn--view"
                  title="Open in Fabrication Console with 3D viewer"
                >
                  <span className="artifact-card__btn-icon">👁️</span>
                  <span className="artifact-card__btn-label">View</span>
                </a>
              </div>
            </div>
          );
        })}
      </div>

      <div className="artifact-card__footer">
        <span className="artifact-card__hint">
          Tip: Open <a href="/fabrication">Fabrication Console</a> for 3D preview and print options
        </span>
      </div>
    </div>
  );
}

export default ArtifactCard;
