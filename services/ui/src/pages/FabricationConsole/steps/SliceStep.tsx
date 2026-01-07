/**
 * SliceStep - Step 3 of fabrication workflow
 *
 * Handles printer selection, quality presets, and G-code slicing.
 * Shows printer recommendations based on model dimensions.
 */

import { StepContainer } from '../../../components/FabricationWorkflow';
import SlicingPanel from '../../../components/SlicingPanel';
import type {
  SliceResult,
  QualityPreset,
  SlicerSettings,
  PrinterRecommendation,
  Artifact,
  SegmentResult,
} from '../hooks/useFabricationWorkflow';
import './SliceStep.css';

interface SliceStepProps {
  // State
  selectedArtifact: Artifact | null;
  orientedMeshPath: string | null;  // Path to oriented/scaled mesh from orientation step
  segmentResult: SegmentResult | null;
  selectedPrinter: string | null;
  printerRecommendations: PrinterRecommendation[];
  preset: QualityPreset;
  advancedSettings: SlicerSettings;
  showAdvanced: boolean;
  sliceResult: SliceResult | null;
  isLoading: boolean;
  error: string | null;
  isActive: boolean;
  isCompleted: boolean;
  isLocked: boolean;

  // Actions
  onPrinterSelect: (printerId: string) => void;
  onPresetChange: (preset: QualityPreset) => void;
  onAdvancedSettingsChange: (settings: Partial<SlicerSettings>) => void;
  onToggleAdvanced: () => void;
  onStartSlicing: () => void;
  onSliceComplete: (result: SliceResult) => void;
}

export function SliceStep({
  selectedArtifact,
  orientedMeshPath,
  segmentResult,
  selectedPrinter,
  printerRecommendations,
  preset,
  advancedSettings,
  showAdvanced,
  sliceResult,
  isLoading,
  error,
  isActive,
  isCompleted,
  isLocked,
  onPrinterSelect,
  onPresetChange,
  onAdvancedSettingsChange,
  onToggleAdvanced,
  onStartSlicing,
  onSliceComplete,
}: SliceStepProps) {
  // Get input path - priority: segmented output > oriented mesh > original artifact
  const getInputPath = () => {
    if (segmentResult?.combined_3mf_path) {
      return segmentResult.combined_3mf_path;
    }
    if (orientedMeshPath) {
      return orientedMeshPath;
    }
    if (selectedArtifact) {
      return selectedArtifact.metadata?.stl_location || selectedArtifact.location;
    }
    return '';
  };

  // Get subtitle based on state
  const getSubtitle = () => {
    if (isLocked) return 'Complete previous steps to configure slicing';
    if (sliceResult?.status === 'completed') {
      const time = formatTime(sliceResult.estimated_print_time_seconds || 0);
      return `Sliced! Estimated print time: ${time}`;
    }
    if (isLoading) return 'Generating G-code...';
    if (!selectedPrinter) return 'Select a printer to continue';
    return 'Configure print settings and generate G-code';
  };

  // Format time helper
  const formatTime = (seconds: number): string => {
    if (!seconds) return 'N/A';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    }
    return `${minutes}m`;
  };

  // Transform printer recommendations for SlicingPanel
  const slicingPanelRecommendations = printerRecommendations.map((rec) => ({
    id: rec.printer.printer_id,
    name: formatPrinterName(rec.printer.printer_id),
    build_volume: getBuildVolume(rec.printer.printer_id),
    recommended: rec.recommended,
    reason: rec.reason,
    is_online: rec.printer.is_online,
    is_printing: rec.printer.is_printing,
    progress_percent: rec.printer.progress_percent || undefined,
  }));

  return (
    <StepContainer
      stepNumber={4}
      title="Slice"
      subtitle={getSubtitle()}
      isActive={isActive}
      isCompleted={isCompleted}
      isLocked={isLocked}
      isLoading={isLoading}
      error={error}
      collapsible={isCompleted}
      helpText="Convert your 3D model to G-code for printing"
    >
      <div className="slice-step">
        {/* Slicing result summary (when completed) */}
        {sliceResult?.status === 'completed' && (
          <div className="slice-step__result-summary">
            <div className="slice-step__result-header">
              <svg viewBox="0 0 24 24" className="slice-step__result-icon">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <span>G-code Ready</span>
            </div>
            <div className="slice-step__result-stats">
              <div className="slice-step__stat">
                <span className="slice-step__stat-label">Print Time</span>
                <span className="slice-step__stat-value">
                  {formatTime(sliceResult.estimated_print_time_seconds || 0)}
                </span>
              </div>
              <div className="slice-step__stat">
                <span className="slice-step__stat-label">Filament</span>
                <span className="slice-step__stat-value">
                  {sliceResult.estimated_filament_grams?.toFixed(1) || '?'}g
                </span>
              </div>
              {selectedPrinter && (
                <div className="slice-step__stat">
                  <span className="slice-step__stat-label">Printer</span>
                  <span className="slice-step__stat-value">
                    {formatPrinterName(selectedPrinter)}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Show SlicingPanel unless we have a completed result */}
        {sliceResult?.status !== 'completed' && (
          <SlicingPanel
            inputPath={getInputPath()}
            onSliceComplete={(result) => {
              onSliceComplete({
                job_id: '',
                status: 'completed',
                progress: 1,
                gcode_path: result.gcode_path,
                estimated_print_time_seconds: result.print_time_seconds,
                estimated_filament_grams: result.filament_used_grams,
              });
            }}
            defaultPrinter={selectedPrinter || undefined}
            disabled={isLocked}
            presetMode={true}
            printerRecommendations={slicingPanelRecommendations.length > 0 ? slicingPanelRecommendations : undefined}
            onPrinterSelect={onPrinterSelect}
          />
        )}

        {/* Quick re-slice option when completed */}
        {sliceResult?.status === 'completed' && (
          <div className="slice-step__reslice">
            <button
              type="button"
              className="slice-step__reslice-btn"
              onClick={onStartSlicing}
              disabled={isLocked || isLoading}
            >
              Re-slice with Different Settings
            </button>
          </div>
        )}
      </div>
    </StepContainer>
  );
}

// Helper functions
function formatPrinterName(printerId: string): string {
  const names: Record<string, string> = {
    bambu_h2d: 'Bambu H2D',
    elegoo_giga: 'Elegoo Giga',
    snapmaker_artisan: 'Snapmaker Artisan',
  };
  return names[printerId] || printerId;
}

function getBuildVolume(printerId: string): [number, number, number] {
  const volumes: Record<string, [number, number, number]> = {
    bambu_h2d: [325, 320, 325],
    elegoo_giga: [800, 800, 1000],
    snapmaker_artisan: [400, 400, 400],
  };
  return volumes[printerId] || [200, 200, 200];
}

export default SliceStep;
