import { useEffect, useState } from 'react';
import './VisionService.css';

interface CameraStatus {
  printer_id: string;
  camera_type: 'bamboo_mqtt' | 'raspberry_pi_http';
  camera_url: string | null;
  status: 'online' | 'offline' | 'unknown';
  last_snapshot_url: string | null;
  last_snapshot_time: string | null;
}

interface SnapshotGallery {
  job_id: string;
  printer_id: string;
  snapshots: {
    milestone: string;
    url: string;
    timestamp: string;
  }[];
}

const VisionService = () => {
  const [cameras, setCameras] = useState<CameraStatus[]>([]);
  const [snapshots, setSnapshots] = useState<SnapshotGallery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [printerFilter, setPrinterFilter] = useState<string>('');

  // Selected camera for live view
  const [selectedCamera, setSelectedCamera] = useState<string | null>(null);
  const [captureInProgress, setCaptureInProgress] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadCameraStatus();
    loadRecentSnapshots();

    // Auto-refresh camera status every 30 seconds
    const interval = setInterval(() => {
      loadCameraStatus();
    }, 30000);

    return () => clearInterval(interval);
  }, []);

  const loadCameraStatus = async () => {
    try {
      const response = await fetch('http://localhost:8080/api/fabrication/cameras/status');
      if (!response.ok) {
        throw new Error(`Failed to load camera status: ${response.status}`);
      }
      const data = await response.json();
      setCameras(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load camera status:', err);
      // Set mock data for development
      setCameras([
        {
          printer_id: 'bamboo_h2d',
          camera_type: 'bamboo_mqtt',
          camera_url: null,
          status: 'unknown',
          last_snapshot_url: null,
          last_snapshot_time: null,
        },
        {
          printer_id: 'snapmaker_artisan',
          camera_type: 'raspberry_pi_http',
          camera_url: 'http://snapmaker-pi.local:8080/snapshot.jpg',
          status: 'unknown',
          last_snapshot_url: null,
          last_snapshot_time: null,
        },
        {
          printer_id: 'elegoo_giga',
          camera_type: 'raspberry_pi_http',
          camera_url: 'http://elegoo-pi.local:8080/snapshot.jpg',
          status: 'unknown',
          last_snapshot_time: null,
          last_snapshot_url: null,
        },
      ]);
      setError('Using mock camera data (API endpoint not available)');
    } finally {
      setLoading(false);
    }
  };

  const loadRecentSnapshots = async () => {
    try {
      const response = await fetch('http://localhost:8080/api/fabrication/cameras/snapshots/recent?limit=10');
      if (!response.ok) {
        throw new Error(`Failed to load snapshots: ${response.status}`);
      }
      const data = await response.json();
      setSnapshots(data);
    } catch (err) {
      console.error('Failed to load recent snapshots:', err);
      setSnapshots([]);
    }
  };

  const captureSnapshot = async (printerId: string) => {
    setCaptureInProgress(prev => new Set(prev).add(printerId));

    try {
      const response = await fetch(`http://localhost:8080/api/fabrication/cameras/${printerId}/snapshot`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          job_id: `manual_${Date.now()}`,
          milestone: 'manual',
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to capture snapshot: ${response.status}`);
      }

      const result = await response.json();

      if (result.success) {
        alert(`Snapshot captured successfully!\nURL: ${result.url}`);
        loadCameraStatus();
        loadRecentSnapshots();
      } else {
        alert(`Snapshot capture failed: ${result.error}`);
      }
    } catch (err) {
      console.error('Failed to capture snapshot:', err);
      alert('Failed to capture snapshot. Check console for details.');
    } finally {
      setCaptureInProgress(prev => {
        const next = new Set(prev);
        next.delete(printerId);
        return next;
      });
    }
  };

  const testCameraConnection = async (printerId: string) => {
    try {
      const response = await fetch(`http://localhost:8080/api/fabrication/cameras/${printerId}/test`);
      if (!response.ok) {
        throw new Error(`Test failed: ${response.status}`);
      }
      const result = await response.json();

      if (result.success) {
        alert(`Camera test successful!\nLatency: ${result.latency_ms}ms`);
      } else {
        alert(`Camera test failed: ${result.error}`);
      }
    } catch (err) {
      console.error('Camera test failed:', err);
      alert('Camera test failed. Check console for details.');
    }
  };

  const getCameraStatusBadge = (status: string) => {
    switch (status) {
      case 'online':
        return <span className="status-badge online">🟢 Online</span>;
      case 'offline':
        return <span className="status-badge offline">🔴 Offline</span>;
      default:
        return <span className="status-badge unknown">⚪ Unknown</span>;
    }
  };

  const getCameraTypeBadge = (type: string) => {
    switch (type) {
      case 'bamboo_mqtt':
        return <span className="type-badge bamboo">📡 Bamboo MQTT</span>;
      case 'raspberry_pi_http':
        return <span className="type-badge pi">🥧 Raspberry Pi</span>;
      default:
        return <span className="type-badge unknown">❓ Unknown</span>;
    }
  };

  const getPrinterDisplayName = (printerId: string) => {
    const names: Record<string, string> = {
      bamboo_h2d: 'Bamboo Labs H2D',
      snapmaker_artisan: 'Snapmaker Artisan',
      elegoo_giga: 'Elegoo Orangestorm Giga',
    };
    return names[printerId] || printerId;
  };

  const filteredCameras = cameras.filter(camera =>
    !printerFilter || camera.printer_id === printerFilter
  );

  if (loading) {
    return (
      <div className="vision-service">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading camera feeds...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="vision-service">
      <div className="vision-header">
        <h1>📹 Vision Service Dashboard</h1>
        <p className="subtitle">Monitor camera feeds and capture snapshots from all printers</p>
      </div>

      {error && (
        <div className="error-banner">
          ⚠️ {error}
        </div>
      )}

      <div className="filter-section">
        <div className="filter-group">
          <label htmlFor="printer-filter">Filter by Printer:</label>
          <select
            id="printer-filter"
            value={printerFilter}
            onChange={e => setPrinterFilter(e.target.value)}
          >
            <option value="">All Printers</option>
            {cameras.map(camera => (
              <option key={camera.printer_id} value={camera.printer_id}>
                {getPrinterDisplayName(camera.printer_id)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="camera-grid">
        {filteredCameras.map(camera => (
          <div key={camera.printer_id} className="camera-card">
            <div className="camera-header">
              <h3>{getPrinterDisplayName(camera.printer_id)}</h3>
              <div className="camera-badges">
                {getCameraTypeBadge(camera.camera_type)}
                {getCameraStatusBadge(camera.status)}
              </div>
            </div>

            <div className="camera-preview">
              {camera.last_snapshot_url ? (
                <img
                  src={camera.last_snapshot_url}
                  alt={`${camera.printer_id} snapshot`}
                  className="snapshot-preview"
                  onError={e => {
                    (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="300"%3E%3Crect fill="%23333" width="400" height="300"/%3E%3Ctext fill="%23999" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3ENo Preview%3C/text%3E%3C/svg%3E';
                  }}
                />
              ) : (
                <div className="no-preview">
                  <div className="no-preview-icon">📷</div>
                  <p>No recent snapshot</p>
                </div>
              )}
            </div>

            <div className="camera-info">
              {camera.camera_url && (
                <div className="info-row">
                  <span className="label">Endpoint:</span>
                  <span className="value">{camera.camera_url}</span>
                </div>
              )}
              {camera.last_snapshot_time && (
                <div className="info-row">
                  <span className="label">Last Snapshot:</span>
                  <span className="value">
                    {new Date(camera.last_snapshot_time).toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            <div className="camera-actions">
              <button
                onClick={() => captureSnapshot(camera.printer_id)}
                disabled={captureInProgress.has(camera.printer_id)}
                className="action-button primary"
              >
                {captureInProgress.has(camera.printer_id) ? '⏳ Capturing...' : '📸 Capture Snapshot'}
              </button>
              <button
                onClick={() => testCameraConnection(camera.printer_id)}
                className="action-button secondary"
              >
                🔍 Test Connection
              </button>
              <button
                onClick={() => setSelectedCamera(
                  selectedCamera === camera.printer_id ? null : camera.printer_id
                )}
                className="action-button secondary"
              >
                {selectedCamera === camera.printer_id ? '👁️ Hide Live View' : '👁️ Live View'}
              </button>
            </div>

            {selectedCamera === camera.printer_id && camera.camera_url && (
              <div className="live-view-container">
                <h4>Live Feed</h4>
                <iframe
                  src={camera.camera_url.replace('/snapshot.jpg', '/')}
                  title={`${camera.printer_id} live feed`}
                  className="live-feed-iframe"
                />
                <p className="live-view-note">
                  If live feed doesn't work, try accessing: <a href={camera.camera_url} target="_blank" rel="noopener noreferrer">{camera.camera_url}</a>
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      {snapshots.length > 0 && (
        <div className="recent-snapshots-section">
          <h2>Recent Snapshots</h2>
          <div className="snapshots-list">
            {snapshots.map((gallery, idx) => (
              <div key={idx} className="snapshot-gallery">
                <h3>
                  Job: {gallery.job_id} ({getPrinterDisplayName(gallery.printer_id)})
                </h3>
                <div className="snapshot-grid">
                  {gallery.snapshots.map((snapshot, sidx) => (
                    <div key={sidx} className="snapshot-item">
                      <img
                        src={snapshot.url}
                        alt={`${snapshot.milestone} snapshot`}
                        className="snapshot-thumbnail"
                        onError={e => {
                          (e.target as HTMLImageElement).src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="200" height="150"%3E%3Crect fill="%23444" width="200" height="150"/%3E%3Ctext fill="%23999" x="50%25" y="50%25" text-anchor="middle" dy=".3em"%3EError%3C/text%3E%3C/svg%3E';
                        }}
                      />
                      <div className="snapshot-info">
                        <span className="milestone-badge">{snapshot.milestone}</span>
                        <span className="timestamp">
                          {new Date(snapshot.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {filteredCameras.length === 0 && (
        <div className="no-cameras">
          <p>No cameras found matching the current filter.</p>
        </div>
      )}
    </div>
  );
};

export default VisionService;
