/**
 * Tests for SystemTab component
 * Tests feature flags, presets, and system configuration
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SystemTab from './SystemTab';
import type { UseIOControlReturn } from '../../../hooks/useIOControl';
import type { Feature, Preset } from '../../../types/iocontrol';

// Create mock API
const createMockApi = (overrides: Partial<UseIOControlReturn> = {}): UseIOControlReturn => ({
  features: [],
  presets: [],
  pendingChanges: {},
  previewData: null,
  loading: false,
  error: null,
  toolAvailability: {},
  enabledFunctions: [],
  unavailableMessage: undefined,
  healthWarnings: [],
  restartImpacts: {},
  costHints: {},
  loadFeatures: vi.fn(),
  loadPresets: vi.fn(),
  loadState: vi.fn(),
  toggleFeature: vi.fn(),
  previewChanges: vi.fn(),
  applyChanges: vi.fn(),
  applyPreset: vi.fn(),
  cancelChanges: vi.fn(),
  clearError: vi.fn(),
  ...overrides,
});

const mockFeatures: Feature[] = [
  {
    id: 'web_search',
    name: 'Web Search',
    description: 'Enable web search functionality',
    category: 'tools',
    env_var: 'ENABLE_WEB_SEARCH',
    default_value: true,
    current_value: true,
    restart_scope: 'none',
    requires: [],
    enables: ['research'],
    conflicts_with: [],
    can_enable: true,
    can_disable: true,
    dependencies_met: true,
  },
  {
    id: 'offline_mode',
    name: 'Offline Mode',
    description: 'Run in offline mode',
    category: 'system',
    env_var: 'OFFLINE_MODE',
    default_value: false,
    current_value: false,
    restart_scope: 'service',
    requires: [],
    enables: [],
    conflicts_with: ['cloud_routing'],
    can_enable: true,
    can_disable: true,
    dependencies_met: true,
  },
];

const mockPresets: Preset[] = [
  {
    id: 'offline',
    name: 'Offline Mode',
    description: 'Disable all cloud services',
    features: { offline_mode: true },
    cost_estimate: {},
  },
  {
    id: 'full',
    name: 'Full Features',
    description: 'Enable all features',
    features: { web_search: true, offline_mode: false },
    cost_estimate: {},
  },
];

describe('SystemTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Initial Load', () => {
    it('calls load functions on mount', () => {
      const mockApi = createMockApi();
      render(<SystemTab api={mockApi} />);

      expect(mockApi.loadFeatures).toHaveBeenCalled();
      expect(mockApi.loadPresets).toHaveBeenCalled();
      expect(mockApi.loadState).toHaveBeenCalled();
    });
  });

  describe('Stats Display', () => {
    it('displays pending changes count', () => {
      const mockApi = createMockApi({
        pendingChanges: { f1: true, f2: false },
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('2')).toBeInTheDocument();
    });

    it('displays features enabled count', () => {
      const mockApi = createMockApi({
        features: mockFeatures,
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('1/2')).toBeInTheDocument(); // 1 enabled out of 2
    });
  });

  describe('Tool Availability', () => {
    it('displays tool availability when present', () => {
      const mockApi = createMockApi({
        toolAvailability: { web_search: true, perplexity: false },
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('Tool Availability')).toBeInTheDocument();
      expect(screen.getByText(/web_search/)).toBeInTheDocument();
      expect(screen.getByText(/perplexity/)).toBeInTheDocument();
    });

    it('displays enabled functions', () => {
      const mockApi = createMockApi({
        toolAvailability: { test: true },
        enabledFunctions: ['search', 'research'],
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Enabled functions:/)).toBeInTheDocument();
      expect(screen.getByText(/search, research/)).toBeInTheDocument();
    });

    it('displays health warnings', () => {
      const mockApi = createMockApi({
        toolAvailability: { test: true },
        healthWarnings: [{ feature_name: 'test', message: 'Test warning' }],
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Health warnings:/)).toBeInTheDocument();
      expect(screen.getByText(/Test warning/)).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('displays error banner when error exists', () => {
      const mockApi = createMockApi({
        error: 'Something went wrong',
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Something went wrong/)).toBeInTheDocument();
    });

    it('calls clearError when dismiss button clicked', async () => {
      const mockApi = createMockApi({
        error: 'Something went wrong',
      });
      render(<SystemTab api={mockApi} />);

      const dismissButton = screen.getByText('×');
      await userEvent.click(dismissButton);

      expect(mockApi.clearError).toHaveBeenCalled();
    });
  });

  describe('Search and Filters', () => {
    it('renders search input', () => {
      const mockApi = createMockApi();
      render(<SystemTab api={mockApi} />);

      expect(screen.getByPlaceholderText(/Search features/i)).toBeInTheDocument();
    });

    it('renders category filter', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByLabelText(/Filter by category/i)).toBeInTheDocument();
    });

    it('renders restart scope filter', () => {
      const mockApi = createMockApi();
      render(<SystemTab api={mockApi} />);

      expect(screen.getByLabelText(/Filter by restart scope/i)).toBeInTheDocument();
    });

    it('filters features by search query', async () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      const searchInput = screen.getByPlaceholderText(/Search features/i);
      await userEvent.type(searchInput, 'Web');

      expect(screen.getByText('Web Search')).toBeInTheDocument();
      expect(screen.queryByText('Offline Mode')).not.toBeInTheDocument();
    });
  });

  describe('Presets', () => {
    it('renders presets when available', () => {
      const mockApi = createMockApi({ presets: mockPresets });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('Quick Presets')).toBeInTheDocument();
      expect(screen.getByText('Offline Mode')).toBeInTheDocument();
      expect(screen.getByText('Full Features')).toBeInTheDocument();
    });

    it('calls applyPreset when preset clicked', async () => {
      vi.spyOn(window, 'confirm').mockImplementation(() => true);

      const mockApi = createMockApi({ presets: mockPresets });
      render(<SystemTab api={mockApi} />);

      const presetButton = screen.getByRole('button', { name: /Offline Mode/i });
      await userEvent.click(presetButton);

      expect(mockApi.applyPreset).toHaveBeenCalledWith('offline');

      vi.restoreAllMocks();
    });
  });

  describe('Feature Cards', () => {
    it('renders feature cards', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('Web Search')).toBeInTheDocument();
      expect(screen.getByText('Offline Mode')).toBeInTheDocument();
    });

    it('displays feature descriptions', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('Enable web search functionality')).toBeInTheDocument();
    });

    it('displays restart scope badges', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      // Multiple elements with these texts may exist (in stats legend and on cards)
      expect(screen.getAllByText(/none/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/service/).length).toBeGreaterThan(0);
    });

    it('displays env var codes', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('ENABLE_WEB_SEARCH')).toBeInTheDocument();
      expect(screen.getByText('OFFLINE_MODE')).toBeInTheDocument();
    });

    it('displays enables relationships', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Enables:/)).toBeInTheDocument();
    });

    it('displays conflicts_with relationships', () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Conflicts with:/)).toBeInTheDocument();
    });
  });

  describe('Feature Toggle', () => {
    it('calls toggleFeature when checkbox clicked', async () => {
      const mockApi = createMockApi({ features: mockFeatures });
      render(<SystemTab api={mockApi} />);

      const toggles = screen.getAllByRole('checkbox');
      await userEvent.click(toggles[0]);

      expect(mockApi.toggleFeature).toHaveBeenCalled();
    });
  });

  describe('Pending Changes', () => {
    it('shows pending changes toolbar when changes exist', () => {
      const mockApi = createMockApi({
        features: mockFeatures,
        pendingChanges: { web_search: false },
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/1 pending changes/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Preview Changes/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Apply Changes/i })).toBeInTheDocument();
    });

    it('calls cancelChanges when Cancel clicked', async () => {
      const mockApi = createMockApi({
        features: mockFeatures,
        pendingChanges: { web_search: false },
      });
      render(<SystemTab api={mockApi} />);

      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));

      expect(mockApi.cancelChanges).toHaveBeenCalled();
    });

    it('shows pending indicator on feature card', () => {
      const mockApi = createMockApi({
        features: mockFeatures,
        pendingChanges: { web_search: false },
      });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText(/Pending change:/)).toBeInTheDocument();
    });
  });

  describe('Refresh', () => {
    it('calls loadFeatures when Refresh clicked', async () => {
      const mockApi = createMockApi();
      render(<SystemTab api={mockApi} />);

      await userEvent.click(screen.getByRole('button', { name: /Refresh/i }));

      // loadFeatures is called once on mount and once on refresh
      expect(mockApi.loadFeatures).toHaveBeenCalledTimes(2);
    });
  });

  describe('Loading State', () => {
    it('shows loading overlay when loading', () => {
      const mockApi = createMockApi({ loading: true });
      render(<SystemTab api={mockApi} />);

      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });
});
