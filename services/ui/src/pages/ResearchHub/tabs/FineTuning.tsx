/**
 * Fine-Tuning Tab - Training Job Management
 *
 * Start fine-tuning jobs, monitor training progress, and manage completed models.
 */

import { useState, useEffect, useCallback } from 'react';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { FinetuneJob, FinetuneConfig, TrainingProgressEvent } from '../../../types/research';
import FinetuneJobCard from '../components/FinetuneJobCard';
import TrainingProgress from '../components/TrainingProgress';
import './FineTuning.css';

interface FineTuningTabProps {
  api: UseResearchApiReturn;
}

const DEFAULT_CONFIG: FinetuneConfig = {
  epochs: 3,
  batch_size: 4,
  learning_rate: 0.0001,
  lora_rank: 16,
  export_gguf: true,
};

const FineTuningTab = ({ api }: FineTuningTabProps) => {
  // Form state
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [config, setConfig] = useState<FinetuneConfig>(DEFAULT_CONFIG);

  // Training progress state
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [trainingProgress, setTrainingProgress] = useState<TrainingProgressEvent | null>(null);

  // Load data on mount
  useEffect(() => {
    api.loadTopics();
    api.loadFinetuneJobs();
    api.loadMemoryMode();
  }, [api.loadTopics, api.loadFinetuneJobs, api.loadMemoryMode]);

  // Filter topics ready for training (>= 5000 entries)
  const eligibleTopics = api.topics.filter((t) => t.dataset_entries >= 5000);

  // Start fine-tuning
  const handleStartFinetune = async () => {
    if (!selectedTopicId) return;

    const job = await api.startFinetune(selectedTopicId, config);

    if (job) {
      setActiveJobId(job.job_id);

      // Connect to training WebSocket
      api.connectTrainingWebSocket(job.job_id, (update) => {
        setTrainingProgress(update);

        // Refresh jobs when complete
        if (update.phase === 'converting' || update.error) {
          api.loadFinetuneJobs();
          api.loadExperts();
          if (update.error) {
            setActiveJobId(null);
          }
        }
      });
    }
  };

  // Close training progress
  const handleCloseProgress = useCallback(() => {
    api.disconnectTrainingWebSocket();
    setActiveJobId(null);
    setTrainingProgress(null);
    api.loadFinetuneJobs();
  }, [api]);

  // Update config field
  const updateConfig = (field: keyof FinetuneConfig, value: number | boolean) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  // Separate jobs by status
  const activeJobs = api.finetuneJobs.filter(
    (j) => !['completed', 'failed'].includes(j.status)
  );
  const completedJobs = api.finetuneJobs.filter((j) => j.status === 'completed');
  const failedJobs = api.finetuneJobs.filter((j) => j.status === 'failed');

  // Stats
  const stats = {
    activeJobs: activeJobs.length,
    completedModels: completedJobs.length,
    failedJobs: failedJobs.length,
    memoryMode: api.memoryMode?.mode || 'unknown',
    canFinetune: api.memoryMode?.can_transition_to?.includes('finetune') ?? false,
  };

  return (
    <div className="finetune-tab">
      {/* Stats Header */}
      <div className="finetune-stats">
        <div className="stat-card">
          <div className="stat-value">{stats.activeJobs}</div>
          <div className="stat-label">Active Jobs</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.completedModels}</div>
          <div className="stat-label">Completed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.failedJobs}</div>
          <div className="stat-label">Failed</div>
        </div>
        <div className={`stat-card memory-mode ${stats.memoryMode}`}>
          <div className="stat-value">{stats.memoryMode.toUpperCase()}</div>
          <div className="stat-label">Memory Mode</div>
        </div>
      </div>

      {/* Memory Mode Warning */}
      {!stats.canFinetune && api.memoryMode && (
        <div className="memory-warning">
          <span className="warning-icon">⚠️</span>
          <span>
            Fine-tuning requires FINETUNE memory mode (~210GB). Current mode:{' '}
            <strong>{api.memoryMode.mode.toUpperCase()}</strong> using{' '}
            {api.memoryMode.memory_used_gb.toFixed(1)}GB.
          </span>
          <button
            className="btn-secondary"
            onClick={() => api.setMemoryMode('finetune')}
            disabled={api.loading}
          >
            Switch to FINETUNE Mode
          </button>
        </div>
      )}

      {/* Start Training Form */}
      <div className="start-training-section">
        <h3>Start Fine-Tuning</h3>

        <div className="form-group">
          <label htmlFor="topicSelect">Select Topic</label>
          <select
            id="topicSelect"
            value={selectedTopicId}
            onChange={(e) => setSelectedTopicId(e.target.value)}
            disabled={api.loading || eligibleTopics.length === 0}
          >
            <option value="">-- Select a topic --</option>
            {eligibleTopics.map((topic) => (
              <option key={topic.topic_id} value={topic.topic_id}>
                {topic.name} ({topic.dataset_entries.toLocaleString()} entries)
              </option>
            ))}
          </select>
          {eligibleTopics.length === 0 && (
            <small className="warning">
              No topics with 5000+ entries. Build datasets first.
            </small>
          )}
        </div>

        <div className="config-grid">
          <div className="form-group">
            <label htmlFor="epochs">Epochs</label>
            <input
              type="number"
              id="epochs"
              value={config.epochs}
              onChange={(e) => updateConfig('epochs', parseInt(e.target.value) || 3)}
              min={1}
              max={10}
              disabled={api.loading}
            />
            <small>Training passes (1-10)</small>
          </div>

          <div className="form-group">
            <label htmlFor="batchSize">Batch Size</label>
            <input
              type="number"
              id="batchSize"
              value={config.batch_size}
              onChange={(e) => updateConfig('batch_size', parseInt(e.target.value) || 4)}
              min={1}
              max={16}
              disabled={api.loading}
            />
            <small>Samples per batch (1-16)</small>
          </div>

          <div className="form-group">
            <label htmlFor="learningRate">Learning Rate</label>
            <input
              type="number"
              id="learningRate"
              value={config.learning_rate}
              onChange={(e) => updateConfig('learning_rate', parseFloat(e.target.value) || 0.0001)}
              min={0.00001}
              max={0.01}
              step={0.00001}
              disabled={api.loading}
            />
            <small>Step size (1e-5 to 1e-2)</small>
          </div>

          <div className="form-group">
            <label htmlFor="loraRank">LoRA Rank</label>
            <input
              type="number"
              id="loraRank"
              value={config.lora_rank}
              onChange={(e) => updateConfig('lora_rank', parseInt(e.target.value) || 16)}
              min={4}
              max={64}
              step={4}
              disabled={api.loading}
            />
            <small>Adapter rank (4-64)</small>
          </div>
        </div>

        <div className="form-group checkbox-group">
          <label htmlFor="exportGguf">
            <input
              type="checkbox"
              id="exportGguf"
              checked={config.export_gguf}
              onChange={(e) => updateConfig('export_gguf', e.target.checked)}
              disabled={api.loading}
            />
            <span>Export to GGUF format for llama.cpp</span>
          </label>
          <small>Creates quantized model for local inference</small>
        </div>

        <button
          className="btn-primary"
          onClick={handleStartFinetune}
          disabled={api.loading || !selectedTopicId || !stats.canFinetune}
        >
          {api.loading ? 'Starting...' : 'Start Training'}
        </button>
      </div>

      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <div className="jobs-section">
          <h3>Active Training Jobs</h3>
          <div className="jobs-list">
            {activeJobs.map((job) => (
              <FinetuneJobCard
                key={job.job_id}
                job={job}
                onViewProgress={() => {
                  setActiveJobId(job.job_id);
                  api.connectTrainingWebSocket(job.job_id, setTrainingProgress);
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Completed Jobs */}
      {completedJobs.length > 0 && (
        <div className="jobs-section">
          <h3>Completed Training</h3>
          <div className="jobs-list">
            {completedJobs.map((job) => (
              <FinetuneJobCard key={job.job_id} job={job} />
            ))}
          </div>
        </div>
      )}

      {/* Training Progress Overlay */}
      {activeJobId && (
        <TrainingProgress
          job={api.finetuneJobs.find((j) => j.job_id === activeJobId)}
          progress={trainingProgress}
          onClose={handleCloseProgress}
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

export default FineTuningTab;
