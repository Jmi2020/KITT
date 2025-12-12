/**
 * New Research Tab - Query Form
 * Creates new research sessions with configurable options
 */

import { useState } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { ResearchSession } from '../../../types/research';

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

      <div className="form-group checkbox-group">
        <label htmlFor="enablePaidTools">
          <input
            type="checkbox"
            id="enablePaidTools"
            checked={enablePaidTools}
            onChange={(e) => setEnablePaidTools(e.target.checked)}
            disabled={api.loading}
          />
          <span>Enable paid tools (Perplexity for deep research)</span>
        </label>
        <small>
          {enablePaidTools
            ? 'Research will use Perplexity API when beneficial (higher cost but better quality)'
            : 'Using free tools only (Brave Search, SearXNG, Jina Reader)'}
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
