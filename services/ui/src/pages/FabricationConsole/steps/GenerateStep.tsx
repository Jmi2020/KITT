/**
 * GenerateStep - Step 1 of fabrication workflow
 *
 * Allows user to either:
 * - Generate a model using AI CAD providers (Tripo, Zoo, etc.)
 * - Import an existing 3MF/STL file
 *
 * Displays generated/imported artifacts with download links and thumbnails.
 */

import { useRef, ChangeEvent, DragEvent, useState } from 'react';
import { StepContainer } from '../../../components/FabricationWorkflow';
import { ArtifactBrowser } from '../components';
import {
  Artifact,
  GenerationProvider,
  GenerationMode,
  GenerationInputMode,
  translateArtifactPath,
} from '../hooks/useFabricationWorkflow';
import './GenerateStep.css';

interface Provider {
  id: GenerationProvider | string;
  name: string;
  description: string;
  available: boolean;
  icon?: string;
}

const PROVIDERS: Provider[] = [
  {
    id: 'meshy',
    name: 'Meshy.ai',
    description: 'AI 3D generation (text & image)',
    available: true,
    icon: '✨',
  },
  {
    id: 'tripo',
    name: 'Tripo',
    description: 'Organic shapes (backup)',
    available: true,
    icon: '🎨',
  },
  {
    id: 'zoo',
    name: 'Zoo (KittyCAD)',
    description: 'Mechanical & parametric parts',
    available: true,
    icon: '⚙️',
  },
  {
    id: 'hitem3d',
    name: 'Hitem3D',
    description: 'High-fidelity mesh generation',
    available: false,
    icon: '🔷',
  },
];

interface GenerateStepProps {
  // State
  provider: GenerationProvider;
  mode: GenerationMode;
  inputMode: GenerationInputMode;
  prompt: string;
  refineMode: boolean;
  imagePreview: string | null;
  artifacts: Artifact[];
  selectedArtifact: Artifact | null;
  isLoading: boolean;
  error: string | null;
  isActive: boolean;
  isCompleted: boolean;
  uploadProgress?: number; // 0-100 for file upload progress

  // Actions
  onProviderChange: (provider: GenerationProvider) => void;
  onModeChange: (mode: GenerationMode) => void;
  onInputModeChange: (inputMode: GenerationInputMode) => void;
  onPromptChange: (prompt: string) => void;
  onRefineChange: (refine: boolean) => void;
  onImageSelect: (file: File | null) => void;
  onClearImage: () => void;
  onGenerate: () => void;
  onImport: (file: File) => void;
  onSelectArtifact: (artifact: Artifact) => void;
  onSelectFromBrowser: (path: string, type: string) => void;
}

