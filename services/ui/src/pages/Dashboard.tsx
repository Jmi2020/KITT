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

  return (
    <section className="dashboard">
      <div className="controls">
        <button onClick={startVoice} disabled={remoteMode}>
          {remoteMode ? 'Voice Disabled (Remote Mode)' : 'Start Voice Command'}
        </button>
      </div>
      <div className="device-grid">
        {Object.values(context.devices).map((device) => (
          <article key={device.deviceId} className={`device-card status-${device.status}`}>
            <h3>{device.deviceId}</h3>
            <p>Status: {device.status}</p>
            <pre>{JSON.stringify(device.payload, null, 2)}</pre>
          </article>
        ))}
      </div>
    </section>
  );
};

export default Dashboard;
