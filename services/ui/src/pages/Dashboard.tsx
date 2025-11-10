import useKittyContext from '../hooks/useKittyContext';
import { createVoiceController, VoiceResult } from '../modules/voice';

interface DashboardProps {
  remoteMode: boolean;
}

const Dashboard = ({ remoteMode }: DashboardProps) => {
  const { context } = useKittyContext();
  const handleTranscript = (result: VoiceResult) => {
    console.info('Voice transcript received', result);
  };

  const voice = createVoiceController(handleTranscript, import.meta.env.VITE_VOICE_ENDPOINT);

  const startVoice = async () => {
    if (remoteMode) {
      alert('Voice capture disabled in remote read-only mode');
      return;
    }
    await voice.start();
  };

  const devices = Object.values(context.devices);
  const onlineDevices = devices.filter((d) => d.status === 'online');
  const offlineDevices = devices.filter((d) => d.status !== 'online');

  return (
    <section className="dashboard">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2>System Dashboard</h2>
          <p className="text-secondary mt-1">Real-time device monitoring and control</p>
        </div>
        {remoteMode && <span className="badge badge-warning">Remote Read-Only Mode</span>}
      </div>

      <div className="card mb-4">
        <div className="card-header">
          <h3 className="card-title">Voice Control</h3>
          <div className="flex gap-2">
            <span className="badge badge-success">{onlineDevices.length} online</span>
            <span className="badge badge-neutral">{devices.length} total</span>
          </div>
        </div>
        <div className="card-body">
          <p className="mb-3 text-secondary">
            {remoteMode
              ? 'Voice capture is disabled in remote mode for security reasons.'
              : 'Initiate voice commands to control devices and workflows.'}
          </p>
          <button onClick={startVoice} disabled={remoteMode} className="btn-primary">
            {remoteMode ? '🔇 Voice Disabled' : '🎤 Start Voice Command'}
          </button>
        </div>
      </div>

      {devices.length === 0 ? (
        <div className="card text-center">
          <div className="card-body">
            <h3 className="mb-2">No Devices Connected</h3>
            <p className="text-secondary">
              Devices will appear here once they publish state to MQTT topics.
            </p>
            <p className="text-muted mt-2">
              Expected topic format: <code>kitty/devices/&lt;device-id&gt;/state</code>
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-3">
          {devices.map((device) => (
            <article key={device.deviceId} className="card">
              <div className="card-header">
                <h3 className="card-title" style={{ fontSize: '1rem' }}>
                  {device.deviceId}
                </h3>
                <span className={`badge ${device.status === 'online' ? 'badge-success' : 'badge-neutral'}`}>
                  {device.status}
                </span>
              </div>
              <div className="card-body">
                {device.payload && Object.keys(device.payload).length > 0 ? (
                  <details>
                    <summary style={{ cursor: 'pointer', color: 'var(--accent-secondary)' }}>
                      View details
                    </summary>
                    <pre style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                      {JSON.stringify(device.payload, null, 2)}
                    </pre>
                  </details>
                ) : (
                  <p className="text-muted">No additional data</p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default Dashboard;
