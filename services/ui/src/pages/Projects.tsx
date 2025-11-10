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

const Projects = () => {
  const [projects, setProjects] = useState<ProjectModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
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
    load();
  }, []);

  if (loading) {
    return (
      <section className="projects">
        <div className="loading-container">
          <div className="spinner" />
          <p>Loading projects...</p>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="projects">
        <div className="card">
          <div className="card-header">
            <h2 className="card-title">Projects</h2>
          </div>
          <div className="status-error">
            <strong>Error loading projects:</strong> {error}
          </div>
          <p className="mt-3 text-secondary">
            The projects API endpoint may not be configured yet. Try accessing the Fabrication Console to generate CAD artifacts instead.
          </p>
        </div>
      </section>
    );
  }

  if (!projects.length) {
    return (
      <section className="projects">
        <div className="card text-center">
          <div className="card-body">
            <h2 className="mb-2">No Projects Yet</h2>
            <p className="text-secondary mb-4">
              Projects are created automatically when you generate CAD artifacts or initiate workflows.
            </p>
            <p className="text-muted">
              Visit the <strong>Fabrication Console</strong> to get started.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="projects">
      <div className="flex items-center justify-between mb-4">
        <h2>Conversation Projects</h2>
        <span className="badge badge-neutral">{projects.length} projects</span>
      </div>
      <div className="grid grid-2">
        {projects.map((project) => (
          <article key={project.projectId} className="card">
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
                    {project.artifacts.map((artifact, idx) => (
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
                        <a href={artifact.location} target="_blank" rel="noreferrer" className="btn-ghost" style={{ fontSize: '0.85rem', padding: '0.25rem 0.75rem' }}>
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
    </section>
  );
};

export default Projects;
