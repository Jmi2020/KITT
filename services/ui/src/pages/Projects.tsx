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
      try {
        const response = await fetch('/api/projects');
        if (!response.ok) {
          throw new Error('Failed to load projects');
        }
        const data = (await response.json()) as ProjectModel[];
        setProjects(data);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return <p>Loading projects…</p>;
  }

  if (error) {
    return <p className="error">{error}</p>;
  }

  if (!projects.length) {
    return <p>No projects yet. Generate CAD or initiate a workflow to create one.</p>;
  }

  return (
    <section className="projects">
      <h2>Conversation Projects</h2>
      {projects.map((project) => (
        <article key={project.projectId} className="project-card">
          <header>
            <h3>{project.title ?? project.projectId}</h3>
            <span>{new Date(project.updatedAt).toLocaleString()}</span>
          </header>
          {project.summary && <p>{project.summary}</p>}
          <h4>Artifacts</h4>
          <ul>
            {project.artifacts.map((artifact) => (
              <li key={`${project.projectId}-${artifact.location}`}>
                <strong>{artifact.provider}</strong> ({artifact.artifactType}) —
                <a href={artifact.location} target="_blank" rel="noreferrer">
                  download
                </a>
              </li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
};

export default Projects;
