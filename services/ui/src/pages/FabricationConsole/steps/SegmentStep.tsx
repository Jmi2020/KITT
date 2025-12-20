/**
 * SegmentStep - Step 2 of fabrication workflow
 *
 * Shows dimension check results and allows optional segmentation
 * for models that exceed printer build volume.
 */

import { StepContainer } from '../../../components/FabricationWorkflow';
import MeshSegmenter from '../../../components/MeshSegmenter';
import type { DimensionCheckResult, SegmentResult, Artifact } from '../hooks/useFabricationWorkflow';
import './SegmentStep.css';

interface SegmentStepProps {
  // State
  selectedArtifact: Artifact | null;
  dimensionCheck: DimensionCheckResult | null;
  segmentationRequired: boolean;
  segmentationSkipped: boolean;
  segmentResult: SegmentResult | null;
  isLoading: boolean;
  error: string | null;
  isActive: boolean;
  isCompleted: boolean;
  isLocked: boolean;
  selectedPrinter?: string;

  // Actions
  onCheckComplete: (result: DimensionCheckResult) => void;
  onSegmentComplete: (result: SegmentResult) => void;
  onSkipSegmentation: () => void;
}

export function SegmentStep({
  selectedArtifact,
  dimensionCheck,
  segmentationRequired,
  segmentationSkipped,
  segmentResult,
  isLoading,
  error,
  isActive,
  isCompleted,
  isLocked,
  selectedPrinter,
  onCheckComplete,
  onSegmentComplete,
  onSkipSegmentation,
}: SegmentStepProps) {
  // Format dimensions for display
  const formatDimensions = (dims: [number, number, number]) => {
    return `${dims[0].toFixed(0)} x ${dims[1].toFixed(0)} x ${dims[2].toFixed(0)} mm`;
  };

  // Get status text based on current state
  const getSubtitle = () => {
    if (isLocked) return 'Select a model in Step 1 to check dimensions';
    if (isLoading) return 'Checking model dimensions...';
    if (segmentResult) return `Segmented into ${segmentResult.parts?.length || 0} parts`;
    if (segmentationSkipped) return 'Segmentation skipped - using original model';
    if (dimensionCheck) {
      if (dimensionCheck.needs_segmentation) {
        return 'Model exceeds build volume - segmentation recommended';
      }
      return 'Model fits within build volume';
    }
    return 'Check if your model needs to be split for printing';
  };

  // Get artifact path for MeshSegmenter
  const artifactPath = selectedArtifact?.metadata?.stl_location || selectedArtifact?.location;

  return (
    <StepContainer
      stepNumber={3}
      title="Segment (Optional)"
      subtitle={getSubtitle()}
      isActive={isActive}
      isCompleted={isCompleted}
      isLocked={isLocked}
      isLoading={isLoading}
      error={error}
      collapsible={isCompleted}
      helpText="Split oversized models into printable parts with automatic joint generation"
    >
      <div className="segment-step">
        {/* Quick status card when we have dimension check but haven't segmented */}
        {dimensionCheck && !segmentResult && !isLoading && (
          <div className="segment-step__status-card">
            <div className="segment-step__dimension-info">
              <div className="segment-step__dimension-row">
                <span className="segment-step__dimension-label">Model Size</span>
                <span className="segment-step__dimension-value">
                  {formatDimensions(dimensionCheck.dimensions)}
                </span>
              </div>
              <div className="segment-step__dimension-row">
                <span className="segment-step__dimension-label">Build Volume</span>
                <span className="segment-step__dimension-value">
                  {formatDimensions(dimensionCheck.build_volume)}
                </span>
              </div>
            </div>

            <div className={`segment-step__verdict ${dimensionCheck.needs_segmentation ? 'segment-step__verdict--warning' : 'segment-step__verdict--success'}`}>
              {dimensionCheck.needs_segmentation ? (
                <>
                  <svg viewBox="0 0 24 24" className="segment-step__verdict-icon">
                    <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  <span>Model exceeds build volume - segmentation recommended</span>
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" className="segment-step__verdict-icon">
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  <span>Model fits - no segmentation needed</span>
                </>
              )}
            </div>

            {!dimensionCheck.needs_segmentation && !segmentationSkipped && (
              <div className="segment-step__skip-section">
                <button
                  type="button"
                  className="segment-step__skip-btn"
                  onClick={onSkipSegmentation}
                >
                  Continue to Slicing
                </button>
                <span className="segment-step__skip-hint">Model is ready for printing</span>
              </div>
            )}
          </div>
        )}

        {/* Show compact MeshSegmenter for advanced options or when segmentation is needed */}
        {selectedArtifact && (!dimensionCheck || dimensionCheck.needs_segmentation) && !segmentationSkipped && (
          <div className="segment-step__segmenter">
            <MeshSegmenter
              artifactPath={artifactPath}
              onCheckComplete={(result) => {
                onCheckComplete({
                  needs_segmentation: result.needs_segmentation,
                  dimensions: result.model_dimensions_mm,
                  build_volume: result.build_volume_mm,
                  exceeds_by: result.exceeds_by_mm,
                });
              }}
              onSegmentComplete={(result) => {
                onSegmentComplete({
                  job_id: '',
                  parts: result.parts.map(p => ({
                    file_path: p.file_path,
                    dimensions: p.dimensions_mm,
                  })),
                  combined_3mf_path: result.combined_3mf_path,
                  hardware_required: result.hardware_required as Record<string, number>,
                });
              }}
              disabled={isLocked}
              compact={true}
              autoCheck={true}
              defaultPrinter={selectedPrinter}
              hideSlicingPanel={true}
            />
          </div>
        )}

        {/* Segmentation complete summary */}
        {segmentResult && (
          <div className="segment-step__result">
            <div className="segment-step__result-header">
              <svg viewBox="0 0 24 24" className="segment-step__result-icon">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              <span>Segmentation Complete</span>
            </div>
            <div className="segment-step__result-stats">
              <div className="segment-step__stat">
                <span className="segment-step__stat-value">{segmentResult.parts?.length || 0}</span>
                <span className="segment-step__stat-label">Parts</span>
              </div>
              {segmentResult.hardware_required && Object.keys(segmentResult.hardware_required).length > 0 && (
                <div className="segment-step__stat">
                  <span className="segment-step__stat-value">
                    {Object.values(segmentResult.hardware_required).reduce((a, b) => a + b, 0)}
                  </span>
                  <span className="segment-step__stat-label">Hardware Items</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Skip segmentation option when model needs it but user wants to override */}
        {dimensionCheck?.needs_segmentation && !segmentResult && !segmentationSkipped && (
          <div className="segment-step__override-section">
            <label className="segment-step__override-checkbox">
              <input
                type="checkbox"
                onChange={(e) => e.target.checked && onSkipSegmentation()}
              />
              <span>Force skip segmentation (model may not fit printer)</span>
            </label>
          </div>
        )}
      </div>
    </StepContainer>
  );
}

export default SegmentStep;
