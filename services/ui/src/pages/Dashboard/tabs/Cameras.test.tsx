/**
 * Tests for Cameras tab component
 * Tests camera grid, WebSocket connection, and snapshot functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CamerasTab from './Cameras';

// Mock useCameraStream hook
const mockConnect = vi.fn();
const mockDisconnect = vi.fn();
const mockSubscribe = vi.fn();
const mockSubscribeAll = vi.fn();
const mockRequestCameraList = vi.fn();

const mockCameraStream = {
  cameras: [] as Array<{ camera_id: string; friendly_name: string; online: boolean }>,
  frames: {} as Record<string, { jpeg_base64: string; timestamp: number }>,
  subscribedCameras: new Set<string>(),
  isConnected: false,
  error: null as string | null,
  connect: mockConnect,
  disconnect: mockDisconnect,
  subscribe: mockSubscribe,
  subscribeAll: mockSubscribeAll,
  requestCameraList: mockRequestCameraList,
};

vi.mock('../../../hooks/useCameraStream', () => ({
  useCameraStream: () => mockCameraStream,
}));

describe('Cameras Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCameraStream.cameras = [];
    mockCameraStream.frames = {};
    mockCameraStream.subscribedCameras = new Set();
    mockCameraStream.isConnected = false;
    mockCameraStream.error = null;
  });

  describe('Connection Controls', () => {
    it('shows connect button when disconnected', () => {
      mockCameraStream.isConnected = false;
      render(<CamerasTab />);

      expect(screen.getByText('🔌 Connect')).toBeInTheDocument();
    });

    it('shows disconnect button when connected', () => {
      mockCameraStream.isConnected = true;
      render(<CamerasTab />);

      expect(screen.getByText('Disconnect')).toBeInTheDocument();
    });

    it('calls connect on mount', () => {
      render(<CamerasTab />);

      expect(mockConnect).toHaveBeenCalled();
    });

    it('shows disconnected status message', () => {
      mockCameraStream.isConnected = false;
      render(<CamerasTab />);

      expect(screen.getByText('Disconnected from camera stream')).toBeInTheDocument();
    });

    it('shows camera count when connected', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: true },
        { camera_id: 'cam2', friendly_name: 'Camera 2', online: true },
      ];
      render(<CamerasTab />);

      expect(screen.getByText('2 cameras online')).toBeInTheDocument();
    });
  });

  describe('Empty State', () => {
    it('shows empty state when no cameras', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [];
      render(<CamerasTab />);

      expect(screen.getByText('No Cameras Connected')).toBeInTheDocument();
      expect(screen.getByText(/Cameras will appear here/i)).toBeInTheDocument();
    });

    it('shows connect button in empty state when disconnected', () => {
      mockCameraStream.isConnected = false;
      render(<CamerasTab />);

      const connectButtons = screen.getAllByText(/Connect/i);
      expect(connectButtons.length).toBeGreaterThan(0);
    });
  });

  describe('Error Display', () => {
    it('shows error message when error occurs', () => {
      mockCameraStream.error = 'Connection failed';
      render(<CamerasTab />);

      expect(screen.getByText('Connection failed')).toBeInTheDocument();
    });
  });

  describe('Camera Grid', () => {
    it('displays camera cards', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Front Camera', online: true },
        { camera_id: 'cam2', friendly_name: 'Side Camera', online: false },
      ];
      render(<CamerasTab />);

      expect(screen.getByText('Front Camera')).toBeInTheDocument();
      expect(screen.getByText('Side Camera')).toBeInTheDocument();
    });

    it('shows live status for online cameras', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: true },
      ];
      render(<CamerasTab />);

      expect(screen.getByText('Live')).toBeInTheDocument();
    });

    it('shows offline status for offline cameras', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: false },
      ];
      render(<CamerasTab />);

      expect(screen.getByText('Offline')).toBeInTheDocument();
    });

    it('shows subscribed badge for subscribed cameras', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: true },
      ];
      mockCameraStream.subscribedCameras = new Set(['cam1']);
      render(<CamerasTab />);

      expect(screen.getByText('Subscribed')).toBeInTheDocument();
    });

    it('shows waiting message when subscribed but no frames', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: true },
      ];
      mockCameraStream.subscribedCameras = new Set(['cam1']);
      mockCameraStream.frames = {};
      render(<CamerasTab />);

      expect(screen.getByText('Waiting for frames...')).toBeInTheDocument();
    });

    it('shows click to subscribe message when not subscribed', () => {
      mockCameraStream.isConnected = true;
      mockCameraStream.cameras = [
        { camera_id: 'cam1', friendly_name: 'Camera 1', online: true },
      ];
      mockCameraStream.subscribedCameras = new Set();
      render(<CamerasTab />);

      expect(screen.getByText('Click to subscribe')).toBeInTheDocument();
    });
  });

  describe('Connection Status Footer', () => {
    it('shows connected status', () => {
      mockCameraStream.isConnected = true;
      render(<CamerasTab />);

      expect(screen.getByText('WebSocket Connected')).toBeInTheDocument();
    });

    it('shows disconnected status', () => {
      mockCameraStream.isConnected = false;
      render(<CamerasTab />);

      expect(screen.getByText('WebSocket Disconnected')).toBeInTheDocument();
    });

    it('shows subscription count', () => {
      mockCameraStream.subscribedCameras = new Set(['cam1', 'cam2']);
      render(<CamerasTab />);

      expect(screen.getByText('2 subscriptions')).toBeInTheDocument();
    });

    it('shows active feeds count', () => {
      mockCameraStream.frames = {
        cam1: { jpeg_base64: 'abc', timestamp: 123 },
        cam2: { jpeg_base64: 'def', timestamp: 456 },
      };
      render(<CamerasTab />);

      expect(screen.getByText('2 active feeds')).toBeInTheDocument();
    });
  });
});
