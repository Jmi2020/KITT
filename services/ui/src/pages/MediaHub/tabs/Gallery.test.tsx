/**
 * Tests for Gallery tab component
 * Tests search, filter, and selection workflows
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Gallery from './Gallery';

// Mock VisionNyan component
vi.mock('../../../components/VisionNyan', () => ({
  default: () => <div data-testid="vision-nyan">VisionNyan</div>,
}));

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock crypto.randomUUID
const mockUUID = 'test-session-uuid-123';
vi.stubGlobal('crypto', {
  randomUUID: () => mockUUID,
});

describe('Gallery Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  describe('Form Controls', () => {
    it('renders query input', () => {
      render(<Gallery />);

      expect(screen.getByPlaceholderText(/gandalf rubber duck/i)).toBeInTheDocument();
    });

    it('renders max results input', () => {
      render(<Gallery />);

      const input = screen.getByRole('spinbutton', { name: /Max results/i });
      expect(input).toBeInTheDocument();
      expect(input).toHaveValue(12);
    });

    it('renders min score input', () => {
      render(<Gallery />);

      const input = screen.getByRole('spinbutton', { name: /Min score/i });
      expect(input).toBeInTheDocument();
      expect(input).toHaveValue(0.2);
    });

    it('renders session ID input', () => {
      render(<Gallery />);

      const input = screen.getByRole('textbox', { name: /Session ID/i });
      expect(input).toBeInTheDocument();
    });

    it('renders search button', () => {
      render(<Gallery />);

      expect(screen.getByRole('button', { name: /Search & Filter/i })).toBeInTheDocument();
    });

    it('renders store button (disabled by default)', () => {
      render(<Gallery />);

      const storeButton = screen.getByRole('button', { name: /Store Selected/i });
      expect(storeButton).toBeInTheDocument();
      expect(storeButton).toBeDisabled();
    });
  });

  describe('Empty State', () => {
    it('shows empty state with VisionNyan', () => {
      render(<Gallery />);

      expect(screen.getByTestId('vision-nyan')).toBeInTheDocument();
      expect(screen.getByText(/Awaiting your next visual brief/i)).toBeInTheDocument();
    });

    it('shows starter prompts', () => {
      render(<Gallery />);

      expect(screen.getByText(/neon-lit robotics lab/i)).toBeInTheDocument();
      expect(screen.getByText(/Surprise me/i)).toBeInTheDocument();
    });
  });

  describe('Search Workflow', () => {
    it('shows error when searching with empty query', async () => {
      render(<Gallery />);

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText(/Enter a query to search/i)).toBeInTheDocument();
      });
    });

    it('submits search request', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: [{ id: '1', image_url: 'http://test.com/img.jpg' }] }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: [{ id: '1', image_url: 'http://test.com/img.jpg', score: 0.9 }] }),
        });

      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/vision/search'),
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    });

    it('shows loading state during search', async () => {
      mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText(/Scanning creative memory/i)).toBeInTheDocument();
      });
    });

    it('handles search error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText(/Search failed/i)).toBeInTheDocument();
      });
    });

    it('shows no results message', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ results: [] }),
      });

      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText(/No results found/i)).toBeInTheDocument();
      });
    });
  });

  describe('Starter Prompts', () => {
    it('searches when starter prompt clicked', async () => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: [] }),
        });

      render(<Gallery />);

      const promptButton = screen.getByText(/neon-lit robotics lab/i);
      await userEvent.click(promptButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalled();
      });
    });
  });

  describe('Results Display', () => {
    const mockResults = [
      { id: '1', title: 'Test Image 1', image_url: 'http://test.com/1.jpg', source: 'test', score: 0.9 },
      { id: '2', title: 'Test Image 2', image_url: 'http://test.com/2.jpg', source: 'test', score: 0.8 },
    ];

    beforeEach(() => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: mockResults }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: mockResults }),
        });
    });

    it('displays result cards', async () => {
      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText('Test Image 1')).toBeInTheDocument();
        expect(screen.getByText('Test Image 2')).toBeInTheDocument();
      });
    });

    it('displays score on result cards', async () => {
      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText(/Score 0.90/i)).toBeInTheDocument();
      });
    });
  });

  describe('Selection', () => {
    const mockResults = [
      { id: '1', title: 'Test Image 1', image_url: 'http://test.com/1.jpg', source: 'test', score: 0.9 },
    ];

    beforeEach(() => {
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: mockResults }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ results: mockResults }),
        });
    });

    it('enables store button when image selected', async () => {
      render(<Gallery />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i);
      await userEvent.type(queryInput, 'test search');

      const searchButton = screen.getByRole('button', { name: /Search & Filter/i });
      await userEvent.click(searchButton);

      await waitFor(() => {
        expect(screen.getByText('Test Image 1')).toBeInTheDocument();
      });

      const checkbox = screen.getByRole('checkbox');
      await userEvent.click(checkbox);

      const storeButton = screen.getByRole('button', { name: /Store Selected/i });
      expect(storeButton).not.toBeDisabled();
    });
  });

  describe('Initial Props', () => {
    it('accepts initialQuery prop', () => {
      render(<Gallery initialQuery="preset query" />);

      const queryInput = screen.getByPlaceholderText(/gandalf rubber duck/i) as HTMLInputElement;
      expect(queryInput.value).toBe('preset query');
    });

    it('accepts initialSession prop', () => {
      render(<Gallery initialSession="custom-session-123" />);

      const sessionInput = screen.getByRole('textbox', { name: /Session ID/i }) as HTMLInputElement;
      expect(sessionInput.value).toBe('custom-session-123');
    });
  });
});
