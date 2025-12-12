/**
 * Tests for Modal shared component
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Modal } from './Modal';

describe('Modal Component', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    title: 'Test Modal',
    children: <p>Modal content</p>,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    document.body.style.overflow = '';
  });

  describe('Rendering', () => {
    it('renders when isOpen is true', () => {
      render(<Modal {...defaultProps} />);

      expect(screen.getByText('Test Modal')).toBeInTheDocument();
      expect(screen.getByText('Modal content')).toBeInTheDocument();
    });

    it('does not render when isOpen is false', () => {
      render(<Modal {...defaultProps} isOpen={false} />);

      expect(screen.queryByText('Test Modal')).not.toBeInTheDocument();
    });

    it('renders footer when provided', () => {
      render(
        <Modal {...defaultProps} footer={<button>Save</button>} />
      );

      expect(screen.getByText('Save')).toBeInTheDocument();
    });

    it('does not render footer when not provided', () => {
      render(<Modal {...defaultProps} />);

      expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    });

    it('applies custom className', () => {
      render(<Modal {...defaultProps} className="custom-modal" />);

      const modalContent = screen.getByRole('dialog');
      expect(modalContent).toHaveClass('custom-modal');
    });
  });

  describe('Closing Behavior', () => {
    it('calls onClose when close button clicked', () => {
      render(<Modal {...defaultProps} />);

      fireEvent.click(screen.getByLabelText('Close modal'));
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when overlay clicked', () => {
      render(<Modal {...defaultProps} />);

      const overlay = screen.getByRole('dialog').parentElement;
      fireEvent.click(overlay!);
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('does not call onClose when overlay clicked and closeOnOverlayClick is false', () => {
      render(<Modal {...defaultProps} closeOnOverlayClick={false} />);

      const overlay = screen.getByRole('dialog').parentElement;
      fireEvent.click(overlay!);
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });

    it('does not call onClose when modal content clicked', () => {
      render(<Modal {...defaultProps} />);

      fireEvent.click(screen.getByRole('dialog'));
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });

    it('calls onClose when Escape pressed', () => {
      render(<Modal {...defaultProps} />);

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(defaultProps.onClose).toHaveBeenCalledTimes(1);
    });

    it('does not call onClose when Escape pressed and closeOnEscape is false', () => {
      render(<Modal {...defaultProps} closeOnEscape={false} />);

      fireEvent.keyDown(document, { key: 'Escape' });
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });
  });

  describe('Body Scroll Lock', () => {
    it('locks body scroll when open', () => {
      render(<Modal {...defaultProps} />);

      expect(document.body.style.overflow).toBe('hidden');
    });

    it('restores body scroll when closed', () => {
      const { rerender } = render(<Modal {...defaultProps} />);

      rerender(<Modal {...defaultProps} isOpen={false} />);
      expect(document.body.style.overflow).toBe('');
    });
  });

  describe('Accessibility', () => {
    it('has correct dialog role', () => {
      render(<Modal {...defaultProps} />);

      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('has aria-modal attribute', () => {
      render(<Modal {...defaultProps} />);

      expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true');
    });

    it('has aria-labelledby pointing to title', () => {
      render(<Modal {...defaultProps} />);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title');
      expect(screen.getByText('Test Modal')).toHaveAttribute('id', 'modal-title');
    });
  });
});
