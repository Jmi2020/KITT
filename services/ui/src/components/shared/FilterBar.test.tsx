/**
 * Tests for FilterBar shared component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FilterBar } from './FilterBar';

describe('FilterBar Component', () => {
  describe('Search Input', () => {
    it('renders search input when onSearchChange provided', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar searchValue="" onSearchChange={onSearchChange} />);

      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument();
    });

    it('does not render search input when onSearchChange not provided', () => {
      render(<FilterBar />);

      expect(screen.queryByPlaceholderText('Search...')).not.toBeInTheDocument();
    });

    it('uses custom placeholder', () => {
      const onSearchChange = vi.fn();
      render(
        <FilterBar
          searchValue=""
          onSearchChange={onSearchChange}
          searchPlaceholder="Find items..."
        />
      );

      expect(screen.getByPlaceholderText('Find items...')).toBeInTheDocument();
    });

    it('calls onSearchChange when input changes', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar searchValue="" onSearchChange={onSearchChange} />);

      fireEvent.change(screen.getByPlaceholderText('Search...'), {
        target: { value: 'test query' },
      });

      expect(onSearchChange).toHaveBeenCalledWith('test query');
    });

    it('displays current search value', () => {
      const onSearchChange = vi.fn();
      render(<FilterBar searchValue="existing value" onSearchChange={onSearchChange} />);

      expect(screen.getByPlaceholderText('Search...')).toHaveValue('existing value');
    });
  });

  describe('Filter Selects', () => {
    it('renders filter selects', () => {
      const filters = [
        {
          id: 'type',
          label: 'Type',
          value: '',
          options: [
            { value: '', label: 'All' },
            { value: 'a', label: 'Type A' },
            { value: 'b', label: 'Type B' },
          ],
          onChange: vi.fn(),
        },
      ];

      render(<FilterBar filters={filters} />);

      expect(screen.getByLabelText('Type')).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('renders multiple filters', () => {
      const filters = [
        {
          id: 'type',
          label: 'Type',
          value: '',
          options: [{ value: '', label: 'All' }],
          onChange: vi.fn(),
        },
        {
          id: 'status',
          label: 'Status',
          value: '',
          options: [{ value: '', label: 'All' }],
          onChange: vi.fn(),
        },
      ];

      render(<FilterBar filters={filters} />);

      expect(screen.getByLabelText('Type')).toBeInTheDocument();
      expect(screen.getByLabelText('Status')).toBeInTheDocument();
    });

    it('calls filter onChange when selection changes', () => {
      const onChange = vi.fn();
      const filters = [
        {
          id: 'type',
          label: 'Type',
          value: '',
          options: [
            { value: '', label: 'All' },
            { value: 'a', label: 'Type A' },
          ],
          onChange,
        },
      ];

      render(<FilterBar filters={filters} />);

      fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'a' } });
      expect(onChange).toHaveBeenCalledWith('a');
    });

    it('displays current filter value', () => {
      const filters = [
        {
          id: 'type',
          label: 'Type',
          value: 'a',
          options: [
            { value: '', label: 'All' },
            { value: 'a', label: 'Type A' },
          ],
          onChange: vi.fn(),
        },
      ];

      render(<FilterBar filters={filters} />);

      expect(screen.getByLabelText('Type')).toHaveValue('a');
    });
  });

  describe('Toggle Filters', () => {
    it('renders toggle checkboxes', () => {
      const toggles = [
        {
          id: 'active',
          label: 'Active Only',
          checked: false,
          onChange: vi.fn(),
        },
      ];

      render(<FilterBar toggles={toggles} />);

      expect(screen.getByText('Active Only')).toBeInTheDocument();
      expect(screen.getByRole('checkbox')).toBeInTheDocument();
    });

    it('renders multiple toggles', () => {
      const toggles = [
        { id: 'active', label: 'Active Only', checked: false, onChange: vi.fn() },
        { id: 'featured', label: 'Featured', checked: true, onChange: vi.fn() },
      ];

      render(<FilterBar toggles={toggles} />);

      expect(screen.getByText('Active Only')).toBeInTheDocument();
      expect(screen.getByText('Featured')).toBeInTheDocument();
    });

    it('calls toggle onChange when checkbox changes', () => {
      const onChange = vi.fn();
      const toggles = [
        { id: 'active', label: 'Active Only', checked: false, onChange },
      ];

      render(<FilterBar toggles={toggles} />);

      fireEvent.click(screen.getByRole('checkbox'));
      expect(onChange).toHaveBeenCalledWith(true);
    });

    it('displays current toggle state', () => {
      const toggles = [
        { id: 'active', label: 'Active Only', checked: true, onChange: vi.fn() },
      ];

      render(<FilterBar toggles={toggles} />);

      expect(screen.getByRole('checkbox')).toBeChecked();
    });
  });

  describe('Children', () => {
    it('renders custom children', () => {
      render(
        <FilterBar>
          <button>Custom Action</button>
        </FilterBar>
      );

      expect(screen.getByText('Custom Action')).toBeInTheDocument();
    });
  });

  describe('Custom className', () => {
    it('applies custom className', () => {
      const { container } = render(<FilterBar className="my-filter-bar" />);

      expect(container.querySelector('.filter-bar')).toHaveClass('my-filter-bar');
    });
  });
});
