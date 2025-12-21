import { useState, useRef, useEffect, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import './Coding.css';

// Types
interface CodingProject {
  id: string;
  title: string;
  workingDir?: string;
  status: string;
  createdAt: string;
  metadata?: {
    gitRepo?: boolean;
    filesGenerated?: number;
  };
}

interface CodingState {
  sessionId: string;
  phase: 'idle' | 'planning' | 'coding' | 'testing' | 'running' | 'refining' | 'summarizing' | 'complete' | 'error';
  request: string;
  plan: string | null;
  code: string | null;
  testCode: string | null;
  testOutput: string | null;
  testsPassed: boolean | null;
  refinementCount: number;
  summary: string | null;
  error: string | null;
  streamingContent: string;
}

interface TerminalLine {
  id: string;
  type: 'input' | 'output' | 'phase' | 'error' | 'success';
  content: string;
  timestamp: Date;
}

const PHASE_LABELS: Record<string, string> = {
  idle: 'Ready',
  planning: 'Planning implementation...',
  coding: 'Generating code...',
  testing: 'Creating tests...',
  running: 'Running tests...',
  refining: 'Refining code...',
  summarizing: 'Generating summary...',
  complete: 'Complete',
  error: 'Error',
};

const PHASE_ICONS: Record<string, string> = {
  idle: '⚡',
  planning: '📋',
  coding: '💻',
  testing: '🧪',
  running: '▶️',
  refining: '🔧',
  summarizing: '📝',
  complete: '✅',
  error: '❌',
};

export default function Coding() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const projectId = searchParams.get('project');

  const [project, setProject] = useState<CodingProject | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);

  // Project selector state
  const [showProjectSelector, setShowProjectSelector] = useState(!projectId);
  const [existingProjects, setExistingProjects] = useState<CodingProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(false);
  const [newProjectTitle, setNewProjectTitle] = useState('');
  const [newProjectDir, setNewProjectDir] = useState('');
  const [createProjectError, setCreateProjectError] = useState<string | null>(null);

  // Quick-start session state (can save to project later)
  const [isQuickStartSession, setIsQuickStartSession] = useState(false);
  const [showSaveToProjectModal, setShowSaveToProjectModal] = useState(false);
  const [saveProjectTitle, setSaveProjectTitle] = useState('');
  const [saveProjectDir, setSaveProjectDir] = useState('');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [state, setState] = useState<CodingState>({
    sessionId: '',
    phase: 'idle',
    request: '',
    plan: null,
    code: null,
    testCode: null,
    testOutput: null,
    testsPassed: null,
    refinementCount: 0,
    summary: null,
    error: null,
    streamingContent: '',
  });

  const [inputValue, setInputValue] = useState('');
  const [terminalLines, setTerminalLines] = useState<TerminalLine[]>([
    {
      id: '0',
      type: 'output',
      content: 'kitty-code v0.1.0 - Local-first AI coding assistant',
      timestamp: new Date(),
    },
    {
      id: '1',
      type: 'output',
      content: 'Powered by Devstral 2 via llama.cpp',
      timestamp: new Date(),
    },
    {
      id: '2',
      type: 'output',
      content: 'Type a coding request and press Enter to begin...',
      timestamp: new Date(),
    },
  ]);
  const [showCodePanel, setShowCodePanel] = useState(true);
  const [showTestPanel, setShowTestPanel] = useState(true);

  const terminalRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Streaming buffer for chunky visualization (like kitty-code TUI)
  // Accumulates tokens and flushes to state at controlled intervals
  const streamBufferRef = useRef<string>('');
  const flushIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const STREAM_FLUSH_INTERVAL_MS = 80; // Flush every 80ms for smooth chunks
  const MIN_CHUNK_SIZE = 3; // Minimum characters before flushing

  // Flush accumulated stream buffer to state
  const flushStreamBuffer = useCallback(() => {
    if (streamBufferRef.current.length > 0) {
      const chunk = streamBufferRef.current;
      streamBufferRef.current = '';
      setState(prev => ({
        ...prev,
        streamingContent: prev.streamingContent + chunk,
      }));
    }
  }, []);

  // Start the flush interval when streaming begins
  const startStreamFlush = useCallback(() => {
    if (flushIntervalRef.current) return;
    flushIntervalRef.current = setInterval(() => {
      if (streamBufferRef.current.length >= MIN_CHUNK_SIZE) {
        flushStreamBuffer();
      }
    }, STREAM_FLUSH_INTERVAL_MS);
  }, [flushStreamBuffer]);

  // Stop the flush interval and flush remaining content
  const stopStreamFlush = useCallback(() => {
    if (flushIntervalRef.current) {
      clearInterval(flushIntervalRef.current);
      flushIntervalRef.current = null;
    }
    // Flush any remaining buffered content
    flushStreamBuffer();
  }, [flushStreamBuffer]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (flushIntervalRef.current) {
        clearInterval(flushIntervalRef.current);
      }
    };
  }, []);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalLines]);

  // Focus input on mount (if not showing project selector)
  useEffect(() => {
    if (!showProjectSelector) {
      inputRef.current?.focus();
    }
  }, [showProjectSelector]);

  // Fetch existing projects for selector
  useEffect(() => {
    if (!showProjectSelector) return;

    const fetchProjects = async () => {
      setProjectsLoading(true);
      try {
        const response = await fetch('/api/coding/projects?status=active&limit=10');
        if (response.ok) {
          const data = await response.json();
          setExistingProjects(data.projects || []);
        }
      } catch (error) {
        console.error('Failed to fetch projects:', error);
      } finally {
        setProjectsLoading(false);
      }
    };

    fetchProjects();
  }, [showProjectSelector]);

  // Create new project
  const handleCreateProject = async () => {
    if (!newProjectTitle.trim()) {
      setCreateProjectError('Please enter a project title');
      return;
    }

    setCreateProjectError(null);
    try {
      const response = await fetch('/api/coding/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: newProjectTitle.trim(),
          working_dir: newProjectDir.trim() || undefined,
          init_git: true,
        }),
      });

      if (response.ok) {
        const newProject = await response.json();
        navigate(`/coding?project=${newProject.id}`);
        setShowProjectSelector(false);
      } else {
        const error = await response.text();
        setCreateProjectError(error || 'Failed to create project');
      }
    } catch (error) {
      setCreateProjectError('Network error creating project');
    }
  };

  // Select existing project
  const handleSelectProject = (projectId: string) => {
    navigate(`/coding?project=${projectId}`);
    setShowProjectSelector(false);
  };

  // Continue without project (standalone session)
  const handleContinueWithoutProject = () => {
    setIsQuickStartSession(true);
    setShowProjectSelector(false);
  };

  // Save quick-start session to a new project
  const handleSaveToProject = async () => {
    if (!saveProjectTitle.trim()) {
      setSaveError('Please enter a project title');
      return;
    }

    setSaving(true);
    setSaveError(null);

    try {
      // Create the project
      const response = await fetch('/api/coding/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: saveProjectTitle.trim(),
          working_dir: saveProjectDir.trim() || undefined,
          init_git: true,
        }),
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(error || 'Failed to create project');
      }

      const newProject = await response.json();

      // If we have a session, attach it to the project
      if (state.sessionId) {
        await fetch(`/api/coding/projects/${newProject.id}/sessions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: state.sessionId }),
        });
      }

      // Navigate to the project
      setIsQuickStartSession(false);
      setShowSaveToProjectModal(false);
      navigate(`/coding?project=${newProject.id}`);
      setProject(newProject);

      // Add confirmation to terminal
      addTerminalLine('success', `Saved to project: ${newProject.title}`);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  // Fetch project details if project ID is present
  useEffect(() => {
    if (!projectId) return;

    const fetchProject = async () => {
      setProjectLoading(true);
      try {
        const response = await fetch(`/api/coding/projects/${projectId}`);
        if (response.ok) {
          const data = await response.json();
          setProject(data);
          // Add project info to terminal
          setTerminalLines(prev => [
            ...prev,
            {
              id: `project-${Date.now()}`,
              type: 'output',
              content: `Project: ${data.title}${data.workingDir ? ` (${data.workingDir})` : ''}`,
              timestamp: new Date(),
            },
          ]);
        }
      } catch (error) {
        console.error('Failed to fetch project:', error);
      } finally {
        setProjectLoading(false);
      }
    };

    fetchProject();
  }, [projectId]);

  // Add terminal line helper
  const addTerminalLine = useCallback((type: TerminalLine['type'], content: string) => {
    setTerminalLines(prev => [
      ...prev,
      {
        id: Date.now().toString(),
        type,
        content,
        timestamp: new Date(),
      },
    ]);
  }, []);

  // Handle SSE streaming
  const startCodingStream = useCallback(async (request: string) => {
    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setState(prev => ({
      ...prev,
      phase: 'planning',
      request,
      plan: null,
      code: null,
      testCode: null,
      testOutput: null,
      testsPassed: null,
      refinementCount: 0,
      summary: null,
      error: null,
      streamingContent: '',
    }));

    addTerminalLine('phase', `${PHASE_ICONS.planning} ${PHASE_LABELS.planning}`);

    try {
      // Use POST with fetch for SSE (EventSource only supports GET)
      const response = await fetch('/api/coding/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleStreamEvent(data);
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      setState(prev => ({ ...prev, phase: 'error', error: message }));
      addTerminalLine('error', `Error: ${message}`);

      // Fallback: Try direct API call without streaming
      addTerminalLine('output', 'Streaming unavailable. Trying non-streaming API...');
      try {
        const response = await fetch('/api/coding/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request }),
        });

        if (response.ok) {
          const result = await response.json();
          handleNonStreamingResult(result);
        }
      } catch {
        addTerminalLine('error', 'Backend unavailable. Make sure the coder-agent service is running.');
      }
    }
  }, [addTerminalLine]);

  // Handle individual stream events
  const handleStreamEvent = useCallback((event: any) => {
    switch (event.type) {
      case 'started':
        setState(prev => ({ ...prev, sessionId: event.sessionId || '' }));
        break;

      case 'plan_start':
        setState(prev => ({ ...prev, phase: 'planning', streamingContent: '' }));
        streamBufferRef.current = '';
        startStreamFlush();
        addTerminalLine('phase', `${PHASE_ICONS.planning} ${PHASE_LABELS.planning}`);
        break;

      case 'plan_chunk':
        // Buffer tokens for chunky visualization
        streamBufferRef.current += event.delta || '';
        break;

      case 'plan_complete':
        stopStreamFlush();
        setState(prev => ({
          ...prev,
          plan: event.plan || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Plan generated');
        break;

      case 'code_start':
        setState(prev => ({ ...prev, phase: 'coding', streamingContent: '' }));
        streamBufferRef.current = '';
        startStreamFlush();
        addTerminalLine('phase', `${PHASE_ICONS.coding} ${PHASE_LABELS.coding}`);
        break;

      case 'code_chunk':
        streamBufferRef.current += event.delta || '';
        break;

      case 'code_complete':
        stopStreamFlush();
        setState(prev => ({
          ...prev,
          code: event.code || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Code generated');
        break;

      case 'test_start':
        setState(prev => ({ ...prev, phase: 'testing', streamingContent: '' }));
        streamBufferRef.current = '';
        startStreamFlush();
        addTerminalLine('phase', `${PHASE_ICONS.testing} ${PHASE_LABELS.testing}`);
        break;

      case 'test_chunk':
        streamBufferRef.current += event.delta || '';
        break;

      case 'test_complete':
        stopStreamFlush();
        setState(prev => ({
          ...prev,
          testCode: event.testCode || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Tests generated');
        break;

      case 'run_start':
        setState(prev => ({ ...prev, phase: 'running' }));
        addTerminalLine('phase', `${PHASE_ICONS.running} ${PHASE_LABELS.running}`);
        break;

      case 'run_output':
        if (event.stdout) {
          addTerminalLine('output', event.stdout);
        }
        if (event.stderr) {
          addTerminalLine('error', event.stderr);
        }
        break;

      case 'run_complete':
        setState(prev => ({
          ...prev,
          testOutput: event.testOutput || '',
          testsPassed: event.testsPassed ?? null,
        }));
        if (event.testsPassed) {
          addTerminalLine('success', '✓ All tests passed!');
        } else {
          addTerminalLine('error', '✗ Tests failed');
        }
        break;

      case 'refine_start':
        setState(prev => ({
          ...prev,
          phase: 'refining',
          refinementCount: prev.refinementCount + 1,
          streamingContent: '',
        }));
        streamBufferRef.current = '';
        startStreamFlush();
        addTerminalLine('phase', `${PHASE_ICONS.refining} Refining code (iteration ${state.refinementCount + 1})...`);
        break;

      case 'refine_chunk':
        streamBufferRef.current += event.delta || '';
        break;

      case 'refine_complete':
        stopStreamFlush();
        setState(prev => ({
          ...prev,
          code: event.code || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Code refined');
        break;

      case 'summary_start':
        setState(prev => ({ ...prev, phase: 'summarizing', streamingContent: '' }));
        streamBufferRef.current = '';
        startStreamFlush();
        addTerminalLine('phase', `${PHASE_ICONS.summarizing} ${PHASE_LABELS.summarizing}`);
        break;

      case 'summary_chunk':
        streamBufferRef.current += event.delta || '';
        break;

      case 'summary_complete':
        stopStreamFlush();
        setState(prev => ({
          ...prev,
          summary: event.summary || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Summary complete');
        break;

      case 'complete':
        stopStreamFlush();
        setState(prev => ({ ...prev, phase: 'complete' }));
        addTerminalLine('success', `${PHASE_ICONS.complete} Code generation complete!`);
        break;

      case 'error':
        stopStreamFlush();
        setState(prev => ({ ...prev, phase: 'error', error: event.error || 'Unknown error' }));
        addTerminalLine('error', `Error: ${event.error || 'Unknown error'}`);
        break;
    }
  }, [addTerminalLine, state.refinementCount, startStreamFlush, stopStreamFlush]);

  // Handle non-streaming result (fallback)
  const handleNonStreamingResult = useCallback((result: any) => {
    setState(prev => ({
      ...prev,
      phase: result.success ? 'complete' : 'error',
      plan: result.plan || null,
      code: result.code || null,
      testCode: result.test_code || null,
      testOutput: result.test_output || null,
      testsPassed: result.tests_passed ?? null,
      refinementCount: result.refinement_count || 0,
      summary: result.summary || null,
      error: result.error || null,
    }));

    if (result.success) {
      addTerminalLine('success', `${PHASE_ICONS.complete} Code generation complete!`);
      if (result.tests_passed) {
        addTerminalLine('success', '✓ All tests passed!');
      }
    } else {
      addTerminalLine('error', `Error: ${result.error || 'Generation failed'}`);
    }
  }, [addTerminalLine]);

  // Handle input submission
  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed) return;

    addTerminalLine('input', `> ${trimmed}`);
    setInputValue('');
    startCodingStream(trimmed);
  }, [inputValue, addTerminalLine, startCodingStream]);

  // Copy code to clipboard
  const copyToClipboard = useCallback(async (text: string | null) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      addTerminalLine('success', 'Copied to clipboard');
    } catch {
      addTerminalLine('error', 'Failed to copy');
    }
  }, [addTerminalLine]);

  return (
    <div className="coding-page">
      {/* Project Selector Overlay */}
      {showProjectSelector && (
        <div className="project-selector-overlay">
          <div className="project-selector-modal">
            <h2 className="selector-title">Start Coding</h2>
            <p className="selector-subtitle">Choose how you want to begin</p>

            {/* Three-column option cards */}
            <div className="selector-options">
              {/* Quick Start */}
              <div className="selector-card quick-start-card">
                <div className="card-icon">⚡</div>
                <h3 className="card-title">Quick Start</h3>
                <p className="card-description">
                  Start coding immediately. You can save your work to a project later.
                </p>
                <button className="card-btn primary" onClick={handleContinueWithoutProject}>
                  Start Now
                </button>
              </div>

              {/* New Project */}
              <div className="selector-card new-project-card">
                <div className="card-icon">✨</div>
                <h3 className="card-title">New Project</h3>
                <div className="new-project-form">
                  <input
                    type="text"
                    className="project-input"
                    placeholder="Project title"
                    value={newProjectTitle}
                    onChange={(e) => setNewProjectTitle(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                  />
                  <input
                    type="text"
                    className="project-input"
                    placeholder="Working directory (optional)"
                    value={newProjectDir}
                    onChange={(e) => setNewProjectDir(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                  />
                  {createProjectError && (
                    <div className="project-error">{createProjectError}</div>
                  )}
                  <button className="card-btn" onClick={handleCreateProject}>
                    Create Project
                  </button>
                </div>
              </div>

              {/* Open Existing */}
              <div className="selector-card open-project-card">
                <div className="card-icon">📂</div>
                <h3 className="card-title">Open Project</h3>
                <div className="existing-projects-list">
                  {projectsLoading ? (
                    <div className="projects-loading">Loading...</div>
                  ) : existingProjects.length > 0 ? (
                    existingProjects.slice(0, 5).map((proj) => (
                      <button
                        key={proj.id}
                        className="project-item"
                        onClick={() => handleSelectProject(proj.id)}
                      >
                        <span className="project-item-icon">
                          {proj.metadata?.gitRepo ? '📁' : '📄'}
                        </span>
                        <div className="project-item-info">
                          <span className="project-item-title">{proj.title}</span>
                          {proj.workingDir && (
                            <span className="project-item-path">{proj.workingDir}</span>
                          )}
                        </div>
                      </button>
                    ))
                  ) : (
                    <div className="no-projects">
                      <span className="no-projects-icon">📭</span>
                      <span>No projects yet</span>
                    </div>
                  )}
                  {existingProjects.length > 5 && (
                    <button
                      className="view-all-btn"
                      onClick={() => navigate('/projects')}
                    >
                      View all projects →
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Save to Project Modal */}
      {showSaveToProjectModal && (
        <div className="project-selector-overlay">
          <div className="project-selector-modal save-modal">
            <h2 className="selector-title">Save to Project</h2>
            <p className="selector-subtitle">Create a new project to save your work</p>
            <div className="new-project-form">
              <input
                type="text"
                className="project-input"
                placeholder="Project title"
                value={saveProjectTitle}
                onChange={(e) => setSaveProjectTitle(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveToProject()}
                autoFocus
              />
              <input
                type="text"
                className="project-input"
                placeholder="Working directory (optional)"
                value={saveProjectDir}
                onChange={(e) => setSaveProjectDir(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveToProject()}
              />
              {saveError && (
                <div className="project-error">{saveError}</div>
              )}
              <div className="modal-actions">
                <button
                  className="cancel-btn"
                  onClick={() => setShowSaveToProjectModal(false)}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  className="card-btn primary"
                  onClick={handleSaveToProject}
                  disabled={saving}
                >
                  {saving ? 'Saving...' : 'Save Project'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Project Header (if project context present) */}
      {project && (
        <div className="project-header">
          <div className="project-info">
            <span className="project-icon">💻</span>
            <div className="project-details">
              <h2 className="project-title">{project.title}</h2>
              {project.workingDir && (
                <span className="project-path">{project.workingDir}</span>
              )}
            </div>
          </div>
          {project.metadata?.gitRepo && (
            <span className="git-badge">Git</span>
          )}
        </div>
      )}

      {/* Quick Start Header (no project, but can save) */}
      {isQuickStartSession && !project && !showProjectSelector && (
        <div className="project-header quick-start-header">
          <div className="project-info">
            <span className="project-icon">⚡</span>
            <div className="project-details">
              <h2 className="project-title">Quick Start Session</h2>
              <span className="project-path">No project tracking</span>
            </div>
          </div>
          <button
            className="save-project-btn"
            onClick={() => setShowSaveToProjectModal(true)}
          >
            Save to Project
          </button>
        </div>
      )}

      {/* Phase Indicator */}
      <div className="phase-indicator">
        {Object.entries(PHASE_LABELS).filter(([key]) => key !== 'idle' && key !== 'error').map(([phase, label]) => (
          <div
            key={phase}
            className={`phase-step ${state.phase === phase ? 'active' : ''} ${
              ['complete'].includes(state.phase) && phase !== 'complete' ? 'done' : ''
            }`}
          >
            <div className="phase-dot">{PHASE_ICONS[phase]}</div>
            <span className="phase-label">{label.replace('...', '')}</span>
          </div>
        ))}
      </div>

      {/* Main 3-Panel Layout */}
      <div className="coding-panels">
        {/* Left: Terminal */}
        <div className="terminal-panel">
          <div className="panel-header">
            <div className="terminal-dots">
              <span className="terminal-dot red"></span>
              <span className="terminal-dot yellow"></span>
              <span className="terminal-dot green"></span>
            </div>
            <span className="panel-title">Terminal</span>
            <span className="panel-status">{PHASE_ICONS[state.phase]} {PHASE_LABELS[state.phase]}</span>
          </div>

          <div className="terminal-output" ref={terminalRef}>
            {terminalLines.map((line) => (
              <div key={line.id} className={`terminal-line ${line.type}`}>
                {line.content}
              </div>
            ))}
            {state.streamingContent && (
              <div className="terminal-line output streaming">
                {state.streamingContent}
                <span className="cursor">▊</span>
              </div>
            )}
          </div>

          <form className="terminal-input-container" onSubmit={handleSubmit}>
            <span className="terminal-prompt">$</span>
            <input
              ref={inputRef}
              type="text"
              className="terminal-input"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Enter coding request..."
              disabled={state.phase !== 'idle' && state.phase !== 'complete' && state.phase !== 'error'}
            />
          </form>
        </div>

        {/* Center: Code Panel */}
        {showCodePanel && (
          <div className="code-panel">
            <div className="panel-header">
              <span className="panel-title">Generated Code</span>
              <div className="panel-actions">
                <button
                  className="panel-btn"
                  onClick={() => copyToClipboard(state.code)}
                  disabled={!state.code}
                  title="Copy code"
                >
                  📋
                </button>
                <button
                  className="panel-btn"
                  onClick={() => setShowCodePanel(false)}
                  title="Close panel"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="code-content">
              {state.code ? (
                <pre><code>{state.code}</code></pre>
              ) : state.phase === 'coding' && state.streamingContent ? (
                <pre><code>{state.streamingContent}<span className="cursor">▊</span></code></pre>
              ) : (
                <div className="code-placeholder">
                  Code will appear here...
                </div>
              )}
            </div>
          </div>
        )}

        {/* Right: Test Panel */}
        {showTestPanel && (
          <div className={`test-panel ${state.testsPassed === false ? 'failed' : ''} ${state.testsPassed === true ? 'passed' : ''}`}>
            <div className="panel-header">
              <span className="panel-title">Tests</span>
              {state.testsPassed !== null && (
                <span className={`test-status ${state.testsPassed ? 'pass' : 'fail'}`}>
                  {state.testsPassed ? '✓ Passed' : '✗ Failed'}
                </span>
              )}
              <div className="panel-actions">
                <button
                  className="panel-btn"
                  onClick={() => copyToClipboard(state.testCode)}
                  disabled={!state.testCode}
                  title="Copy tests"
                >
                  📋
                </button>
                <button
                  className="panel-btn"
                  onClick={() => setShowTestPanel(false)}
                  title="Close panel"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="test-content">
              {state.testCode ? (
                <>
                  <div className="test-code">
                    <pre><code>{state.testCode}</code></pre>
                  </div>
                  {state.testOutput && (
                    <div className="test-output">
                      <div className="test-output-header">Output:</div>
                      <pre>{state.testOutput}</pre>
                    </div>
                  )}
                </>
              ) : state.phase === 'testing' && state.streamingContent ? (
                <div className="test-code">
                  <pre><code>{state.streamingContent}<span className="cursor">▊</span></code></pre>
                </div>
              ) : (
                <div className="test-placeholder">
                  Tests will appear here...
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Panel Toggle Buttons */}
      {(!showCodePanel || !showTestPanel) && (
        <div className="panel-toggles">
          {!showCodePanel && (
            <button className="toggle-btn" onClick={() => setShowCodePanel(true)}>
              Show Code
            </button>
          )}
          {!showTestPanel && (
            <button className="toggle-btn" onClick={() => setShowTestPanel(true)}>
              Show Tests
            </button>
          )}
        </div>
      )}

      {/* Summary (shown during summarizing phase and after complete) */}
      {(state.summary || state.phase === 'summarizing') && (
        <div className="summary-panel">
          <div className="panel-header">
            <span className="panel-title">Summary</span>
            {state.phase === 'summarizing' && (
              <span className="panel-status streaming-indicator">Generating...</span>
            )}
            <button
              className="panel-btn"
              onClick={() => copyToClipboard(state.summary)}
              disabled={!state.summary}
              title="Copy summary"
            >
              📋
            </button>
          </div>
          <div className="summary-content">
            {state.summary ? (
              <pre>{state.summary}</pre>
            ) : state.phase === 'summarizing' && state.streamingContent ? (
              <pre>{state.streamingContent}<span className="cursor">▊</span></pre>
            ) : (
              <div className="summary-placeholder">Summary generating...</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
