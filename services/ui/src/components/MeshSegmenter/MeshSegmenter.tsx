import { useState, useEffect, useCallback, useRef } from 'react';
import './MeshSegmenter.css';
import SlicingPanel from '../SlicingPanel';

interface Printer {
  printer_id: string;
  name: string;
  build_volume_mm: [number, number, number];
  model: string;
}

interface CheckResult {
  needs_segmentation: boolean;
  model_dimensions_mm: [number, number, number];
  build_volume_mm: [number, number, number];
  exceeds_by_mm: [number, number, number];
  recommended_cuts: number;
}

interface SegmentPart {
  index: number;
  name: string;
  dimensions_mm: [number, number, number];
  volume_cm3: number;
  file_path: string;
  minio_uri: string;
  requires_supports: boolean;
}

interface SegmentResult {
  success: boolean;
  needs_segmentation: boolean;
  num_parts: number;
  parts: SegmentPart[];
  combined_3mf_path: string;
  combined_3mf_uri: string;
  hardware_required: Record<string, unknown>;
  assembly_notes: string;
  error?: string;
}

interface SegmentJobStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  result?: SegmentResult;
  error?: string;
}

interface MeshSegmenterProps {
  artifactPath?: string;
  onSegmentComplete?: (result: SegmentResult) => void;
}

const JOINT_TYPES = [
  { value: 'integrated', label: 'Integrated Pins', description: 'Printed pins & holes (no hardware)' },
  { value: 'dowel', label: 'Dowel Holes', description: 'Holes for external dowel pins' },
  { value: 'dovetail', label: 'Dovetail', description: 'Interlocking joints (coming soon)' },
  { value: 'pyramid', label: 'Pyramid', description: 'Self-centering cones (coming soon)' },
  { value: 'none', label: 'None', description: 'No joints - manual alignment' },
];

const QUALITY_PRESETS = [
  { value: 'fast', label: 'Fast', resolution: 200, description: 'Quick preview (~10s)' },
  { value: 'medium', label: 'Medium', resolution: 500, description: 'Balanced (~30s)' },
  { value: 'high', label: 'High', resolution: 1000, description: 'Best quality (~1-2min)' },
];

