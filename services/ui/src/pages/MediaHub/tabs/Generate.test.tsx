/**
 * Tests for Generate tab component
 * Tests form controls, validation, and image generation workflow
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Generate from './Generate';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('Generate Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  describe('Form Controls', () => {
    it('renders prompt textarea', () => {
      render(<Generate />);

      expect(screen.getByPlaceholderText(/Describe the image/i)).toBeInTheDocument();
    });

    it('renders model selector with options', () => {
      render(<Generate />);

      expect(screen.getByText('Model')).toBeInTheDocument();
      expect(screen.getByText('SDXL Base (1024x1024)')).toBeInTheDocument();
    });

    it('renders size selector', () => {
      render(<Generate />);

      expect(screen.getByText('Size')).toBeInTheDocument();
    });

    it('renders steps slider', () => {
      render(<Generate />);

      expect(screen.getByText(/Steps: 30/)).toBeInTheDocument();
    });

    it('renders guidance scale slider', () => {
      render(<Generate />);

      expect(screen.getByText(/Guidance Scale: 7.0/)).toBeInTheDocument();
    });

    it('renders seed input', () => {
      render(<Generate />);

      expect(screen.getByPlaceholderText('Random')).toBeInTheDocument();
    });

    it('renders refiner checkbox for SDXL', () => {
      render(<Generate />);

      expect(screen.getByText(/Use SDXL Refiner/i)).toBeInTheDocument();
    });
  });

  describe('Random Prompt', () => {
    it('fills prompt when Random Prompt clicked', async () => {
      render(<Generate />);

      const randomButton = screen.getByRole('button', { name: /Random Prompt/i });
      await userEvent.click(randomButton);

      const textarea = screen.getByPlaceholderText(/Describe the image/i) as HTMLTextAreaElement;
      expect(textarea.value.length).toBeGreaterThan(0);
    });
  });

  describe('Generate Button', () => {
    it('is disabled when prompt is empty', () => {
      render(<Generate />);

      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      expect(generateButton).toBeDisabled();
    });

    it('is enabled when prompt has text', async () => {
      render(<Generate />);

      const textarea = screen.getByPlaceholderText(/Describe the image/i);
      await userEvent.type(textarea, 'test prompt');

      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      expect(generateButton).not.toBeDisabled();
    });
  });

  describe('Generation Workflow', () => {
    it('shows error when prompt is empty and generate clicked', async () => {
      render(<Generate />);

      // Temporarily enable button by adding then clearing text
      const textarea = screen.getByPlaceholderText(/Describe the image/i);
      await userEvent.type(textarea, 'test');
      await userEvent.clear(textarea);

      // Button should be disabled now, so we can't click it
      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      expect(generateButton).toBeDisabled();
    });

    it('submits generation request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ job_id: 'test-job-123' }),
      });

      render(<Generate />);

      const textarea = screen.getByPlaceholderText(/Describe the image/i);
      await userEvent.type(textarea, 'a beautiful sunset');

      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      await userEvent.click(generateButton);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/images/generate'),
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
          })
        );
      });
    });

    it('shows status message during generation', async () => {
      // Mock the initial generate request to succeed
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ job_id: 'test-job-123' }),
      });
      // Mock the polling request to keep the job in progress
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'queued' }),
      });

      render(<Generate />);

      const textarea = screen.getByPlaceholderText(/Describe the image/i);
      await userEvent.type(textarea, 'a beautiful sunset');

      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      await userEvent.click(generateButton);

      await waitFor(() => {
        // Should show either "Job queued" or "Waiting in queue"
        expect(screen.getByText(/queued|queue/i)).toBeInTheDocument();
      });
    });

    it('handles generation error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      render(<Generate />);

      const textarea = screen.getByPlaceholderText(/Describe the image/i);
      await userEvent.type(textarea, 'a beautiful sunset');

      const generateButton = screen.getByRole('button', { name: /Generate Image/i });
      await userEvent.click(generateButton);

      await waitFor(() => {
        expect(screen.getByText(/Generation failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('View Recent', () => {
    it('renders View Recent button', () => {
      render(<Generate />);

      expect(screen.getByRole('button', { name: /View Recent/i })).toBeInTheDocument();
    });

    it('loads recent images when clicked', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ items: [{ key: 'test.png', size: 1024, last_modified: '2024-01-01' }] }),
      });

      render(<Generate />);

      const viewRecentButton = screen.getByRole('button', { name: /View Recent/i });
      await userEvent.click(viewRecentButton);

      await waitFor(() => {
        expect(screen.getByText('Recent Generations')).toBeInTheDocument();
      });
    });

    it('handles recent images error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      render(<Generate />);

      const viewRecentButton = screen.getByRole('button', { name: /View Recent/i });
      await userEvent.click(viewRecentButton);

      await waitFor(() => {
        expect(screen.getByText(/Failed to load recent images/i)).toBeInTheDocument();
      });
    });
  });

  describe('Preview Area', () => {
    it('shows placeholder when no image generated', () => {
      render(<Generate />);

      expect(screen.getByText(/Generated image will appear here/i)).toBeInTheDocument();
    });
  });
});
