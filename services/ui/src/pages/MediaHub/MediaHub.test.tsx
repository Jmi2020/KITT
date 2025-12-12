/**
 * Tests for MediaHub page
 * Tests tab switching and integration with Generate and Gallery tabs
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MediaHub from './index';

// Mock the tabs
vi.mock('./tabs/Generate', () => ({
  default: () => <div data-testid="generate-tab">Generate Tab Content</div>,
}));

vi.mock('./tabs/Gallery', () => ({
  default: ({ initialQuery, initialSession }: { initialQuery?: string; initialSession?: string }) => (
    <div data-testid="gallery-tab">
      Gallery Tab Content
      {initialQuery && <span data-testid="initial-query">{initialQuery}</span>}
      {initialSession && <span data-testid="initial-session">{initialSession}</span>}
    </div>
  ),
}));

describe('MediaHub Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (initialEntries = ['/media']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <MediaHub />
      </MemoryRouter>
    );
  };

  describe('Header', () => {
    it('renders the header', () => {
      renderWithRouter();

      expect(screen.getByText('Media Hub')).toBeInTheDocument();
      expect(screen.getByText(/Generate images with Stable Diffusion/)).toBeInTheDocument();
    });
  });

  describe('Tab Navigation', () => {
    it('renders both tabs', () => {
      renderWithRouter();

      expect(screen.getByText('Generate')).toBeInTheDocument();
      expect(screen.getByText('Gallery')).toBeInTheDocument();
    });

    it('shows Generate tab by default', () => {
      renderWithRouter();

      const generateTab = screen.getByText('Generate').closest('button');
      expect(generateTab).toHaveClass('active');
      expect(screen.getByTestId('generate-tab')).toBeInTheDocument();
    });

    it('switches to Gallery tab when clicked', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Gallery'));

      await waitFor(() => {
        const galleryTab = screen.getByText('Gallery').closest('button');
        expect(galleryTab).toHaveClass('active');
        expect(screen.getByTestId('gallery-tab')).toBeInTheDocument();
      });
    });

    it('switches back to Generate tab when clicked', async () => {
      renderWithRouter();

      // First switch to Gallery
      fireEvent.click(screen.getByText('Gallery'));
      await waitFor(() => {
        expect(screen.getByTestId('gallery-tab')).toBeInTheDocument();
      });

      // Then switch back to Generate
      fireEvent.click(screen.getByText('Generate'));
      await waitFor(() => {
        const generateTab = screen.getByText('Generate').closest('button');
        expect(generateTab).toHaveClass('active');
        expect(screen.getByTestId('generate-tab')).toBeInTheDocument();
      });
    });
  });

  describe('Generate Tab', () => {
    it('renders generate content by default', () => {
      renderWithRouter();

      expect(screen.getByTestId('generate-tab')).toBeInTheDocument();
    });
  });

  describe('Gallery Tab', () => {
    it('renders gallery content when Gallery tab is active', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Gallery'));

      await waitFor(() => {
        expect(screen.getByTestId('gallery-tab')).toBeInTheDocument();
      });
    });
  });

  describe('URL Tab Param', () => {
    it('opens correct tab from URL param', () => {
      renderWithRouter(['/media?tab=gallery']);

      const galleryTab = screen.getByText('Gallery').closest('button');
      expect(galleryTab).toHaveClass('active');
    });

    it('opens generate tab from URL param', () => {
      renderWithRouter(['/media?tab=generate']);

      const generateTab = screen.getByText('Generate').closest('button');
      expect(generateTab).toHaveClass('active');
    });

    it('defaults to generate for invalid tab param', () => {
      renderWithRouter(['/media?tab=invalid']);

      const generateTab = screen.getByText('Generate').closest('button');
      expect(generateTab).toHaveClass('active');
    });
  });

  describe('Gallery Query Params', () => {
    it('passes query param to Gallery tab', async () => {
      renderWithRouter(['/media?tab=gallery&query=test+search']);

      await waitFor(() => {
        expect(screen.getByTestId('initial-query')).toHaveTextContent('test search');
      });
    });

    it('passes session param to Gallery tab', async () => {
      renderWithRouter(['/media?tab=gallery&session=test-session-123']);

      await waitFor(() => {
        expect(screen.getByTestId('initial-session')).toHaveTextContent('test-session-123');
      });
    });
  });
});
