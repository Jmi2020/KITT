import { useEffect, useState } from 'react';

interface ProjectArtifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata: Record<string, string>;
}

interface ProjectModel {
  projectId: string;
  conversationId: string;
  title?: string | null;
  summary?: string | null;
  artifacts: ProjectArtifact[];
  metadata: Record<string, string>;
  updatedAt: string;
}

interface LocalStlModel {
  filename: string;
  sizeBytes: number;
  modifiedAt: string;
  downloadUrl: string;
}

const LOCAL_STL_PATH = 'host /Users/Shared/KITTY/artifacts/stl (mounted to /app/storage/stl)';

const formatFileSize = (bytes: number) => {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
};

const Projects = () => {
  const [projects, setProjects] = useState<ProjectModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [localStl, setLocalStl] = useState<LocalStlModel[]>([]);
  const [localStlLoading, setLocalStlLoading] = useState(true);
  const [localStlError, setLocalStlError] = useState<string | null>(null);
  const [selectedStl, setSelectedStl] = useState<string>('');

  useEffect(() => {
    const loadProjects = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/projects');
        if (!response.ok) {
          // Handle cases where the endpoint doesn't exist or returns non-JSON
          if (response.status === 404 || response.status === 502) {
            throw new Error('Projects API is not available. This feature may not be implemented yet.');
          }
          throw new Error(`Failed to load projects (${response.status})`);
        }

        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('Projects API returned invalid response. API may not be configured correctly.');
        }

        const data = (await response.json()) as ProjectModel[];
        setProjects(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Projects load error:', err);
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    loadProjects();
  }, []);

  useEffect(() => {
    const loadLocalStl = async () => {
      setLocalStlLoading(true);
      setLocalStlError(null);
      try {
        const response = await fetch('/api/projects/stl');
        if (!response.ok) {
          throw new Error(`Failed to list STL artifacts (${response.status})`);
        }
        const data = (await response.json()) as LocalStlModel[];
        setLocalStl(Array.isArray(data) ? data : []);
        if (data?.length) {
          setSelectedStl(data[0].filename);
        }
      } catch (err) {
        console.error('Local STL load error:', err);
        setLocalStlError((err as Error).message);
      } finally {
        setLocalStlLoading(false);
      }
    };

    loadLocalStl();
  }, []);

  return (
    <section className="projects">
      {loading ? (
        <div className="loading-container">
          <div className="spinner" />
          <p>Loading projects...</p>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="card-header flex items-center justify-between">
            <h2 className="card-title">Conversation Projects</h2>
            <span className="badge badge-neutral">{projects.length} projects</span>
          </div>
          <div className="card-body">
            {error && (
              <div className="status-error" style={{ marginBottom: '1rem' }}>
                <strong>Error loading projects:</strong> {error}
                <div className="text-secondary" style={{ marginTop: '0.4rem' }}>
                  The projects API may be offline. You can still pull local STL files below.
                </div>
              </div>
            )}

            {!error && !projects.length && (
              <div className="text-center">
                <h3 className="mb-2">No Projects Yet</h3>
                <p className="text-secondary mb-3">
                  Projects are created automatically when you generate CAD artifacts or initiate workflows.
                </p>
                <p className="text-muted">
                  Visit the <strong>Fabrication Console</strong> to get started.
                </p>
              </div>
            )}

            {!error && projects.length > 0 && (
              <div className="grid grid-2" style={{ gap: '1rem' }}>
                {projects.map((project) => (
                  <article key={project.projectId} className="card" style={{ boxShadow: 'none', border: '1px solid var(--border-color)' }}>
                    <div className="card-header">
                      <div>
                        <h3 className="card-title">{project.title ?? project.projectId}</h3>
                        <p className="text-muted" style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                          {new Date(project.updatedAt).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <div className="card-body">
                      {project.summary && <p className="mb-3">{project.summary}</p>}

                      {project.artifacts.length > 0 && (
                        <>
                          <h4 style={{ fontSize: '1rem', marginBottom: '0.75rem', color: 'var(--text-primary)' }}>
                            Artifacts ({project.artifacts.length})
                          </h4>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {project.artifacts.map((artifact) => (
                              <div
                                key={`${project.projectId}-${artifact.location}`}
                                style={{
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center',
                                  padding: '0.5rem',
                                  background: 'var(--bg-secondary)',
                                  borderRadius: '6px'
                                }}
                              >
                                <div>
                                  <span className="badge badge-primary" style={{ marginRight: '0.5rem' }}>
                                    {artifact.provider}
                                  </span>
                                  <span className="text-secondary">{artifact.artifactType}</span>
                                </div>
                                <a
                                  href={artifact.location}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="btn-ghost"
                                  style={{ fontSize: '0.85rem', padding: '0.25rem 0.75rem' }}
                                >
                                  Download
                                </a>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div className="card">
        <div className="card-header flex items-center justify-between">
          <div>
            <h3 className="card-title">Local STL Library</h3>
            <p className="text-muted" style={{ marginTop: '0.25rem' }}>
              Listing files from {LOCAL_STL_PATH}
            </p>
          </div>
          <span className="badge badge-neutral">{localStl.length} files</span>
        </div>
        <div className="card-body">
          {localStlLoading && (
            <div className="loading-container" style={{ minHeight: '80px' }}>
              <div className="spinner" />
              <p>Scanning STL directory...</p>
            </div>
          )}

          {localStlError && (
            <div className="status-error">
              <strong>Could not read local STL files:</strong> {localStlError}
            </div>
          )}

          {!localStlLoading && !localStlError && !localStl.length && (
            <p className="text-muted">No STL files found in the local artifacts directory.</p>
          )}

          {!localStlLoading && !localStlError && localStl.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label htmlFor="stl-select" className="text-secondary" style={{ fontSize: '0.9rem' }}>
                Choose a model to download
              </label>
              <select
                id="stl-select"
                value={selectedStl}
                onChange={(e) => setSelectedStl(e.target.value)}
                style={{ padding: '0.5rem', borderRadius: '6px', border: '1px solid var(--border-color)' }}
              >
                {localStl.map((model) => (
                  <option key={model.filename} value={model.filename}>
                    {model.filename} · {formatFileSize(model.sizeBytes)} · {new Date(model.modifiedAt).toLocaleString()}
                  </option>
                ))}
              </select>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <a
                  className="btn"
                  href={selectedStl ? `/api/projects/stl/${selectedStl}` : undefined}
                  target="_blank"
                  rel="noreferrer"
                  style={{ pointerEvents: selectedStl ? 'auto' : 'none', opacity: selectedStl ? 1 : 0.6 }}
                >
                  Download STL
                </a>
                {selectedStl && (
                  <span className="text-secondary" style={{ fontSize: '0.9rem' }}>
                    {selectedStl}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default Projects;
