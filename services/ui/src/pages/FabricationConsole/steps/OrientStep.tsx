/**
 * OrientStep - Step 1.5 of fabrication workflow (between Generate and Segment)
 *
 * Analyzes mesh orientations and lets user select optimal print orientation
 * to minimize support requirements and improve print quality.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { StepContainer } from '../../../components/FabricationWorkflow';
import { OrientationPreview } from '../../../components/OrientationPreview';
import { translateArtifactPath, type Artifact } from '../hooks/useFabricationWorkflow';
import './OrientStep.css';

// Types matching backend schemas
export interface OrientationOption {
  id: string;
  label: string;
  rotation_matrix: number[][];
  up_vector: [number, number, number];
  overhang_ratio: number;
  support_estimate: 'none' | 'minimal' | 'moderate' | 'significant';
  is_recommended: boolean;
}

export interface OrientationAnalysis {
  success: boolean;
  original_dimensions: [number, number, number];
  face_count: number;
  orientations: OrientationOption[];
  best_orientation_id: string;
  analysis_time_ms: number;
  error?: string;
}

interface OrientStepProps {
  // State
  selectedArtifact: Artifact | null;
  orientationAnalysis: OrientationAnalysis | null;
  selectedOrientation: OrientationOption | null;
  orientedMeshPath: string | null;
  isLoading: boolean;
  error: string | null;
  isActive: boolean;
  isCompleted: boolean;
  isLocked: boolean;
  // Scaling state
  scalingEnabled: boolean;
  targetHeight: number | null;
  appliedScaleFactor: number | null;

  // Actions
  onAnalyze: () => Promise<void>;
  onSelectOrientation: (orientation: OrientationOption) => void;
  onApplyOrientation: () => Promise<void>;
  onSkipOrientation: () => void;
  onSetScalingEnabled: (enabled: boolean) => void;
  onSetTargetHeight: (height: number | null) => void;
}

export function OrientStep({
  selectedArtifact,
  orientationAnalysis,
  selectedOrientation,
  orientedMeshPath,
  isLoading,
  error,
  isActive,
  isCompleted,
  isLocked,
  scalingEnabled,
  targetHeight,
  appliedScaleFactor,
  onAnalyze,
  onSelectOrientation,
  onApplyOrientation,
  onSkipOrientation,
  onSetScalingEnabled,
  onSetTargetHeight,
}: OrientStepProps) {
  const [previewLoading, setPreviewLoading] = useState(false);

  // Memoize the onMeshLoaded callback to prevent infinite re-renders in OrientationPreview
  const handleMeshLoaded = useCallback(() => {
    setPreviewLoading(false);
  }, []);

  // Check if the selected artifact is a GLB file (preview only, not printable)
  const isGlbFile = selectedArtifact?.artifactType?.toLowerCase() === 'glb' ||
    selectedArtifact?.artifactType?.toLowerCase() === 'gltf';

  // Auto-analyze when artifact is selected and step becomes active
  // Skip analysis for GLB files - they are for viewing only
  useEffect(() => {
    if (selectedArtifact && isActive && !orientationAnalysis && !isLoading && !isGlbFile) {
      onAnalyze();
    }
  }, [selectedArtifact, isActive, orientationAnalysis, isLoading, onAnalyze, isGlbFile]);

  // Auto-select recommended orientation
  useEffect(() => {
    if (orientationAnalysis && !selectedOrientation) {
      const recommended = orientationAnalysis.orientations.find((o) => o.is_recommended);
      if (recommended) {
        onSelectOrientation(recommended);
      }
    }
  }, [orientationAnalysis, selectedOrientation, onSelectOrientation]);

  // Get artifact URL for preview
  const getArtifactUrl = useCallback((): string => {
    if (!selectedArtifact) return '';
    const path =
      selectedArtifact.metadata?.stl_location || selectedArtifact.location;
    return translateArtifactPath(path);
  }, [selectedArtifact]);

  // Get file type
  const getFileType = useCallback((): string => {
    if (!selectedArtifact) return 'stl';
    const artifactType = selectedArtifact.artifactType?.toLowerCase();
    if (artifactType === '3mf' || artifactType === 'stl' || artifactType === 'glb') {
      return artifactType;
    }
    // Check location extension
    const location = selectedArtifact.location || '';
    if (location.endsWith('.3mf')) return '3mf';
    if (location.endsWith('.glb')) return 'glb';
    return 'stl';
  }, [selectedArtifact]);

  // Get status subtitle
  const getSubtitle = () => {
    if (isLocked) return 'Select a model in Step 1 to analyze orientation';
    if (isGlbFile) return 'GLB files are for preview only - skip to use STL/3MF for printing';
    if (isLoading) return 'Analyzing mesh orientations...';
    if (error) return 'Failed to analyze orientations';
    if (orientedMeshPath) return `Orientation applied: ${selectedOrientation?.label || 'Custom'}`;
    if (selectedOrientation) {
      const ratio = (selectedOrientation.overhang_ratio * 100).toFixed(1);
      return `Selected: ${selectedOrientation.label} (${ratio}% overhangs)`;
    }
    if (orientationAnalysis) {
      return `${orientationAnalysis.orientations.length} orientations analyzed`;
    }
    return 'Optimize model orientation and scale for printing';
  };

  // Format support estimate with color
  const getSupportBadge = (estimate: string) => {
    const classes: Record<string, string> = {
      none: 'orient-step__badge--success',
      minimal: 'orient-step__badge--success',
      moderate: 'orient-step__badge--warning',
      significant: 'orient-step__badge--error',
    };
    return (
      <span className={`orient-step__badge ${classes[estimate] || ''}`}>
        {estimate}
      </span>
    );
  };

  // Compute current height and scale preview
  const scalingPreview = useMemo(() => {
    if (!orientationAnalysis || !selectedOrientation) {
      return null;
    }

    // Get original dimensions
    const [w, d, h] = orientationAnalysis.original_dimensions;

    // For now, use height (Z) as the dimension - in reality this should
    // be calculated based on the rotation matrix, but we use height for simplicity
    // The backend will handle the actual calculation
    const currentHeight = h;

    if (!targetHeight || targetHeight <= 0) {
      return {
        currentHeight,
        scaleFactor: null,
        scaledDimensions: null,
      };
    }

    const scaleFactor = targetHeight / currentHeight;
    const scaledDimensions: [number, number, number] = [
      w * scaleFactor,
      d * scaleFactor,
      h * scaleFactor,
    ];

    return {
      currentHeight,
      scaleFactor,
      scaledDimensions,
    };
  }, [orientationAnalysis, selectedOrientation, targetHeight]);

  return (
    <StepContainer
      stepNumber={2}
      title="Orient and Scale"
      subtitle={getSubtitle()}
      isActive={isActive}
      isCompleted={isCompleted}
      isLocked={isLocked}
      isLoading={isLoading}
      error={error}
      collapsible={isCompleted}
      helpText="Choose optimal orientation and adjust scale to minimize support material and fit your printer"
    >
      <div className="orient-step">
        {/* Analysis results with preview */}
        {orientationAnalysis && selectedArtifact && (
          <div className="orient-step__layout">
            {/* 3D Preview */}
            <div className="orient-step__preview">
              <OrientationPreview
                meshUrl={getArtifactUrl()}
                fileType={getFileType()}
                rotationMatrix={selectedOrientation?.rotation_matrix}
                overhangRatio={selectedOrientation?.overhang_ratio}
                showOverhangs={true}
                height={280}
                autoRotate={false}
                onMeshLoaded={handleMeshLoaded}
              />
            </div>

            {/* Orientation options */}
            <div className="orient-step__options">
              <h4 className="orient-step__options-title">
                Select Orientation
                <span className="orient-step__options-count">
                  {orientationAnalysis.orientations.length} options
                </span>
              </h4>

              <div className="orient-step__option-list">
                {orientationAnalysis.orientations.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    className={`orient-step__option ${
                      selectedOrientation?.id === option.id
                        ? 'orient-step__option--selected'
                        : ''
                    } ${option.is_recommended ? 'orient-step__option--recommended' : ''}`}
                    onClick={() => onSelectOrientation(option)}
                    disabled={isLoading || !!orientedMeshPath}
                  >
                    <div className="orient-step__option-header">
                      <span className="orient-step__option-label">{option.label}</span>
                      {option.is_recommended && (
                        <span className="orient-step__recommended-badge">Recommended</span>
                      )}
                    </div>
                    <div className="orient-step__option-details">
                      <span className="orient-step__overhang">
                        {(option.overhang_ratio * 100).toFixed(1)}% overhangs
                      </span>
                      {getSupportBadge(option.support_estimate)}
                    </div>
                  </button>
                ))}
              </div>

              {/* Scaling controls */}
              {!orientedMeshPath && (
                <div className="orient-step__scaling">
                  <div className="orient-step__scaling-toggle">
                    <input
                      type="checkbox"
                      id="enable-scaling"
                      checked={scalingEnabled}
                      onChange={(e) => onSetScalingEnabled(e.target.checked)}
                      disabled={isLoading}
                    />
                    <label htmlFor="enable-scaling">Enable Scaling</label>
                  </div>

                  {scalingEnabled && (
                    <div className="orient-step__scaling-controls">
                      <div className="orient-step__scaling-input">
                        <label htmlFor="target-height">Target Height:</label>
                        <input
                          type="number"
                          id="target-height"
                          min="1"
                          max="1000"
                          step="1"
                          value={targetHeight || ''}
                          onChange={(e) => {
                            const val = e.target.value;
                            onSetTargetHeight(val ? parseFloat(val) : null);
                          }}
                          placeholder={scalingPreview?.currentHeight?.toFixed(0) || ''}
                          disabled={isLoading}
                        />
                        <span>mm</span>
                      </div>

                      {scalingPreview?.scaleFactor && scalingPreview.scaledDimensions && (
                        <div className="orient-step__scaling-preview">
                          <div className="orient-step__scaling-preview-row orient-step__scaling-preview-row--highlight">
                            <span>Scale Factor:</span>
                            <span>{scalingPreview.scaleFactor.toFixed(3)}x</span>
                          </div>
                          <div className="orient-step__scaling-preview-row">
                            <span>New Dimensions:</span>
                            <span>
                              {scalingPreview.scaledDimensions[0].toFixed(1)} x{' '}
                              {scalingPreview.scaledDimensions[1].toFixed(1)} x{' '}
                              {scalingPreview.scaledDimensions[2].toFixed(1)} mm
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Show applied scale factor if orientation was applied with scaling */}
              {orientedMeshPath && appliedScaleFactor && (
                <div className="orient-step__scaling-preview">
                  <div className="orient-step__scaling-preview-row orient-step__scaling-preview-row--highlight">
                    <span>Applied Scale Factor:</span>
                    <span>{appliedScaleFactor.toFixed(3)}x</span>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="orient-step__actions">
                {!orientedMeshPath ? (
                  <>
                    <button
                      type="button"
                      className="orient-step__apply-btn"
                      onClick={onApplyOrientation}
                      disabled={!selectedOrientation || isLoading}
                    >
                      Apply Orientation
                    </button>
                    <button
                      type="button"
                      className="orient-step__skip-btn"
                      onClick={onSkipOrientation}
                      disabled={isLoading}
                    >
                      Skip (Use Original)
                    </button>
                  </>
                ) : (
                  <div className="orient-step__applied">
                    <svg
                      viewBox="0 0 24 24"
                      className="orient-step__applied-icon"
                    >
                      <path
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                    <span>Orientation applied - ready for segmentation</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Loading state */}
        {isLoading && !orientationAnalysis && (
          <div className="orient-step__loading">
            <div className="orient-step__spinner"></div>
            <p>Analyzing mesh orientations...</p>
            <p className="orient-step__loading-hint">
              Testing 6 cardinal orientations to find optimal print position
            </p>
          </div>
        )}

        {/* GLB file message */}
        {isGlbFile && selectedArtifact && (
          <div className="orient-step__glb-notice">
            <svg viewBox="0 0 24 24" className="orient-step__glb-icon">
              <path
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className="orient-step__glb-content">
              <h4>GLB files are for preview only</h4>
              <p>
                Orientation analysis requires STL or 3MF format. If available, select the STL or 3MF
                version of this model in Step 1, or skip this step to proceed with the original file.
              </p>
              <button
                type="button"
                className="orient-step__skip-btn"
                onClick={onSkipOrientation}
                disabled={isLoading}
              >
                Skip Orientation Step
              </button>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!selectedArtifact && !isLocked && (
          <div className="orient-step__empty">
            <p>Select a model in Step 1 to analyze print orientations</p>
          </div>
        )}

        {/* Dimensions info */}
        {orientationAnalysis && (
          <div className="orient-step__info">
            <div className="orient-step__info-item">
              <span className="orient-step__info-label">Model Size</span>
              <span className="orient-step__info-value">
                {orientationAnalysis.original_dimensions[0].toFixed(1)} x{' '}
                {orientationAnalysis.original_dimensions[1].toFixed(1)} x{' '}
                {orientationAnalysis.original_dimensions[2].toFixed(1)} mm
              </span>
            </div>
            <div className="orient-step__info-item">
              <span className="orient-step__info-label">Faces</span>
              <span className="orient-step__info-value">
                {orientationAnalysis.face_count.toLocaleString()}
              </span>
            </div>
            <div className="orient-step__info-item">
              <span className="orient-step__info-label">Analysis Time</span>
              <span className="orient-step__info-value">
                {orientationAnalysis.analysis_time_ms}ms
              </span>
            </div>
          </div>
        )}
      </div>
    </StepContainer>
  );
}

export default OrientStep;
