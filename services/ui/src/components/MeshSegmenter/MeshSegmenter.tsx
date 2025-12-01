import { useState, useEffect, useCallback } from 'react';
import './MeshSegmenter.css';

interface Printer {
  id: string;
  name: string;
  build_volume: {
    x: number;
    y: number;
    z: number;
  };
  technology: string;
}

interface CheckResult {
  needs_segmentation: boolean;
  model_dimensions: {
    x: number;
    y: number;
    z: number;
  };
  build_volume: {
    x: number;
    y: number;
    z: number;
  };
  exceeds: {
    x: boolean;
    y: boolean;
    z: boolean;
  };
  recommended_cuts: number;
  printer_id: string;
}

interface SegmentPart {
  part_id: string;
  path: string;
  dimensions: {
    x: number;
    y: number;
    z: number;
  };
  volume_mm3: number;
  joint_count: number;
}

interface SegmentResult {
  needs_segmentation: boolean;
  num_parts: number;
  parts: SegmentPart[];
  combined_3mf_path?: string;
  combined_3mf_uri?: string;
  hardware_required: {
    dowels?: { count: number; diameter_mm: number; length_mm: number };
  };
  assembly_notes?: string;
}

interface MeshSegmenterProps {
  artifactPath?: string;
  onSegmentComplete?: (result: SegmentResult) => void;
}

const JOINT_TYPES = [
  { value: 'dowel', label: 'Dowel Pins', description: 'Cylindrical alignment pins' },
  { value: 'dovetail', label: 'Dovetail', description: 'Interlocking joints' },
  { value: 'pyramid', label: 'Pyramid', description: 'Pyramid-shaped alignment keys' },
  { value: 'none', label: 'None', description: 'No joints - manual alignment' },
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
  const [wallThickness, setWallThickness] = useState(2.0);
  const [jointType, setJointType] = useState('dowel');
  const [maxParts, setMaxParts] = useState(10);

  // Load available printers
  useEffect(() => {
    const loadPrinters = async () => {
      try {
        const response = await fetch('/api/fabrication/segmentation/printers');
        if (response.ok) {
          const data = await response.json();
          setPrinters(data);
          if (data.length > 0 && !selectedPrinter) {
            setSelectedPrinter(data[0].id);
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

  const handleCheck = useCallback(async () => {
    if (!filePath.trim()) {
      setError('Please enter a file path');
      return;
    }

    setChecking(true);
    setError(null);
    setCheckResult(null);

    try {
      const response = await fetch('/api/fabrication/segmentation/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stl_path: filePath,
          printer_id: selectedPrinter || undefined,
        }),
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
  }, [filePath, selectedPrinter]);

  const handleSegment = useCallback(async () => {
    if (!filePath.trim()) {
      setError('Please enter a file path');
      return;
    }

    setLoading(true);
    setError(null);
    setSegmentResult(null);

    try {
      const response = await fetch('/api/fabrication/segmentation/segment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stl_path: filePath,
          printer_id: selectedPrinter || undefined,
          enable_hollowing: enableHollowing,
          wall_thickness_mm: wallThickness,
          joint_type: jointType,
          max_parts: maxParts,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Segmentation failed');
      }

      const data = await response.json();
      setSegmentResult(data);
      onSegmentComplete?.(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [filePath, selectedPrinter, enableHollowing, wallThickness, jointType, maxParts, onSegmentComplete]);

  const formatDimensions = (dims: { x: number; y: number; z: number }) => {
    return `${dims.x.toFixed(1)} x ${dims.y.toFixed(1)} x ${dims.z.toFixed(1)} mm`;
  };

  return (
    <div className="mesh-segmenter">
      <div className="segmenter-header">
        <h3>Mesh Segmenter</h3>
        <p className="text-muted">Split large models for multi-part printing</p>
      </div>

      <div className="segmenter-form">
        <div className="form-row">
          <label>
            STL/3MF File Path
            <input
              type="text"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="/path/to/model.stl or artifacts/stl/model.stl"
            />
          </label>
        </div>

        <div className="form-row two-col">
          <label>
            Target Printer
            <select value={selectedPrinter} onChange={(e) => setSelectedPrinter(e.target.value)}>
              <option value="">Auto-detect</option>
              {printers.map((printer) => (
                <option key={printer.id} value={printer.id}>
                  {printer.name} ({formatDimensions(printer.build_volume)})
                </option>
              ))}
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

        <div className="form-row three-col">
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
              onChange={(e) => setWallThickness(parseFloat(e.target.value) || 2.0)}
              min={0.5}
              max={10}
              step={0.5}
              disabled={!enableHollowing}
            />
          </label>

          <label>
            Max Parts
            <input
              type="number"
              value={maxParts}
              onChange={(e) => setMaxParts(parseInt(e.target.value, 10) || 10)}
              min={2}
              max={50}
            />
          </label>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={handleCheck}
            disabled={checking || !filePath.trim()}
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
      </div>

      {error && <div className="status-error">{error}</div>}

      {checkResult && (
        <div className="check-result">
          <h4>Dimension Check</h4>
          <div className="dimension-comparison">
            <div className="dimension-card">
              <span className="label">Model Size</span>
              <span className="value">{formatDimensions(checkResult.model_dimensions)}</span>
            </div>
            <div className="dimension-card">
              <span className="label">Build Volume</span>
              <span className="value">{formatDimensions(checkResult.build_volume)}</span>
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

          {checkResult.exceeds && (
            <div className="exceeds-detail">
              {checkResult.exceeds.x && <span className="badge badge-warning">Exceeds X</span>}
              {checkResult.exceeds.y && <span className="badge badge-warning">Exceeds Y</span>}
              {checkResult.exceeds.z && <span className="badge badge-warning">Exceeds Z</span>}
            </div>
          )}
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
                      <th>Joints</th>
                      <th>Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {segmentResult.parts.map((part) => (
                      <tr key={part.part_id}>
                        <td>{part.part_id}</td>
                        <td>{formatDimensions(part.dimensions)}</td>
                        <td>{(part.volume_mm3 / 1000).toFixed(1)} cm³</td>
                        <td>{part.joint_count}</td>
                        <td>
                          <a
                            href={`/api/fabrication/artifacts/${part.path.replace('artifacts/', '')}`}
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
                    href={`/api/fabrication/artifacts/${segmentResult.combined_3mf_path.replace('artifacts/', '')}`}
                    className="btn-primary download-btn"
                    download
                  >
                    📦 Download Combined 3MF Assembly
                  </a>
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
    </div>
  );
}
