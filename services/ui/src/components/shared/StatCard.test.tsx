/**
 * Tests for StatCard shared component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StatCard } from './StatCard';

describe('StatCard Component', () => {
  describe('Rendering', () => {
    it('renders label and value', () => {
      render(<StatCard label="Total Items" value={42} />);

      expect(screen.getByText('Total Items')).toBeInTheDocument();
      expect(screen.getByText('42')).toBeInTheDocument();
    });

    it('renders string value', () => {
      render(<StatCard label="Status" value="Active" />);

      expect(screen.getByText('Active')).toBeInTheDocument();
    });

    it('renders icon when provided', () => {
      render(<StatCard label="Users" value={100} icon="👤" />);

      expect(screen.getByText('👤')).toBeInTheDocument();
    });

    it('renders subtitle when provided', () => {
      render(<StatCard label="Revenue" value="$1,234" subtitle="This month" />);

      expect(screen.getByText('This month')).toBeInTheDocument();
    });

    it('does not render icon when not provided', () => {
      render(<StatCard label="Items" value={10} />);

      const card = screen.getByText('Items').closest('.stat-card');
      expect(card?.querySelector('.stat-icon')).not.toBeInTheDocument();
    });
  });

  describe('Variants', () => {
    it('applies success variant class', () => {
      render(<StatCard label="Success" value={100} variant="success" />);

      const card = screen.getByText('Success').closest('.stat-card');
      expect(card).toHaveClass('stat-success');
    });

    it('applies warning variant class', () => {
      render(<StatCard label="Warning" value={50} variant="warning" />);

      const card = screen.getByText('Warning').closest('.stat-card');
      expect(card).toHaveClass('stat-warning');
    });

    it('applies danger variant class', () => {
      render(<StatCard label="Danger" value={0} variant="danger" />);

      const card = screen.getByText('Danger').closest('.stat-card');
      expect(card).toHaveClass('stat-danger');
    });

    it('applies info variant class', () => {
      render(<StatCard label="Info" value="N/A" variant="info" />);

      const card = screen.getByText('Info').closest('.stat-card');
      expect(card).toHaveClass('stat-info');
    });

    it('does not apply variant class for default variant', () => {
      render(<StatCard label="Default" value={10} variant="default" />);

      const card = screen.getByText('Default').closest('.stat-card');
      expect(card).not.toHaveClass('stat-default');
    });
  });

  describe('Click Handler', () => {
    it('calls onClick when clicked', () => {
      const onClick = vi.fn();
      render(<StatCard label="Clickable" value={10} onClick={onClick} />);

      fireEvent.click(screen.getByText('Clickable').closest('.stat-card')!);
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('applies clickable class when onClick provided', () => {
      const onClick = vi.fn();
      render(<StatCard label="Clickable" value={10} onClick={onClick} />);

      const card = screen.getByText('Clickable').closest('.stat-card');
      expect(card).toHaveClass('stat-clickable');
    });

    it('has button role when clickable', () => {
      const onClick = vi.fn();
      render(<StatCard label="Clickable" value={10} onClick={onClick} />);

      const card = screen.getByText('Clickable').closest('.stat-card');
      expect(card).toHaveAttribute('role', 'button');
    });

    it('responds to Enter key when clickable', () => {
      const onClick = vi.fn();
      render(<StatCard label="Clickable" value={10} onClick={onClick} />);

      const card = screen.getByText('Clickable').closest('.stat-card');
      fireEvent.keyDown(card!, { key: 'Enter' });
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it('does not have button role when not clickable', () => {
      render(<StatCard label="Static" value={10} />);

      const card = screen.getByText('Static').closest('.stat-card');
      expect(card).not.toHaveAttribute('role');
    });
  });

  describe('Custom className', () => {
    it('applies custom className', () => {
      render(<StatCard label="Custom" value={10} className="my-custom-class" />);

      const card = screen.getByText('Custom').closest('.stat-card');
      expect(card).toHaveClass('my-custom-class');
    });
  });
});
