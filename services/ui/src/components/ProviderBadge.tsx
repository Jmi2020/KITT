/**
 * ProviderBadge Component
 *
 * Displays which provider/model was used for a message, with cost information.
 * Shows on assistant messages to provide transparency.
 */

import './ProviderBadge.css';

export interface ProviderMetadata {
  provider_used?: string;
  model_used?: string;
  tokens_used?: number;
  cost_usd?: number;
  fallback_occurred?: boolean;
}

interface ProviderBadgeProps {
  metadata?: ProviderMetadata;
  compact?: boolean;
}

const PROVIDER_ICONS: Record<string, string> = {
  'local': '🏠',
  'local/q4': '🏠',
  'local/f16': '🏠',
  'local/coder': '🏠',
  'local/q4b': '🏠',
  'openai': '🤖',
  'anthropic': '🧠',
  'mistral': '🌀',
  'perplexity': '🔍',
  'gemini': '💎',
};

const getProviderIcon = (provider?: string): string => {
  if (!provider) return '🏠';
  const lowerProvider = provider.toLowerCase();
  return PROVIDER_ICONS[lowerProvider] || '❓';
};

const formatCost = (cost?: number): string => {
  if (!cost || cost === 0) return 'Free';
  if (cost < 0.0001) return '<$0.0001';
  return `$${cost.toFixed(4)}`;
};

const formatTokens = (tokens?: number): string => {
  if (!tokens || tokens === 0) return '0';
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}K`;
  return tokens.toString();
};

const ProviderBadge: React.FC<ProviderBadgeProps> = ({ metadata, compact = false }) => {
  if (!metadata) {
    // Default: Local provider
    return (
      <div className="provider-badge local">
        <span className="provider-icon">🏠</span>
        <span className="provider-name">Local</span>
      </div>
    );
  }

  const { provider_used, model_used, tokens_used, cost_usd, fallback_occurred } = metadata;

  const isLocal = !provider_used || provider_used.toLowerCase().includes('local');
  const providerIcon = getProviderIcon(provider_used);
  const providerLabel = provider_used || 'local/Q4';
  const modelLabel = model_used || 'Q4';

  if (compact) {
    return (
      <div className={`provider-badge compact ${isLocal ? 'local' : 'cloud'}`} title={`${providerLabel}/${modelLabel}`}>
        <span className="provider-icon">{providerIcon}</span>
      </div>
    );
  }

  return (
    <div className={`provider-badge ${isLocal ? 'local' : 'cloud'} ${fallback_occurred ? 'fallback' : ''}`}>
      <div className="provider-badge-header">
        <span className="provider-icon">{providerIcon}</span>
        <span className="provider-info">
          <span className="provider-name">{providerLabel}</span>
          {model_used && <span className="model-name"> / {modelLabel}</span>}
        </span>
      </div>

      {!isLocal && (tokens_used !== undefined || cost_usd !== undefined) && (
        <div className="provider-badge-stats">
          {tokens_used !== undefined && (
            <span className="stat tokens" title={`${tokens_used} tokens`}>
              📊 {formatTokens(tokens_used)}
            </span>
          )}
          {cost_usd !== undefined && (
            <span className="stat cost" title={`Cost: ${formatCost(cost_usd)}`}>
              💰 {formatCost(cost_usd)}
            </span>
          )}
        </div>
      )}

      {fallback_occurred && (
        <div className="fallback-notice" title="Requested provider unavailable, fell back to local">
          ⚠️ Fallback
        </div>
      )}
    </div>
  );
};

export default ProviderBadge;
