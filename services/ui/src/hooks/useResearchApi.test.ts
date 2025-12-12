/**
 * Tests for useResearchApi hook
 * Verifies API calls, error handling, and state management
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { useResearchApi } from './useResearchApi';
import type { ResearchSession, ResearchTemplate } from '../types/research';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock WebSocket
class MockWebSocket {
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: (() => void) | null = null;
  readyState = 1;
  close = vi.fn();
  send = vi.fn();
}

vi.stubGlobal('WebSocket', MockWebSocket);

// Mock getWebUserId
vi.mock('../utils/user', () => ({
  getWebUserId: () => 'test-user-123',
}));

describe('useResearchApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Initial State', () => {
    it('initializes with empty arrays and no errors', () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ sessions: [] }),
      });

      const { result } = renderHook(() => useResearchApi());

      expect(result.current.sessions).toEqual([]);
      expect(result.current.templates).toEqual([]);
      expect(result.current.schedules).toEqual([]);
      expect(result.current.scheduleHistory).toEqual([]);
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
      expect(result.current.isConnected).toBe(false);
    });

    it('provides userId from user utils', () => {
      const { result } = renderHook(() => useResearchApi());
      expect(result.current.userId).toBe('test-user-123');
    });
  });

  describe('Session Management', () => {
    it('creates a new research session', async () => {
      const mockSession: Partial<ResearchSession> = {
        session_id: 'test-123',
        query: 'Test query for research',
        status: 'active',
        total_findings: 0,
        total_sources: 0,
        total_iterations: 0,
        total_cost_usd: 0,
        external_calls_used: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      // Mock all fetch calls in sequence
      mockFetch.mockImplementation((url: string) => {
        if (url.includes('/api/research/sessions') && !url.includes('?')) {
          // POST to create session
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve(mockSession),
          });
        }
        // GET sessions list
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        });
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const session = await result.current.createSession({
          query: 'Test query for research', // Must be at least 10 chars
          strategy: 'comprehensive',
          maxIterations: 5,
          maxCost: 1.0,
          enablePaidTools: false,
          enableHierarchical: false,
          maxSubQuestions: 3,
        });

        expect(session).toBeDefined();
        expect(session?.session_id).toBe('test-123');
      });

      // Verify the fetch was called with correct endpoint
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/research/sessions',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
      );
    });

    it('loads sessions list', async () => {
      const mockSessions: Partial<ResearchSession>[] = [
        { session_id: '1', query: 'Query 1', status: 'completed' } as ResearchSession,
        { session_id: '2', query: 'Query 2', status: 'active' } as ResearchSession,
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ sessions: mockSessions }),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        await result.current.loadSessions();
      });

      expect(result.current.sessions).toHaveLength(2);
    });

    it('loads session details by ID', async () => {
      const mockSession: Partial<ResearchSession> = {
        session_id: 'test-456',
        query: 'Detailed query',
        status: 'active',
        config: { max_iterations: 10 },
      } as ResearchSession;

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSession),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const session = await result.current.loadSessionDetails('test-456');
        expect(session?.session_id).toBe('test-456');
      });
    });

    it('pauses a session', async () => {
      // Mock both the pause call and the subsequent sessions reload
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ message: 'Session paused' }),
        })
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const success = await result.current.pauseSession('test-123');
        expect(success).toBe(true);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('test-123/pause'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('resumes a session', async () => {
      // Mock both the resume call and the subsequent sessions reload
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ message: 'Session resumed' }),
        })
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const success = await result.current.resumeSession('test-123');
        expect(success).toBe(true);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('test-123/resume'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('cancels a session', async () => {
      // Mock both the cancel call and the subsequent sessions reload
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ message: 'Session cancelled' }),
        })
        .mockResolvedValue({
          ok: true,
          json: () => Promise.resolve({ sessions: [] }),
        });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const success = await result.current.cancelSession('test-123');
        expect(success).toBe(true);
      });
    });
  });

  describe('Templates', () => {
    it('loads research templates', async () => {
      const mockTemplates: Partial<ResearchTemplate>[] = [
        { id: 't1', name: 'Technical Research', query_template: 'Research {topic}' },
        { id: 't2', name: 'Market Analysis', query_template: 'Analyze market for {product}' },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ templates: mockTemplates }),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        await result.current.loadTemplates();
      });

      expect(result.current.templates).toHaveLength(2);
    });
  });

  describe('Results', () => {
    it('loads results for a session', async () => {
      const mockResults = {
        session_id: 'test-123',
        query: 'Test query',
        total_findings: 10,
        total_sources: 5,
        total_cost_usd: 0.5,
        findings: [
          { id: 'f1', content: 'Finding 1', confidence: 0.8 },
          { id: 'f2', content: 'Finding 2', confidence: 0.9 },
        ],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResults),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const results = await result.current.loadResults('test-123');
        expect(results?.total_findings).toBe(10);
        expect(results?.findings).toHaveLength(2);
      });
    });

    it('generates synthesis', async () => {
      const mockSynthesis = {
        synthesis: 'Combined analysis of all findings...',
        model: 'claude-opus-4-20250514',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSynthesis),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const synthesis = await result.current.generateSynthesis('test-123');
        expect(synthesis?.synthesis).toContain('Combined analysis');
      });
    });
  });

  describe('Schedules', () => {
    it('loads schedules', async () => {
      const mockSchedules = [
        { id: 's1', job_name: 'Weekly Research', cron_expression: '0 9 * * 1' },
        { id: 's2', job_name: 'Daily Check', cron_expression: '0 8 * * *' },
      ];

      // Schedule endpoint returns direct array, not { schedules: [] }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSchedules),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        await result.current.loadSchedules();
      });

      expect(result.current.schedules).toHaveLength(2);
    });

    it('creates a schedule', async () => {
      const mockSchedule = {
        id: 's-new',
        job_name: 'New Schedule',
        cron_expression: '0 10 * * *',
        enabled: true,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockSchedule),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const schedule = await result.current.createSchedule({
          jobName: 'New Schedule',
          jobType: 'research',
          cronExpression: '0 10 * * *',
          enabled: true,
          priority: 5,
        });

        expect(schedule?.id).toBe('s-new');
      });
    });

    it('updates a schedule', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ enabled: false }),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const success = await result.current.updateSchedule('s1', { enabled: false });
        expect(success).toBe(true);
      });
    });

    it('deletes a schedule', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ message: 'Deleted' }),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const success = await result.current.deleteSchedule('s1');
        expect(success).toBe(true);
      });
    });

    it('loads schedule history', async () => {
      const mockHistory = [
        { id: 'h1', job_name: 'Weekly', status: 'success', execution_time: '2024-01-01T00:00:00Z' },
        { id: 'h2', job_name: 'Daily', status: 'failed', execution_time: '2024-01-02T00:00:00Z' },
      ];

      // History endpoint returns direct array, not { executions: [] }
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockHistory),
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        await result.current.loadScheduleHistory();
      });

      expect(result.current.scheduleHistory).toHaveLength(2);
    });
  });

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const session = await result.current.createSession({
          query: 'Test',
          strategy: 'quick',
          maxIterations: 3,
          maxCost: 0.5,
          enablePaidTools: false,
          enableHierarchical: false,
          maxSubQuestions: 3,
        });
        expect(session).toBeNull();
      });

      expect(result.current.error).toBeTruthy();
    });

    it('handles network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useResearchApi());

      await act(async () => {
        const session = await result.current.createSession({
          query: 'Test',
          strategy: 'quick',
          maxIterations: 3,
          maxCost: 0.5,
          enablePaidTools: false,
          enableHierarchical: false,
          maxSubQuestions: 3,
        });
        expect(session).toBeNull();
      });

      expect(result.current.error).toBeTruthy();
    });

    it('clears error when clearError is called', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useResearchApi());

      // First, trigger an error
      await act(async () => {
        await result.current.createSession({
          query: 'Test',
          strategy: 'quick',
          maxIterations: 3,
          maxCost: 0.5,
          enablePaidTools: false,
          enableHierarchical: false,
          maxSubQuestions: 3,
        });
      });

      expect(result.current.error).toBeTruthy();

      // Clear the error
      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('WebSocket', () => {
    it('connects to WebSocket for streaming', async () => {
      const { result } = renderHook(() => useResearchApi());
      const onProgress = vi.fn();

      act(() => {
        result.current.connectWebSocket('test-123', onProgress);
      });

      // WebSocket connected state is set on 'onopen' event
      expect(result.current.isConnected).toBe(false); // Not connected until onopen
    });

    it('disconnects WebSocket', async () => {
      const { result } = renderHook(() => useResearchApi());
      const onProgress = vi.fn();

      act(() => {
        result.current.connectWebSocket('test-123', onProgress);
        result.current.disconnectWebSocket();
      });

      expect(result.current.isConnected).toBe(false);
    });
  });
});

// Export type for use in tests
export type { UseResearchApiReturn } from './useResearchApi';
