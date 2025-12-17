import { useState, useEffect, useCallback, useRef } from 'react';
import './SlicingPanel.css';

interface PrinterProfile {
  id: string;
  name: string;
  build_volume: [number, number, number];
  gcode_flavor: string;
}

interface MaterialProfile {
  id: string;
  name: string;
  type: string;
  nozzle_temp: number;
  bed_temp: number;
}

interface QualityProfile {
  id: string;
  name: string;
  layer_height: number;
  print_speed: number;
}

interface SlicingJobStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  result?: SlicingResult;
  error?: string;
}

interface SlicingResult {
  gcode_path: string;
  print_time_seconds: number;
  filament_used_mm: number;
  filament_used_grams: number;
}

interface SlicingPanelProps {
  inputPath: string; // 3MF file path from segmentation
  onSliceComplete?: (result: SlicingResult) => void;
  defaultPrinter?: string;
}

const SUPPORT_TYPES = [
  { value: 'tree', label: 'Tree Supports', description: 'Efficient, easy to remove' },
  { value: 'normal', label: 'Normal Supports', description: 'Standard grid supports' },
  { value: 'none', label: 'No Supports', description: 'Print without supports' },
];

const INFILL_PATTERNS = [
  { value: 'gyroid', label: 'Gyroid', description: 'Strong, flexible, fast' },
  { value: 'cubic', label: 'Cubic', description: 'Good all-around' },
  { value: 'grid', label: 'Grid', description: 'Fast, less material' },
  { value: 'honeycomb', label: 'Honeycomb', description: 'Strong, more material' },
];

