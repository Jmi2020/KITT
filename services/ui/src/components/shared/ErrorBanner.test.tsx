/**
 * Tests for ErrorBanner shared component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBanner } from './ErrorBanner';

describe('ErrorBanner Component', () => {
  describe('Rendering', () => {
    it('renders error message', () => {
      render(<ErrorBanner message="Something went wrong" />);

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('renders title when provided', () => {
      render(<ErrorBanner message="Details here" title="Error Occurred" />);

      expect(screen.getByText('Error Occurred')).toBeInTheDocument();
      expect(screen.getByText('Details here')).toBeInTheDocument();
    });

    it('does not render title when not provided', () => {
      const { container } = render(<ErrorBanner message="Just a message" />);

      expect(container.querySelector('.error-title')).not.toBeInTheDocument();
    });
  });

  describe('Severity Variants', () => {
    it('applies error severity by default', () => {
      render(<ErrorBanner message="Error" />);

      expect(screen.getByRole('alert')).toHaveClass('error-error');
    });

    it('applies error severity class', () => {
      render(<ErrorBanner message="Error" severity="error" />);

      expect(screen.getByRole('alert')).toHaveClass('error-error');
      expect(screen.getByText('❌')).toBeInTheDocument();
    });

    it('applies warning severity class', () => {
      render(<ErrorBanner message="Warning" severity="warning" />);

      expect(screen.getByRole('alert')).toHaveClass('error-warning');
      expect(screen.getByText('⚠️')).toBeInTheDocument();
    });

    it('applies info severity class', () => {
      render(<ErrorBanner message="Info" severity="info" />);

      expect(screen.getByRole('alert')).toHaveClass('error-info');
      expect(screen.getByText('ℹ️')).toBeInTheDocument();
    });
  });

  describe('Retry Button', () => {
    it('renders retry button when onRetry provided', () => {
      const onRetry = vi.fn();
      render(<ErrorBanner message="Error" onRetry={onRetry} />);

      expect(screen.getByText('Retry')).toBeInTheDocument();
    });

    it('does not render retry button when onRetry not provided', () => {
      render(<ErrorBanner message="Error" />);

      expect(screen.queryByText('Retry')).not.toBeInTheDocument();
    });

    it('calls onRetry when retry button clicked', () => {
      const onRetry = vi.fn();
      render(<ErrorBanner message="Error" onRetry={onRetry} />);

      fireEvent.click(screen.getByText('Retry'));
      expect(onRetry).toHaveBeenCalledTimes(1);
    });

    it('uses custom retry text', () => {
      const onRetry = vi.fn();
      render(<ErrorBanner message="Error" onRetry={onRetry} retryText="Try Again" />);

      expect(screen.getByText('Try Again')).toBeInTheDocument();
    });
  });

  describe('Dismiss Button', () => {
    it('renders dismiss button when onDismiss provided', () => {
      const onDismiss = vi.fn();
      render(<ErrorBanner message="Error" onDismiss={onDismiss} />);

      expect(screen.getByLabelText('Dismiss error')).toBeInTheDocument();
    });

    it('does not render dismiss button when onDismiss not provided', () => {
      render(<ErrorBanner message="Error" />);

      expect(screen.queryByLabelText('Dismiss error')).not.toBeInTheDocument();
    });

    it('calls onDismiss when dismiss button clicked', () => {
      const onDismiss = vi.fn();
      render(<ErrorBanner message="Error" onDismiss={onDismiss} />);

      fireEvent.click(screen.getByLabelText('Dismiss error'));
      expect(onDismiss).toHaveBeenCalledTimes(1);
    });
  });

  describe('Both Actions', () => {
    it('renders both retry and dismiss buttons', () => {
      const onRetry = vi.fn();
      const onDismiss = vi.fn();
      render(
        <ErrorBanner message="Error" onRetry={onRetry} onDismiss={onDismiss} />
      );

      expect(screen.getByText('Retry')).toBeInTheDocument();
      expect(screen.getByLabelText('Dismiss error')).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has alert role', () => {
      render(<ErrorBanner message="Error" />);

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('has aria-live assertive attribute', () => {
      render(<ErrorBanner message="Error" />);

      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive');
    });
  });

  describe('Custom className', () => {
    it('applies custom className', () => {
      render(<ErrorBanner message="Error" className="my-error-banner" />);

      expect(screen.getByRole('alert')).toHaveClass('my-error-banner');
    });
  });
});
