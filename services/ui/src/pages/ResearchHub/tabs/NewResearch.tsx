/**
 * New Research Tab - Query Form
 * Creates new research sessions with configurable options
 *
 * Enhanced with search provider selection following the
 * Collective Intelligence specialist pattern.
 */

import { useState, useEffect, useCallback } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { ResearchSession } from '../../../types/research';

interface SearchProvider {
  id: string;
  name: string;
  provider_type: string;
  cost_per_query: number;
  description: string;
  icon: string;
  is_available: boolean;
  is_free: boolean;
  max_results_per_query: number;
}

interface CostEstimate {
  total_queries: number;
  total_cost_usd: number;
  breakdown: Record<string, { name: string; queries: number; cost_usd: number }>;
  is_valid: boolean;
  validation_error?: string;
}

interface NewResearchProps {
  api: UseResearchApiReturn;
  onSessionCreated: (session: ResearchSession) => void;
}

const NewResearch = ({ api, onSessionCreated }: NewResearchProps) => {
  const [query, setQuery] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [maxIterations, setMaxIterations] = useState(10);
  const [maxCost, setMaxCost] = useState(2.0);
  const [strategy, setStrategy] = useState('hybrid');
  const [enablePaidTools, setEnablePaidTools] = useState(false);
  const [enableHierarchical, setEnableHierarchical] = useState(false);
  const [maxSubQuestions, setMaxSubQuestions] = useState(5);

  // Search provider selection state
  const [providers, setProviders] = useState<SearchProvider[]>([]);
  const [selectedProviders, setSelectedProviders] = useState<string[]>(['duckduckgo']);
  const [costEstimate, setCostEstimate] = useState<CostEstimate | null>(null);
  const [showAdvancedProviders, setShowAdvancedProviders] = useState(false);

  // Fetch available providers on mount
  useEffect(() => {
    const fetchProviders = async () => {
      try {
        const response = await fetch('/api/research/providers');
        if (response.ok) {
          const data = await response.json();
          setProviders(data.providers || []);
          // Default to free providers
          setSelectedProviders(data.default || ['duckduckgo']);
        }
      } catch (err) {
        console.error('Failed to fetch search providers:', err);
      }
    };
    fetchProviders();
  }, []);

  // Update cost estimate when selection changes
  const updateCostEstimate = useCallback(async () => {
    if (selectedProviders.length === 0) {
      setCostEstimate(null);
      return;
    }
    try {
      const response = await fetch('/api/research/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider_ids: selectedProviders,
          max_iterations: maxIterations,
          queries_per_iteration: 5,
        }),
      });
      if (response.ok) {
        const estimate = await response.json();
        setCostEstimate(estimate);
      }
    } catch (err) {
      console.error('Failed to estimate cost:', err);
    }
  }, [selectedProviders, maxIterations]);

  useEffect(() => {
    updateCostEstimate();
  }, [updateCostEstimate]);

  // Toggle provider selection
  const toggleProvider = (providerId: string) => {
    setSelectedProviders((prev) => {
      if (prev.includes(providerId)) {
        // Don't allow deselecting the last provider
        if (prev.length === 1) return prev;
        return prev.filter((p) => p !== providerId);
      } else {
        return [...prev, providerId];
      }
    });
  };

  const handleTemplateChange = (templateType: string) => {
    setSelectedTemplate(templateType);

    const template = api.templates.find((t) => t.type === templateType);
    if (template) {
      setMaxIterations(template.max_iterations);
    }
  };

  const handleSubmit = async () => {
    const session = await api.createSession({
      query,
      strategy,
      maxIterations,
      maxCost,
      enablePaidTools,
      enableHierarchical,
      maxSubQuestions,
      template: selectedTemplate || undefined,
    });

    if (session) {
      onSessionCreated(session);
      setQuery('');
    }
  };

  return (
    <div className="new-research-tab">
      <h2>Start New Research</h2>

      <div className="form-group">
        <label htmlFor="template">Research Template</label>
        <select
          id="template"
          value={selectedTemplate}
          onChange={(e) => handleTemplateChange(e.target.value)}
          disabled={api.loading}
        >
          <option value="">Auto-detect (recommended)</option>
          {api.templates.map((template) => (
            <option key={template.type} value={template.type}>
              {template.name} - {template.description}
            </option>
          ))}
        </select>
        <small>
          {selectedTemplate
            ? `Using ${api.templates.find((t) => t.type === selectedTemplate)?.name} template`
            : 'Template will be auto-detected from your query'}
        </small>
      </div>

      <div className="form-group">
        <label htmlFor="query">Research Query</label>
        <textarea
          id="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="What would you like to research? (min. 10 characters)"
          rows={4}
          disabled={api.loading}
        />
        <small>{query.length}/10 characters minimum</small>
      </div>

      <div className="form-group">
        <label htmlFor="strategy">Research Strategy</label>
        <select
          id="strategy"
          value={strategy}
          onChange={(e) => setStrategy(e.target.value)}
          disabled={api.loading}
        >
          <option value="hybrid">Hybrid (Recommended)</option>
          <option value="breadth_first">Breadth First - Wide coverage</option>
          <option value="depth_first">Depth First - Deep dive</option>
          <option value="task_decomposition">Task Decomposition - Break down complex queries</option>
        </select>
        <small>Strategy determines how research is conducted</small>
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="maxIterations">Max Iterations</label>
          <input
            type="number"
            id="maxIterations"
            value={maxIterations}
            onChange={(e) => setMaxIterations(parseInt(e.target.value) || 10)}
            min={1}
            max={50}
            disabled={api.loading}
          />
          <small>Research depth (1-50)</small>
        </div>

        <div className="form-group">
          <label htmlFor="maxCost">Max Cost (USD)</label>
          <input
            type="number"
            id="maxCost"
            value={maxCost}
            onChange={(e) => setMaxCost(parseFloat(e.target.value) || 2.0)}
            min={0.1}
            max={10}
            step={0.1}
            disabled={api.loading}
          />
          <small>Budget limit ($0.10-$10.00)</small>
        </div>
      </div>

      {/* Search Provider Selection */}
      <div className="form-group provider-selection">
        <div className="provider-header">
          <label>Search Providers</label>
          <button
            type="button"
            className="btn-link"
            onClick={() => setShowAdvancedProviders(!showAdvancedProviders)}
          >
            {showAdvancedProviders ? 'Simple' : 'Advanced'}
          </button>
        </div>

        {!showAdvancedProviders ? (
          // Simple mode - just show free vs paid toggle
          <div className="provider-simple">
            <div className="provider-chips">
              {providers.filter(p => p.is_free).map((provider) => (
                <button
                  key={provider.id}
                  type="button"
                  className={`provider-chip ${selectedProviders.includes(provider.id) ? 'selected' : ''}`}
                  onClick={() => toggleProvider(provider.id)}
                  disabled={api.loading}
                  title={provider.description}
                >
                  <span className="provider-icon">{provider.icon}</span>
                  <span className="provider-name">{provider.name}</span>
                  <span className="provider-badge free">Free</span>
                </button>
              ))}
            </div>
            <small>
              Selected: {selectedProviders.length} provider(s).
              {costEstimate && costEstimate.total_cost_usd > 0
                ? ` Estimated cost: $${costEstimate.total_cost_usd.toFixed(4)}`
                : ' Free'}
            </small>
          </div>
        ) : (
          // Advanced mode - show all providers with checkboxes
          <div className="provider-advanced">
            <div className="provider-group">
              <h4>Free Providers</h4>
              <div className="provider-list">
                {providers.filter(p => p.is_free).map((provider) => (
                  <label
                    key={provider.id}
                    className={`provider-option ${!provider.is_available ? 'unavailable' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedProviders.includes(provider.id)}
                      onChange={() => toggleProvider(provider.id)}
                      disabled={api.loading || !provider.is_available}
                    />
                    <span className="provider-icon">{provider.icon}</span>
                    <span className="provider-info">
                      <span className="provider-name">{provider.name}</span>
                      <span className="provider-desc">{provider.description}</span>
                    </span>
                    {provider.is_available ? (
                      <span className="provider-status available">Available</span>
                    ) : (
                      <span className="provider-status unavailable">Not configured</span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            <div className="provider-group">
              <h4>Paid Providers</h4>
              <div className="provider-list">
                {providers.filter(p => !p.is_free).map((provider) => (
                  <label
                    key={provider.id}
                    className={`provider-option ${!provider.is_available ? 'unavailable' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedProviders.includes(provider.id)}
                      onChange={() => toggleProvider(provider.id)}
                      disabled={api.loading || !provider.is_available}
                    />
                    <span className="provider-icon">{provider.icon}</span>
                    <span className="provider-info">
                      <span className="provider-name">{provider.name}</span>
                      <span className="provider-desc">{provider.description}</span>
                      <span className="provider-cost">
                        ${(provider.cost_per_query * 1000).toFixed(2)}/1K queries
                      </span>
                    </span>
                    {provider.is_available ? (
                      <span className="provider-status available">API Key Set</span>
                    ) : (
                      <span className="provider-status unavailable">Missing API Key</span>
                    )}
                  </label>
                ))}
              </div>
            </div>

            {/* Cost Estimate */}
            {costEstimate && costEstimate.is_valid && (
              <div className="cost-estimate">
                <strong>Estimated Cost:</strong>
                <span className="estimate-value">
                  ~${costEstimate.total_cost_usd.toFixed(4)}
                </span>
                <span className="estimate-queries">
                  ({costEstimate.total_queries} queries)
                </span>
              </div>
            )}
            {costEstimate && !costEstimate.is_valid && (
              <div className="cost-estimate error">
                {costEstimate.validation_error}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="form-group checkbox-group">
        <label htmlFor="enablePaidTools">
          <input
            type="checkbox"
            id="enablePaidTools"
            checked={enablePaidTools}
            onChange={(e) => setEnablePaidTools(e.target.checked)}
            disabled={api.loading}
          />
          <span>Enable paid LLM tools (Perplexity for deep research)</span>
        </label>
        <small>
          {enablePaidTools
            ? 'Research will use Perplexity API when beneficial (higher cost but better quality)'
            : 'Using local LLM models only for analysis'}
        </small>
      </div>

      <div className="form-group checkbox-group">
        <label htmlFor="enableHierarchical">
          <input
            type="checkbox"
            id="enableHierarchical"
            checked={enableHierarchical}
            onChange={(e) => setEnableHierarchical(e.target.checked)}
            disabled={api.loading}
          />
          <span>Enable hierarchical research (multi-stage synthesis)</span>
        </label>
        <small>
          {enableHierarchical
            ? 'Will decompose complex questions into sub-questions, research each independently, and synthesize into comprehensive answer'
            : 'Standard single-stage research and synthesis'}
        </small>
      </div>

      {enableHierarchical && (
        <div className="form-group">
          <label htmlFor="maxSubQuestions">
            Max Sub-Questions (2-5)
            <input
              type="number"
              id="maxSubQuestions"
              min="2"
              max="5"
              value={maxSubQuestions}
              onChange={(e) =>
                setMaxSubQuestions(Math.min(5, Math.max(2, parseInt(e.target.value) || 5)))
              }
              disabled={api.loading}
            />
          </label>
          <small>
            Number of sub-questions to break down the query into (higher = more detailed analysis)
          </small>
        </div>
      )}

      <button
        className="btn-primary"
        onClick={handleSubmit}
        disabled={api.loading || query.length < 10}
      >
        {api.loading ? 'Creating Session...' : 'Start Research'}
      </button>
    </div>
  );
};

export default NewResearch;