export default function SlicingPanel({ inputPath, onSliceComplete, defaultPrinter }: SlicingPanelProps) {
  // Profile data
  const [printers, setPrinters] = useState<PrinterProfile[]>([]);
  const [materials, setMaterials] = useState<MaterialProfile[]>([]);
  const [qualities, setQualities] = useState<QualityProfile[]>([]);

  // Selected options
  const [selectedPrinter, setSelectedPrinter] = useState(defaultPrinter || '');
  const [selectedMaterial, setSelectedMaterial] = useState('pla_generic');
  const [selectedQuality, setSelectedQuality] = useState('normal');
  const [supportType, setSupportType] = useState('tree');
  const [infillPercent, setInfillPercent] = useState(20);
  const [infillPattern, setInfillPattern] = useState('gyroid');

  // Job state
  const [slicingJobId, setSlicingJobId] = useState<string | null>(null);
  const [slicingProgress, setSlicingProgress] = useState(0);
  const [slicingResult, setSlicingResult] = useState<SlicingResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Polling
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Load profiles on mount
  useEffect(() => {
    const loadProfiles = async () => {
      try {
        const [printersRes, materialsRes, qualitiesRes] = await Promise.all([
          fetch('/api/fabrication/slicer/profiles/printers'),
          fetch('/api/fabrication/slicer/profiles/materials'),
          fetch('/api/fabrication/slicer/profiles/quality'),
        ]);

        if (printersRes.ok) {
          const data = await printersRes.json();
          setPrinters(data);
          if (data.length > 0 && !selectedPrinter) {
            setSelectedPrinter(data[0].id);
          }
        }

        if (materialsRes.ok) {
          const data = await materialsRes.json();
          setMaterials(data);
        }

        if (qualitiesRes.ok) {
          const data = await qualitiesRes.json();
          setQualities(data);
        }
      } catch (err) {
        console.warn('Failed to load slicer profiles:', err);
      }
    };
    loadProfiles();
  }, [selectedPrinter]);

  // Set default printer when prop changes
  useEffect(() => {
    if (defaultPrinter) {
      setSelectedPrinter(defaultPrinter);
    }
  }, [defaultPrinter]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  // Poll job status
  const pollJobStatus = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`/api/fabrication/slicer/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error('Failed to get job status');
      }
      const status: SlicingJobStatus = await response.json();

      setSlicingProgress(status.progress * 100);

      if (status.status === 'completed' && status.result) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setSlicingResult(status.result);
        setLoading(false);
        setSlicingJobId(null);
        onSliceComplete?.(status.result);
      } else if (status.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setError(status.error || 'Slicing failed');
        setLoading(false);
        setSlicingJobId(null);
      }
    } catch (err) {
      console.error('Polling error:', err);
    }
  }, [onSliceComplete]);

  const handleSlice = useCallback(async () => {
    if (!inputPath || !selectedPrinter) {
      setError('Please select a printer and ensure a 3MF file is available');
      return;
    }

    setLoading(true);
    setError(null);
    setSlicingResult(null);
    setSlicingProgress(0);

    try {
      const requestBody = {
        input_path: inputPath,
        printer_id: selectedPrinter,
        material_id: selectedMaterial,
        quality: selectedQuality,
        support_type: supportType,
        infill_percent: infillPercent,
        infill_pattern: infillPattern,
      };

      const response = await fetch('/api/fabrication/slicer/slice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to start slicing');
      }

      const { job_id } = await response.json();
      setSlicingJobId(job_id);

      // Start polling
      pollingRef.current = setInterval(() => {
        pollJobStatus(job_id);
      }, 1000);

      // Initial poll
      pollJobStatus(job_id);

    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  }, [inputPath, selectedPrinter, selectedMaterial, selectedQuality, supportType, infillPercent, infillPattern, pollJobStatus]);

  const handleUploadToPrinter = useCallback(async () => {
    if (!slicingJobId && !slicingResult) {
      setError('No slicing result available');
      return;
    }

    try {
      // Get the job ID from the result path or use the stored job ID
      const jobId = slicingJobId || slicingResult?.gcode_path.split('/').slice(-2)[0];

      const response = await fetch(`/api/fabrication/slicer/jobs/${jobId}/upload`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ printer_id: selectedPrinter }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to upload to printer');
      }

      // Show success message
      setError(null);
      alert('G-code uploaded to printer successfully!');
    } catch (err) {
      setError((err as Error).message);
    }
  }, [slicingJobId, slicingResult, selectedPrinter]);

  const formatTime = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  const formatFilament = (grams: number): string => {
    return `${grams.toFixed(1)}g`;
  };

  const selectedPrinterInfo = printers.find(p => p.id === selectedPrinter);
  const selectedMaterialInfo = materials.find(m => m.id === selectedMaterial);
  const selectedQualityInfo = qualities.find(q => q.id === selectedQuality);

  return (
    <div className="slicing-panel">
      <div className="slicing-header">
        <h3>G-code Slicer</h3>
        <p className="text-muted">Convert 3MF to printable G-code</p>
      </div>

      {inputPath && (
        <div className="input-file-info">
          <span className="file-icon">📁</span>
          <span className="file-path">{inputPath.split('/').pop()}</span>
        </div>
      )}

      <div className="slicing-form">
        {/* Printer & Material Selection */}
        <div className="form-row two-col">
          <label>
            Target Printer
            <select value={selectedPrinter} onChange={(e) => setSelectedPrinter(e.target.value)}>
              <option value="">Select printer...</option>
              {printers.map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            Material
            <select value={selectedMaterial} onChange={(e) => setSelectedMaterial(e.target.value)}>
              {materials.map((material) => (
                <option key={material.id} value={material.id}>
                  {material.name} ({material.nozzle_temp}°C)
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Quality & Support Selection */}
        <div className="form-row two-col">
          <label>
            Print Quality
            <select value={selectedQuality} onChange={(e) => setSelectedQuality(e.target.value)}>
              {qualities.map((quality) => (
                <option key={quality.id} value={quality.id}>
                  {quality.name} ({quality.layer_height}mm)
                </option>
              ))}
            </select>
          </label>

          <label>
            Support Type
            <select value={supportType} onChange={(e) => setSupportType(e.target.value)}>
              {SUPPORT_TYPES.map((st) => (
                <option key={st.value} value={st.value}>
                  {st.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Infill Settings */}
        <div className="form-row two-col">
          <label>
            Infill Density
            <div className="slider-container">
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={infillPercent}
                onChange={(e) => setInfillPercent(parseInt(e.target.value, 10))}
              />
              <span className="slider-value">{infillPercent}%</span>
            </div>
          </label>

          <label>
            Infill Pattern
            <select value={infillPattern} onChange={(e) => setInfillPattern(e.target.value)}>
              {INFILL_PATTERNS.map((ip) => (
                <option key={ip.value} value={ip.value}>
                  {ip.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Settings Summary */}
        {selectedPrinterInfo && selectedMaterialInfo && selectedQualityInfo && (
          <div className="settings-summary">
            <div className="summary-item">
              <span className="summary-label">Printer:</span>
              <span className="summary-value">{selectedPrinterInfo.name}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Material:</span>
              <span className="summary-value">
                {selectedMaterialInfo.type} @ {selectedMaterialInfo.nozzle_temp}°C / {selectedMaterialInfo.bed_temp}°C
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Layer Height:</span>
              <span className="summary-value">{selectedQualityInfo.layer_height}mm</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Support:</span>
              <span className="summary-value">{SUPPORT_TYPES.find(s => s.value === supportType)?.label}</span>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="form-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleSlice}
            disabled={loading || !inputPath || !selectedPrinter}
          >
            {loading ? 'Slicing...' : 'Generate G-code'}
          </button>
        </div>

        {/* Progress Bar */}
        {loading && (
          <div className="slicing-progress">
            <div className="progress-header">
              <span>Slicing model...</span>
              <span className="progress-percent">{Math.round(slicingProgress)}%</span>
            </div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${slicingProgress}%` }}
              />
            </div>
            <p className="progress-hint">
              This may take several minutes depending on model complexity.
            </p>
          </div>
        )}
      </div>

      {error && <div className="status-error">{error}</div>}

      {/* Slicing Result */}
      {slicingResult && (
        <div className="slicing-result">
          <h4>Slicing Complete</h4>

          <div className="result-stats">
            <div className="stat-card">
              <span className="stat-icon">⏱️</span>
              <span className="stat-value">{formatTime(slicingResult.print_time_seconds)}</span>
              <span className="stat-label">Print Time</span>
            </div>
            <div className="stat-card">
              <span className="stat-icon">🧵</span>
              <span className="stat-value">{formatFilament(slicingResult.filament_used_grams)}</span>
              <span className="stat-label">Filament</span>
            </div>
            <div className="stat-card">
              <span className="stat-icon">📏</span>
              <span className="stat-value">{(slicingResult.filament_used_mm / 1000).toFixed(2)}m</span>
              <span className="stat-label">Length</span>
            </div>
          </div>

          <div className="result-actions">
            <a
              href={`/api/fabrication/slicer/jobs/${slicingResult.gcode_path.split('/').slice(-2)[0]}/download`}
              className="btn-secondary"
              download
            >
              Download G-code
            </a>
            <button
              type="button"
              className="btn-primary"
              onClick={handleUploadToPrinter}
            >
              Send to Printer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
