/**
 * Tests for useIOControl hook
 * Verifies API calls, state management, and error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useIOControl } from './useIOControl';
import type { Feature, Preset } from '../types/iocontrol';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('useIOControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Initial State', () => {
    it('initializes with empty arrays and no errors', () => {
      const { result } = renderHook(() => useIOControl());

      expect(result.current.features).toEqual([]);
      expect(result.current.presets).toEqual([]);
      expect(result.current.pendingChanges).toEqual({});
      expect(result.current.previewData).toBeNull();
      expect(result.current.loading).toBe(false);
      expect(result.current.error).toBeNull();
    });

    it('initializes with empty tool availability', () => {
      const { result } = renderHook(() => useIOControl());

      expect(result.current.toolAvailability).toEqual({});
      expect(result.current.enabledFunctions).toEqual([]);
      expect(result.current.healthWarnings).toEqual([]);
    });
  });

  describe('Feature Loading', () => {
    it('loads features successfully', async () => {
      const mockFeatures: Partial<Feature>[] = [
        {
          id: 'f1',
          name: 'Feature 1',
          description: 'Test feature',
          category: 'test',
          env_var: 'TEST_F1',
          default_value: true,
          current_value: true,
          restart_scope: 'none',
          requires: [],
          enables: [],
          conflicts_with: [],
          can_enable: true,
          can_disable: true,
          dependencies_met: true,
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockFeatures),
      });

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.loadFeatures();
      });

      expect(result.current.features).toHaveLength(1);
      expect(result.current.features[0].id).toBe('f1');
    });

    it('handles feature loading errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.loadFeatures();
      });

      expect(result.current.error).toBeTruthy();
    });
  });

  describe('Preset Loading', () => {
    it('loads presets successfully', async () => {
      const mockPresets: Partial<Preset>[] = [
        {
          id: 'p1',
          name: 'Preset 1',
          description: 'Test preset',
          features: { f1: true },
          cost_estimate: {},
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ presets: mockPresets }),
      });

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.loadPresets();
      });

      expect(result.current.presets).toHaveLength(1);
      expect(result.current.presets[0].id).toBe('p1');
    });
  });

  describe('State Loading', () => {
    it('loads state successfully', async () => {
      const mockState = {
        tool_availability: { web_search: true, perplexity: false },
        enabled_functions: ['search', 'research'],
        unavailable_message: 'Some tools unavailable',
        health_warnings: [{ feature_name: 'test', message: 'Warning' }],
        restart_impacts: { service: ['brain'] },
        cost_hints: { perplexity: '$0.01/query' },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockState),
      });

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.loadState();
      });

      expect(result.current.toolAvailability).toEqual({ web_search: true, perplexity: false });
      expect(result.current.enabledFunctions).toEqual(['search', 'research']);
      expect(result.current.unavailableMessage).toBe('Some tools unavailable');
      expect(result.current.healthWarnings).toHaveLength(1);
    });
  });

  describe('Feature Toggling', () => {
    it('adds feature to pending changes', () => {
      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
      });

      expect(result.current.pendingChanges).toEqual({ f1: true });
    });

    it('accumulates multiple pending changes', () => {
      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
        result.current.toggleFeature('f2', false);
        result.current.toggleFeature('f3', 'custom_value');
      });

      expect(result.current.pendingChanges).toEqual({
        f1: true,
        f2: false,
        f3: 'custom_value',
      });
    });
  });

  describe('Preview Changes', () => {
    it('previews changes successfully', async () => {
      const mockPreview = {
        dependencies: { f1: ['f2'] },
        costs: {},
        restarts: { service: ['brain'] },
        conflicts: {},
        health_warnings: {},
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockPreview),
      });

      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
      });

      await act(async () => {
        await result.current.previewChanges();
      });

      expect(result.current.previewData).toEqual(mockPreview);
    });

    it('does not preview when no pending changes', async () => {
      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.previewChanges();
      });

      expect(mockFetch).not.toHaveBeenCalled();
    });
  });

  describe('Apply Changes', () => {
    it('applies changes successfully', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([]),
        });

      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
      });

      await act(async () => {
        const success = await result.current.applyChanges();
        expect(success).toBe(true);
      });

      expect(result.current.pendingChanges).toEqual({});
    });

    it('handles apply errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'Apply failed' }),
      });

      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
      });

      await act(async () => {
        const success = await result.current.applyChanges();
        expect(success).toBe(false);
      });

      expect(result.current.error).toBeTruthy();
    });
  });

  describe('Apply Preset', () => {
    it('applies preset successfully', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ success: true }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve([]),
        });

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        const success = await result.current.applyPreset('offline_mode');
        expect(success).toBe(true);
      });

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/io-control/presets/offline_mode/apply',
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  describe('Cancel Changes', () => {
    it('clears pending changes', () => {
      const { result } = renderHook(() => useIOControl());

      act(() => {
        result.current.toggleFeature('f1', true);
        result.current.toggleFeature('f2', false);
      });

      expect(Object.keys(result.current.pendingChanges)).toHaveLength(2);

      act(() => {
        result.current.cancelChanges();
      });

      expect(result.current.pendingChanges).toEqual({});
      expect(result.current.previewData).toBeNull();
    });
  });

  describe('Clear Error', () => {
    it('clears error state', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'));

      const { result } = renderHook(() => useIOControl());

      await act(async () => {
        await result.current.loadFeatures();
      });

      expect(result.current.error).toBeTruthy();

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });
});

// Export type for use in tests
export type { UseIOControlReturn } from './useIOControl';
