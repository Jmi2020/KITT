/**
 * Cameras Tab - Live camera feeds with WebSocket streaming
 * Extracted from VisionService.tsx and CameraDashboard component
 */

import { useCallback, useEffect, useState } from 'react';
import { useCameraStream } from '../../../hooks/useCameraStream';
import type { Camera, CameraFrame } from '../../../types/dashboard';

const CamerasTab = () => {
  const {
    cameras,
    frames,
    subscribedCameras,
    isConnected,
    error,
    connect,
    disconnect,
    subscribe,
    subscribeAll,
    requestCameraList,
  } = useCameraStream();

  const [selectedCamera, setSelectedCamera] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'single'>('grid');

  // Auto-connect on mount
  useEffect(() => {
    connect();
  }, [connect]);

  // Auto-subscribe to all cameras when connected
  useEffect(() => {
    if (isConnected && cameras.length > 0) {
      subscribeAll();
    }
  }, [isConnected, cameras.length, subscribeAll]);

  // Periodic camera list refresh
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      requestCameraList();
    }, 10000);

    return () => clearInterval(interval);
  }, [isConnected, requestCameraList]);

  const handleCameraClick = useCallback(
    (cameraId: string) => {
      setSelectedCamera(cameraId);
      setViewMode('single');
      if (!subscribedCameras.has(cameraId)) {
        subscribe(cameraId);
      }
    },
    [subscribedCameras, subscribe]
  );

  const handleBackToGrid = useCallback(() => {
    setSelectedCamera(null);
    setViewMode('grid');
  }, []);

  const handleDownloadFrame = useCallback(
    (cameraId: string) => {
      const frame = frames[cameraId];
      if (!frame) return;

      const link = document.createElement('a');
      link.href = `data:image/jpeg;base64,${frame.jpeg_base64}`;
      link.download = `${cameraId}-${Date.now()}.jpg`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    },
    [frames]
  );

  const formatTimestamp = (ts: number) => {
    return new Date(ts * 1000).toLocaleTimeString();
  };

  const onlineCameras = cameras.filter((c: Camera) => c.online);

  // Single camera fullscreen view
  if (viewMode === 'single' && selectedCamera) {
    const frame = frames[selectedCamera];
    const camera = cameras.find((c: Camera) => c.camera_id === selectedCamera);

    return (
      <div className="camera-fullscreen">
        <div className="camera-fullscreen-header">
          <div>
            <h2>{camera?.friendly_name || selectedCamera}</h2>
            {frame && (
              <p style={{ margin: '0.25rem 0 0', color: 'var(--text-secondary, #888)', fontSize: '0.9rem' }}>
                Last frame: {formatTimestamp(frame.timestamp)}
              </p>
            )}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => handleDownloadFrame(selectedCamera)}
              disabled={!frame}
              className="btn-secondary"
            >
              📥 Save Snapshot
            </button>
            <button onClick={handleBackToGrid} className="btn-secondary">
              ← Back to Grid
            </button>
          </div>
        </div>
        <div className="camera-fullscreen-content">
          {frame ? (
            <img
              src={`data:image/jpeg;base64,${frame.jpeg_base64}`}
              alt="Camera feed"
            />
          ) : (
            <div style={{ color: 'var(--text-secondary, #888)' }}>Waiting for frames...</div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="cameras-tab">
      {/* Header with connection controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <p style={{ color: 'var(--text-secondary, #888)', margin: 0 }}>
            {isConnected
              ? `${onlineCameras.length} camera${onlineCameras.length !== 1 ? 's' : ''} online`
              : 'Disconnected from camera stream'}
          </p>
        </div>
        <div>
          {!isConnected ? (
            <button onClick={connect} className="btn-primary">
              🔌 Connect
            </button>
          ) : (
            <button onClick={disconnect} className="btn-secondary">
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="error-state" style={{ marginBottom: '1.5rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px' }}>
          {error}
        </div>
      )}

      {/* Camera grid */}
      {cameras.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📹</div>
          <div className="empty-state-title">No Cameras Connected</div>
          <p className="empty-state-text">
            Cameras will appear here when they connect to the stream.
          </p>
          {!isConnected && (
            <button onClick={connect} className="btn-primary" style={{ marginTop: '1rem' }}>
              Connect to Camera Stream
            </button>
          )}
        </div>
      ) : (
        <div className="cameras-grid">
          {cameras.map((camera: Camera) => {
            const frame = frames[camera.camera_id];
            const isSubscribed = subscribedCameras.has(camera.camera_id);

            return (
              <div
                key={camera.camera_id}
                className="camera-card"
                onClick={() => handleCameraClick(camera.camera_id)}
              >
                <div className="camera-preview">
                  {frame ? (
                    <img
                      src={`data:image/jpeg;base64,${frame.jpeg_base64}`}
                      alt={camera.friendly_name}
                    />
                  ) : (
                    <div className="camera-placeholder">
                      {isSubscribed ? 'Waiting for frames...' : 'Click to subscribe'}
                    </div>
                  )}

                  <div className="camera-status">
                    <span className={`status-dot ${camera.online ? 'online' : 'offline'}`} />
                    <span style={{ color: '#fff' }}>{camera.online ? 'Live' : 'Offline'}</span>
                  </div>

                  {isSubscribed && (
                    <div
                      style={{
                        position: 'absolute',
                        top: '0.5rem',
                        right: '0.5rem',
                        padding: '0.25rem 0.5rem',
                        background: 'rgba(99, 102, 241, 0.8)',
                        borderRadius: '9999px',
                        fontSize: '0.75rem',
                        color: '#fff',
                      }}
                    >
                      Subscribed
                    </div>
                  )}
                </div>

                <div className="camera-info">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span className="camera-name">{camera.friendly_name}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownloadFrame(camera.camera_id);
                      }}
                      disabled={!frame}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        cursor: frame ? 'pointer' : 'default',
                        opacity: frame ? 1 : 0.3,
                        padding: '0.25rem',
                      }}
                      title="Save snapshot"
                    >
                      📥
                    </button>
                  </div>
                  {frame && (
                    <div className="camera-timestamp">{formatTimestamp(frame.timestamp)}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Connection status footer */}
      <div className="connection-status">
        <span className={isConnected ? 'connected' : ''}>
          WebSocket {isConnected ? 'Connected' : 'Disconnected'}
        </span>
        <span>|</span>
        <span>{subscribedCameras.size} subscriptions</span>
        <span>|</span>
        <span>{Object.keys(frames).length} active feeds</span>
      </div>
    </div>
  );
};

export default CamerasTab;
