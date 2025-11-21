import { useEffect, useMemo, useState } from 'react';
import useKittyContext from '../hooks/useKittyContext';
import './FabricationConsole.css';

type LocalModelResponse = {
  local: string[];
  aliases: Record<string, string | null>;
  frontier?: string[];
};

interface Artifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata: Record<string, string>;
}

interface CadResponse {
  conversationId: string;
  artifacts: Artifact[];
}

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

const FabricationConsole = () => {
  const { context } = useKittyContext();
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [verbosity, setVerbosity] = useState<number>(3);
  const [cadPrompt, setCadPrompt] = useState('');
  const [conversationId, setConversationId] = useState(() => `ui-${Date.now()}`);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [cadLoading, setCadLoading] = useState(false);
  const [cadError, setCadError] = useState<string | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<string>('');
  const [selectedPrinter, setSelectedPrinter] = useState<string>('');
  const [llmPrompt, setLlmPrompt] = useState('');
  const [llmResponse, setLlmResponse] = useState<string>('');
  const [llmRouting, setLlmRouting] = useState<Record<string, unknown> | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [printStatus, setPrintStatus] = useState<string>('');

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
      }
    };
    loadModels();
  }, [selectedModel]);

  const printers = useMemo(() => {
    return Object.values(context.devices).filter((device) => {
      const meta = device.payload || {};
      const category = typeof meta.category === 'string' ? meta.category.toLowerCase() : '';
      const type = typeof meta.type === 'string' ? meta.type.toLowerCase() : '';
      return category === 'printer' || type === 'printer' || device.deviceId.toLowerCase().includes('print');
    });
  }, [context.devices]);

  useEffect(() => {
    if (printers.length && !selectedPrinter) {
      setSelectedPrinter(printers[0].deviceId);
    }
  }, [printers, selectedPrinter]);

  const handleGenerateCad = async () => {
    if (!cadPrompt.trim()) {
      setCadError('Enter a CAD prompt first.');
      return;
    }
    setCadLoading(true);
    setCadError(null);
    setArtifacts([]);
    try {
      const response = await fetch('/api/cad/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversationId, prompt: cadPrompt }),
      });
      if (!response.ok) throw new Error('CAD generation failed');
      const data = (await response.json()) as CadResponse;
      setArtifacts(data.artifacts);
      if (data.artifacts.length) {
        setSelectedArtifact(data.artifacts[0].location);
      }
    } catch (error) {
      setCadError((error as Error).message);
    } finally {
      setCadLoading(false);
    }
  };

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

  const handleSendToPrinter = async () => {
    if (!selectedArtifact) {
      setPrintStatus('Select an artifact first.');
      return;
    }
    if (!selectedPrinter) {
      setPrintStatus('Select a printer.');
      return;
    }
    setPrintStatus('Sending job to printer…');
    try {
      const response = await fetch(`/api/device/${encodeURIComponent(selectedPrinter)}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          intent: 'start_print',
          payload: {
            jobId: `job-${Date.now()}`,
            gcodePath: selectedArtifact,
          },
        }),
      });
      if (!response.ok) throw new Error('Printer command failed');
      setPrintStatus('Print job queued successfully.');
    } catch (error) {
      setPrintStatus((error as Error).message);
    }
  };

  const resetConversation = () => {
    const nextId = `ui-${Date.now()}`;
    setConversationId(nextId);
    setArtifacts([]);
    setSelectedArtifact('');
    setLlmResponse('');
    setLlmRouting(null);
  };

  const copyCommand = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      alert('Command copied to clipboard');
    } catch (error) {
      console.warn('Clipboard copy failed, showing prompt instead.');
      window.prompt('Copy command', command);
    }
  };

  const serviceControls = [
    {
      name: 'Ollama (GPT-OSS)',
      start: 'ops/scripts/ollama/start.sh',
      stop: 'ops/scripts/ollama/stop.sh',
      restart: 'ops/scripts/ollama/stop.sh && ops/scripts/ollama/start.sh',
      description: 'Primary reasoning + judge stack (GPT-OSS via Ollama).',
    },
    {
      name: 'llama.cpp (Legacy)',
      start: 'ops/scripts/llama/start.sh',
      stop: 'ops/scripts/llama/stop.sh',
      restart: 'ops/scripts/llama/stop.sh && ops/scripts/llama/start.sh',
      description: 'Fallback local inference stack.',
    },
    {
      name: 'Docker Compose (Core Stack)',
      start: 'ops/scripts/start-all.sh',
      stop: 'ops/scripts/stop-all.sh',
      restart: 'ops/scripts/stop-all.sh && ops/scripts/start-all.sh',
      description: 'Gateway/brain/api services.',
    },
    {
      name: 'Images Service',
      start: 'ops/scripts/start-images-service.sh',
      stop: 'ops/scripts/stop-images-service.sh',
      restart: 'ops/scripts/stop-images-service.sh && ops/scripts/start-images-service.sh',
      description: 'Stable Diffusion/image generation backend.',
    },
  ];

  return (
    <section className="fabrication-console">
      <header>
        <h2>Fabrication Console</h2>
        <button type="button" onClick={resetConversation}>
          New Session
        </button>
      </header>

      <div className="panel grid service-grid">
        <div>
          <h3>Runtime Controls</h3>
          <p className="text-muted">Start/stop/restart individual stacks quickly.</p>
        </div>
        <div className="service-list">
          {serviceControls.map((svc) => (
            <div key={svc.name} className="service-card">
              <div className="service-card-header">
                <strong>{svc.name}</strong>
              </div>
              <p className="text-muted">{svc.description}</p>
              <div className="service-actions">
                <button type="button" onClick={() => copyCommand(svc.start)}>Start</button>
                <button type="button" onClick={() => copyCommand(svc.stop)}>Stop</button>
                <button type="button" onClick={() => copyCommand(svc.restart)}>Restart</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Model & Verbosity</h3>
        <label>
          Verbosity Level
          <select value={verbosity} onChange={(event) => setVerbosity(Number(event.target.value))}>
            {VERBOSITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Local Model
          <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="panel">
        <h3>Test Prompt</h3>
        <textarea
          rows={4}
          value={llmPrompt}
          onChange={(event) => setLlmPrompt(event.target.value)}
          placeholder="Ask KITTY something to gauge verbosity and model output."
        />
        <button type="button" onClick={handleTestPrompt} disabled={llmLoading}>
          {llmLoading ? 'Running…' : 'Run Prompt'}
        </button>
        {llmError && <p className="error">{llmError}</p>}
        {llmResponse && (
          <div className="llm-output">
            <h4>Response</h4>
            <pre>{llmResponse}</pre>
            {llmRouting && (
              <details>
                <summary>Routing Details</summary>
                <pre>{JSON.stringify(llmRouting, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
      </div>

      <div className="panel">
        <h3>CAD Generation</h3>
        <textarea
          rows={4}
          value={cadPrompt}
          onChange={(event) => setCadPrompt(event.target.value)}
          placeholder="Describe the part to generate (e.g., 2U faceplate with cable passthrough)."
        />
        <button type="button" onClick={handleGenerateCad} disabled={cadLoading}>
          {cadLoading ? 'Generating…' : 'Generate Preview'}
        </button>
        {cadError && <p className="error">{cadError}</p>}
        {artifacts.length > 0 && (
          <div className="artifact-list">
            <h4>Artifacts</h4>
            <ul>
              {artifacts.map((artifact) => (
                <li key={artifact.location}>
                  <label>
                    <input
                      type="radio"
                      name="artifact"
                      value={artifact.location}
                      checked={selectedArtifact === artifact.location}
                      onChange={() => setSelectedArtifact(artifact.location)}
                    />
                    <span>
                      {artifact.provider} ({artifact.artifactType}) —
                      <a href={artifact.location} target="_blank" rel="noreferrer">
                        view/download
                      </a>
                    </span>
                  </label>
                  {Object.keys(artifact.metadata).length > 0 && (
                    <details>
                      <summary>Metadata</summary>
                      <pre>{JSON.stringify(artifact.metadata, null, 2)}</pre>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="panel">
        <h3>Printer Selection</h3>
        {printers.length === 0 ? (
          <p>
            No printers online. Ensure devices publish to{' '}
            <code>kitty/devices/&lt;printer&gt;/state</code>.
          </p>
        ) : (
          <label>
            Printer
            <select value={selectedPrinter} onChange={(event) => setSelectedPrinter(event.target.value)}>
              {printers.map((printer) => (
                <option key={printer.deviceId} value={printer.deviceId}>
                  {printer.deviceId} — {printer.status}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="button" onClick={handleSendToPrinter} disabled={!selectedArtifact || !selectedPrinter}>
          Queue Print
        </button>
        {printStatus && <p>{printStatus}</p>}
      </div>
    </section>
  );
};

export default FabricationConsole;
