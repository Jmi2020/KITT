/**
 * IO Control Hook
 * Manages feature flags and system configuration
 */

import { useState, useCallback, useEffect } from 'react';
import type {
  Feature,
  Preset,
  PreviewChanges,
  IOControlState,
} from '../types/iocontrol';

export interface UseIOControlReturn {
  // State
  features: Feature[];
  presets: Preset[];
  pendingChanges: Record<string, boolean | string>;
  previewData: PreviewChanges | null;
  loading: boolean;
  error: string | null;

  // Computed state
  toolAvailability: Record<string, boolean>;
  enabledFunctions: string[];
  unavailableMessage?: string;
  healthWarnings: Array<{ feature_name: string; message: string }>;
  restartImpacts: Record<string, string[]>;
  costHints: Record<string, string>;

  // Actions
  loadFeatures: () => Promise<void>;
  loadPresets: () => Promise<void>;
  loadState: () => Promise<void>;
  toggleFeature: (featureId: string, newValue: boolean | string) => void;
  previewChanges: () => Promise<void>;
  applyChanges: () => Promise<boolean>;
  applyPreset: (presetId: string) => Promise<boolean>;
  cancelChanges: () => void;
  clearError: () => void;
}

export function useIOControl(): UseIOControlReturn {
  const [features, setFeatures] = useState<Feature[]>([]);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [pendingChanges, setPendingChanges] = useState<Record<string, boolean | string>>({});
  const [previewData, setPreviewData] = useState<PreviewChanges | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // IO Control state
  const [toolAvailability, setToolAvailability] = useState<Record<string, boolean>>({});
  const [enabledFunctions, setEnabledFunctions] = useState<string[]>([]);
  const [unavailableMessage, setUnavailableMessage] = useState<string | undefined>();
  const [healthWarnings, setHealthWarnings] = useState<Array<{ feature_name: string; message: string }>>([]);
  const [restartImpacts, setRestartImpacts] = useState<Record<string, string[]>>({});
  const [costHints, setCostHints] = useState<Record<string, string>>({});

  const clearError = useCallback(() => setError(null), []);

  const loadFeatures = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/io-control/features');
      if (!response.ok) throw new Error('Failed to load features');
      const data: Feature[] = await response.json();
      setFeatures(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error loading features:', message);
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPresets = useCallback(async () => {
    try {
      const response = await fetch('/api/io-control/presets');
      if (!response.ok) throw new Error('Failed to load presets');
      const data = await response.json();
      setPresets(data.presets || []);
    } catch (err: unknown) {
      console.error('Error loading presets:', err);
    }
  }, []);

  const loadState = useCallback(async () => {
    try {
      const response = await fetch('/api/io-control/state');
      if (!response.ok) throw new Error('Failed to load state');
      const data: IOControlState = await response.json();
      setToolAvailability(data.tool_availability || {});
      setEnabledFunctions(data.enabled_functions || []);
      setUnavailableMessage(data.unavailable_message);
      setHealthWarnings(data.health_warnings || []);
      setRestartImpacts(data.restart_impacts || {});
      setCostHints(data.cost_hints || {});
    } catch (err: unknown) {
      console.warn('Error loading state:', err);
    }
  }, []);

  const toggleFeature = useCallback((featureId: string, newValue: boolean | string) => {
    setPendingChanges((prev) => ({ ...prev, [featureId]: newValue }));
  }, []);

  const previewChanges = useCallback(async () => {
    if (Object.keys(pendingChanges).length === 0) return;

    try {
      const response = await fetch('/api/io-control/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ changes: pendingChanges }),
      });

      if (!response.ok) throw new Error('Failed to preview changes');
      const data = await response.json();
      setPreviewData(data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error previewing changes:', message);
      setError(message);
    }
  }, [pendingChanges]);

  const applyChanges = useCallback(async (): Promise<boolean> => {
    if (Object.keys(pendingChanges).length === 0) return false;

    setLoading(true);
    try {
      const response = await fetch('/api/io-control/features/bulk-update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ changes: pendingChanges, persist: true }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to apply changes');
      }

      // Reload features and clear pending changes
      await loadFeatures();
      setPendingChanges({});
      setPreviewData(null);
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error applying changes:', message);
      setError(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [pendingChanges, loadFeatures]);

  const applyPreset = useCallback(async (presetId: string): Promise<boolean> => {
    setLoading(true);
    try {
      const response = await fetch(`/api/io-control/presets/${presetId}/apply`, {
        method: 'POST',
      });

      if (!response.ok) throw new Error('Failed to apply preset');

      // Reload features
      await loadFeatures();
      setPendingChanges({});
      return true;
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      console.error('Error applying preset:', message);
      setError(message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadFeatures]);

  const cancelChanges = useCallback(() => {
    setPendingChanges({});
    setPreviewData(null);
  }, []);

  return {
    features,
    presets,
    pendingChanges,
    previewData,
    loading,
    error,
    toolAvailability,
    enabledFunctions,
    unavailableMessage,
    healthWarnings,
    restartImpacts,
    costHints,
    loadFeatures,
    loadPresets,
    loadState,
    toggleFeature,
    previewChanges,
    applyChanges,
    applyPreset,
    cancelChanges,
    clearError,
  };
}

export default useIOControl;
