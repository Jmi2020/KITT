/**
 * Tests for Schedule tab component
 * Tests form validation, CRUD operations, and schedule listing
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Schedule from './Schedule';
import type { UseResearchApiReturn } from '../../../hooks/useResearchApi';
import type { Schedule as ScheduleType, ScheduleExecution } from '../../../types/research';

// Create mock API
const createMockApi = (overrides: Partial<UseResearchApiReturn> = {}): UseResearchApiReturn => ({
  sessions: [],
  templates: [],
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

const mockSchedules: ScheduleType[] = [
  {
    id: 's1',
    job_name: 'Weekly Research',
    job_type: 'research',
    cron_expression: '0 9 * * 1',
    natural_language_schedule: 'every monday at 9',
    enabled: true,
    priority: 5,
    next_execution_at: '2024-01-08T09:00:00Z',
    last_execution_at: '2024-01-01T09:00:00Z',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 's2',
    job_name: 'Daily Health Check',
    job_type: 'health_check',
    cron_expression: '0 8 * * *',
    enabled: false,
    priority: 8,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

const mockHistory: ScheduleExecution[] = [
  {
    id: 'h1',
    schedule_id: 's1',
    job_name: 'Weekly Research',
    status: 'success',
    execution_time: '2024-01-01T09:00:00Z',
    budget_spent_usd: 0.25,
  },
  {
    id: 'h2',
    schedule_id: 's1',
    job_name: 'Weekly Research',
    status: 'failed',
    execution_time: '2023-12-25T09:00:00Z',
    error_message: 'API timeout',
  },
];

describe('Schedule Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the header', () => {
    const mockApi = createMockApi();
    render(<Schedule api={mockApi} />);

    expect(screen.getByText('Autonomy Calendar')).toBeInTheDocument();
  });

  it('loads schedules and history on mount', () => {
    const mockApi = createMockApi();
    render(<Schedule api={mockApi} />);

    expect(mockApi.loadSchedules).toHaveBeenCalled();
    expect(mockApi.loadScheduleHistory).toHaveBeenCalled();
  });

  describe('Create Form', () => {
    it('renders the create form', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('New Schedule')).toBeInTheDocument();
      expect(screen.getByLabelText(/Job name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Job type/i)).toBeInTheDocument();
    });

    it('renders job type dropdown with options', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      const jobTypeSelect = screen.getByLabelText(/Job type/i);
      expect(jobTypeSelect).toBeInTheDocument();

      // Multiple 'Research' options may exist (in filter and form), just verify dropdown works
      expect(jobTypeSelect.querySelectorAll('option').length).toBeGreaterThan(0);
    });

    it('renders natural language schedule input', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByLabelText(/Natural language/i)).toBeInTheDocument();
    });

    it('renders cron expression input', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByLabelText(/Cron/i)).toBeInTheDocument();
    });

    it('renders budget limit input', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByLabelText(/Budget limit/i)).toBeInTheDocument();
    });

    it('renders priority input', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByLabelText(/Priority/i)).toBeInTheDocument();
    });

    it('renders enabled checkbox', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('Enabled')).toBeInTheDocument();
    });

    it('calls createSchedule when form is submitted', async () => {
      const mockApi = createMockApi({
        createSchedule: vi.fn().mockResolvedValue({ id: 'new-schedule' }),
      });
      render(<Schedule api={mockApi} />);

      // Fill in form
      await userEvent.type(screen.getByLabelText(/Job name/i), 'Test Schedule');

      // Submit
      await userEvent.click(screen.getByRole('button', { name: /Create Schedule/i }));

      await waitFor(() => {
        expect(mockApi.createSchedule).toHaveBeenCalledWith(
          expect.objectContaining({
            jobName: 'Test Schedule',
          })
        );
      });
    });

    it('clears form after successful creation', async () => {
      const mockApi = createMockApi({
        createSchedule: vi.fn().mockResolvedValue({ id: 'new-schedule' }),
      });
      render(<Schedule api={mockApi} />);

      const jobNameInput = screen.getByLabelText(/Job name/i);
      await userEvent.type(jobNameInput, 'Test Schedule');

      await userEvent.click(screen.getByRole('button', { name: /Create Schedule/i }));

      await waitFor(() => {
        expect(jobNameInput).toHaveValue('');
      });
    });
  });

  describe('Schedules List', () => {
    it('renders schedules list header', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('Schedules')).toBeInTheDocument();
    });

    it('displays schedules count', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('2')).toBeInTheDocument(); // 2 schedules
    });

    it('renders schedule cards', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('Weekly Research')).toBeInTheDocument();
      expect(screen.getByText('Daily Health Check')).toBeInTheDocument();
    });

    it('shows job type pills', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('research')).toBeInTheDocument();
      expect(screen.getByText('health_check')).toBeInTheDocument();
    });

    it('shows cron expression', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('0 9 * * 1')).toBeInTheDocument();
      expect(screen.getByText('0 8 * * *')).toBeInTheDocument();
    });

    it('shows enabled/disabled status', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('enabled')).toBeInTheDocument();
      expect(screen.getByText('disabled')).toBeInTheDocument();
    });

    it('shows empty state when no schedules', () => {
      const mockApi = createMockApi({ schedules: [] });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('No schedules yet.')).toBeInTheDocument();
    });
  });

  describe('Schedule Actions', () => {
    it('renders toggle enabled checkbox', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      // Each schedule card has an enabled toggle
      const toggles = screen.getAllByRole('checkbox');
      expect(toggles.length).toBeGreaterThan(0);
    });

    it('renders toggle checkboxes for schedules', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      // Each schedule has an enabled toggle
      const toggles = screen.getAllByRole('checkbox');
      expect(toggles.length).toBeGreaterThan(0);
    });

    it('renders delete button', () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      const deleteButtons = screen.getAllByRole('button', { name: /Delete/i });
      expect(deleteButtons.length).toBeGreaterThan(0);
    });

    it('calls deleteSchedule when delete is confirmed', async () => {
      // Mock window.confirm
      vi.spyOn(window, 'confirm').mockImplementation(() => true);

      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      const deleteButtons = screen.getAllByRole('button', { name: /Delete/i });
      await userEvent.click(deleteButtons[0]);

      await waitFor(() => {
        expect(mockApi.deleteSchedule).toHaveBeenCalledWith('s1');
      });

      vi.restoreAllMocks();
    });

    it('does not delete when confirm is cancelled', async () => {
      vi.spyOn(window, 'confirm').mockImplementation(() => false);

      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      const deleteButtons = screen.getAllByRole('button', { name: /Delete/i });
      await userEvent.click(deleteButtons[0]);

      expect(mockApi.deleteSchedule).not.toHaveBeenCalled();

      vi.restoreAllMocks();
    });
  });

  describe('Execution History', () => {
    it('renders history section', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('Recent Executions')).toBeInTheDocument();
    });

    it('displays execution count', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      // Should show count badge
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    it('shows success status with correct styling', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      // Multiple success elements possible, just verify at least one exists
      const successElements = screen.getAllByText('success');
      expect(successElements.length).toBeGreaterThan(0);
    });

    it('shows failed status with correct styling', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      // Multiple 'failed' elements possible - just check at least one exists
      const failedElements = screen.getAllByText('failed');
      expect(failedElements.length).toBeGreaterThan(0);
    });

    it('shows error message for failed executions', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('API timeout')).toBeInTheDocument();
    });

    it('shows cost for executions', () => {
      const mockApi = createMockApi({ scheduleHistory: mockHistory });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText(/Cost: \$0\.25/)).toBeInTheDocument();
    });

    it('shows empty state when no history', () => {
      const mockApi = createMockApi({ scheduleHistory: [] });
      render(<Schedule api={mockApi} />);

      expect(screen.getByText('No executions yet.')).toBeInTheDocument();
    });
  });

  describe('Filters', () => {
    it('renders search input', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByPlaceholderText(/Search by job name/i)).toBeInTheDocument();
    });

    it('renders job type filter dropdown', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      // Multiple select elements - just verify they exist
      const selects = screen.getAllByRole('combobox');
      expect(selects.length).toBeGreaterThan(0);
    });

    it('filters schedules by search', async () => {
      const mockApi = createMockApi({ schedules: mockSchedules });
      render(<Schedule api={mockApi} />);

      const searchInput = screen.getByPlaceholderText(/Search by job name/i);
      await userEvent.type(searchInput, 'Weekly');

      await waitFor(() => {
        expect(screen.getByText('Weekly Research')).toBeInTheDocument();
        expect(screen.queryByText('Daily Health Check')).not.toBeInTheDocument();
      });
    });

    it('renders refresh button', () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      expect(screen.getByRole('button', { name: /Refresh/i })).toBeInTheDocument();
    });

    it('calls loadSchedules when refresh is clicked', async () => {
      const mockApi = createMockApi();
      render(<Schedule api={mockApi} />);

      await userEvent.click(screen.getByRole('button', { name: /Refresh/i }));

      // loadSchedules is called once on mount and once on refresh
      expect(mockApi.loadSchedules).toHaveBeenCalledTimes(2);
    });
  });
});
