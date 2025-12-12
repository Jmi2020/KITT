/**
 * Devices Tab - MQTT device monitoring and voice control
 * Extracted from original Dashboard.tsx
 */

import useKittyContext from '../../../hooks/useKittyContext';
import { createVoiceController, VoiceResult } from '../../../modules/voice';

interface DevicesTabProps {
  remoteMode: boolean;
}

const DevicesTab = ({ remoteMode }: DevicesTabProps) => {
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

  return (
    <div className="devices-tab">
      {/* Voice Control Card */}
      <div className="voice-control-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <h3>Voice Control</h3>
            <p>
              {remoteMode
                ? 'Voice capture is disabled in remote mode for security reasons.'
                : 'Initiate voice commands to control devices and workflows.'}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <span className="badge badge-success">{onlineDevices.length} online</span>
            <span className="badge badge-neutral">{devices.length} total</span>
          </div>
        </div>
        <button onClick={startVoice} disabled={remoteMode} className="btn-primary">
          {remoteMode ? '🔇 Voice Disabled' : '🎤 Start Voice Command'}
        </button>
      </div>

      {/* Device Cards */}
      {devices.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">📡</div>
          <div className="empty-state-title">No Devices Connected</div>
          <p className="empty-state-text">
            Devices will appear here once they publish state to MQTT topics.
          </p>
          <p className="empty-state-text" style={{ marginTop: '0.5rem', opacity: 0.7 }}>
            Expected topic format: <code>kitty/devices/&lt;device-id&gt;/state</code>
          </p>
        </div>
      ) : (
        <div className="devices-grid">
          {devices.map((device) => (
            <article key={device.deviceId} className="device-card">
              <div className="device-card-header">
                <h4 className="device-card-title">{device.deviceId}</h4>
                <span
                  className={`badge ${device.status === 'online' ? 'badge-success' : 'badge-neutral'}`}
                >
                  {device.status}
                </span>
              </div>
              <div className="device-card-body">
                {device.payload && Object.keys(device.payload).length > 0 ? (
                  <details>
                    <summary style={{ cursor: 'pointer', color: 'var(--accent-secondary, #818cf8)' }}>
                      View details
                    </summary>
                    <pre style={{ marginTop: '0.5rem', fontSize: '0.85rem', overflow: 'auto' }}>
                      {JSON.stringify(device.payload, null, 2)}
                    </pre>
                  </details>
                ) : (
                  <p style={{ color: 'var(--text-secondary, #888)' }}>No additional data</p>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
};

export default DevicesTab;
