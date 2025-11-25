/**
 * ProviderSelector Component
 *
 * Model selector for Shell page showing flat list of available models.
 * Includes inline toggles for enabling/disabling cloud providers via I/O Control.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import './ProviderSelector.css';

// New flat model interface matching backend /api/providers/models
export interface ModelInfo {
  id: string;
  name: string;
  type: 'local' | 'cloud';
  provider: string;
  enabled: boolean;
  default: boolean;
  icon: string;
  description: string;
  supports_vision?: boolean;
  supports_tools?: boolean;
  feature_flag?: string;
  cost?: string;
  setup_url?: string;
  huggingface_url?: string;
  docs_url?: string;
  parameters?: string;
  context_length?: string;
}

// Full model card information from /api/providers/models/{id}/card
export interface ModelCard {
  id: string;
  name: string;
  short_description: string;
  description: string;
  capabilities: string[];
  parameters: string;
  context_length: string;
  architecture: string;
  developer: string;
  license: string;
  huggingface_url?: string;
  docs_url?: string;
  release_date?: string;
  base_model?: string;
  quantization?: string;
  supports_vision: boolean;
  supports_tools: boolean;
  languages?: string[];
}

export interface ModelsResponse {
  models: ModelInfo[];
  default_model: string;
}

interface ProviderSelectorProps {
  selectedModel: string | null;
  onModelChange: (modelId: string) => void;
  onVisionModelSelected?: (isVision: boolean) => void;
  apiBase?: string;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  selectedModel,
  onModelChange,
  onVisionModelSelected,
  apiBase = '',
}) => {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState<string>('gpt-oss');
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingFeature, setTogglingFeature] = useState<string | null>(null);
  const initialLoadDone = useRef(false);

  // Model card modal state
  const [showModelCard, setShowModelCard] = useState(false);
  const [modelCard, setModelCard] = useState<ModelCard | null>(null);
  const [loadingCard, setLoadingCard] = useState(false);

  // Fetch available models
  const fetchModels = useCallback(async (isInitialLoad = false) => {
    try {
      setLoading(true);
      const response = await fetch(`${apiBase}/api/providers/models`);
      if (!response.ok) {
        throw new Error(`Failed to fetch models: ${response.statusText}`);
      }
      const data: ModelsResponse = await response.json();
      setModels(data.models);
      setDefaultModel(data.default_model);
      setError(null);

      // Auto-select default model only on initial load if none selected
      if (isInitialLoad && !selectedModel) {
        onModelChange(data.default_model);
      }
    } catch (err) {
      console.error('Error fetching models:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [apiBase]); // Remove selectedModel and onModelChange from deps

  useEffect(() => {
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      fetchModels(true);
    }
  }, [fetchModels, selectedModel, onModelChange]);

  // Notify parent when vision model is selected
  useEffect(() => {
    if (onVisionModelSelected && selectedModel) {
      const model = models.find(m => m.id === selectedModel);
      onVisionModelSelected(model?.supports_vision ?? false);
    }
  }, [selectedModel, models, onVisionModelSelected]);

  const handleModelSelect = (modelId: string) => {
    const model = models.find(m => m.id === modelId);
    if (model && model.enabled) {
      onModelChange(modelId);
      setIsOpen(false);
    }
  };

  // Toggle cloud provider via I/O Control API
  const handleToggleProvider = async (featureFlag: string, currentEnabled: boolean, e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger model selection

    setTogglingFeature(featureFlag);
    try {
      const response = await fetch(`${apiBase}/api/io-control/features/bulk-update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          changes: { [featureFlag]: !currentEnabled },
          persist: true
        })
      });

      if (!response.ok) {
        throw new Error('Failed to update feature');
      }

      // Refresh models list to get updated enabled state
      await fetchModels();
    } catch (err) {
      console.error('Error toggling provider:', err);
    } finally {
      setTogglingFeature(null);
    }
  };

  // Fetch detailed model card information
  const fetchModelCard = async (modelId: string) => {
    setLoadingCard(true);
    try {
      const response = await fetch(`${apiBase}/api/providers/models/${modelId}/card`);
      if (!response.ok) {
        throw new Error('Failed to fetch model card');
      }
      const data: ModelCard = await response.json();
      setModelCard(data);
      setShowModelCard(true);
    } catch (err) {
      console.error('Error fetching model card:', err);
      // Fallback to basic info from models list
      const model = models.find(m => m.id === modelId);
      if (model) {
        setModelCard({
          id: model.id,
          name: model.name,
          short_description: model.description,
          description: model.description,
          capabilities: [],
          parameters: model.parameters || 'Unknown',
          context_length: model.context_length || 'Unknown',
          architecture: 'Unknown',
          developer: model.provider,
          license: 'See documentation',
          huggingface_url: model.huggingface_url,
          docs_url: model.docs_url,
          supports_vision: model.supports_vision || false,
          supports_tools: model.supports_tools || false,
        });
        setShowModelCard(true);
      }
    } finally {
      setLoadingCard(false);
    }
  };

  const handleShowModelCard = (modelId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Don't trigger model selection
    fetchModelCard(modelId);
  };

  const getCurrentModel = (): ModelInfo | undefined => {
    return models.find(m => m.id === selectedModel);
  };

  const getCurrentModelLabel = (): string => {
    const model = getCurrentModel();
    if (!model) return 'Select Model';
    return model.name;
  };

  const getCurrentModelIcon = (): string => {
    const model = getCurrentModel();
    return model?.icon ?? '🤖';
  };

  const localModels = models.filter(m => m.type === 'local');
  const cloudModels = models.filter(m => m.type === 'cloud');

  if (loading) {
    return (
      <div className="provider-selector loading">
        <button className="provider-selector-button" disabled>
          <span className="provider-icon">⏳</span>
          <span className="provider-label">Loading...</span>
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="provider-selector error">
        <button className="provider-selector-button error" disabled>
          <span className="provider-icon">❌</span>
          <span className="provider-label">Error</span>
        </button>
        <div className="error-tooltip">{error}</div>
      </div>
    );
  }

  return (
    <div className="provider-selector">
      <button
        className="provider-selector-button"
        onClick={() => setIsOpen(!isOpen)}
        title="Select model"
      >
        <span className="provider-icon">{getCurrentModelIcon()}</span>
        <span className="provider-label">{getCurrentModelLabel()}</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && (
        <div className="provider-dropdown">
          <div className="provider-dropdown-header">
            <span>Select Model</span>
            <button className="close-button" onClick={() => setIsOpen(false)}>
              ×
            </button>
          </div>

          <div className="provider-list">
            {/* Local Models Section */}
            <div className="model-section-header">
              <span className="section-icon">🏠</span>
              <span>LOCAL MODELS</span>
              <span className="section-badge free">Free</span>
            </div>
            {localModels.map((model) => (
              <div
                key={model.id}
                className={`provider-option ${selectedModel === model.id ? 'selected' : ''}`}
                onClick={() => handleModelSelect(model.id)}
              >
                <div className="provider-option-header">
                  <span className="model-radio">
                    {selectedModel === model.id ? '●' : '○'}
                  </span>
                  <span className="provider-icon-large">{model.icon}</span>
                  <div className="provider-info">
                    <div className="provider-name">
                      {model.name}
                      {model.default && <span className="default-badge">Default</span>}
                      {model.supports_vision && <span className="vision-badge">Vision</span>}
                      {model.supports_tools && <span className="tools-badge">Tools</span>}
                    </div>
                    <div className="provider-models">
                      {model.description}
                      {model.parameters && <span className="model-params"> • {model.parameters}</span>}
                    </div>
                  </div>
                  <button
                    className="info-button"
                    onClick={(e) => handleShowModelCard(model.id, e)}
                    title="View model card"
                  >
                    ℹ️
                  </button>
                </div>
              </div>
            ))}

            {/* Cloud Models Section */}
            <div className="model-section-header cloud">
              <span className="section-icon">☁️</span>
              <span>CLOUD MODELS</span>
              <span className="section-badge paid">Paid</span>
            </div>
            {cloudModels.map((model) => (
              <div
                key={model.id}
                className={`provider-option ${!model.enabled ? 'disabled' : ''} ${
                  selectedModel === model.id ? 'selected' : ''
                }`}
                onClick={() => model.enabled && handleModelSelect(model.id)}
              >
                <div className="provider-option-header">
                  <span className="model-radio">
                    {selectedModel === model.id ? '●' : '○'}
                  </span>
                  <span className="provider-icon-large">{model.icon}</span>
                  <div className="provider-info">
                    <div className="provider-name">
                      {model.name}
                      {model.supports_vision && <span className="vision-badge">Vision</span>}
                      {model.supports_tools && <span className="tools-badge">Tools</span>}
                    </div>
                    <div className="provider-models">{model.description}</div>
                  </div>
                  <button
                    className="info-button"
                    onClick={(e) => handleShowModelCard(model.id, e)}
                    title="View model card"
                  >
                    ℹ️
                  </button>
                  <div className="cloud-model-actions">
                    <span className="provider-cost">{model.cost || 'Paid'}</span>
                    {model.feature_flag && (
                      <button
                        className={`toggle-switch ${model.enabled ? 'on' : 'off'} ${
                          togglingFeature === model.feature_flag ? 'toggling' : ''
                        }`}
                        onClick={(e) => handleToggleProvider(model.feature_flag!, model.enabled, e)}
                        disabled={togglingFeature === model.feature_flag}
                        title={model.enabled ? 'Disable provider' : 'Enable provider'}
                      >
                        <span className="toggle-slider"></span>
                        <span className="toggle-label">{model.enabled ? 'ON' : 'OFF'}</span>
                      </button>
                    )}
                  </div>
                </div>
                {!model.enabled && model.setup_url && (
                  <div className="provider-setup">
                    <a
                      href={model.setup_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="setup-link"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Get API Key →
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="provider-dropdown-footer">
            <div className="info-text">
              Toggle switches control providers via I/O Control
            </div>
          </div>
        </div>
      )}

      {/* Model Card Modal */}
      {showModelCard && modelCard && (
        <div className="model-card-overlay" onClick={() => setShowModelCard(false)}>
          <div className="model-card-modal" onClick={(e) => e.stopPropagation()}>
            <div className="model-card-header">
              <h2>{modelCard.name}</h2>
              <button className="close-button" onClick={() => setShowModelCard(false)}>×</button>
            </div>

            <div className="model-card-content">
              <p className="model-card-description">{modelCard.description}</p>

              <div className="model-card-specs">
                <div className="spec-row">
                  <span className="spec-label">Developer:</span>
                  <span className="spec-value">{modelCard.developer}</span>
                </div>
                <div className="spec-row">
                  <span className="spec-label">Parameters:</span>
                  <span className="spec-value">{modelCard.parameters}</span>
                </div>
                <div className="spec-row">
                  <span className="spec-label">Context Length:</span>
                  <span className="spec-value">{modelCard.context_length}</span>
                </div>
                <div className="spec-row">
                  <span className="spec-label">Architecture:</span>
                  <span className="spec-value">{modelCard.architecture}</span>
                </div>
                {modelCard.quantization && (
                  <div className="spec-row">
                    <span className="spec-label">Quantization:</span>
                    <span className="spec-value">{modelCard.quantization}</span>
                  </div>
                )}
                {modelCard.release_date && (
                  <div className="spec-row">
                    <span className="spec-label">Release Date:</span>
                    <span className="spec-value">{modelCard.release_date}</span>
                  </div>
                )}
                <div className="spec-row">
                  <span className="spec-label">License:</span>
                  <span className="spec-value">{modelCard.license}</span>
                </div>
              </div>

              {modelCard.capabilities && modelCard.capabilities.length > 0 && (
                <div className="model-card-capabilities">
                  <h3>Capabilities</h3>
                  <ul>
                    {modelCard.capabilities.map((cap, idx) => (
                      <li key={idx}>{cap}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="model-card-badges">
                {modelCard.supports_vision && <span className="badge vision">Vision</span>}
                {modelCard.supports_tools && <span className="badge tools">Tool Calling</span>}
              </div>

              <div className="model-card-links">
                {modelCard.huggingface_url && (
                  <a
                    href={modelCard.huggingface_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="model-card-link hf"
                  >
                    🤗 HuggingFace
                  </a>
                )}
                {modelCard.docs_url && (
                  <a
                    href={modelCard.docs_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="model-card-link docs"
                  >
                    📚 Documentation
                  </a>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Loading indicator for model card */}
      {loadingCard && (
        <div className="model-card-overlay">
          <div className="model-card-loading">
            <span>Loading model card...</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProviderSelector;
