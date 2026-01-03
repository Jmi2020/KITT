/**
 * Research API Hook
 * Consolidates API calls for Research Hub components
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { getWebUserId } from '../utils/user';
import type {
  ResearchSession,
  ResearchTemplate,
  SessionResults,
  Schedule,
  ScheduleExecution,
  ProgressUpdate,
  ResearchTopic,
  CreateTopicParams,
  FinetuneJob,
  FinetuneConfig,
  ExpertModel,
  MemoryModeState,
  DiskUsage,
  HarvestProgressEvent,
  TrainingProgressEvent,
} from '../types/research';

export interface UseResearchApiReturn {
  // State
  userId: string;
  loading: boolean;
  error: string | null;
  clearError: () => void;

  // Sessions
  sessions: ResearchSession[];
  loadSessions: (status?: string, limit?: number) => Promise<void>;
  loadSessionDetails: (sessionId: string) => Promise<ResearchSession | null>;
  createSession: (params: CreateSessionParams) => Promise<ResearchSession | null>;
  pauseSession: (sessionId: string) => Promise<boolean>;
  resumeSession: (sessionId: string) => Promise<boolean>;
  cancelSession: (sessionId: string) => Promise<boolean>;

  // Templates
  templates: ResearchTemplate[];
  loadTemplates: () => Promise<void>;

  // Results
  loadResults: (sessionId: string) => Promise<SessionResults | null>;
  generateSynthesis: (sessionId: string) => Promise<{ synthesis: string; model: string } | null>;

  // WebSocket
  connectWebSocket: (sessionId: string, onUpdate: (update: ProgressUpdate) => void) => void;
  disconnectWebSocket: () => void;
  isConnected: boolean;

  // Schedules
  schedules: Schedule[];
  scheduleHistory: ScheduleExecution[];
  loadSchedules: () => Promise<void>;
  loadScheduleHistory: (limit?: number) => Promise<void>;
  createSchedule: (params: CreateScheduleParams) => Promise<Schedule | null>;
  updateSchedule: (id: string, updates: Partial<Schedule>) => Promise<boolean>;
  deleteSchedule: (id: string) => Promise<boolean>;

  // Topics (Dataset Generation)
  topics: ResearchTopic[];
  loadTopics: () => Promise<void>;
  createTopic: (params: CreateTopicParams) => Promise<ResearchTopic | null>;
  getTopicDetails: (topicId: string) => Promise<ResearchTopic | null>;
  startHarvest: (topicId: string) => Promise<boolean>;
  connectHarvestWebSocket: (topicId: string, onUpdate: (update: HarvestProgressEvent) => void) => void;
  disconnectHarvestWebSocket: () => void;

  // Fine-Tuning
  finetuneJobs: FinetuneJob[];
  loadFinetuneJobs: () => Promise<void>;
  startFinetune: (topicId: string, config: FinetuneConfig) => Promise<FinetuneJob | null>;
  getFinetuneJob: (jobId: string) => Promise<FinetuneJob | null>;
  connectTrainingWebSocket: (jobId: string, onUpdate: (update: TrainingProgressEvent) => void) => void;
  disconnectTrainingWebSocket: () => void;

  // Expert Models
  experts: ExpertModel[];
  loadExperts: (activeOnly?: boolean) => Promise<void>;
  activateExpert: (modelId: string) => Promise<boolean>;
  deactivateExpert: (modelId: string) => Promise<boolean>;
  deleteExpert: (modelId: string) => Promise<boolean>;

  // Resources (Memory + Disk)
  memoryMode: MemoryModeState | null;
  diskUsage: DiskUsage | null;
  loadMemoryMode: () => Promise<void>;
  setMemoryMode: (mode: string) => Promise<MemoryModeState | null>;
  loadDiskUsage: () => Promise<void>;
  compressOldData: (ageDays: number) => Promise<{ files_compressed: number; bytes_saved: number } | null>;
}

interface CreateSessionParams {
  query: string;
  strategy: string;
  maxIterations: number;
  maxCost: number;
  enablePaidTools: boolean;
  enableHierarchical: boolean;
  maxSubQuestions: number;
  template?: string;
}

interface CreateScheduleParams {
  jobName: string;
  jobType: string;
  naturalLanguageSchedule?: string;
  cronExpression?: string;
  budgetLimit?: number;
  priority: number;
  enabled: boolean;
}

export function useResearchApi(): UseResearchApiReturn {
  const [userId] = useState<string>(() => getWebUserId());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [templates, setTemplates] = useState<ResearchTemplate[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [scheduleHistory, setScheduleHistory] = useState<ScheduleExecution[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  // Dataset Generation state
  const [topics, setTopics] = useState<ResearchTopic[]>([]);
  const [finetuneJobs, setFinetuneJobs] = useState<FinetuneJob[]>([]);
  const [experts, setExperts] = useState<ExpertModel[]>([]);
  const [memoryMode, setMemoryModeState] = useState<MemoryModeState | null>(null);
  const [diskUsage, setDiskUsage] = useState<DiskUsage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const harvestWsRef = useRef<WebSocket | null>(null);
  const trainingWsRef = useRef<WebSocket | null>(null);

  // Cleanup WebSockets on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (harvestWsRef.current) harvestWsRef.current.close();
      if (trainingWsRef.current) trainingWsRef.current.close();
    };
  }, []);

  const clearError = useCallback(() => setError(null), []);

  // Sessions API
  const loadSessions = useCallback(async (status?: string, limit = 20) => {
    try {
      const params = new URLSearchParams({
        user_id: userId,
        limit: String(limit),
      });
      if (status) params.append('status', status);

      const response = await fetch(`/api/research/sessions?${params}`);
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading sessions:', message);
      setError(message);
    }
  }, [userId]);

  const loadSessionDetails = useCallback(async (sessionId: string): Promise<ResearchSession | null> => {
    try {
      const response = await fetch(`/api/research/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session details');
      return await response.json();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading session details:', message);
      return null;
    }
  }, []);

  const createSession = useCallback(async (params: CreateSessionParams): Promise<ResearchSession | null> => {
    if (!params.query.trim() || params.query.length < 10) {
      setError('Query must be at least 10 characters');
      return null;
    }

    setLoading(true);
    setError(null);

    try {
      const requestBody: Record<string, unknown> = {
        query: params.query.trim(),
        user_id: userId,
        config: {
          strategy: params.strategy,
          max_iterations: params.maxIterations,
          max_cost_usd: params.maxCost,
        },
      };

      if (params.enablePaidTools) {
        (requestBody.config as Record<string, unknown>).base_priority = 0.7;
      }

      if (params.enableHierarchical) {
        const config = requestBody.config as Record<string, unknown>;
        config.enable_hierarchical = true;
        config.max_sub_questions = params.maxSubQuestions;
        config.min_sub_questions = 2;
        config.sub_question_min_iterations = 2;
        config.sub_question_max_iterations = 5;
      }

      if (params.template) {
        requestBody.template = params.template;
      }

      const response = await fetch('/api/research/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create session');
      }

      const data = await response.json();
      const session = await loadSessionDetails(data.session_id);

      // Refresh sessions list
      loadSessions();

      return session;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error creating session:', message);
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [userId, loadSessionDetails, loadSessions]);

  const pauseSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/sessions/${sessionId}/pause`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to pause session');
      loadSessions();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadSessions]);

  const resumeSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/sessions/${sessionId}/resume`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to resume session');
      loadSessions();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadSessions]);

  const cancelSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to cancel session');
      loadSessions();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadSessions]);

  // Templates API
  const loadTemplates = useCallback(async () => {
    try {
      const response = await fetch('/api/research/templates');
      if (!response.ok) throw new Error('Failed to load templates');
      const data = await response.json();
      setTemplates(data.templates || []);
    } catch (err: unknown) {
      console.error('Error loading templates:', err);
    }
  }, []);

  // Results API
  const loadResults = useCallback(async (sessionId: string): Promise<SessionResults | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/research/sessions/${sessionId}/results`);
      if (!response.ok) throw new Error('Failed to load results');
      return await response.json();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading results:', message);
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const generateSynthesis = useCallback(async (sessionId: string): Promise<{ synthesis: string; model: string } | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/research/sessions/${sessionId}/generate-synthesis`,
        { method: 'POST' }
      );
      if (!response.ok) throw new Error('Failed to generate synthesis');
      return await response.json();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error generating synthesis:', message);
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // WebSocket
  const connectWebSocket = useCallback((sessionId: string, onUpdate: (update: ProgressUpdate) => void) => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/research/sessions/${sessionId}/stream`;

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const update: ProgressUpdate = JSON.parse(event.data);
        onUpdate(update);

        if (update.type === 'complete' || update.type === 'error') {
          setIsConnected(false);
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setError('WebSocket connection error');
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      setIsConnected(false);
    };

    wsRef.current = ws;
  }, []);

  const disconnectWebSocket = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // Schedules API
  const loadSchedules = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/autonomy/calendar/schedules?user_id=${encodeURIComponent(userId)}`);
      if (!response.ok) throw new Error(`Failed to load schedules (${response.status})`);
      const data: Schedule[] = await response.json();
      setSchedules(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  const loadScheduleHistory = useCallback(async (limit = 50) => {
    try {
      const response = await fetch(`/api/autonomy/calendar/history?limit=${limit}`);
      if (!response.ok) throw new Error(`Failed to load history (${response.status})`);
      const data: ScheduleExecution[] = await response.json();
      setScheduleHistory(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading schedule history:', message);
    }
  }, []);

  const createSchedule = useCallback(async (params: CreateScheduleParams): Promise<Schedule | null> => {
    if (!params.jobName.trim()) {
      setError('Job name is required');
      return null;
    }

    setError(null);
    try {
      const payload = {
        job_type: params.jobType,
        job_name: params.jobName,
        natural_language_schedule: params.naturalLanguageSchedule || undefined,
        cron_expression: params.cronExpression || undefined,
        budget_limit_usd: params.budgetLimit,
        priority: params.priority,
        enabled: params.enabled,
        user_id: userId,
      };

      const response = await fetch('/api/autonomy/calendar/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(`Failed to create schedule (${response.status})`);
      const schedule = await response.json();
      loadSchedules();
      return schedule;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    }
  }, [userId, loadSchedules]);

  const updateSchedule = useCallback(async (id: string, updates: Partial<Schedule>): Promise<boolean> => {
    try {
      const response = await fetch(`/api/autonomy/calendar/schedules/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      });
      if (!response.ok) throw new Error(`Failed to update schedule (${response.status})`);
      loadSchedules();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadSchedules]);

  const deleteSchedule = useCallback(async (id: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/autonomy/calendar/schedules/${id}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(`Failed to delete schedule (${response.status})`);
      loadSchedules();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadSchedules]);

  // ============================================================================
  // Topics (Dataset Generation) API
  // ============================================================================

  const loadTopics = useCallback(async () => {
    try {
      const response = await fetch('/api/research/topics');
      if (!response.ok) throw new Error('Failed to load topics');
      const data = await response.json();
      setTopics(data.topics || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading topics:', message);
      setError(message);
    }
  }, []);

  const createTopic = useCallback(async (params: CreateTopicParams): Promise<ResearchTopic | null> => {
    if (!params.name.trim()) {
      setError('Topic name is required');
      return null;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/research/topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: params.name.trim(),
          description: params.description,
          sources: params.sources,
          max_papers: params.max_papers,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create topic');
      }

      const topic = await response.json();
      loadTopics();
      return topic;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [loadTopics]);

  const getTopicDetails = useCallback(async (topicId: string): Promise<ResearchTopic | null> => {
    try {
      const response = await fetch(`/api/research/topics/${topicId}`);
      if (!response.ok) throw new Error('Failed to load topic details');
      return await response.json();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading topic details:', message);
      return null;
    }
  }, []);

  const startHarvest = useCallback(async (topicId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/topics/${topicId}/harvest`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to start harvest');
      loadTopics();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadTopics]);

  const connectHarvestWebSocket = useCallback((topicId: string, onUpdate: (update: HarvestProgressEvent) => void) => {
    if (harvestWsRef.current) {
      harvestWsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/research/topics/${topicId}/stream`;

    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const update: HarvestProgressEvent = JSON.parse(event.data);
        onUpdate(update);
      } catch (err) {
        console.error('Error parsing harvest WebSocket message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('Harvest WebSocket error:', error);
    };

    harvestWsRef.current = ws;
  }, []);

  const disconnectHarvestWebSocket = useCallback(() => {
    if (harvestWsRef.current) {
      harvestWsRef.current.close();
      harvestWsRef.current = null;
    }
  }, []);

  // ============================================================================
  // Fine-Tuning API
  // ============================================================================

  const loadFinetuneJobs = useCallback(async () => {
    try {
      const response = await fetch('/api/research/finetune/jobs');
      if (!response.ok) throw new Error('Failed to load fine-tune jobs');
      const data = await response.json();
      setFinetuneJobs(data.jobs || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading fine-tune jobs:', message);
    }
  }, []);

  const startFinetune = useCallback(async (topicId: string, config: FinetuneConfig): Promise<FinetuneJob | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/research/topics/${topicId}/finetune`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start fine-tuning');
      }

      const job = await response.json();
      loadFinetuneJobs();
      return job;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [loadFinetuneJobs]);

  const getFinetuneJob = useCallback(async (jobId: string): Promise<FinetuneJob | null> => {
    try {
      const response = await fetch(`/api/research/finetune/jobs/${jobId}`);
      if (!response.ok) throw new Error('Failed to load job details');
      return await response.json();
    } catch (err: unknown) {
      console.error('Error loading job details:', err);
      return null;
    }
  }, []);

  const connectTrainingWebSocket = useCallback((jobId: string, onUpdate: (update: TrainingProgressEvent) => void) => {
    if (trainingWsRef.current) {
      trainingWsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/research/finetune/jobs/${jobId}/stream`;

    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const update: TrainingProgressEvent = JSON.parse(event.data);
        onUpdate(update);
      } catch (err) {
        console.error('Error parsing training WebSocket message:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('Training WebSocket error:', error);
    };

    trainingWsRef.current = ws;
  }, []);

  const disconnectTrainingWebSocket = useCallback(() => {
    if (trainingWsRef.current) {
      trainingWsRef.current.close();
      trainingWsRef.current = null;
    }
  }, []);

  // ============================================================================
  // Expert Models API
  // ============================================================================

  const loadExperts = useCallback(async (activeOnly = false) => {
    try {
      const params = new URLSearchParams();
      if (activeOnly) params.append('active_only', 'true');

      const response = await fetch(`/api/research/experts?${params}`);
      if (!response.ok) throw new Error('Failed to load experts');
      const data = await response.json();
      setExperts(data.experts || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading experts:', message);
    }
  }, []);

  const activateExpert = useCallback(async (modelId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/experts/${modelId}/activate`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to activate expert');
      loadExperts();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadExperts]);

  const deactivateExpert = useCallback(async (modelId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/experts/${modelId}/deactivate`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to deactivate expert');
      loadExperts();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadExperts]);

  const deleteExpert = useCallback(async (modelId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/research/experts/${modelId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error('Failed to delete expert');
      loadExperts();
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return false;
    }
  }, [loadExperts]);

  // ============================================================================
  // Resources (Memory + Disk) API
  // ============================================================================

  const loadMemoryMode = useCallback(async () => {
    try {
      const response = await fetch('/api/research/memory/mode');
      if (!response.ok) throw new Error('Failed to load memory mode');
      const data = await response.json();
      setMemoryModeState(data);
    } catch (err: unknown) {
      console.error('Error loading memory mode:', err);
    }
  }, []);

  const setMemoryMode = useCallback(async (mode: string): Promise<MemoryModeState | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/research/memory/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to set memory mode');
      }

      const data = await response.json();
      setMemoryModeState(data);
      return data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDiskUsage = useCallback(async () => {
    try {
      const response = await fetch('/api/research/disk');
      if (!response.ok) throw new Error('Failed to load disk usage');
      const data = await response.json();
      setDiskUsage(data);
    } catch (err: unknown) {
      console.error('Error loading disk usage:', err);
    }
  }, []);

  const compressOldData = useCallback(async (ageDays: number): Promise<{ files_compressed: number; bytes_saved: number } | null> => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/research/disk/compress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ age_days: ageDays }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to compress data');
      }

      const result = await response.json();
      loadDiskUsage();
      return result;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      return null;
    } finally {
      setLoading(false);
    }
  }, [loadDiskUsage]);

  return {
    userId,
    loading,
    error,
    clearError,
    sessions,
    loadSessions,
    loadSessionDetails,
    createSession,
    pauseSession,
    resumeSession,
    cancelSession,
    templates,
    loadTemplates,
    loadResults,
    generateSynthesis,
    connectWebSocket,
    disconnectWebSocket,
    isConnected,
    schedules,
    scheduleHistory,
    loadSchedules,
    loadScheduleHistory,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    // Dataset Generation
    topics,
    loadTopics,
    createTopic,
    getTopicDetails,
    startHarvest,
    connectHarvestWebSocket,
    disconnectHarvestWebSocket,
    // Fine-Tuning
    finetuneJobs,
    loadFinetuneJobs,
    startFinetune,
    getFinetuneJob,
    connectTrainingWebSocket,
    disconnectTrainingWebSocket,
    // Experts
    experts,
    loadExperts,
    activateExpert,
    deactivateExpert,
    deleteExpert,
    // Resources
    memoryMode,
    diskUsage,
    loadMemoryMode,
    setMemoryMode,
    loadDiskUsage,
    compressOldData,
  };
}

export default useResearchApi;