export function GenerateStep({
  provider,
  mode,
  inputMode,
  prompt,
  refineMode,
  imagePreview,
  artifacts,
  selectedArtifact,
  isLoading,
  error,
  isActive,
  isCompleted,
  uploadProgress = 0,
  onProviderChange,
  onModeChange,
  onInputModeChange,
  onPromptChange,
  onRefineChange,
  onImageSelect,
  onClearImage,
  onGenerate,
  onImport,
  onSelectArtifact,
  onSelectFromBrowser,
}: GenerateStepProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [imageDragOver, setImageDragOver] = useState(false);

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onImport(file);
    }
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && (file.name.endsWith('.3mf') || file.name.endsWith('.stl'))) {
      onImport(file);
    }
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      onGenerate();
    }
  };

  // Image upload handlers
  const handleImageSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type.startsWith('image/')) {
      onImageSelect(file);
    }
  };

  const handleImageDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setImageDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith('image/')) {
      onImageSelect(file);
    }
  };

  const handleImageDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setImageDragOver(true);
  };

  const handleImageDragLeave = () => {
    setImageDragOver(false);
  };

  // Check if image input is supported (only Meshy supports image-to-3D)
  const supportsImageInput = provider === 'meshy';

  return (
    <StepContainer
      stepNumber={1}
      title="Generate or Import"
      subtitle="Create a 3D model using AI or import an existing file"
      isActive={isActive}
      isCompleted={isCompleted}
      isLoading={isLoading}
      error={error}
      collapsible={isCompleted}
      helpText="Tripo: best for organic/artistic shapes. Zoo: best for mechanical/parametric parts."
    >
      <div className="generate-step">
        {/* Mode Toggle */}
        <div className="generate-step__mode-toggle" role="tablist">
          <button
            type="button"
            role="tab"
            className={`generate-step__mode-btn ${mode === 'generate' ? 'generate-step__mode-btn--active' : ''}`}
            onClick={() => onModeChange('generate')}
            aria-selected={mode === 'generate'}
          >
            <svg viewBox="0 0 24 24" className="generate-step__mode-icon">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Generate Model
          </button>
          <button
            type="button"
            role="tab"
            className={`generate-step__mode-btn ${mode === 'import' ? 'generate-step__mode-btn--active' : ''}`}
            onClick={() => onModeChange('import')}
            aria-selected={mode === 'import'}
          >
            <svg viewBox="0 0 24 24" className="generate-step__mode-icon">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Import File
          </button>
          <button
            type="button"
            role="tab"
            className={`generate-step__mode-btn ${mode === 'browse' ? 'generate-step__mode-btn--active' : ''}`}
            onClick={() => onModeChange('browse')}
            aria-selected={mode === 'browse'}
          >
            <svg viewBox="0 0 24 24" className="generate-step__mode-icon">
              <path d="M3 3h18v18H3V3z" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M3 9h18M9 21V9" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            Browse Storage
          </button>
        </div>

        {/* Generate Mode */}
        {mode === 'generate' && (
          <div className="generate-step__generate-panel" role="tabpanel">
            {/* Provider Selection */}
            <div className="generate-step__provider-section">
              <label className="generate-step__label">
                CAD Provider
                <span className="generate-step__label-hint">Choose based on model type</span>
              </label>
              <div className="generate-step__provider-grid">
                {PROVIDERS.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={`generate-step__provider-card ${provider === p.id ? 'generate-step__provider-card--selected' : ''} ${!p.available ? 'generate-step__provider-card--disabled' : ''}`}
                    onClick={() => p.available && onProviderChange(p.id as GenerationProvider)}
                    disabled={!p.available}
                    aria-pressed={provider === p.id}
                  >
                    <span className="generate-step__provider-icon">{p.icon}</span>
                    <span className="generate-step__provider-name">
                      {p.name}
                      {!p.available && <span className="generate-step__coming-soon">Coming Soon</span>}
                    </span>
                    <span className="generate-step__provider-desc">{p.description}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Input Mode Toggle (Meshy only) */}
            {supportsImageInput && (
              <div className="generate-step__input-mode-section">
                <label className="generate-step__label">
                  Input Type
                  <span className="generate-step__label-hint">Choose text or image input</span>
                </label>
                <div className="generate-step__input-mode-toggle">
                  <button
                    type="button"
                    className={`generate-step__input-mode-btn ${inputMode === 'text' ? 'generate-step__input-mode-btn--active' : ''}`}
                    onClick={() => onInputModeChange('text')}
                    disabled={isLoading}
                  >
                    <svg viewBox="0 0 24 24" className="generate-step__input-mode-icon">
                      <path d="M4 7V4h16v3M9 20h6M12 4v16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    Text to 3D
                  </button>
                  <button
                    type="button"
                    className={`generate-step__input-mode-btn ${inputMode === 'image' ? 'generate-step__input-mode-btn--active' : ''}`}
                    onClick={() => onInputModeChange('image')}
                    disabled={isLoading}
                  >
                    <svg viewBox="0 0 24 24" className="generate-step__input-mode-icon">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="none" stroke="currentColor" strokeWidth="2"/>
                      <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
                      <path d="M21 15l-5-5L5 21" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    Image to 3D
                  </button>
                </div>
              </div>
            )}

            {/* Text Input (default mode or when text mode selected) */}
            {inputMode === 'text' && (
              <div className="generate-step__prompt-section">
                <label className="generate-step__label" htmlFor="cad-prompt">
                  Model Description
                  <span className="generate-step__label-hint">Describe what you want to create</span>
                </label>
                <textarea
                  id="cad-prompt"
                  className="generate-step__textarea"
                  rows={4}
                  value={prompt}
                  onChange={(e) => onPromptChange(e.target.value)}
                  onKeyDown={handleKeyPress}
                  placeholder={
                    provider === 'zoo'
                      ? 'Describe the part (e.g., "2U rack faceplate with 80mm cable passthrough")'
                      : 'Describe the model (e.g., "A cat sitting on a pillow")'
                  }
                  disabled={isLoading}
                />
                <div className="generate-step__prompt-footer">
                  <span className="generate-step__shortcut">
                    <kbd>Cmd</kbd> + <kbd>Enter</kbd> to generate
                  </span>
                </div>
              </div>
            )}

            {/* Image Input (when image mode selected) */}
            {inputMode === 'image' && supportsImageInput && (
              <div className="generate-step__image-section">
                <label className="generate-step__label">
                  Reference Image
                  <span className="generate-step__label-hint">Upload an image to convert to 3D</span>
                </label>

                {!imagePreview ? (
                  /* Image Dropzone */
                  <div
                    className={`generate-step__image-dropzone ${imageDragOver ? 'generate-step__image-dropzone--dragover' : ''}`}
                    onDrop={handleImageDrop}
                    onDragOver={handleImageDragOver}
                    onDragLeave={handleImageDragLeave}
                  >
                    <input
                      ref={imageInputRef}
                      type="file"
                      accept="image/*"
                      onChange={handleImageSelect}
                      className="generate-step__file-input"
                      id="image-upload"
                      disabled={isLoading}
                    />
                    <label htmlFor="image-upload" className="generate-step__image-dropzone-content">
                      <svg viewBox="0 0 24 24" className="generate-step__image-upload-icon">
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="none" stroke="currentColor" strokeWidth="2"/>
                        <circle cx="8.5" cy="8.5" r="1.5" fill="currentColor"/>
                        <path d="M21 15l-5-5L5 21" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                      <span className="generate-step__image-dropzone-text">
                        Drag & drop an image here
                      </span>
                      <span className="generate-step__image-dropzone-hint">or click to browse</span>
                    </label>
                  </div>
                ) : (
                  /* Image Preview */
                  <div className="generate-step__image-preview">
                    <img src={imagePreview} alt="Selected reference" className="generate-step__preview-image" />
                    <button
                      type="button"
                      className="generate-step__clear-image-btn"
                      onClick={onClearImage}
                      disabled={isLoading}
                      title="Remove image"
                    >
                      <svg viewBox="0 0 24 24" className="generate-step__clear-icon">
                        <path d="M18 6L6 18M6 6l12 12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                      </svg>
                    </button>
                  </div>
                )}

                <p className="generate-step__image-note">
                  Supported: <strong>PNG</strong>, <strong>JPG</strong>, <strong>WEBP</strong> (max 10MB)
                </p>
              </div>
            )}

            {/* Refine Toggle (Meshy only, text-to-3D) */}
            {provider === 'meshy' && (
              <div className="generate-step__refine-section">
                <label className="generate-step__refine-toggle">
                  <input
                    type="checkbox"
                    checked={refineMode}
                    onChange={(e) => onRefineChange(e.target.checked)}
                    disabled={isLoading}
                  />
                  <span className="generate-step__refine-label">
                    Enable HD Refinement
                    <span className="generate-step__refine-hint">
                      Higher quality textures (slower)
                    </span>
                  </span>
                </label>
              </div>
            )}

            {/* Generate Button */}
            <button
              type="button"
              className="generate-step__generate-btn"
              onClick={onGenerate}
              disabled={isLoading || (inputMode === 'text' && !prompt.trim()) || (inputMode === 'image' && !imagePreview)}
            >
              {isLoading ? (
                <>
                  <span className="generate-step__spinner" />
                  {inputMode === 'image' ? 'Converting Image...' : 'Generating...'}
                </>
              ) : (
                <>
                  <svg viewBox="0 0 24 24" className="generate-step__btn-icon">
                    <path d="M12 2v4m0 12v4m10-10h-4M6 12H2m15.07-5.07l-2.83 2.83M9.76 14.24l-2.83 2.83m11.31 0l-2.83-2.83M9.76 9.76L6.93 6.93" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                  {inputMode === 'image' ? 'Convert to 3D' : 'Generate Model'}
                </>
              )}
            </button>
          </div>
        )}

        {/* Import Mode */}
        {mode === 'import' && (
          <div className="generate-step__import-panel" role="tabpanel">
            {isLoading ? (
              /* Upload Progress Display */
              <div className="generate-step__upload-progress">
                <div className="generate-step__upload-status">
                  <span className="generate-step__spinner" />
                  <span>Uploading file...</span>
                </div>
                <div className="generate-step__progress-bar">
                  <div
                    className="generate-step__progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <span className="generate-step__progress-text">{uploadProgress}%</span>
              </div>
            ) : (
              /* Dropzone */
              <>
                <div
                  className={`generate-step__dropzone ${dragOver ? 'generate-step__dropzone--dragover' : ''}`}
                  onDrop={handleDrop}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".3mf,.stl"
                    onChange={handleFileSelect}
                    className="generate-step__file-input"
                    id="model-upload"
                  />
                  <label htmlFor="model-upload" className="generate-step__dropzone-content">
                    <svg viewBox="0 0 24 24" className="generate-step__upload-icon">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    <span className="generate-step__dropzone-text">
                      Drag & drop a 3MF or STL file here
                    </span>
                    <span className="generate-step__dropzone-hint">or click to browse</span>
                  </label>
                </div>
                <p className="generate-step__import-note">
                  Supported formats: <strong>.3mf</strong> (preferred), <strong>.stl</strong>
                </p>
              </>
            )}
          </div>
        )}

        {/* Browse Mode */}
        {mode === 'browse' && (
          <div className="generate-step__browse-panel" role="tabpanel">
            <ArtifactBrowser onSelectArtifact={onSelectFromBrowser} />
          </div>
        )}

        {/* Artifacts Display */}
        {artifacts.length > 0 && (
          <div className="generate-step__artifacts">
            <h4 className="generate-step__artifacts-title">
              Generated Artifacts
              <span className="generate-step__artifact-count">{artifacts.length}</span>
            </h4>
            <ul className="generate-step__artifact-list">
              {artifacts.map((artifact, index) => {
                const glbUrl = artifact.metadata?.glb_location
                  ? translateArtifactPath(artifact.metadata.glb_location)
                  : null;
                const stlUrl = artifact.metadata?.stl_location
                  ? translateArtifactPath(artifact.metadata.stl_location)
                  : null;
                // 3MF can be location itself or stored in metadata
                const threemfPath = artifact.location?.endsWith('.3mf')
                  ? artifact.location
                  : artifact.metadata?.threemf_location || null;
                const threemfDownloadUrl = threemfPath
                  ? translateArtifactPath(threemfPath)
                  : null;
                const isSelected = selectedArtifact?.location === artifact.location;

                return (
                  <li
                    key={artifact.location}
                    className={`generate-step__artifact-item ${isSelected ? 'generate-step__artifact-item--selected' : ''}`}
                  >
                    <button
                      type="button"
                      className="generate-step__artifact-select"
                      onClick={() => onSelectArtifact(artifact)}
                      aria-pressed={isSelected}
                    >
                      <span className="generate-step__artifact-radio">
                        {isSelected && (
                          <svg viewBox="0 0 16 16" className="generate-step__check-icon">
                            <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 111.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
                          </svg>
                        )}
                      </span>
                      <span className="generate-step__artifact-info">
                        <span className="generate-step__artifact-name">
                          Model {index + 1}
                          <span className="generate-step__artifact-provider">
                            via {artifact.provider}
                          </span>
                        </span>
                        <span className="generate-step__artifact-type">
                          {artifact.artifactType.toUpperCase()}
                        </span>
                      </span>
                    </button>

                    <div className="generate-step__artifact-links">
                      {glbUrl && (
                        <a
                          href={glbUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="generate-step__format-link"
                          title="Download GLB for 3D preview"
                        >
                          <svg viewBox="0 0 16 16" className="generate-step__format-icon">
                            <path d="M8 0a8 8 0 100 16A8 8 0 008 0zM1.5 8a6.5 6.5 0 1113 0 6.5 6.5 0 01-13 0z"/>
                            <path d="M8 3.5v5l2.5 1.5"/>
                          </svg>
                          GLB
                        </a>
                      )}
                      {stlUrl && (
                        <a
                          href={stlUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="generate-step__format-link"
                          title="Download STL for slicer"
                        >
                          <svg viewBox="0 0 16 16" className="generate-step__format-icon">
                            <path d="M3.5 3.5v9h9v-9h-9z" fill="none" stroke="currentColor" strokeWidth="1.5"/>
                          </svg>
                          STL
                        </a>
                      )}
                      {threemfDownloadUrl && (
                        <a
                          href={threemfDownloadUrl}
                          download
                          className="generate-step__format-link generate-step__format-link--bambu"
                          title="Download 3MF for Bambu Studio"
                        >
                          <svg viewBox="0 0 16 16" className="generate-step__format-icon">
                            <path d="M8 1L2 4v8l6 3 6-3V4L8 1z" fill="none" stroke="currentColor" strokeWidth="1.2"/>
                            <path d="M2 4l6 3 6-3M8 7v8" fill="none" stroke="currentColor" strokeWidth="1.2"/>
                          </svg>
                          3MF
                        </a>
                      )}
                    </div>

                    {artifact.metadata?.thumbnail && (
                      <img
                        src={artifact.metadata.thumbnail}
                        alt="Model preview"
                        className="generate-step__artifact-thumb"
                        loading="lazy"
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </StepContainer>
  );
}

export default GenerateStep;
