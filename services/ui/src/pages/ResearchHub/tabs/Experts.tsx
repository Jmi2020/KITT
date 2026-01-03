/**
 * Experts Tab - Expert Model Browser
 *
 * Browse trained domain expert models, activate/deactivate for inference,
 * and manage model lifecycle.
 */

import { useState, useEffect } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import ExpertCard from '../components/ExpertCard';
import './Experts.css';

interface ExpertsTabProps {
  api: UseResearchApiReturn;
}

const ExpertsTab = ({ api }: ExpertsTabProps) => {
  // Filter state
  const [showActiveOnly, setShowActiveOnly] = useState(false);
  const [topicFilter, setTopicFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState<'created' | 'samples' | 'loss'>('created');

  // Load data on mount
  useEffect(() => {
    api.loadExperts();
  }, [api.loadExperts]);

  // Get unique topics for filter dropdown
  const uniqueTopics = [...new Set(api.experts.map((e) => e.topic_name))];

  // Filter and sort experts
  const filteredExperts = api.experts
    .filter((expert) => {
      if (showActiveOnly && !expert.is_active) return false;
      if (topicFilter && expert.topic_name !== topicFilter) return false;
      return true;
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'samples':
          return b.training_samples - a.training_samples;
        case 'loss':
          return a.final_loss - b.final_loss;
        case 'created':
        default:
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
    });

  // Stats
  const stats = {
    totalExperts: api.experts.length,
    activeExperts: api.experts.filter((e) => e.is_active).length,
    totalSamples: api.experts.reduce((sum, e) => sum + e.training_samples, 0),
    avgLoss: api.experts.length
      ? (api.experts.reduce((sum, e) => sum + e.final_loss, 0) / api.experts.length).toFixed(4)
      : '0.0000',
  };

  // Handle actions
  const handleActivate = async (modelId: string) => {
    await api.activateExpert(modelId);
  };

  const handleDeactivate = async (modelId: string) => {
    await api.deactivateExpert(modelId);
  };

  const handleDelete = async (modelId: string) => {
    if (window.confirm('Are you sure you want to delete this expert model? This cannot be undone.')) {
      await api.deleteExpert(modelId);
    }
  };

  return (
    <div className="experts-tab">
      {/* Stats Header */}
      <div className="experts-stats">
        <div className="stat-card">
          <div className="stat-value">{stats.totalExperts}</div>
          <div className="stat-label">Total Experts</div>
        </div>
        <div className="stat-card highlight">
          <div className="stat-value">{stats.activeExperts}</div>
          <div className="stat-label">Active</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.totalSamples.toLocaleString()}</div>
          <div className="stat-label">Training Samples</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.avgLoss}</div>
          <div className="stat-label">Avg. Loss</div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="experts-filters">
        <div className="filter-group">
          <label className="toggle-filter">
            <input
              type="checkbox"
              checked={showActiveOnly}
              onChange={(e) => setShowActiveOnly(e.target.checked)}
            />
            <span>Active Only</span>
          </label>
        </div>

        <div className="filter-group">
          <label htmlFor="topicFilter">Topic:</label>
          <select
            id="topicFilter"
            value={topicFilter}
            onChange={(e) => setTopicFilter(e.target.value)}
          >
            <option value="">All Topics</option>
            {uniqueTopics.map((topic) => (
              <option key={topic} value={topic}>
                {topic}
              </option>
            ))}
          </select>
        </div>

        <div className="filter-group">
          <label htmlFor="sortBy">Sort by:</label>
          <select
            id="sortBy"
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          >
            <option value="created">Newest First</option>
            <option value="samples">Most Samples</option>
            <option value="loss">Lowest Loss</option>
          </select>
        </div>

        <button className="btn-refresh" onClick={() => api.loadExperts()}>
          Refresh
        </button>
      </div>

      {/* Experts Grid */}
      {filteredExperts.length === 0 ? (
        <div className="empty-state">
          {api.experts.length === 0 ? (
            <p>No expert models yet. Complete fine-tuning to create your first expert.</p>
          ) : (
            <p>No experts match the current filters.</p>
          )}
        </div>
      ) : (
        <div className="experts-grid">
          {filteredExperts.map((expert) => (
            <ExpertCard
              key={expert.model_id}
              expert={expert}
              onActivate={() => handleActivate(expert.model_id)}
              onDeactivate={() => handleDeactivate(expert.model_id)}
              onDelete={() => handleDelete(expert.model_id)}
              disabled={api.loading}
            />
          ))}
        </div>
      )}

      {/* Usage Info */}
      <div className="experts-info">
        <h4>Using Expert Models</h4>
        <p>
          Active experts are automatically loaded when their topic is detected in queries.
          You can also explicitly invoke them using the <code>/expert:topic_name</code> syntax.
        </p>
        <ul>
          <li>
            <strong>Activate</strong> - Load the model for inference
          </li>
          <li>
            <strong>Deactivate</strong> - Unload to free memory
          </li>
          <li>
            <strong>Delete</strong> - Permanently remove model files
          </li>
        </ul>
      </div>

      {/* Error Display */}
      {api.error && (
        <div className="error-banner">
          <span>{api.error}</span>
          <button onClick={api.clearError}>Dismiss</button>
        </div>
      )}
    </div>
  );
};

export default ExpertsTab;
