/**
 * Collective Meta-Agent API Hook
 * Provides API calls and WebSocket streaming for the Collective feature
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { getWebUserId } from '../utils/user';
import type {
  CollectiveSession,
  CollectivePattern,
  CollectiveEvent,
  CollectiveProposal,
  StreamStartResponse,
  SpecialistConfig,
  SpecialistsListResponse,
  CostEstimateResponse,
  ProviderType,
} from '../types/collective';

export interface SearchPhaseInfo {
  isActive: boolean;
  currentPhase: 1 | 2 | null;
  searchQueries: string[];
  currentSearchIndex: number;
  totalSearches: number;
  completedSearches: number;
  message?: string;
}

export interface UseCollectiveApiReturn {
  // State
  userId: string;
  loading: boolean;
  error: string | null;
  clearError: () => void;

  // Current run state
  currentSession: CollectiveSession | null;
  proposals: CollectiveProposal[];
  verdict: string | null;
  phase: 'idle' | 'planning' | 'searching' | 'proposing' | 'judging' | 'complete' | 'error';
  activeProposalIndex: number;
  searchPhaseInfo: SearchPhaseInfo;

  // Sessions
  sessions: CollectiveSession[];
  loadSessions: (status?: string, limit?: number) => Promise<void>;
  loadSessionDetails: (sessionId: string) => Promise<CollectiveSession | null>;
  deleteSession: (sessionId: string) => Promise<boolean>;

  // Specialists
  specialists: SpecialistConfig[];
  specialistsLoading: boolean;
  fetchSpecialists: () => Promise<void>;
  estimateCost: (specialistIds: string[]) => Promise<number>;

  // Streaming
  startStreaming: (params: StartStreamingParams) => Promise<string | null>;
  cancelStreaming: () => void;
  isConnected: boolean;

  // Non-streaming (for simpler use cases)
  runCollective: (params: RunCollectiveParams) => Promise<CollectiveSession | null>;
}

interface StartStreamingParams {
  task: string;
  pattern: CollectivePattern;
  k: number;
  enableSearchPhase?: boolean;
  selectedSpecialists?: string[];  // List of specialist IDs (overrides k)
}

interface RunCollectiveParams {
  task: string;
  pattern: CollectivePattern;
  k: number;
}

export function useCollectiveApi(): UseCollectiveApiReturn {
  const [userId] = useState<string>(() => getWebUserId());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<CollectiveSession[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  // Current run state
  const [currentSession, setCurrentSession] = useState<CollectiveSession | null>(null);
  const [proposals, setProposals] = useState<CollectiveProposal[]>([]);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [phase, setPhase] = useState<'idle' | 'planning' | 'searching' | 'proposing' | 'judging' | 'complete' | 'error'>('idle');
  const [activeProposalIndex, setActiveProposalIndex] = useState(-1);
  const [searchPhaseInfo, setSearchPhaseInfo] = useState<SearchPhaseInfo>({
    isActive: false,
    currentPhase: null,
    searchQueries: [],
    currentSearchIndex: -1,
    totalSearches: 0,
    completedSearches: 0,
  });

  // Specialists state
  const [specialists, setSpecialists] = useState<SpecialistConfig[]>([]);
  const [specialistsLoading, setSpecialistsLoading] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const clearError = useCallback(() => setError(null), []);

  // Reset state for new run
  const resetState = useCallback(() => {
    setCurrentSession(null);
    setProposals([]);
    setVerdict(null);
    setPhase('idle');
    setActiveProposalIndex(-1);
    setError(null);
    setSearchPhaseInfo({
      isActive: false,
      currentPhase: null,
      searchQueries: [],
      currentSearchIndex: -1,
      totalSearches: 0,
      completedSearches: 0,
    });
  }, []);

  // Fetch available specialists
  const fetchSpecialists = useCallback(async () => {
    setSpecialistsLoading(true);
    try {
      const response = await fetch('/api/collective/specialists');
      if (!response.ok) throw new Error('Failed to fetch specialists');
      const data: SpecialistsListResponse = await response.json();

      // Convert snake_case to camelCase
      const converted = data.specialists.map(s => ({
        id: s.id,
        displayName: (s as unknown as { display_name?: string }).display_name || s.displayName,
        provider: s.provider,
        model: s.model,
        description: s.description,
        costPer1mIn: (s as unknown as { cost_per_1m_in?: number }).cost_per_1m_in ?? s.costPer1mIn ?? 0,
        costPer1mOut: (s as unknown as { cost_per_1m_out?: number }).cost_per_1m_out ?? s.costPer1mOut ?? 0,
        isAvailable: (s as unknown as { is_available?: boolean }).is_available ?? s.isAvailable ?? false,
      }));

      setSpecialists(converted);
    } catch (err) {
      console.error('Error fetching specialists:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch specialists');
    } finally {
      setSpecialistsLoading(false);
    }
  }, []);

  // Estimate cost for selected specialists
  const estimateCost = useCallback(async (specialistIds: string[]): Promise<number> => {
    try {
      const response = await fetch('/api/collective/specialists/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          specialist_ids: specialistIds,
          tokens_per_proposal: 4000,
        }),
      });
      if (!response.ok) throw new Error('Failed to estimate cost');
      const data: CostEstimateResponse = await response.json();
      return (data as unknown as { estimated_cost_usd?: number }).estimated_cost_usd ?? data.estimatedCostUsd ?? 0;
    } catch (err) {
      console.error('Error estimating cost:', err);
      return 0;
    }
  }, []);

  // Handle WebSocket events
  const handleEvent = useCallback((event: CollectiveEvent) => {
    switch (event.type) {
      case 'connection':
        console.log('Collective WebSocket connected');
        break;

      case 'started':
        setPhase('planning');
        setCurrentSession(prev => prev ? {
          ...prev,
          status: 'running',
          pattern: event.pattern || prev.pattern,
          k: event.k || prev.k,
        } : null);
        break;

      case 'plan_start':
        setPhase('planning');
        break;

      case 'plan_complete':
        // Plan phase done, moving to proposals
        break;

      case 'proposals_start':
        setPhase('proposing');
        setActiveProposalIndex(0);
        break;

      case 'proposal_start':
        setActiveProposalIndex(event.index ?? -1);
        break;

      case 'proposal_complete':
        if (event.text && event.role) {
          setProposals(prev => {
            const newProposal: CollectiveProposal = {
              role: event.role!,
              text: event.text!,
              model: event.model,
              temperature: event.temperature,
            };
            // Update at specific index or append
            if (event.index !== undefined && event.index < prev.length) {
              const updated = [...prev];
              updated[event.index] = newProposal;
              return updated;
            }
            return [...prev, newProposal];
          });
        }
        break;

      case 'judge_start':
        setPhase('judging');
        setActiveProposalIndex(-1);
        break;

      case 'verdict_complete':
        setVerdict(event.verdict || null);
        // After receiving verdict, if we don't get 'complete' event within 2 seconds,
        // transition to complete state anyway
        setTimeout(() => {
          setPhase((currentPhase) => {
            if (currentPhase === 'judging') {
              console.log('Timeout: transitioning to complete after verdict');
              return 'complete';
            }
            return currentPhase;
          });
        }, 2000);
        break;

      case 'complete':
        setPhase('complete');
        setIsConnected(false);
        if (event.verdict) {
          setVerdict(event.verdict);
        }
        if (event.proposals) {
          setProposals(event.proposals);
        }
        setCurrentSession(prev => prev ? {
          ...prev,
          status: 'completed',
          verdict: event.verdict || null,
          proposals: event.proposals || prev.proposals,
        } : null);
        break;

      case 'error':
        setPhase('error');
        setError(event.message || 'Unknown error');
        setIsConnected(false);
        setCurrentSession(prev => prev ? {
          ...prev,
          status: 'error',
          error: event.message,
        } : null);
        break;

      case 'cancelled':
        setPhase('idle');
        setIsConnected(false);
        break;

      // Search phase events (two-phase proposal generation)
      case 'search_phase_start':
        setPhase('searching');
        setSearchPhaseInfo(prev => ({
          ...prev,
          isActive: true,
          currentPhase: event.phase as 1 | 2 || 1,
          message: event.message || 'Analyzing search needs...',
        }));
        break;

      case 'phase1_start':
        setSearchPhaseInfo(prev => ({
          ...prev,
          currentPhase: 1,
          message: `Specialist ${(event.index ?? 0) + 1} analyzing search needs...`,
        }));
        break;

      case 'phase1_complete':
        // Phase 1 complete for a specialist
        break;

      case 'search_requests_collected':
        setSearchPhaseInfo(prev => ({
          ...prev,
          searchQueries: event.queries || [],
          totalSearches: event.unique_queries || 0,
          message: `Collected ${event.unique_queries || 0} unique search queries (${event.duplicates_removed || 0} duplicates removed)`,
        }));
        break;

      case 'search_execution_start':
        setSearchPhaseInfo(prev => ({
          ...prev,
          currentSearchIndex: 0,
          message: `Executing ${event.total || 0} searches...`,
        }));
        break;

      case 'search_executing':
        setSearchPhaseInfo(prev => ({
          ...prev,
          currentSearchIndex: event.index ?? 0,
          message: `Searching: "${event.query}"`,
        }));
        break;

      case 'search_complete':
        setSearchPhaseInfo(prev => ({
          ...prev,
          completedSearches: (event.index ?? 0) + 1,
          message: `Search ${(event.index ?? 0) + 1}/${prev.totalSearches}: ${event.success ? 'Found ' + (event.result_count || 0) + ' results' : 'Failed'}`,
        }));
        break;

      case 'search_phase_complete':
        setSearchPhaseInfo(prev => ({
          ...prev,
          isActive: false,
          message: event.message || `Search complete: ${event.total_results || 0} results from ${event.successful_queries || 0} queries`,
        }));
        break;

      case 'proposal_phase_start':
        setPhase('proposing');
        setSearchPhaseInfo(prev => ({
          ...prev,
          currentPhase: 2,
          message: event.message || 'Generating proposals with search results...',
        }));
        break;
    }
  }, []);

  // Start streaming collective run
  const startStreaming = useCallback(async (params: StartStreamingParams): Promise<string | null> => {
    resetState();
    setLoading(true);
    setError(null);

    try {
      // Start the session
      const response = await fetch('/api/collective/stream/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: params.task,
          pattern: params.pattern,
          k: params.selectedSpecialists?.length || params.k,
          userId,
          enableSearchPhase: params.enableSearchPhase ?? false,
          selectedSpecialists: params.selectedSpecialists,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start collective');
      }

      const data: StreamStartResponse = await response.json();
      const sessionId = data.session_id;

      // Set initial session state and phase immediately for UI feedback
      setPhase('planning');
      setCurrentSession({
        session_id: sessionId,
        task: params.task,
        pattern: params.pattern,
        k: params.selectedSpecialists?.length || params.k,
        status: 'running',
        created_at: new Date().toISOString(),
        proposals: [],
        verdict: null,
      });

      // Connect to WebSocket
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/collective/stream/${sessionId}`;

      // Close existing connection
      if (wsRef.current) {
        wsRef.current.close();
      }

      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Collective WebSocket opened');
        setIsConnected(true);
      };

      ws.onmessage = (e) => {
        try {
          const event: CollectiveEvent = JSON.parse(e.data);
          handleEvent(event);
        } catch (err) {
          console.error('Error parsing WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('Collective WebSocket error:', err);
        setError('WebSocket connection error');
        setIsConnected(false);
      };

      ws.onclose = () => {
        console.log('Collective WebSocket closed');
        setIsConnected(false);
        // If we have a verdict but phase is still 'judging', transition to complete
        // This handles the case where the 'complete' event wasn't processed before close
        setPhase((currentPhase) => {
          if (currentPhase === 'judging') {
            setVerdict((currentVerdict) => {
              if (currentVerdict) {
                console.log('WebSocket closed with verdict - transitioning to complete');
                return currentVerdict;
              }
              return currentVerdict;
            });
            // Check if we have verdict via a timeout to allow state to settle
            setTimeout(() => {
              setVerdict((v) => {
                if (v) {
                  setPhase('complete');
                }
                return v;
              });
            }, 100);
          }
          return currentPhase;
        });
      };

      wsRef.current = ws;
      return sessionId;

    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error starting collective:', message);
      setError(message);
      setPhase('error');
      return null;
    } finally {
      setLoading(false);
    }
  }, [userId, resetState, handleEvent]);

  // Cancel streaming
  const cancelStreaming = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send('cancel');
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setPhase('idle');
  }, []);

  // Non-streaming run (for simpler use cases)
  const runCollective = useCallback(async (params: RunCollectiveParams): Promise<CollectiveSession | null> => {
    resetState();
    setLoading(true);
    setError(null);
    setPhase('planning');

    try {
      const response = await fetch('/api/collective/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: params.task,
          pattern: params.pattern,
          k: params.k,
          userId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to run collective');
      }

      const data = await response.json();

      const session: CollectiveSession = {
        session_id: crypto.randomUUID(),
        task: params.task,
        pattern: params.pattern,
        k: params.k,
        status: 'completed',
        created_at: new Date().toISOString(),
        proposals: data.proposals || [],
        verdict: data.verdict || null,
      };

      setCurrentSession(session);
      setProposals(data.proposals || []);
      setVerdict(data.verdict || null);
      setPhase('complete');

      return session;

    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error running collective:', message);
      setError(message);
      setPhase('error');
      return null;
    } finally {
      setLoading(false);
    }
  }, [userId, resetState]);

  // Load sessions
  const loadSessions = useCallback(async (status?: string, limit = 20) => {
    try {
      const params = new URLSearchParams({
        userId,
        limit: String(limit),
      });
      if (status) params.append('status', status);

      const response = await fetch(`/api/collective/sessions?${params}`);
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading sessions:', message);
      setError(message);
    }
  }, [userId]);

  // Load session details
  const loadSessionDetails = useCallback(async (sessionId: string): Promise<CollectiveSession | null> => {
    try {
      const response = await fetch(`/api/collective/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session details');
      const data = await response.json();
      console.log('Loaded session details:', {
        sessionId,
        proposalsCount: data.proposals?.length ?? 0,
        hasVerdict: !!data.verdict,
        proposals: data.proposals,
      });
      return data;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading session details:', message);
      return null;
    }
  }, []);

  // Delete session
  const deleteSession = useCallback(async (sessionId: string): Promise<boolean> => {
    try {
      const response = await fetch(`/api/collective/sessions/${sessionId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete session');
      }
      // Remove from local sessions list
      setSessions(prev => prev.filter(s => s.session_id !== sessionId));
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error deleting session:', message);
      setError(message);
      return false;
    }
  }, []);

  return {
    userId,
    loading,
    error,
    clearError,
    currentSession,
    proposals,
    verdict,
    phase,
    activeProposalIndex,
    searchPhaseInfo,
    sessions,
    loadSessions,
    loadSessionDetails,
    deleteSession,
    specialists,
    specialistsLoading,
    fetchSpecialists,
    estimateCost,
    startStreaming,
    cancelStreaming,
    isConnected,
    runCollective,
  };
}

export default useCollectiveApi;
