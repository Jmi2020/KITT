/**
 * Tests for LoadingState shared component
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LoadingState } from './LoadingState';

describe('LoadingState Component', () => {
  describe('Rendering', () => {
    it('renders with default message', () => {
      render(<LoadingState />);

      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('renders with custom message', () => {
      render(<LoadingState message="Fetching data..." />);

      expect(screen.getByText('Fetching data...')).toBeInTheDocument();
    });

    it('does not render message when empty string', () => {
      render(<LoadingState message="" />);

      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    it('renders spinner', () => {
      const { container } = render(<LoadingState />);

      expect(container.querySelector('.spinner')).toBeInTheDocument();
    });
  });

  describe('Sizes', () => {
    it('applies small size class', () => {
      const { container } = render(<LoadingState size="small" />);

      expect(container.querySelector('.loading-state')).toHaveClass('loading-small');
    });

    it('applies medium size class (default)', () => {
      const { container } = render(<LoadingState />);

      expect(container.querySelector('.loading-state')).toHaveClass('loading-medium');
    });

    it('applies large size class', () => {
      const { container } = render(<LoadingState size="large" />);

      expect(container.querySelector('.loading-state')).toHaveClass('loading-large');
    });
  });

  describe('Overlay Mode', () => {
    it('does not render overlay by default', () => {
      const { container } = render(<LoadingState />);

      expect(container.querySelector('.loading-overlay')).not.toBeInTheDocument();
    });

    it('renders overlay when overlay prop is true', () => {
      const { container } = render(<LoadingState overlay />);

      expect(container.querySelector('.loading-overlay')).toBeInTheDocument();
    });

    it('renders loading state inside overlay', () => {
      const { container } = render(<LoadingState overlay message="Processing..." />);

      const overlay = container.querySelector('.loading-overlay');
      expect(overlay?.querySelector('.loading-state')).toBeInTheDocument();
      expect(screen.getByText('Processing...')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has status role', () => {
      render(<LoadingState />);

      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('has aria-live polite attribute', () => {
      render(<LoadingState />);

      expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    });

    it('spinner has aria-hidden', () => {
      const { container } = render(<LoadingState />);

      expect(container.querySelector('.loading-spinner')).toHaveAttribute(
        'aria-hidden',
        'true'
      );
    });
  });

  describe('Custom className', () => {
    it('applies custom className', () => {
      const { container } = render(<LoadingState className="my-loading" />);

      expect(container.querySelector('.loading-state')).toHaveClass('my-loading');
    });
  });
});
