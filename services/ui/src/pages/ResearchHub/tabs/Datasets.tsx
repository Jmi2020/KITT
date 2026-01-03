/**
 * Datasets Tab - Topic Management & Paper Harvesting
 *
 * Create research topics, harvest academic papers, and generate training datasets
 * for domain expert fine-tuning.
 */

import { useState, useEffect, useCallback } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { ResearchTopic, HarvestProgressEvent } from '../../../types/research';
import TopicCard from '../components/TopicCard';
import HarvestProgress from '../components/HarvestProgress';
import './Datasets.css';

// Available academic sources
const SOURCES = [
  { id: 'arxiv', name: 'arXiv', description: 'Open-access preprints (no API key required)', icon: '📚' },
  { id: 'pubmed', name: 'PubMed', description: 'Biomedical & life sciences (NCBI API key)', icon: '🔬' },
  { id: 'core', name: 'CORE', description: 'Open access research (CORE API key)', icon: '🌐' },
  { id: 'semantic_scholar', name: 'Semantic Scholar', description: 'AI-curated papers (S2 API key)', icon: '🧠' },
];

interface DatasetsTabProps {
  api: UseResearchApiReturn;
}

const DatasetsTab = ({ api }: DatasetsTabProps) => {
  // Form state
  const [topicName, setTopicName] = useState('');
  const [topicDescription, setTopicDescription] = useState('');
  const [selectedSources, setSelectedSources] = useState<string[]>(['arxiv']);
  const [maxPapers, setMaxPapers] = useState(100);

  // Harvest progress state
  const [harvestingTopic, setHarvestingTopic] = useState<string | null>(null);
  const [harvestProgress, setHarvestProgress] = useState<HarvestProgressEvent | null>(null);

  // Load topics on mount
  useEffect(() => {
    api.loadTopics();
  }, [api.loadTopics]);

  // Toggle source selection
  const toggleSource = (sourceId: string) => {
    setSelectedSources((prev) => {
      if (prev.includes(sourceId)) {
        if (prev.length === 1) return prev; // Keep at least one
        return prev.filter((s) => s !== sourceId);
      }
      return [...prev, sourceId];
    });
  };

  // Create topic
  const handleCreateTopic = async () => {
    if (!topicName.trim()) return;

    const topic = await api.createTopic({
      name: topicName.trim(),
      description: topicDescription.trim() || undefined,
      sources: selectedSources,
      max_papers: maxPapers,
    });

    if (topic) {
      setTopicName('');
      setTopicDescription('');
      // Keep sources and maxPapers for convenience
    }
  };

  // Start harvest for topic
  const handleStartHarvest = useCallback(async (topicId: string) => {
    setHarvestingTopic(topicId);
    setHarvestProgress(null);

    // Connect to WebSocket for progress updates
    api.connectHarvestWebSocket(topicId, (update) => {
      setHarvestProgress(update);

      // Refresh topics when complete
      if (update.phase === 'building' || update.error) {
        api.loadTopics();
        if (update.error) {
          setHarvestingTopic(null);
        }
      }
    });

    // Start the harvest
    await api.startHarvest(topicId);
  }, [api]);

  // Close harvest progress overlay
  const handleCloseHarvest = useCallback(() => {
    api.disconnectHarvestWebSocket();
    setHarvestingTopic(null);
    setHarvestProgress(null);
    api.loadTopics();
  }, [api]);

  // Calculate stats
  const stats = {
    totalTopics: api.topics.length,
    papersHarvested: api.topics.reduce((sum, t) => sum + t.papers_harvested, 0),
    claimsExtracted: api.topics.reduce((sum, t) => sum + t.claims_extracted, 0),
    datasetEntries: api.topics.reduce((sum, t) => sum + t.dataset_entries, 0),
    readyForTraining: api.topics.filter((t) => t.dataset_entries >= 5000).length,
  };

  return (
    <div className="datasets-tab">
      {/* Stats Header */}
      <div className="datasets-stats">
        <div className="stat-card">
          <div className="stat-value">{stats.totalTopics}</div>
          <div className="stat-label">Topics</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.papersHarvested}</div>
          <div className="stat-label">Papers</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.claimsExtracted}</div>
          <div className="stat-label">Claims</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.datasetEntries}</div>
          <div className="stat-label">Dataset Entries</div>
        </div>
        <div className="stat-card highlight">
          <div className="stat-value">{stats.readyForTraining}</div>
          <div className="stat-label">Ready for Training</div>
        </div>
      </div>

      {/* Create Topic Form */}
      <div className="create-topic-section">
        <h3>Create New Research Topic</h3>

        <div className="form-group">
          <label htmlFor="topicName">Topic Name</label>
          <input
            type="text"
            id="topicName"
            value={topicName}
            onChange={(e) => setTopicName(e.target.value)}
            placeholder="e.g., metal additive manufacturing defect detection"
            disabled={api.loading}
          />
        </div>

        <div className="form-group">
          <label htmlFor="topicDescription">Description (optional)</label>
          <textarea
            id="topicDescription"
            value={topicDescription}
            onChange={(e) => setTopicDescription(e.target.value)}
            placeholder="Additional context or keywords for paper search..."
            rows={2}
            disabled={api.loading}
          />
        </div>

        <div className="form-group">
          <label>Academic Sources</label>
          <div className="source-chips">
            {SOURCES.map((source) => (
              <button
                key={source.id}
                type="button"
                className={`source-chip ${selectedSources.includes(source.id) ? 'selected' : ''}`}
                onClick={() => toggleSource(source.id)}
                disabled={api.loading}
                title={source.description}
              >
                <span className="source-icon">{source.icon}</span>
                <span className="source-name">{source.name}</span>
              </button>
            ))}
          </div>
          <small>Selected: {selectedSources.length} source(s)</small>
        </div>

        <div className="form-group">
          <label htmlFor="maxPapers">Max Papers to Harvest</label>
          <input
            type="number"
            id="maxPapers"
            value={maxPapers}
            onChange={(e) => setMaxPapers(parseInt(e.target.value) || 100)}
            min={10}
            max={1000}
            step={10}
            disabled={api.loading}
          />
          <small>Recommended: 100-500 papers for good dataset coverage</small>
        </div>

        <button
          className="btn-primary"
          onClick={handleCreateTopic}
          disabled={api.loading || !topicName.trim()}
        >
          {api.loading ? 'Creating...' : 'Create Topic'}
        </button>
      </div>

      {/* Topic List */}
      <div className="topics-section">
        <h3>Research Topics</h3>

        {api.topics.length === 0 ? (
          <div className="empty-state">
            <p>No research topics yet. Create one above to start harvesting papers.</p>
          </div>
        ) : (
          <div className="topics-grid">
            {api.topics.map((topic) => (
              <TopicCard
                key={topic.topic_id}
                topic={topic}
                onStartHarvest={() => handleStartHarvest(topic.topic_id)}
                isHarvesting={harvestingTopic === topic.topic_id}
                disabled={api.loading}
              />
            ))}
          </div>
        )}
      </div>

      {/* Harvest Progress Overlay */}
      {harvestingTopic && (
        <HarvestProgress
          topic={api.topics.find((t) => t.topic_id === harvestingTopic)}
          progress={harvestProgress}
          onClose={handleCloseHarvest}
        />
      )}

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

export default DatasetsTab;
