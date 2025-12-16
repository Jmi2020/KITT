/**
 * Model Testing Tab - LLM Debugging Tool
 * Test prompts with different models and verbosity levels
 */

import { useEffect, useState } from 'react';
import './ModelTestingTab.css';

type LocalModelResponse = {
  local: string[];
  aliases: Record<string, string | null>;
  frontier?: string[];
};

interface QueryResponse {
  result: {
    output: string;
    verbosityLevel?: number;
  };
  routing?: Record<string, unknown> | null;
}

const VERBOSITY_OPTIONS = [
  { value: 1, label: '1 — extremely terse' },
  { value: 2, label: '2 — concise' },
  { value: 3, label: '3 — detailed (default)' },
  { value: 4, label: '4 — comprehensive' },
  { value: 5, label: '5 — exhaustive & nuanced' },
];

export default function ModelTestingTab() {
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [verbosity, setVerbosity] = useState<number>(3);
  const [conversationId] = useState(() => `ui-test-${Date.now()}`);
  const [llmPrompt, setLlmPrompt] = useState('');
  const [llmResponse, setLlmResponse] = useState<string>('');
  const [llmRouting, setLlmRouting] = useState<Record<string, unknown> | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [modelsLoading, setModelsLoading] = useState(true);

  // Load available models
  useEffect(() => {
    const loadModels = async () => {
      try {
        const response = await fetch('/api/routing/models');
        if (!response.ok) throw new Error('Failed to fetch model list');
        const data = (await response.json()) as LocalModelResponse;
        const list = data.local ?? [];
        setModels(list);
        if (list.length && !selectedModel) {
          setSelectedModel(list[0]);
        }
      } catch (error) {
        console.warn('Unable to load models', error);
      } finally {
        setModelsLoading(false);
      }
    };
    loadModels();
  }, [selectedModel]);

  const handleTestPrompt = async () => {
    if (!llmPrompt.trim()) {
      setLlmError('Enter a prompt to test the model.');
      return;
    }
    setLlmLoading(true);
    setLlmError(null);
    setLlmResponse('');
    setLlmRouting(null);
    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversationId,
          userId: 'ui-console',
          intent: 'chat.prompt',
          prompt: llmPrompt,
          verbosity,
          modelAlias: selectedModel || null,
        }),
      });
      if (!response.ok) throw new Error('Query failed');
      const data = (await response.json()) as QueryResponse;
      setLlmResponse(data.result?.output ?? '');
      setLlmRouting((data.routing as Record<string, unknown>) ?? null);
    } catch (error) {
      setLlmError((error as Error).message);
    } finally {
      setLlmLoading(false);
    }
  };

  const handleClear = () => {
    setLlmPrompt('');
    setLlmResponse('');
    setLlmRouting(null);
    setLlmError(null);
  };

  return (
    <div className="model-testing-tab">
      {/* Info Card */}
      <div className="testing-info-card">
        <h3>LLM Testing Console</h3>
        <p>
          Test how KITTY responds to prompts with different models and verbosity levels.
          Useful for debugging routing, response quality, and model behavior.
        </p>
      </div>

      {/* Settings Row */}
      <div className="testing-settings">
        <div className="setting-group">
          <label htmlFor="model-select">Local Model</label>
          <select
            id="model-select"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={modelsLoading}
          >
            {modelsLoading ? (
              <option>Loading models...</option>
            ) : models.length === 0 ? (
              <option>No models available</option>
            ) : (
              models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))
            )}
          </select>
        </div>

        <div className="setting-group">
          <label htmlFor="verbosity-select">Verbosity Level</label>
          <select
            id="verbosity-select"
            value={verbosity}
            onChange={(e) => setVerbosity(Number(e.target.value))}
          >
            {VERBOSITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Prompt Input */}
      <div className="testing-prompt">
        <label htmlFor="test-prompt">Test Prompt</label>
        <textarea
          id="test-prompt"
          rows={4}
          value={llmPrompt}
          onChange={(e) => setLlmPrompt(e.target.value)}
          placeholder="Enter a prompt to test how KITTY responds..."
        />
        <div className="prompt-actions">
          <button
            className="btn btn-primary"
            onClick={handleTestPrompt}
            disabled={llmLoading || !llmPrompt.trim()}
          >
            {llmLoading ? 'Running...' : 'Run Prompt'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleClear}
            disabled={llmLoading}
          >
            Clear
          </button>
        </div>
      </div>

      {/* Error Display */}
      {llmError && (
        <div className="testing-error">
          <span>{llmError}</span>
          <button onClick={() => setLlmError(null)}>×</button>
        </div>
      )}

      {/* Response Display */}
      {llmResponse && (
        <div className="testing-response">
          <div className="response-header">
            <h4>Response</h4>
            <span className="response-meta">
              Model: {selectedModel || 'default'} | Verbosity: {verbosity}
            </span>
          </div>
          <pre className="response-content">{llmResponse}</pre>

          {llmRouting && (
            <details className="routing-details">
              <summary>Routing Details</summary>
              <pre>{JSON.stringify(llmRouting, null, 2)}</pre>
            </details>
          )}
        </div>
      )}

      {/* Help Section */}
      <div className="testing-help">
        <h4>Verbosity Levels</h4>
        <ul>
          <li><strong>1</strong> — Extremely terse, minimal output</li>
          <li><strong>2</strong> — Concise, brief responses</li>
          <li><strong>3</strong> — Detailed (default), balanced responses</li>
          <li><strong>4</strong> — Comprehensive, thorough explanations</li>
          <li><strong>5</strong> — Exhaustive & nuanced, maximum detail</li>
        </ul>
      </div>
    </div>
  );
}