export default function MeshSegmenter({ artifactPath, onSegmentComplete }: MeshSegmenterProps) {
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [selectedPrinter, setSelectedPrinter] = useState<string>('');
  const [filePath, setFilePath] = useState(artifactPath || '');
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [segmentResult, setSegmentResult] = useState<SegmentResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Config options
  const [enableHollowing, setEnableHollowing] = useState(true);
  const [wallThickness, setWallThickness] = useState(10.0);
  const [jointType, setJointType] = useState('integrated');
  const [maxParts, setMaxParts] = useState(0); // 0 = auto-calculate
  const [quality, setQuality] = useState<'fast' | 'medium' | 'high'>('high');

  // Custom build volume
  const [customBuildX, setCustomBuildX] = useState(300);
  const [customBuildY, setCustomBuildY] = useState(300);
  const [customBuildZ, setCustomBuildZ] = useState(400);

  // File upload state
  const [inputMode, setInputMode] = useState<'upload' | 'path'>('upload');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Segmentation job state
  const [segmentJobId, setSegmentJobId] = useState<string | null>(null);
  const [segmentProgress, setSegmentProgress] = useState<number>(0);
  const [completedJobId, setCompletedJobId] = useState<string | null>(null);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Load available printers
  useEffect(() => {
    const loadPrinters = async () => {
      try {
        const response = await fetch('/api/fabrication/segmentation/printers');
        if (response.ok) {
          const data = await response.json();
          setPrinters(data);
          if (data.length > 0 && !selectedPrinter) {
            setSelectedPrinter(data[0].printer_id);
          }
        }
      } catch (err) {
        console.warn('Failed to load printers:', err);
      }
    };
    loadPrinters();
  }, [selectedPrinter]);

  // Update file path when artifactPath prop changes
  useEffect(() => {
    if (artifactPath) {
      setFilePath(artifactPath);
      setCheckResult(null);
      setSegmentResult(null);
    }
  }, [artifactPath]);

  // File upload handler with XMLHttpRequest for progress tracking
  const handleFileUpload = useCallback((file: File) => {
    if (!file) return;

    // Validate file type
    const validExtensions = ['.3mf', '.stl'];
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    if (!validExtensions.includes(ext)) {
      setError('Invalid file type. Only .3mf and .stl files are accepted.');
      return;
    }

    // Validate file size (100MB limit)
    const maxSize = 100 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('File too large. Maximum size is 100MB.');
      return;
    }

    setError(null);
    setUploadProgress(0);
    setCheckResult(null);
    setSegmentResult(null);

    const formData = new FormData();
    formData.append('file', file);

    // Use XMLHttpRequest for upload progress
    const xhr = new XMLHttpRequest();

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
      }
    };

    xhr.onload = () => {
      setUploadProgress(null);

      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          setFilePath(response.container_path);
          setUploadedFileName(response.filename);
        } catch {
          setError('Failed to parse upload response');
        }
      } else {
        try {
          const errData = JSON.parse(xhr.responseText);
          setError(errData.detail || 'Upload failed');
        } catch {
          setError(`Upload failed (${xhr.status})`);
        }
      }
    };

    xhr.onerror = () => {
      setUploadProgress(null);
      setError('Upload failed - network error');
    };

    xhr.open('POST', '/api/fabrication/segmentation/upload');
    xhr.send(formData);
  }, []);

  // Handle file input change
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  }, [handleFileUpload]);

  // Handle drag-and-drop
  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileUpload(file);
    }
  }, [handleFileUpload]);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const clearUpload = useCallback(() => {
    setFilePath('');
    setUploadedFileName(null);
    setCheckResult(null);
    setSegmentResult(null);
    setCompletedJobId(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const handleCheck = useCallback(async () => {
    if (!filePath.trim()) {
      setError('Please enter a file path');
      return;
    }

    setChecking(true);
    setError(null);
    setCheckResult(null);

    try {
      const requestBody: Record<string, unknown> = {
        stl_path: filePath,
      };

      if (selectedPrinter === 'custom') {
        requestBody.custom_build_volume = [customBuildX, customBuildY, customBuildZ];
      } else if (selectedPrinter) {
        requestBody.printer_id = selectedPrinter;
      }

      const response = await fetch('/api/fabrication/segmentation/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Check failed');
      }

      const data = await response.json();
      setCheckResult(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setChecking(false);
    }
  }, [filePath, selectedPrinter, customBuildX, customBuildY, customBuildZ]);

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
      const response = await fetch(`/api/fabrication/segmentation/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error('Failed to get job status');
      }
      const status: SegmentJobStatus = await response.json();

      setSegmentProgress(status.progress * 100);

      if (status.status === 'completed' && status.result) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setSegmentResult(status.result);
        setLoading(false);
        setCompletedJobId(jobId);  // Preserve job ID for ZIP download
        setSegmentJobId(null);
        onSegmentComplete?.(status.result);
      } else if (status.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setError(status.error || 'Segmentation failed');
        setLoading(false);
        setSegmentJobId(null);
      }
    } catch (err) {
      console.error('Polling error:', err);
    }
  }, [onSegmentComplete]);

  const handleSegment = useCallback(async () => {
    if (!filePath.trim()) {
      setError('Please enter a file path');
      return;
    }

    setLoading(true);
    setError(null);
    setSegmentResult(null);
    setSegmentProgress(0);
    setCompletedJobId(null);

    try {
      const hollowingResolution = QUALITY_PRESETS.find(q => q.value === quality)?.resolution || 1000;

      const requestBody: Record<string, unknown> = {
        stl_path: filePath,
        enable_hollowing: enableHollowing,
        wall_thickness_mm: wallThickness,
        joint_type: jointType,
        max_parts: maxParts,
        hollowing_resolution: hollowingResolution,
      };

      if (selectedPrinter === 'custom') {
        requestBody.custom_build_volume = [customBuildX, customBuildY, customBuildZ];
      } else if (selectedPrinter) {
        requestBody.printer_id = selectedPrinter;
      }

      // Use async endpoint for progress tracking
      const response = await fetch('/api/fabrication/segmentation/segment/async', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to start segmentation');
      }

      const { job_id } = await response.json();
      setSegmentJobId(job_id);

      // Start polling for status
      pollingRef.current = setInterval(() => {
        pollJobStatus(job_id);
      }, 1000);

      // Initial poll
      pollJobStatus(job_id);

    } catch (err) {
      setError((err as Error).message);
      setLoading(false);
    }
  }, [filePath, selectedPrinter, customBuildX, customBuildY, customBuildZ, enableHollowing, wallThickness, jointType, maxParts, quality, pollJobStatus]);

  const formatDimensions = (dims: [number, number, number]) => {
    return `${dims[0].toFixed(1)} x ${dims[1].toFixed(1)} x ${dims[2].toFixed(1)} mm`;
  };

  const formatTupleDimensions = (dims: [number, number, number]) => {
    return `${dims[0].toFixed(0)} x ${dims[1].toFixed(0)} x ${dims[2].toFixed(0)} mm`;
  };

  // Check if any dimension exceeds build volume
  const dimensionExceeds = (dims: [number, number, number], buildVol: [number, number, number]) => ({
    x: dims[0] > buildVol[0],
    y: dims[1] > buildVol[1],
    z: dims[2] > buildVol[2],
  });

  return (
    <div className="mesh-segmenter">
      <div className="segmenter-header">
        <h3>Mesh Segmenter</h3>
        <p className="text-muted">Split large models for multi-part printing</p>
      </div>

      <div className="segmenter-form">
        {/* Input Mode Toggle */}
        <div className="input-mode-toggle">
          <button
            type="button"
            className={`toggle-btn ${inputMode === 'upload' ? 'active' : ''}`}
            onClick={() => setInputMode('upload')}
          >
            Upload File
          </button>
          <button
            type="button"
            className={`toggle-btn ${inputMode === 'path' ? 'active' : ''}`}
            onClick={() => setInputMode('path')}
          >
            Enter Path
          </button>
        </div>

        {inputMode === 'upload' ? (
          <div
            className="file-upload-zone"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".3mf,.stl"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />

            {uploadProgress !== null ? (
              <div className="upload-progress">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <span className="progress-text">{uploadProgress}%</span>
              </div>
            ) : uploadedFileName ? (
              <div className="uploaded-file">
                <span className="file-icon">📁</span>
                <span className="file-name">{uploadedFileName}</span>
                <button
                  type="button"
                  className="btn-clear"
                  onClick={(e) => {
                    e.stopPropagation();
                    clearUpload();
                  }}
                >
                  Clear
                </button>
              </div>
            ) : (
              <div className="upload-placeholder">
                <span className="upload-icon">📤</span>
                <span className="upload-text">
                  Drop 3MF or STL file here, or click to browse
                </span>
                <span className="upload-hint">Max file size: 100MB</span>
              </div>
            )}
          </div>
        ) : (
          <div className="form-row">
            <label>
              STL/3MF File Path
              <input
                type="text"
                value={filePath}
                onChange={(e) => setFilePath(e.target.value)}
                placeholder="/app/artifacts/3mf/model.3mf"
              />
            </label>
          </div>
        )}

        <div className="form-row two-col">
          <label>
            Target Printer
            <select value={selectedPrinter} onChange={(e) => setSelectedPrinter(e.target.value)}>
              <option value="">Auto-detect</option>
              {printers.map((printer) => (
                <option key={printer.printer_id} value={printer.printer_id}>
                  {printer.name} ({formatTupleDimensions(printer.build_volume_mm)})
                </option>
              ))}
              <option value="custom">Custom Dimensions...</option>
            </select>
          </label>

          <label>
            Joint Type
            <select value={jointType} onChange={(e) => setJointType(e.target.value)}>
              {JOINT_TYPES.map((jt) => (
                <option key={jt.value} value={jt.value}>
                  {jt.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {selectedPrinter === 'custom' && (
          <div className="form-row three-col custom-dimensions">
            <label>
              Build X (mm)
              <input
                type="number"
                value={customBuildX}
                onChange={(e) => setCustomBuildX(parseInt(e.target.value, 10) || 0)}
                min={50}
                max={2000}
                step={10}
              />
            </label>
            <label>
              Build Y (mm)
              <input
                type="number"
                value={customBuildY}
                onChange={(e) => setCustomBuildY(parseInt(e.target.value, 10) || 0)}
                min={50}
                max={2000}
                step={10}
              />
            </label>
            <label>
              Build Z (mm)
              <input
                type="number"
                value={customBuildZ}
                onChange={(e) => setCustomBuildZ(parseInt(e.target.value, 10) || 0)}
                min={50}
                max={2000}
                step={10}
              />
            </label>
          </div>
        )}

        <div className="form-row four-col">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={enableHollowing}
              onChange={(e) => setEnableHollowing(e.target.checked)}
            />
            Enable Hollowing
          </label>

          <label>
            Wall Thickness (mm)
            <input
              type="number"
              value={wallThickness}
              onChange={(e) => setWallThickness(parseFloat(e.target.value) || 10.0)}
              min={1.2}
              max={50}
              step={0.5}
              disabled={!enableHollowing}
            />
          </label>

          <label>
            Quality
            <select
              value={quality}
              onChange={(e) => setQuality(e.target.value as 'fast' | 'medium' | 'high')}
              disabled={!enableHollowing}
            >
              {QUALITY_PRESETS.map((q) => (
                <option key={q.value} value={q.value}>
                  {q.label} - {q.description}
                </option>
              ))}
            </select>
          </label>

          <label>
            Max Parts
            <input
              type="number"
              value={maxParts}
              onChange={(e) => setMaxParts(parseInt(e.target.value, 10) || 0)}
              min={0}
              max={500}
              title="0 = auto-calculate based on model size"
            />
            <span className="form-hint">0 = auto</span>
          </label>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleCheck}
            disabled={checking || loading || !filePath.trim()}
          >
            {checking ? 'Checking...' : 'Check Dimensions'}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSegment}
            disabled={loading || !filePath.trim()}
          >
            {loading ? 'Segmenting...' : 'Segment Model'}
          </button>
        </div>

        {/* Segmentation Progress */}
        {loading && (
          <div className="segmentation-progress">
            <div className="progress-header">
              <span>Segmenting model...</span>
              <span className="progress-percent">{Math.round(segmentProgress)}%</span>
            </div>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${segmentProgress}%` }}
              />
            </div>
            <p className="progress-hint">
              This may take several minutes for large models with hollowing enabled.
            </p>
          </div>
        )}
      </div>

      {error && <div className="status-error">{error}</div>}

      {checkResult && (
        <div className="check-result">
          <h4>Dimension Check</h4>
          <div className="dimension-comparison">
            <div className="dimension-card">
              <span className="label">Model Size</span>
              <span className="value">{formatDimensions(checkResult.model_dimensions_mm)}</span>
            </div>
            <div className="dimension-card">
              <span className="label">Build Volume</span>
              <span className="value">{formatDimensions(checkResult.build_volume_mm)}</span>
            </div>
          </div>

          <div className={`segmentation-verdict ${checkResult.needs_segmentation ? 'needs-split' : 'fits'}`}>
            {checkResult.needs_segmentation ? (
              <>
                <span className="icon">⚠️</span>
                <span>Model exceeds build volume. Recommended cuts: {checkResult.recommended_cuts}</span>
              </>
            ) : (
              <>
                <span className="icon">✓</span>
                <span>Model fits within build volume - no segmentation needed</span>
              </>
            )}
          </div>

          {checkResult.needs_segmentation && (() => {
            const exceeds = dimensionExceeds(checkResult.model_dimensions_mm, checkResult.build_volume_mm);
            return (
              <div className="exceeds-detail">
                {exceeds.x && <span className="badge badge-warning">Exceeds X</span>}
                {exceeds.y && <span className="badge badge-warning">Exceeds Y</span>}
                {exceeds.z && <span className="badge badge-warning">Exceeds Z</span>}
              </div>
            );
          })()}
        </div>
      )}

      {segmentResult && (
        <div className="segment-result">
          <h4>Segmentation Result</h4>

          {!segmentResult.needs_segmentation ? (
            <div className="segmentation-verdict fits">
              <span className="icon">✓</span>
              <span>Model fits build volume - exported as single part</span>
            </div>
          ) : (
            <>
              <div className="result-summary">
                <div className="summary-stat">
                  <span className="stat-value">{segmentResult.num_parts}</span>
                  <span className="stat-label">Parts</span>
                </div>
                {segmentResult.hardware_required?.dowels && (
                  <div className="summary-stat">
                    <span className="stat-value">{segmentResult.hardware_required.dowels.count}</span>
                    <span className="stat-label">
                      Dowels ({segmentResult.hardware_required.dowels.diameter_mm}mm x{' '}
                      {segmentResult.hardware_required.dowels.length_mm}mm)
                    </span>
                  </div>
                )}
              </div>

              <div className="parts-list">
                <h5>Generated Parts</h5>
                <table>
                  <thead>
                    <tr>
                      <th>Part</th>
                      <th>Dimensions</th>
                      <th>Volume</th>
                      <th>Supports</th>
                      <th>Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {segmentResult.parts.map((part) => (
                      <tr key={part.index}>
                        <td>{part.name}</td>
                        <td>{formatDimensions(part.dimensions_mm)}</td>
                        <td>{part.volume_cm3.toFixed(1)} cm³</td>
                        <td>{part.requires_supports ? 'Yes' : 'No'}</td>
                        <td>
                          <a
                            href={`/api/fabrication/artifacts/${part.file_path.replace(/^\/app\/artifacts\//, '').replace(/^artifacts\//, '')}`}
                            className="download-link"
                            download
                          >
                            📥
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {segmentResult.combined_3mf_path && (
                <div className="combined-download">
                  <a
                    href={`/api/fabrication/artifacts/${segmentResult.combined_3mf_path.replace(/^\/app\/artifacts\//, '').replace(/^artifacts\//, '')}`}
                    className="btn-primary download-btn"
                    download
                  >
                    📦 Download Combined 3MF Assembly
                  </a>
                  {completedJobId && (
                    <a
                      href={`/api/fabrication/segmentation/download/${completedJobId}`}
                      className="btn-secondary download-btn"
                      download
                    >
                      📁 Download All Parts (.zip)
                    </a>
                  )}
                </div>
              )}

              {segmentResult.assembly_notes && (
                <details className="assembly-notes">
                  <summary>Assembly Notes</summary>
                  <pre>{segmentResult.assembly_notes}</pre>
                </details>
              )}
            </>
          )}
        </div>
      )}

      {/* Slicing Panel - shown after segmentation completes */}
      {segmentResult && segmentResult.combined_3mf_path && (
        <SlicingPanel
          inputPath={segmentResult.combined_3mf_path}
          defaultPrinter={selectedPrinter !== 'custom' ? selectedPrinter : undefined}
          onSliceComplete={(result) => {
            console.log('Slicing complete:', result);
          }}
        />
      )}
    </div>
  );
}
