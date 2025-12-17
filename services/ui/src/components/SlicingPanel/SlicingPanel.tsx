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

interface PrinterRecommendation {
  id: string;
  name: string;
  build_volume: [number, number, number];
  recommended: boolean;
  reason: string;
  is_online?: boolean;
  is_printing?: boolean;
  progress_percent?: number;
}

interface SlicingPanelProps {
  inputPath: string; // 3MF file path from segmentation
  onSliceComplete?: (result: SlicingResult) => void;
  defaultPrinter?: string;
  /** Disable all interactions */
  disabled?: boolean;
  /** Show compact preset-first UI */
  presetMode?: boolean;
  /** Printer recommendations with status */
  printerRecommendations?: PrinterRecommendation[];
  /** Callback when printer is selected */
  onPrinterSelect?: (printerId: string) => void;
}

export type { SlicingResult, PrinterRecommendation };

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

// Quality presets for quick selection
const QUALITY_PRESETS = [
  {
    id: 'quick',
    label: 'Quick',
    description: 'Fast prints, visible layers',
    icon: '⚡',
    quality: 'draft',
    infill: 15,
    support: 'tree',
  },
  {
    id: 'standard',
    label: 'Standard',
    description: 'Balanced quality & speed',
    icon: '⚖️',
    quality: 'normal',
    infill: 20,
    support: 'tree',
  },
  {
    id: 'quality',
    label: 'Quality',
    description: 'Best finish, slower print',
    icon: '✨',
    quality: 'fine',
    infill: 25,
    support: 'tree',
  },
];

