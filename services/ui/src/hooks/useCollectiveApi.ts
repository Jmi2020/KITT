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
} from '../types/collective';

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
  phase: 'idle' | 'planning' | 'proposing' | 'judging' | 'complete' | 'error';
  activeProposalIndex: number;

  // Sessions
  sessions: CollectiveSession[];
  loadSessions: (status?: string, limit?: number) => Promise<void>;
  loadSessionDetails: (sessionId: string) => Promise<CollectiveSession | null>;

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
  const [phase, setPhase] = useState<'idle' | 'planning' | 'proposing' | 'judging' | 'complete' | 'error'>('idle');
  const [activeProposalIndex, setActiveProposalIndex] = useState(-1);

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
          k: params.k,
          userId,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to start collective');
      }

      const data: StreamStartResponse = await response.json();
      const sessionId = data.session_id;

      // Set initial session state
      setCurrentSession({
        session_id: sessionId,
        task: params.task,
        pattern: params.pattern,
        k: params.k,
        status: 'pending',
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
      return await response.json();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading session details:', message);
      return null;
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
    sessions,
    loadSessions,
    loadSessionDetails,
    startStreaming,
    cancelStreaming,
    isConnected,
    runCollective,
  };
}

export default useCollectiveApi;
