/**
 * PageDescriptor - Onboarding section for the Artifact Library
 */

import type { ArtifactStats } from '../types';

interface PageDescriptorProps {
  stats: ArtifactStats | null;
  isDismissed: boolean;
  onDismiss: () => void;
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

export function PageDescriptor({ stats, isDismissed, onDismiss }: PageDescriptorProps) {
  if (isDismissed) return null;

  return (
    <section className="page-descriptor">
      <div className="descriptor-content">
        <div className="descriptor-icon">📁</div>
        <div className="descriptor-text">
          <h2>Artifact Library</h2>
          <p>
            Your fabrication artifacts in one place. Browse 3D models, print-ready files, G-code
            instructions, and reference images generated through KITTY workflows.
          </p>
          <ul className="descriptor-features">
            <li>
              <span className="feature-icon">📐</span>
              <strong>3D Meshes:</strong> STL, GLB, and GLTF models
            </li>
            <li>
              <span className="feature-icon">🖨️</span>
              <strong>Print-Ready:</strong> 3MF files with embedded settings
            </li>
            <li>
              <span className="feature-icon">⚙️</span>
              <strong>Instructions:</strong> Sliced G-code for your printers
            </li>
            <li>
              <span className="feature-icon">🔧</span>
              <strong>CAD Sources:</strong> STEP files for editing
            </li>
          </ul>
        </div>
        {stats && (
          <div className="descriptor-stats">
            <div className="stat-pill">{stats.totalCount} artifacts</div>
            <div className="stat-pill">{formatBytes(stats.totalSizeBytes)}</div>
          </div>
        )}
      </div>
      <button className="descriptor-dismiss" onClick={onDismiss} title="Dismiss">
        &times;
      </button>
    </section>
  );
}

export default PageDescriptor;
