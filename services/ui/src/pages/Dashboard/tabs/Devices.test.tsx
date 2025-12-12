/**
 * Tests for Devices tab component
 * Tests device cards, voice control, and MQTT device display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import DevicesTab from './Devices';

// Mock useKittyContext
const mockContext = {
  devices: {} as Record<string, { deviceId: string; status: string; payload?: Record<string, unknown> }>,
};

vi.mock('../../../hooks/useKittyContext', () => ({
  default: () => ({ context: mockContext }),
}));

// Mock voice module
const mockStart = vi.fn();
vi.mock('../../../modules/voice', () => ({
  createVoiceController: () => ({
    start: mockStart,
    stop: vi.fn(),
  }),
}));

// Mock import.meta.env
vi.stubGlobal('import', {
  meta: {
    env: {
      VITE_VOICE_ENDPOINT: 'ws://localhost:8400',
    },
  },
});

describe('Devices Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockContext.devices = {};
    mockStart.mockReset();
  });

  describe('Voice Control', () => {
    it('renders voice control card', () => {
      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('Voice Control')).toBeInTheDocument();
    });

    it('shows voice button when not in remote mode', () => {
      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('🎤 Start Voice Command')).toBeInTheDocument();
    });

    it('shows disabled voice button in remote mode', () => {
      render(<DevicesTab remoteMode={true} />);

      expect(screen.getByText('🔇 Voice Disabled')).toBeInTheDocument();
    });

    it('disables voice button in remote mode', () => {
      render(<DevicesTab remoteMode={true} />);

      const voiceButton = screen.getByRole('button', { name: /Voice Disabled/i });
      expect(voiceButton).toBeDisabled();
    });

    it('shows remote mode message', () => {
      render(<DevicesTab remoteMode={true} />);

      expect(screen.getByText(/Voice capture is disabled in remote mode/i)).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no devices', () => {
      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('No Devices Connected')).toBeInTheDocument();
      expect(screen.getByText(/Devices will appear here/i)).toBeInTheDocument();
    });
  });

  describe('Device Display', () => {
    it('shows device cards when devices exist', () => {
      mockContext.devices = {
        'printer-1': { deviceId: 'printer-1', status: 'online' },
        'printer-2': { deviceId: 'printer-2', status: 'offline' },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('printer-1')).toBeInTheDocument();
      expect(screen.getByText('printer-2')).toBeInTheDocument();
    });

    it('shows online status badge for online devices', () => {
      mockContext.devices = {
        'printer-1': { deviceId: 'printer-1', status: 'online' },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('online')).toBeInTheDocument();
    });

    it('shows offline status badge for offline devices', () => {
      mockContext.devices = {
        'printer-1': { deviceId: 'printer-1', status: 'offline' },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('offline')).toBeInTheDocument();
    });

    it('shows device count in header', () => {
      mockContext.devices = {
        'printer-1': { deviceId: 'printer-1', status: 'online' },
        'printer-2': { deviceId: 'printer-2', status: 'online' },
        'printer-3': { deviceId: 'printer-3', status: 'offline' },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('2 online')).toBeInTheDocument();
      expect(screen.getByText('3 total')).toBeInTheDocument();
    });

    it('shows device payload in details', () => {
      mockContext.devices = {
        'printer-1': {
          deviceId: 'printer-1',
          status: 'online',
          payload: { temperature: 200, progress: 50 },
        },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('View details')).toBeInTheDocument();
    });

    it('shows no additional data message when no payload', () => {
      mockContext.devices = {
        'printer-1': { deviceId: 'printer-1', status: 'online', payload: {} },
      };

      render(<DevicesTab remoteMode={false} />);

      expect(screen.getByText('No additional data')).toBeInTheDocument();
    });
  });
});
