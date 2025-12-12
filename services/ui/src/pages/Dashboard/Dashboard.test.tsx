/**
 * Tests for Dashboard page
 * Tests tab switching and integration with Devices, Cameras, and Materials tabs
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './index';

// Mock the tabs
vi.mock('./tabs/Devices', () => ({
  default: ({ remoteMode }: { remoteMode: boolean }) => (
    <div data-testid="devices-tab">
      Devices Tab Content
      {remoteMode && <span data-testid="remote-mode">Remote Mode</span>}
    </div>
  ),
}));

vi.mock('./tabs/Cameras', () => ({
  default: () => <div data-testid="cameras-tab">Cameras Tab Content</div>,
}));

vi.mock('./tabs/Materials', () => ({
  default: () => <div data-testid="materials-tab">Materials Tab Content</div>,
}));

describe('Dashboard Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderWithRouter = (initialEntries = ['/dashboard']) => {
    return render(
      <MemoryRouter initialEntries={initialEntries}>
        <Dashboard />
      </MemoryRouter>
    );
  };

  describe('Header', () => {
    it('renders the header', () => {
      renderWithRouter();

      expect(screen.getByText('System Dashboard')).toBeInTheDocument();
      expect(screen.getByText(/Monitor devices, cameras, and material inventory/)).toBeInTheDocument();
    });

    it('shows remote mode badge when in remote mode', () => {
      render(
        <MemoryRouter>
          <Dashboard remoteMode={{ isRemote: true }} />
        </MemoryRouter>
      );

      expect(screen.getByText('Remote Read-Only Mode')).toBeInTheDocument();
    });
  });

  describe('Tab Navigation', () => {
    it('renders all three tabs', () => {
      renderWithRouter();

      expect(screen.getByText('Devices')).toBeInTheDocument();
      expect(screen.getByText('Cameras')).toBeInTheDocument();
      expect(screen.getByText('Materials')).toBeInTheDocument();
    });

    it('shows Devices tab by default', () => {
      renderWithRouter();

      const devicesTab = screen.getByText('Devices').closest('button');
      expect(devicesTab).toHaveClass('active');
      expect(screen.getByTestId('devices-tab')).toBeInTheDocument();
    });

    it('switches to Cameras tab when clicked', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Cameras'));

      await waitFor(() => {
        const camerasTab = screen.getByText('Cameras').closest('button');
        expect(camerasTab).toHaveClass('active');
        expect(screen.getByTestId('cameras-tab')).toBeInTheDocument();
      });
    });

    it('switches to Materials tab when clicked', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Materials'));

      await waitFor(() => {
        const materialsTab = screen.getByText('Materials').closest('button');
        expect(materialsTab).toHaveClass('active');
        expect(screen.getByTestId('materials-tab')).toBeInTheDocument();
      });
    });

    it('switches back to Devices tab when clicked', async () => {
      renderWithRouter();

      // First switch to Cameras
      fireEvent.click(screen.getByText('Cameras'));
      await waitFor(() => {
        expect(screen.getByTestId('cameras-tab')).toBeInTheDocument();
      });

      // Then switch back to Devices
      fireEvent.click(screen.getByText('Devices'));
      await waitFor(() => {
        const devicesTab = screen.getByText('Devices').closest('button');
        expect(devicesTab).toHaveClass('active');
        expect(screen.getByTestId('devices-tab')).toBeInTheDocument();
      });
    });
  });

  describe('Devices Tab', () => {
    it('renders devices content by default', () => {
      renderWithRouter();

      expect(screen.getByTestId('devices-tab')).toBeInTheDocument();
    });

    it('passes remoteMode prop to Devices tab', () => {
      render(
        <MemoryRouter>
          <Dashboard remoteMode={{ isRemote: true }} />
        </MemoryRouter>
      );

      expect(screen.getByTestId('remote-mode')).toBeInTheDocument();
    });
  });

  describe('Cameras Tab', () => {
    it('renders cameras content when Cameras tab is active', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Cameras'));

      await waitFor(() => {
        expect(screen.getByTestId('cameras-tab')).toBeInTheDocument();
      });
    });
  });

  describe('Materials Tab', () => {
    it('renders materials content when Materials tab is active', async () => {
      renderWithRouter();

      fireEvent.click(screen.getByText('Materials'));

      await waitFor(() => {
        expect(screen.getByTestId('materials-tab')).toBeInTheDocument();
      });
    });
  });

  describe('URL Tab Param', () => {
    it('opens correct tab from URL param - cameras', () => {
      renderWithRouter(['/dashboard?tab=cameras']);

      const camerasTab = screen.getByText('Cameras').closest('button');
      expect(camerasTab).toHaveClass('active');
    });

    it('opens correct tab from URL param - materials', () => {
      renderWithRouter(['/dashboard?tab=materials']);

      const materialsTab = screen.getByText('Materials').closest('button');
      expect(materialsTab).toHaveClass('active');
    });

    it('opens devices tab from URL param', () => {
      renderWithRouter(['/dashboard?tab=devices']);

      const devicesTab = screen.getByText('Devices').closest('button');
      expect(devicesTab).toHaveClass('active');
    });

    it('defaults to devices for invalid tab param', () => {
      renderWithRouter(['/dashboard?tab=invalid']);

      const devicesTab = screen.getByText('Devices').closest('button');
      expect(devicesTab).toHaveClass('active');
    });
  });
});
