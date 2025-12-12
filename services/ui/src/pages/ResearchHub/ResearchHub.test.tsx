/**
 * Tests for Research Hub component
 * Tests tab switching, state management, and integration with tabs
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import ResearchHub from './index';

// Mock useResearchApi hook
vi.mock('../../hooks/useResearchApi', () => ({
  useResearchApi: () => ({
    // State
    sessions: [],
    templates: [],
    schedules: [],
    scheduleHistory: [],
    loading: false,
    error: null,
    isConnected: false,

    // Session methods
    createSession: vi.fn(),
    loadSessions: vi.fn(),
    loadSessionDetails: vi.fn(),
    pauseSession: vi.fn(),
    resumeSession: vi.fn(),
    cancelSession: vi.fn(),

    // Template methods
    loadTemplates: vi.fn(),

    // Results methods
    loadResults: vi.fn(),
    generateSynthesis: vi.fn(),

    // Schedule methods
    loadSchedules: vi.fn(),
    createSchedule: vi.fn(),
    updateSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
    loadScheduleHistory: vi.fn(),

    // WebSocket
    connectWebSocket: vi.fn(),
    disconnectWebSocket: vi.fn(),
  }),
}));

// Mock useSearchParams
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...(actual as object),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

describe('ResearchHub', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (initialEntries = ['/research']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <ResearchHub />
      </MemoryRouter>
    );
  };

  describe('Tab Navigation', () => {
    it('renders all four tabs', () => {
      renderWithRouter();

      expect(screen.getByText('New Research')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Results')).toBeInTheDocument();
      expect(screen.getByText('Schedule')).toBeInTheDocument();
    });

    it('shows New Research tab by default', () => {
      renderWithRouter();

      // Check that the New Research tab is active
      const newTab = screen.getByText('New Research').closest('button');
      expect(newTab).toHaveClass('active');
    });

    it('switches tabs when clicked', async () => {
      renderWithRouter();

      // Click on Results tab
      fireEvent.click(screen.getByText('Results'));

      await waitFor(() => {
        const resultsTab = screen.getByText('Results').closest('button');
        expect(resultsTab).toHaveClass('active');
      });
    });

    it('shows correct icons for each tab', () => {
      renderWithRouter();

      // Icons are rendered as emoji text
      expect(screen.getByText('🔬')).toBeInTheDocument(); // New Research
      expect(screen.getByText('📡')).toBeInTheDocument(); // Active
      expect(screen.getByText('📊')).toBeInTheDocument(); // Results
      expect(screen.getByText('📅')).toBeInTheDocument(); // Schedule
    });
  });

  describe('Header', () => {
    it('renders the header with title', () => {
      renderWithRouter();

      expect(screen.getByText('Research Hub')).toBeInTheDocument();
    });

    it('renders the subtitle', () => {
      renderWithRouter();

      expect(
        screen.getByText(/Autonomous research pipeline with real-time streaming/)
      ).toBeInTheDocument();
    });
  });

  describe('Layout', () => {
    it('has research-hub class on container', () => {
      const { container } = renderWithRouter();

      expect(container.querySelector('.research-hub')).toBeInTheDocument();
    });

    it('has tabs container', () => {
      const { container } = renderWithRouter();

      expect(container.querySelector('.research-hub-tabs')).toBeInTheDocument();
    });

    it('has content container', () => {
      const { container } = renderWithRouter();

      expect(container.querySelector('.research-hub-content')).toBeInTheDocument();
    });
  });
});

describe('ResearchHub Tab Content', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = () => {
    return render(
      <MemoryRouter initialEntries={['/research']}>
        <ResearchHub />
      </MemoryRouter>
    );
  };

  it('renders NewResearch tab content by default', async () => {
    renderWithRouter();

    // The New Research tab should show the query form
    await waitFor(() => {
      expect(screen.getByText('Start New Research')).toBeInTheDocument();
    });
  });

  it('renders Results tab content when clicked', async () => {
    renderWithRouter();

    fireEvent.click(screen.getByText('Results'));

    await waitFor(() => {
      expect(screen.getByText('Research Results')).toBeInTheDocument();
    });
  });

  it('renders Schedule tab content when clicked', async () => {
    renderWithRouter();

    fireEvent.click(screen.getByText('Schedule'));

    await waitFor(() => {
      expect(screen.getByText('Autonomy Calendar')).toBeInTheDocument();
    });
  });

  it('renders Active Sessions tab content when clicked', async () => {
    renderWithRouter();

    fireEvent.click(screen.getByText('Active'));

    await waitFor(() => {
      expect(screen.getByText('No Active Session')).toBeInTheDocument();
    });
  });
});
