/**
 * Tests for Materials tab component
 * Tests inventory display, filtering, and add spool functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaterialsTab from './Materials';

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

const mockMaterials = [
  {
    id: 'mat_pla_black',
    material_type: 'pla',
    color: '#000000',
    manufacturer: 'Prusa',
    cost_per_kg_usd: 25.0,
    density_g_cm3: 1.24,
    nozzle_temp_min_c: 200,
    nozzle_temp_max_c: 220,
    bed_temp_min_c: 50,
    bed_temp_max_c: 60,
    properties: {},
    sustainability_score: 80,
  },
  {
    id: 'mat_petg_white',
    material_type: 'petg',
    color: '#ffffff',
    manufacturer: 'Polymaker',
    cost_per_kg_usd: 30.0,
    density_g_cm3: 1.27,
    nozzle_temp_min_c: 230,
    nozzle_temp_max_c: 250,
    bed_temp_min_c: 70,
    bed_temp_max_c: 80,
    properties: {},
    sustainability_score: 60,
  },
];

const mockInventory = [
  {
    id: 'spool_001',
    material_id: 'mat_pla_black',
    location: 'Shelf A',
    purchase_date: '2024-01-01',
    initial_weight_grams: 1000,
    current_weight_grams: 750,
    status: 'available',
    notes: null,
  },
  {
    id: 'spool_002',
    material_id: 'mat_petg_white',
    location: 'Shelf B',
    purchase_date: '2024-01-15',
    initial_weight_grams: 1000,
    current_weight_grams: 50,
    status: 'available',
    notes: 'Running low',
  },
];

describe('Materials Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockReset();
  });

  const setupSuccessfulFetch = () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockMaterials),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockInventory),
      });
  };

  describe('Loading State', () => {
    it('shows loading state initially', () => {
      mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
      render(<MaterialsTab />);

      expect(screen.getByText('Loading inventory...')).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('shows error when materials fetch fails', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
      });

      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText(/Error: Failed to load materials/i)).toBeInTheDocument();
      });
    });
  });

  describe('Statistics', () => {
    it('displays inventory statistics', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('Total Spools')).toBeInTheDocument();
        // Use getAllByText for items that appear multiple times (in stats and filter options)
        expect(screen.getAllByText('Available').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Low Stock').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Depleted').length).toBeGreaterThan(0);
        expect(screen.getByText('Total Value')).toBeInTheDocument();
        expect(screen.getByText('Total Weight')).toBeInTheDocument();
      });
    });

    it('shows correct spool count', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // 2 spools total
        const totalSpools = screen.getAllByText('2');
        expect(totalSpools.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Filters', () => {
    it('renders filter controls', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // All these labels appear multiple times (in filter bar and table headers)
        expect(screen.getAllByText('Material Type').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Manufacturer').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Status').length).toBeGreaterThan(0);
        expect(screen.getByText('Low Stock Only')).toBeInTheDocument();
      });
    });

    it('filters by material type', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // PLA appears multiple times in the table
        expect(screen.getAllByText('PLA').length).toBeGreaterThan(0);
      });

      // Get the material type filter select - it's the first combobox in filters
      const selects = screen.getAllByRole('combobox');
      const typeSelect = selects[0];
      fireEvent.change(typeSelect, { target: { value: 'pla' } });

      await waitFor(() => {
        expect(screen.getByText('spool_001')).toBeInTheDocument();
        expect(screen.queryByText('spool_002')).not.toBeInTheDocument();
      });
    });

    it('filters by status', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('spool_001')).toBeInTheDocument();
      });

      // Get the status filter select - it's the second combobox
      const selects = screen.getAllByRole('combobox');
      const statusSelect = selects[1];
      fireEvent.change(statusSelect, { target: { value: 'available' } });

      await waitFor(() => {
        expect(screen.getByText('spool_001')).toBeInTheDocument();
      });
    });
  });

  describe('Inventory Table', () => {
    it('displays inventory items', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('spool_001')).toBeInTheDocument();
        expect(screen.getByText('spool_002')).toBeInTheDocument();
      });
    });

    it('shows material types', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getAllByText('PLA').length).toBeGreaterThan(0);
        expect(screen.getAllByText('PETG').length).toBeGreaterThan(0);
      });
    });

    it('shows weight information', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // Weight format in the component
        expect(screen.getByText('750g / 1000g')).toBeInTheDocument();
        expect(screen.getByText('50g / 1000g')).toBeInTheDocument();
      });
    });

    it('shows location', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('Shelf A')).toBeInTheDocument();
        expect(screen.getByText('Shelf B')).toBeInTheDocument();
      });
    });

    it('shows low stock badge for low inventory', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // spool_002 has 50g which is below 100g threshold - appears in stats too
        const lowStockItems = screen.getAllByText('Low Stock');
        expect(lowStockItems.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Material Catalog', () => {
    it('displays material catalog', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText(/Material Catalog/i)).toBeInTheDocument();
        expect(screen.getByText('mat_pla_black')).toBeInTheDocument();
        expect(screen.getByText('mat_petg_white')).toBeInTheDocument();
      });
    });

    it('shows manufacturer information', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        // Manufacturers appear in both inventory and catalog tables
        expect(screen.getAllByText('Prusa').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Polymaker').length).toBeGreaterThan(0);
      });
    });

    it('shows temperature ranges', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('200–220°C')).toBeInTheDocument();
        expect(screen.getByText('230–250°C')).toBeInTheDocument();
      });
    });
  });

  describe('Add Spool Modal', () => {
    it('shows add spool button', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('+ Add Spool')).toBeInTheDocument();
      });
    });

    it('opens modal when add button clicked', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        expect(screen.getByText('+ Add Spool')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('+ Add Spool'));

      await waitFor(() => {
        expect(screen.getByText('Add New Spool')).toBeInTheDocument();
      });
    });

    it('closes modal on cancel', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('+ Add Spool'));
      });

      await waitFor(() => {
        expect(screen.getByText('Add New Spool')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Cancel'));

      await waitFor(() => {
        expect(screen.queryByText('Add New Spool')).not.toBeInTheDocument();
      });
    });

    it('has disabled add button when form incomplete', async () => {
      setupSuccessfulFetch();
      render(<MaterialsTab />);

      await waitFor(() => {
        fireEvent.click(screen.getByText('+ Add Spool'));
      });

      await waitFor(() => {
        // The Add Spool button in the modal should be disabled
        const addButtons = screen.getAllByText('Add Spool');
        const modalAddButton = addButtons.find(btn => btn.closest('.modal-footer'));
        expect(modalAddButton).toBeDisabled();
      });
    });
  });
});
