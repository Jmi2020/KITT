/**
 * ProviderSelector Component
 *
 * Dropdown selector for choosing LLM provider (local, OpenAI, Anthropic, etc.)
 * Displays provider status, models, and cost estimates.
 */

import { useState, useEffect } from 'react';
import './ProviderSelector.css';

export interface ProviderInfo {
  enabled: boolean;
  name: string;
  models: string[];
  cost_per_1m_tokens: {
    input: number;
    output: number;
  };
  icon: string;
  setup_url?: string;
}

export interface ProvidersResponse {
  providers: {
    [key: string]: ProviderInfo;
  };
}

interface ProviderSelectorProps {
  selectedProvider: string | null;
  selectedModel: string | null;
  onProviderChange: (provider: string | null, model: string | null) => void;
  apiBase?: string;
}

const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  selectedProvider,
  selectedModel,
  onProviderChange,
  apiBase = '',
}) => {
  const [providers, setProviders] = useState<ProvidersResponse | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch available providers
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${apiBase}/api/providers/available`);
        if (!response.ok) {
          throw new Error(`Failed to fetch providers: ${response.statusText}`);
        }
        const data = await response.json();
        setProviders(data);
        setError(null);
      } catch (err) {
        console.error('Error fetching providers:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchProviders();
  }, [apiBase]);

  const handleProviderSelect = (providerKey: string, modelName: string | null = null) => {
    if (providerKey === 'local') {
      onProviderChange(null, null);
    } else {
      const provider = providers?.providers[providerKey];
      const model = modelName || (provider?.models[0] ?? null);
      onProviderChange(providerKey, model);
    }
    setIsOpen(false);
  };

  const getCurrentProviderIcon = (): string => {
    if (!selectedProvider) return '🏠';
    const provider = providers?.providers[selectedProvider];
    return provider?.icon || '❓';
  };

  const getCurrentProviderLabel = (): string => {
    if (!selectedProvider) return 'Local (Q4)';
    const provider = providers?.providers[selectedProvider];
    if (!provider) return 'Unknown';
    return `${provider.name} ${selectedModel ? `(${selectedModel})` : ''}`;
  };

  const getCostEstimate = (providerKey: string): string => {
    const provider = providers?.providers[providerKey];
    if (!provider || providerKey === 'local') return 'Free';
    const avgCost = (provider.cost_per_1m_tokens.input + provider.cost_per_1m_tokens.output) / 2;
    return `~$${(avgCost / 1000).toFixed(4)}/1K`;
  };

  if (loading) {
    return (
      <div className="provider-selector loading">
        <button className="provider-selector-button" disabled>
          ⏳ Loading...
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="provider-selector error">
        <button className="provider-selector-button error" disabled>
          ❌ Error
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
        title="Select LLM provider"
      >
        <span className="provider-icon">{getCurrentProviderIcon()}</span>
        <span className="provider-label">{getCurrentProviderLabel()}</span>
        <span className="dropdown-arrow">{isOpen ? '▲' : '▼'}</span>
      </button>

      {isOpen && providers && (
        <div className="provider-dropdown">
          <div className="provider-dropdown-header">
            <span>Select Provider</span>
            <button className="close-button" onClick={() => setIsOpen(false)}>
              ×
            </button>
          </div>

          <div className="provider-list">
            {Object.entries(providers.providers).map(([key, provider]) => (
              <div
                key={key}
                className={`provider-option ${!provider.enabled ? 'disabled' : ''} ${
                  selectedProvider === (key === 'local' ? null : key) ? 'selected' : ''
                }`}
              >
                <div
                  className="provider-option-header"
                  onClick={() => provider.enabled && handleProviderSelect(key)}
                >
                  <span className="provider-icon-large">{provider.icon}</span>
                  <div className="provider-info">
                    <div className="provider-name">
                      {provider.name}
                      {!provider.enabled && <span className="disabled-badge">Disabled</span>}
                    </div>
                    <div className="provider-models">
                      {provider.models.slice(0, 2).join(', ')}
                      {provider.models.length > 2 && ` +${provider.models.length - 2} more`}
                    </div>
                  </div>
                  <div className="provider-cost">{getCostEstimate(key)}</div>
                </div>

                {!provider.enabled && provider.setup_url && (
                  <div className="provider-setup">
                    <a
                      href={provider.setup_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="setup-link"
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
              💡 Enable providers in I/O Control Dashboard
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProviderSelector;
