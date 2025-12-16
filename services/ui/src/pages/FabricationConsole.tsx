import { useEffect, useState, useCallback } from 'react';
import useKittyContext from '../hooks/useKittyContext';
import MeshSegmenter from '../components/MeshSegmenter';
import ThermalPanel from '../components/ThermalPanel';
import GcodeConsole from '../components/GcodeConsole';
import './FabricationConsole.css';

interface Artifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata: Record<string, string>;
}

// Artifact path translation (mirrors CLI ARTIFACTS_DIR logic)
const ARTIFACTS_BASE_URL = '/api/cad/artifacts';

const translateArtifactPath = (location: string): string => {
  // CAD service returns paths like "artifacts/stl/xyz.stl" or "artifacts/glb/xyz.glb"
  // Convert to API-accessible URL
  if (location.startsWith('artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('artifacts/', '')}`;
  }
  if (location.startsWith('storage/artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('storage/artifacts/', '')}`;
  }
  if (location.startsWith('/')) {
    // Absolute path - extract filename
    const filename = location.split('/').pop() || location;
    return `${ARTIFACTS_BASE_URL}/${filename}`;
  }
  return location;
};

interface CadResponse {
  conversationId: string;
  artifacts: Artifact[];
}

interface PrinterStatus {
  printer_id: string;
  is_online: boolean;
  is_printing: boolean;
  status: string;
  current_job: string | null;
  progress_percent: number | null;
  bed_temp: number | null;
  bed_target: number | null;
  extruder_temp: number | null;
  extruder_target: number | null;
}

const FabricationConsole = () => {
  const { context } = useKittyContext();
  const [cadPrompt, setCadPrompt] = useState('');
  const [conversationId, setConversationId] = useState(() => `ui-${Date.now()}`);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [cadLoading, setCadLoading] = useState(false);
  const [cadError, setCadError] = useState<string | null>(null);
  const [selectedArtifact, setSelectedArtifact] = useState<string>('');
  const [selectedPrinter, setSelectedPrinter] = useState<string>('');
  const [printStatus, setPrintStatus] = useState<string>('');

  // Printer status from REST API (replaces MQTT-based device filtering)
  const [printers, setPrinters] = useState<PrinterStatus[]>([]);
  const [printersLoading, setPrintersLoading] = useState(true);

  // Fetch printer status from fabrication service
  const fetchPrinters = useCallback(async () => {
    try {
      const response = await fetch('/api/fabrication/printer_status');
      if (response.ok) {
        const data = await response.json();
        setPrinters(Object.values(data.printers) as PrinterStatus[]);
      }
    } catch (err) {
      console.warn('Failed to fetch printers:', err);
    } finally {
      setPrintersLoading(false);
    }
  }, []);

  // Poll printer status - faster when Elegoo is selected for thermal responsiveness
  useEffect(() => {
    fetchPrinters();
    // Use 2s polling when Elegoo is selected (for thermal updates), 10s otherwise
    const pollInterval = selectedPrinter === 'elegoo_giga' ? 2000 : 10000;
    const interval = setInterval(fetchPrinters, pollInterval);
    return () => clearInterval(interval);
  }, [fetchPrinters, selectedPrinter]);

  // Auto-select first printer
  useEffect(() => {
    if (printers.length && !selectedPrinter) {
      setSelectedPrinter(printers[0].printer_id);
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
        body: JSON.stringify({ conversationId, prompt: cadPrompt, mode: 'organic' }),
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
  };

  return (
    <section className="fabrication-console">
      <header>
        <h2>Fabrication Console</h2>
        <button type="button" onClick={resetConversation}>
          New Session
        </button>
      </header>

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
              {artifacts.map((artifact) => {
                const glbLocation = artifact.metadata?.glb_location;
                const stlLocation = artifact.metadata?.stl_location;
                const primaryUrl = translateArtifactPath(artifact.location);
                const glbUrl = glbLocation ? translateArtifactPath(glbLocation) : null;
                const stlUrl = stlLocation ? translateArtifactPath(stlLocation) : null;

                return (
                  <li key={artifact.location} className="artifact-item">
                    <label>
                      <input
                        type="radio"
                        name="artifact"
                        value={artifact.location}
                        checked={selectedArtifact === artifact.location}
                        onChange={() => setSelectedArtifact(artifact.location)}
                      />
                      <span className="artifact-header">
                        {artifact.provider} ({artifact.artifactType})
                      </span>
                    </label>
                    <div className="artifact-formats">
                      {glbUrl && (
                        <a
                          href={glbUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="format-link glb"
                          title="Download GLB for 3D preview"
                        >
                          📦 GLB (preview)
                        </a>
                      )}
                      {stlUrl && (
                        <a
                          href={stlUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="format-link stl"
                          title="Download STL for slicer"
                        >
                          🖨️ STL (slicer)
                        </a>
                      )}
                      {!glbUrl && !stlUrl && (
                        <a
                          href={primaryUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="format-link"
                        >
                          📥 Download
                        </a>
                      )}
                    </div>
                    {artifact.metadata?.thumbnail && (
                      <div className="artifact-thumbnail">
                        <img
                          src={artifact.metadata.thumbnail}
                          alt="Model preview"
                          loading="lazy"
                        />
                      </div>
                    )}
                    {Object.keys(artifact.metadata).length > 0 && (
                      <details>
                        <summary>Metadata</summary>
                        <pre>{JSON.stringify(artifact.metadata, null, 2)}</pre>
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {/* Mesh Segmentation - for splitting oversized models */}
      <div className="panel">
        <MeshSegmenter
          artifactPath={selectedArtifact ? translateArtifactPath(selectedArtifact) : undefined}
        />
      </div>

      <div className="panel">
        <h3>Printer Selection</h3>
        {printers.length === 0 ? (
          printersLoading ? (
            <p>Loading printers...</p>
          ) : (
            <p>No printers configured. Check fabrication service connection.</p>
          )
        ) : (
          <label>
            Printer
            <select value={selectedPrinter} onChange={(event) => setSelectedPrinter(event.target.value)}>
              {printers.map((printer) => (
                <option key={printer.printer_id} value={printer.printer_id}>
                  {printer.printer_id} — {printer.is_online ? printer.status : 'offline'}
                  {printer.is_printing && printer.progress_percent !== null && ` (${printer.progress_percent}%)`}
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

      {/* Elegoo Giga Control Panel - shown when Elegoo is selected */}
      {selectedPrinter === 'elegoo_giga' && (() => {
        const elegooStatus = printers.find(p => p.printer_id === 'elegoo_giga');
        return (
          <div className="panel elegoo-control-panel">
            <h3>Elegoo Giga Control</h3>
            {elegooStatus?.is_online ? (
              <>
                <ThermalPanel
                  bedTemp={elegooStatus.bed_temp}
                  bedTarget={elegooStatus.bed_target}
                  nozzleTemp={elegooStatus.extruder_temp}
                  nozzleTarget={elegooStatus.extruder_target}
                  onRefresh={fetchPrinters}
                />
                <GcodeConsole printerId="elegoo_giga" />
              </>
            ) : (
              <p className="offline-message">
                Printer is offline. Check connection to 192.168.0.63.
              </p>
            )}
          </div>
        );
      })()}
    </section>
  );
};

export default FabricationConsole;
