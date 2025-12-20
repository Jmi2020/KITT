import { useState, useRef, useEffect, useCallback } from 'react';
import './Coding.css';

// Types
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
      content: 'Powered by Devstral 2 via Ollama',
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

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [terminalLines]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

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
        setState(prev => ({ ...prev, phase: 'planning' }));
        addTerminalLine('phase', `${PHASE_ICONS.planning} ${PHASE_LABELS.planning}`);
        break;

      case 'plan_chunk':
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + (event.delta || ''),
        }));
        break;

      case 'plan_complete':
        setState(prev => ({
          ...prev,
          plan: event.plan || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Plan generated');
        break;

      case 'code_start':
        setState(prev => ({ ...prev, phase: 'coding', streamingContent: '' }));
        addTerminalLine('phase', `${PHASE_ICONS.coding} ${PHASE_LABELS.coding}`);
        break;

      case 'code_chunk':
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + (event.delta || ''),
        }));
        break;

      case 'code_complete':
        setState(prev => ({
          ...prev,
          code: event.code || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Code generated');
        break;

      case 'test_start':
        setState(prev => ({ ...prev, phase: 'testing', streamingContent: '' }));
        addTerminalLine('phase', `${PHASE_ICONS.testing} ${PHASE_LABELS.testing}`);
        break;

      case 'test_chunk':
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + (event.delta || ''),
        }));
        break;

      case 'test_complete':
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
        addTerminalLine('phase', `${PHASE_ICONS.refining} Refining code (iteration ${state.refinementCount + 1})...`);
        break;

      case 'refine_chunk':
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + (event.delta || ''),
        }));
        break;

      case 'refine_complete':
        setState(prev => ({
          ...prev,
          code: event.code || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Code refined');
        break;

      case 'summary_start':
        setState(prev => ({ ...prev, phase: 'summarizing', streamingContent: '' }));
        addTerminalLine('phase', `${PHASE_ICONS.summarizing} ${PHASE_LABELS.summarizing}`);
        break;

      case 'summary_chunk':
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + (event.delta || ''),
        }));
        break;

      case 'summary_complete':
        setState(prev => ({
          ...prev,
          summary: event.summary || prev.streamingContent,
          streamingContent: '',
        }));
        addTerminalLine('success', 'Summary complete');
        break;

      case 'complete':
        setState(prev => ({ ...prev, phase: 'complete' }));
        addTerminalLine('success', `${PHASE_ICONS.complete} Code generation complete!`);
        break;

      case 'error':
        setState(prev => ({ ...prev, phase: 'error', error: event.error || 'Unknown error' }));
        addTerminalLine('error', `Error: ${event.error || 'Unknown error'}`);
        break;
    }
  }, [addTerminalLine, state.refinementCount]);

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

      {/* Summary (shown at bottom when complete) */}
      {state.summary && (
        <div className="summary-panel">
          <div className="panel-header">
            <span className="panel-title">Summary</span>
            <button
              className="panel-btn"
              onClick={() => copyToClipboard(state.summary)}
              title="Copy summary"
            >
              📋
            </button>
          </div>
          <div className="summary-content">
            <pre>{state.summary}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
