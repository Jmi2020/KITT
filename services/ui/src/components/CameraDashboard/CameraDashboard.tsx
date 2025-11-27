import { useCallback, useEffect, useState } from 'react';
import { useCameraStream } from '../../hooks/useCameraStream';

interface CameraDashboardProps {
  autoConnect?: boolean;
  autoSubscribe?: boolean;
}

/**
 * Camera dashboard component for live camera feeds.
 * Displays connected cameras in a grid with real-time frame updates.
 */
export function CameraDashboard({
  autoConnect = true,
  autoSubscribe = true,
}: CameraDashboardProps) {
  const {
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
    requestCameraList,
  } = useCameraStream();

  const [selectedCamera, setSelectedCamera] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'single'>('grid');

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
  }, [autoConnect, connect]);

  // Auto-subscribe to all cameras when connected
  useEffect(() => {
    if (isConnected && autoSubscribe && cameras.length > 0) {
      subscribeAll();
    }
  }, [isConnected, autoSubscribe, cameras.length, subscribeAll]);

  // Periodic camera list refresh
  useEffect(() => {
    if (!isConnected) return;

    const interval = setInterval(() => {
      requestCameraList();
    }, 10000);

    return () => clearInterval(interval);
  }, [isConnected, requestCameraList]);

  const handleCameraClick = useCallback((cameraId: string) => {
    setSelectedCamera(cameraId);
    setViewMode('single');
    if (!subscribedCameras.has(cameraId)) {
      subscribe(cameraId);
    }
  }, [subscribedCameras, subscribe]);

  const handleBackToGrid = useCallback(() => {
    setSelectedCamera(null);
    setViewMode('grid');
  }, []);

  const handleDownloadFrame = useCallback((cameraId: string) => {
    const frame = frames[cameraId];
    if (!frame) return;

    const link = document.createElement('a');
    link.href = `data:image/jpeg;base64,${frame.jpeg_base64}`;
    link.download = `${cameraId}-${Date.now()}.jpg`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }, [frames]);

  const formatTimestamp = (ts: number) => {
    return new Date(ts * 1000).toLocaleTimeString();
  };

  const onlineCameras = cameras.filter((c) => c.online);
  const offlineCameras = cameras.filter((c) => !c.online);

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Camera Dashboard</h1>
          <p className="text-sm text-gray-400">
            {isConnected
              ? `${onlineCameras.length} cameras online`
              : 'Disconnected'}
          </p>
        </div>
        <div className="flex gap-2">
          {!isConnected ? (
            <button
              onClick={connect}
              className="px-4 py-2 bg-green-500/20 text-green-400 border border-green-500/50 rounded-lg hover:bg-green-500/30"
            >
              Connect
            </button>
          ) : (
            <button
              onClick={disconnect}
              className="px-4 py-2 bg-red-500/20 text-red-400 border border-red-500/50 rounded-lg hover:bg-red-500/30"
            >
              Disconnect
            </button>
          )}
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="p-4 bg-red-900/20 border border-red-500/30 rounded-lg text-red-400">
          {error}
        </div>
      )}

      {/* Single camera view */}
      {viewMode === 'single' && selectedCamera && (
        <div className="fixed inset-0 z-50 bg-black/90 flex flex-col">
          <div className="flex items-center justify-between p-4 bg-gray-900/50">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {cameras.find((c) => c.camera_id === selectedCamera)?.friendly_name || selectedCamera}
              </h2>
              {frames[selectedCamera] && (
                <p className="text-sm text-gray-400">
                  Last frame: {formatTimestamp(frames[selectedCamera].timestamp)}
                </p>
              )}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => handleDownloadFrame(selectedCamera)}
                disabled={!frames[selectedCamera]}
                className="px-4 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 rounded-lg hover:bg-cyan-500/30 disabled:opacity-50"
              >
                Save Snapshot
              </button>
              <button
                onClick={handleBackToGrid}
                className="px-4 py-2 bg-gray-500/20 text-gray-400 border border-gray-500/50 rounded-lg hover:bg-gray-500/30"
              >
                Back to Grid
              </button>
            </div>
          </div>
          <div className="flex-1 flex items-center justify-center p-4">
            {frames[selectedCamera] ? (
              <img
                src={`data:image/jpeg;base64,${frames[selectedCamera].jpeg_base64}`}
                alt="Camera feed"
                className="max-w-full max-h-full object-contain rounded-lg"
              />
            ) : (
              <div className="text-gray-500">Waiting for frames...</div>
            )}
          </div>
        </div>
      )}

      {/* Camera grid */}
      {viewMode === 'grid' && (
        <>
          {cameras.length === 0 ? (
            <div className="p-8 text-center bg-gray-800/50 rounded-lg border border-gray-700">
              <div className="text-4xl mb-4">📹</div>
              <p className="text-gray-400 mb-2">No cameras connected</p>
              <p className="text-sm text-gray-500">
                Cameras will appear here when they connect to the stream
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {cameras.map((camera) => {
                const frame = frames[camera.camera_id];
                const isSubscribed = subscribedCameras.has(camera.camera_id);

                return (
                  <div
                    key={camera.camera_id}
                    className="bg-gray-800/50 rounded-lg border border-gray-700 overflow-hidden cursor-pointer hover:border-cyan-500/50 transition-colors"
                    onClick={() => handleCameraClick(camera.camera_id)}
                  >
                    {/* Camera preview */}
                    <div className="relative aspect-video bg-black">
                      {frame ? (
                        <img
                          src={`data:image/jpeg;base64,${frame.jpeg_base64}`}
                          alt={camera.friendly_name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-gray-500">
                          {isSubscribed ? 'Waiting for frames...' : 'Click to subscribe'}
                        </div>
                      )}

                      {/* Status indicator */}
                      <div className="absolute top-2 left-2 flex items-center gap-2 px-2 py-1 bg-black/70 rounded-full text-xs">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            camera.online ? 'bg-green-400' : 'bg-red-400'
                          }`}
                        />
                        <span className="text-white">
                          {camera.online ? 'Live' : 'Offline'}
                        </span>
                      </div>

                      {/* Subscription badge */}
                      {isSubscribed && (
                        <div className="absolute top-2 right-2 px-2 py-1 bg-cyan-500/80 rounded-full text-xs text-white">
                          Subscribed
                        </div>
                      )}
                    </div>

                    {/* Camera info */}
                    <div className="p-3">
                      <div className="flex items-center justify-between">
                        <h3 className="font-medium text-white truncate">
                          {camera.friendly_name}
                        </h3>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDownloadFrame(camera.camera_id);
                          }}
                          disabled={!frame}
                          className="p-1 text-gray-400 hover:text-white disabled:opacity-30"
                          title="Save snapshot"
                        >
                          📥
                        </button>
                      </div>
                      {frame && (
                        <p className="text-xs text-gray-500 mt-1">
                          {formatTimestamp(frame.timestamp)}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Connection status */}
      <div className="flex items-center justify-center gap-4 text-xs text-gray-500 pt-4">
        <span className={isConnected ? 'text-green-400' : 'text-gray-600'}>
          WebSocket {isConnected ? 'Connected' : 'Disconnected'}
        </span>
        <span>|</span>
        <span>{subscribedCameras.size} subscriptions</span>
        <span>|</span>
        <span>{Object.keys(frames).length} active feeds</span>
      </div>
    </div>
  );
}
