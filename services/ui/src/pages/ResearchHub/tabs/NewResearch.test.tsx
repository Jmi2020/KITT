/**
 * Tests for NewResearch tab component
 * Tests form validation, template selection, and submission
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NewResearch from './NewResearch';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { ResearchSession } from '../../../types/research';

// Create mock API
const createMockApi = (overrides: Partial<UseResearchApiReturn> = {}): UseResearchApiReturn => ({
  sessions: [],
  templates: [
    {
      id: 't1',
      name: 'Technical Research',
      description: 'Deep technical analysis',
      query_template: 'Research {topic} in depth',
      default_strategy: 'comprehensive',
      default_max_iterations: 10,
      default_max_cost: 2.0,
      suggested_paid_tools: ['perplexity'],
    },
    {
      id: 't2',
      name: 'Quick Lookup',
      description: 'Fast simple queries',
      query_template: 'Find information about {topic}',
      default_strategy: 'quick',
      default_max_iterations: 3,
      default_max_cost: 0.5,
      suggested_paid_tools: [],
    },
  ],
  schedules: [],
  scheduleHistory: [],
  loading: false,
  error: null,
  isConnected: false,
  createSession: vi.fn(),
  loadSessions: vi.fn(),
  loadSessionDetails: vi.fn(),
  pauseSession: vi.fn(),
  resumeSession: vi.fn(),
  cancelSession: vi.fn(),
  loadTemplates: vi.fn(),
  loadResults: vi.fn(),
  generateSynthesis: vi.fn(),
  loadSchedules: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  loadScheduleHistory: vi.fn(),
  connectWebSocket: vi.fn(),
  disconnectWebSocket: vi.fn(),
  ...overrides,
});

describe('NewResearch Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the form', () => {
    const mockApi = createMockApi();
    render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

    expect(screen.getByText('Start New Research')).toBeInTheDocument();
    expect(screen.getByLabelText(/Research Query/i)).toBeInTheDocument();
  });

  it('renders template selection', () => {
    const mockApi = createMockApi();
    render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

    // Templates render in select dropdown
    expect(screen.getByLabelText(/Research Template/i)).toBeInTheDocument();
  });

  it('renders strategy dropdown', () => {
    const mockApi = createMockApi();
    render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

    expect(screen.getByLabelText(/Strategy/i)).toBeInTheDocument();
  });

  it('renders iteration slider', () => {
    const mockApi = createMockApi();
    render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

    expect(screen.getByLabelText(/Max Iterations/i)).toBeInTheDocument();
  });

  it('renders cost input', () => {
    const mockApi = createMockApi();
    render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

    expect(screen.getByLabelText(/Max Cost/i)).toBeInTheDocument();
  });

  describe('Form Submission', () => {
    it('calls createSession when form is submitted', async () => {
      const mockSession = {
        session_id: 'new-session',
        query: 'Test query',
      } as ResearchSession;

      const mockApi = createMockApi({
        createSession: vi.fn().mockResolvedValue(mockSession),
      });
      const onSessionCreated = vi.fn();

      render(<NewResearch api={mockApi} onSessionCreated={onSessionCreated} />);

      // Fill in the query
      const queryInput = screen.getByLabelText(/Research Query/i);
      await userEvent.type(queryInput, 'Test research query');

      // Submit the form
      const submitButton = screen.getByRole('button', { name: /Start Research/i });
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(mockApi.createSession).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(onSessionCreated).toHaveBeenCalledWith(mockSession);
      });
    });

    it('disables submit button when query is empty', () => {
      const mockApi = createMockApi();
      render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

      const submitButton = screen.getByRole('button', { name: /Start Research/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when query has content', async () => {
      const mockApi = createMockApi();
      render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

      const queryInput = screen.getByLabelText(/Research Query/i);
      await userEvent.type(queryInput, 'Test query');

      const submitButton = screen.getByRole('button', { name: /Start Research/i });
      expect(submitButton).not.toBeDisabled();
    });

    it('disables submit when loading', () => {
      const mockApi = createMockApi({ loading: true });
      render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

      // When loading, button text changes to "Creating Session..."
      const submitButton = screen.getByRole('button', { name: /Creating Session/i });
      expect(submitButton).toBeDisabled();
    });
  });

  describe('Paid Tools', () => {
    it('renders paid tools toggle', () => {
      const mockApi = createMockApi();
      render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

      expect(screen.getByLabelText(/Paid Tools/i)).toBeInTheDocument();
    });
  });

  describe('Hierarchical Toggle', () => {
    it('renders hierarchical mode toggle', () => {
      const mockApi = createMockApi();
      render(<NewResearch api={mockApi} onSessionCreated={vi.fn()} />);

      expect(screen.getByLabelText(/Hierarchical/i)).toBeInTheDocument();
    });
  });
});
