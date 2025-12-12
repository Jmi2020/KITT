/**
 * Tests for Settings page
 * Tests tab switching and integration with System tab
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Settings from './index';

// Mock useSettings hook
vi.mock('../../hooks/useSettings', () => ({
  useSettings: () => ({
    settings: {
      voice: {
        voice: 'alloy',
        language: 'en',
        prefer_local: true,
      },
      fabrication: {
        default_material: 'pla_black_esun',
        default_profile: 'standard',
        safety_confirmation: true,
      },
      ui: {
        theme: 'dark',
        default_view: 'shell',
        show_debug: false,
      },
      custom_voice_modes: [],
    },
    updateSection: vi.fn(),
    updateSettings: vi.fn(),
    isLoading: false,
  }),
}));

// Mock useIOControl hook
vi.mock('../../hooks/useIOControl', () => ({
  useIOControl: () => ({
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
  }),
}));

// Mock BambuLogin component
vi.mock('../../components/BambuLogin', () => ({
  BambuLogin: () => <div data-testid="bambu-login">BambuLogin</div>,
}));

// Mock VoiceModeEditor component
vi.mock('../../components/VoiceModeEditor', () => ({
  VoiceModeEditor: () => <div data-testid="voice-mode-editor">VoiceModeEditor</div>,
}));

describe('Settings Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (initialEntries = ['/settings']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <Settings />
      </MemoryRouter>
    );
  };

  describe('Header', () => {
    it('renders the header', () => {
      renderWithRouter();

      expect(screen.getByText('Settings')).toBeInTheDocument();
      expect(screen.getByText(/Configure connections/)).toBeInTheDocument();
    });
  });

  describe('Tab Navigation', () => {
    it('renders all six tabs', () => {
      renderWithRouter();

      expect(screen.getByText('Connections')).toBeInTheDocument();
      expect(screen.getByText('Voice')).toBeInTheDocument();
      expect(screen.getByText('Voice Modes')).toBeInTheDocument();
      expect(screen.getByText('Fabrication')).toBeInTheDocument();
      expect(screen.getByText('Interface')).toBeInTheDocument();
      expect(screen.getByText('System')).toBeInTheDocument();
    });

    it('shows Connections tab by default', () => {
      renderWithRouter();

      const connectionsTab = screen.getByText('Connections').closest('button');
      expect(connectionsTab).toHaveClass('active');
    });

    it('switches to Voice tab when clicked', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice'));

      await waitFor(() => {
        const voiceTab = screen.getByText('Voice').closest('button');
        expect(voiceTab).toHaveClass('active');
      });
    });

    it('switches to System tab when clicked', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('System'));

      await waitFor(() => {
        const systemTab = screen.getByText('System').closest('button');
        expect(systemTab).toHaveClass('active');
      });
    });
  });

  describe('Connections Tab', () => {
    it('renders connections content by default', () => {
      renderWithRouter();

      expect(screen.getByText('Service Connections')).toBeInTheDocument();
      expect(screen.getByTestId('bambu-login')).toBeInTheDocument();
      expect(screen.getByText('Home Assistant')).toBeInTheDocument();
    });
  });

  describe('Voice Tab', () => {
    it('renders voice settings when Voice tab is active', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice'));

      await waitFor(() => {
        expect(screen.getByText('Voice Settings')).toBeInTheDocument();
      });
    });

    it('renders voice preference toggle', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice'));

      await waitFor(() => {
        expect(screen.getByText('Prefer Local Processing')).toBeInTheDocument();
      });
    });

    it('renders TTS voice selector', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice'));

      await waitFor(() => {
        expect(screen.getByLabelText('TTS Voice')).toBeInTheDocument();
      });
    });

    it('renders language selector', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice'));

      await waitFor(() => {
        expect(screen.getByLabelText('Language')).toBeInTheDocument();
      });
    });
  });

  describe('Voice Modes Tab', () => {
    it('renders voice modes editor', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Voice Modes'));

      await waitFor(() => {
        expect(screen.getByTestId('voice-mode-editor')).toBeInTheDocument();
      });
    });
  });

  describe('Fabrication Tab', () => {
    it('renders fabrication settings', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Fabrication'));

      await waitFor(() => {
        expect(screen.getByText('Fabrication Settings')).toBeInTheDocument();
      });
    });

    it('renders safety confirmation toggle', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Fabrication'));

      await waitFor(() => {
        expect(screen.getByText('Safety Confirmations')).toBeInTheDocument();
      });
    });

    it('renders default material selector', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Fabrication'));

      await waitFor(() => {
        expect(screen.getByLabelText('Default Material')).toBeInTheDocument();
      });
    });
  });

  describe('Interface Tab', () => {
    it('renders interface settings', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Interface'));

      await waitFor(() => {
        expect(screen.getByText('Interface Settings')).toBeInTheDocument();
      });
    });

    it('renders theme selector', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Interface'));

      await waitFor(() => {
        expect(screen.getByLabelText('Theme')).toBeInTheDocument();
      });
    });

    it('renders default view selector', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Interface'));

      await waitFor(() => {
        expect(screen.getByLabelText('Default View')).toBeInTheDocument();
      });
    });

    it('renders debug toggle', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Interface'));

      await waitFor(() => {
        expect(screen.getByText('Show Debug Info')).toBeInTheDocument();
      });
    });
  });

  describe('System Tab (IOControl)', () => {
    it('renders System tab content', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('System'));

      // SystemTab component should be rendered
      await waitFor(() => {
        expect(screen.getByText(/Pending Changes/)).toBeInTheDocument();
      });
    });
  });

  describe('URL Tab Param', () => {
    it('opens correct tab from URL param', () => {
      renderWithRouter(['/settings?tab=system']);

      const systemTab = screen.getByText('System').closest('button');
      expect(systemTab).toHaveClass('active');
    });

    it('opens fabrication tab from URL param', () => {
      renderWithRouter(['/settings?tab=fabrication']);

      const fabricationTab = screen.getByText('Fabrication').closest('button');
      expect(fabricationTab).toHaveClass('active');
    });
  });
});