export default function SlicingPanel({
  inputPath,
  onSliceComplete,
  defaultPrinter,
  disabled = false,
  presetMode = false,
  printerRecommendations,
  onPrinterSelect,
}: SlicingPanelProps) {
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

  // Preset mode state
  const [selectedPreset, setSelectedPreset] = useState('standard');
  const [showAdvanced, setShowAdvanced] = useState(!presetMode);

  // Job state
  const [slicingJobId, setSlicingJobId] = useState<string | null>(null);
  const [slicingProgress, setSlicingProgress] = useState(0);
  const [slicingResult, setSlicingResult] = useState<SlicingResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Custom profile upload state
  const [showProfileUpload, setShowProfileUpload] = useState(false);
  const [customProfileName, setCustomProfileName] = useState('');
  const [customLayerHeight, setCustomLayerHeight] = useState(0.2);
  const [customPrintSpeed, setCustomPrintSpeed] = useState(80);
  const [customInfillDensity, setCustomInfillDensity] = useState(20);
  const [uploadingProfile, setUploadingProfile] = useState(false);

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

  // Handle preset selection
  const handlePresetSelect = useCallback((presetId: string) => {
    setSelectedPreset(presetId);
    const preset = QUALITY_PRESETS.find(p => p.id === presetId);
    if (preset) {
      setSelectedQuality(preset.quality);
      setInfillPercent(preset.infill);
      setSupportType(preset.support);
    }
  }, []);

  // Handle printer selection with callback
  const handlePrinterSelect = useCallback((printerId: string) => {
    setSelectedPrinter(printerId);
    onPrinterSelect?.(printerId);
  }, [onPrinterSelect]);

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
      // API returns flat structure, not nested result
      const apiResponse = await response.json();

      setSlicingProgress(apiResponse.progress * 100);

      if (apiResponse.status === 'completed' && apiResponse.gcode_path) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        // Construct result from top-level API fields
        const result: SlicingResult = {
          gcode_path: apiResponse.gcode_path,
          print_time_seconds: apiResponse.estimated_print_time_seconds || 0,
          filament_used_mm: 0, // Not provided by API
          filament_used_grams: apiResponse.estimated_filament_grams || 0,
        };
        setSlicingResult(result);
        setLoading(false);
        setSlicingJobId(null);
        onSliceComplete?.(result);
      } else if (apiResponse.status === 'failed') {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
        setError(apiResponse.error || 'Slicing failed');
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
        config: {
          printer_id: selectedPrinter,
          material_id: selectedMaterial,
          quality: selectedQuality,
          support_type: supportType,
          infill_percent: infillPercent,
        },
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

  // Handle custom profile upload
  const handleUploadCustomProfile = useCallback(async () => {
    if (!customProfileName.trim()) {
      setError('Please enter a profile name');
      return;
    }

    setUploadingProfile(true);
    setError(null);

    try {
      // Generate profile ID from name (lowercase, underscores)
      const profileId = customProfileName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');

      if (profileId.length < 3) {
        throw new Error('Profile name too short (minimum 3 characters)');
      }

      const response = await fetch('/api/fabrication/slicer/profiles/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_type: 'quality',
          profile_id: `custom_${profileId}`,
          name: customProfileName,
          data: {
            layer_height: customLayerHeight,
            first_layer_height: customLayerHeight + 0.08,
            perimeters: 3,
            top_solid_layers: 5,
            bottom_solid_layers: 4,
            fill_density: customInfillDensity,
            fill_pattern: 'gyroid',
            print_speed: customPrintSpeed,
          },
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to upload profile');
      }

      // Reload profiles to include the new one
      const qualitiesRes = await fetch('/api/fabrication/slicer/profiles/quality');
      if (qualitiesRes.ok) {
        const data = await qualitiesRes.json();
        setQualities(data);
        // Select the newly created profile
        setSelectedQuality(`custom_${profileId}`);
      }

      // Reset form and close dialog
      setShowProfileUpload(false);
      setCustomProfileName('');

    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploadingProfile(false);
    }
  }, [customProfileName, customLayerHeight, customPrintSpeed, customInfillDensity]);

  const selectedPrinterInfo = printers.find(p => p.id === selectedPrinter);
  const selectedMaterialInfo = materials.find(m => m.id === selectedMaterial);
  const selectedQualityInfo = qualities.find(q => q.id === selectedQuality);

  // Get printer list (either from recommendations or profile data)
  const displayPrinters = printerRecommendations || printers.map(p => ({
    ...p,
    recommended: false,
    reason: '',
  }));

  return (
    <div className={`slicing-panel ${disabled ? 'slicing-panel--disabled' : ''} ${presetMode ? 'slicing-panel--preset-mode' : ''}`}>
      <div className="slicing-header">
        <h3>G-code Slicer</h3>
        {!presetMode && <p className="text-muted">Convert 3MF to printable G-code</p>}
      </div>

      {inputPath && (
        <div className="input-file-info">
          <span className="file-icon">📁</span>
          <span className="file-path">{inputPath.split('/').pop()}</span>
        </div>
      )}

      <div className="slicing-form">
        {/* Printer Selection with Recommendations */}
        {printerRecommendations && printerRecommendations.length > 0 && (
          <div className="printer-recommendations">
            <label className="section-label">Select Printer</label>
            <div className="printer-cards">
              {printerRecommendations.map((printer) => (
                <button
                  key={printer.id}
                  type="button"
                  className={`printer-card ${selectedPrinter === printer.id ? 'printer-card--selected' : ''} ${printer.recommended ? 'printer-card--recommended' : ''} ${!printer.is_online ? 'printer-card--offline' : ''}`}
                  onClick={() => handlePrinterSelect(printer.id)}
                  disabled={disabled}
                >
                  <div className="printer-card__header">
                    <span className="printer-card__name">{printer.name}</span>
                    {printer.recommended && <span className="printer-card__badge">Recommended</span>}
                  </div>
                  <div className="printer-card__status">
                    {printer.is_online ? (
                      printer.is_printing ? (
                        <span className="printer-card__printing">
                          Printing {printer.progress_percent || 0}%
                        </span>
                      ) : (
                        <span className="printer-card__available">Available</span>
                      )
                    ) : (
                      <span className="printer-card__offline">Offline</span>
                    )}
                  </div>
                  {printer.reason && (
                    <div className="printer-card__reason">{printer.reason}</div>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Quality Presets (shown in preset mode) */}
        {presetMode && (
          <div className="quality-presets">
            <label className="section-label">Quality</label>
            <div className="preset-buttons">
              {QUALITY_PRESETS.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  className={`preset-btn ${selectedPreset === preset.id ? 'preset-btn--selected' : ''}`}
                  onClick={() => handlePresetSelect(preset.id)}
                  disabled={disabled}
                >
                  <span className="preset-btn__icon">{preset.icon}</span>
                  <span className="preset-btn__label">{preset.label}</span>
                  <span className="preset-btn__desc">{preset.description}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Advanced Settings Toggle */}
        {presetMode && (
          <button
            type="button"
            className="advanced-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
            disabled={disabled}
          >
            <span className={`advanced-toggle__icon ${showAdvanced ? 'advanced-toggle__icon--open' : ''}`}>▶</span>
            Advanced Settings
          </button>
        )}

        {/* Traditional/Advanced Form Controls */}
        {showAdvanced && (
          <>
            {/* Printer & Material Selection (non-recommendation mode) */}
            {!printerRecommendations && (
              <div className="form-row two-col">
                <label>
                  Target Printer
                  <select
                    value={selectedPrinter}
                    onChange={(e) => handlePrinterSelect(e.target.value)}
                    disabled={disabled}
                  >
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
                  <select
                    value={selectedMaterial}
                    onChange={(e) => setSelectedMaterial(e.target.value)}
                    disabled={disabled}
                  >
                    {materials.map((material) => (
                      <option key={material.id} value={material.id}>
                        {material.name} ({material.nozzle_temp}°C)
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {/* Material (when using recommendations) */}
            {printerRecommendations && (
              <div className="form-row">
                <label>
                  Material
                  <select
                    value={selectedMaterial}
                    onChange={(e) => setSelectedMaterial(e.target.value)}
                    disabled={disabled}
                  >
                    {materials.map((material) => (
                      <option key={material.id} value={material.id}>
                        {material.name} ({material.nozzle_temp}°C)
                      </option>
                    ))}
                  </select>
                </label>
              </div>
            )}

            {/* Quality & Support Selection */}
            <div className="form-row two-col">
              <label>
                Print Quality
                <select
                  value={selectedQuality}
                  onChange={(e) => setSelectedQuality(e.target.value)}
                  disabled={disabled}
                >
                  {qualities.map((quality) => (
                    <option key={quality.id} value={quality.id}>
                      {quality.name} ({quality.layer_height}mm)
                    </option>
                  ))}
                </select>
              </label>

              <label>
                Support Type
                <select
                  value={supportType}
                  onChange={(e) => setSupportType(e.target.value)}
                  disabled={disabled}
                >
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
                    disabled={disabled}
                  />
                  <span className="slider-value">{infillPercent}%</span>
                </div>
              </label>

              <label>
                Infill Pattern
                <select
                  value={infillPattern}
                  onChange={(e) => setInfillPattern(e.target.value)}
                  disabled={disabled}
                >
                  {INFILL_PATTERNS.map((ip) => (
                    <option key={ip.value} value={ip.value}>
                      {ip.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {/* Custom Profile Upload Section */}
            <div className="custom-profile-section">
              <button
                type="button"
                className="custom-profile-toggle"
                onClick={() => setShowProfileUpload(!showProfileUpload)}
                disabled={disabled}
              >
                <span className={`custom-profile-toggle__icon ${showProfileUpload ? 'custom-profile-toggle__icon--open' : ''}`}>+</span>
                Create Custom Quality Profile
              </button>

              {showProfileUpload && (
                <div className="custom-profile-form">
                  <p className="custom-profile-hint">
                    Create a custom quality profile with your preferred settings.
                  </p>

                  <label>
                    Profile Name
                    <input
                      type="text"
                      value={customProfileName}
                      onChange={(e) => setCustomProfileName(e.target.value)}
                      placeholder="e.g., Ultra Fine, Speed Print"
                      disabled={disabled || uploadingProfile}
                    />
                  </label>

                  <div className="form-row two-col">
                    <label>
                      Layer Height (mm)
                      <input
                        type="number"
                        min={0.05}
                        max={0.5}
                        step={0.01}
                        value={customLayerHeight}
                        onChange={(e) => setCustomLayerHeight(parseFloat(e.target.value))}
                        disabled={disabled || uploadingProfile}
                      />
                    </label>

                    <label>
                      Print Speed (mm/s)
                      <input
                        type="number"
                        min={20}
                        max={200}
                        step={5}
                        value={customPrintSpeed}
                        onChange={(e) => setCustomPrintSpeed(parseInt(e.target.value, 10))}
                        disabled={disabled || uploadingProfile}
                      />
                    </label>
                  </div>

                  <label>
                    Default Infill (%)
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={5}
                      value={customInfillDensity}
                      onChange={(e) => setCustomInfillDensity(parseInt(e.target.value, 10))}
                      disabled={disabled || uploadingProfile}
                    />
                  </label>

                  <div className="custom-profile-actions">
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => setShowProfileUpload(false)}
                      disabled={uploadingProfile}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={handleUploadCustomProfile}
                      disabled={disabled || uploadingProfile || !customProfileName.trim()}
                    >
                      {uploadingProfile ? 'Saving...' : 'Save Profile'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* Settings Summary (non-preset mode) */}
        {!presetMode && selectedPrinterInfo && selectedMaterialInfo && selectedQualityInfo && (
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
            disabled={disabled || loading || !inputPath || !selectedPrinter}
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
