import { useCallback, useEffect, useRef, useState } from 'react';

interface CameraInfo {
  camera_id: string;
  friendly_name: string;
  online: boolean;
  resolution?: [number, number];
  fps?: number;
}

interface CameraFrame {
  camera_id: string;
  jpeg_base64: string;
  timestamp: number;
}

interface UseCameraStreamReturn {
  cameras: CameraInfo[];
  frames: Record<string, CameraFrame>;
  subscribedCameras: Set<string>;
  isConnected: boolean;
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  subscribe: (cameraId: string) => void;
  unsubscribe: (cameraId: string) => void;
  subscribeAll: () => void;
  unsubscribeAll: () => void;
  requestCameraList: () => void;
}

/**
 * Hook for managing WebSocket camera streaming connection.
 * Handles camera discovery and frame subscription.
 */
export function useCameraStream(endpoint?: string): UseCameraStreamReturn {
  const wsEndpoint = endpoint || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/cameras/stream`;

  const [cameras, setCameras] = useState<CameraInfo[]>([]);
  const [frames, setFrames] = useState<Record<string, CameraFrame>>({});
  const [subscribedCameras, setSubscribedCameras] = useState<Set<string>>(new Set());
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'status':
          setIsConnected(true);
          if (msg.cameras) {
            setCameras(msg.cameras);
          }
          break;

        case 'cameras_list':
          setCameras(msg.cameras || []);
          break;

        case 'camera_joined':
          setCameras((prev) => {
            const exists = prev.some((c) => c.camera_id === msg.camera_id);
            if (exists) return prev;
            return [...prev, {
              camera_id: msg.camera_id,
              friendly_name: msg.friendly_name,
              online: true,
            }];
          });
          break;

        case 'camera_left':
          setCameras((prev) => prev.filter((c) => c.camera_id !== msg.camera_id));
          setFrames((prev) => {
            const next = { ...prev };
            delete next[msg.camera_id];
            return next;
          });
          setSubscribedCameras((prev) => {
            const next = new Set(prev);
            next.delete(msg.camera_id);
            return next;
          });
          break;

        case 'frame':
          setFrames((prev) => ({
            ...prev,
            [msg.camera_id]: {
              camera_id: msg.camera_id,
              jpeg_base64: msg.jpeg_base64,
              timestamp: msg.timestamp,
            },
          }));
          break;

        case 'subscribed':
          setSubscribedCameras((prev) => new Set(prev).add(msg.camera_id));
          break;

        case 'unsubscribed':
          setSubscribedCameras((prev) => {
            const next = new Set(prev);
            next.delete(msg.camera_id);
            return next;
          });
          break;

        case 'error':
          setError(msg.message);
          break;
      }
    } catch (err) {
      console.error('Error parsing camera WebSocket message:', err);
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setError(null);

    const ws = new WebSocket(wsEndpoint);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = handleMessage;

    ws.onerror = () => {
      setError('WebSocket connection error');
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
    };
  }, [wsEndpoint, handleMessage]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
    setSubscribedCameras(new Set());
    setFrames({});
  }, []);

  const subscribe = useCallback((cameraId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        camera_id: cameraId,
      }));
    }
  }, []);

  const unsubscribe = useCallback((cameraId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'unsubscribe',
        camera_id: cameraId,
      }));
    }
  }, []);

  const subscribeAll = useCallback(() => {
    cameras.forEach((camera) => {
      if (!subscribedCameras.has(camera.camera_id)) {
        subscribe(camera.camera_id);
      }
    });
  }, [cameras, subscribedCameras, subscribe]);

  const unsubscribeAll = useCallback(() => {
    subscribedCameras.forEach((cameraId) => {
      unsubscribe(cameraId);
    });
  }, [subscribedCameras, unsubscribe]);

  const requestCameraList = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'request_cameras' }));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    cameras,
    frames,
    subscribedCameras,
    isConnected,
    error,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    subscribeAll,
    unsubscribeAll,
    requestCameraList,
  };
}
