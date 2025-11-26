import { CameraDashboard } from '../components/CameraDashboard';

/**
 * Cameras page with live WebSocket streaming.
 * Displays all connected cameras with real-time frame updates.
 */
export default function Cameras() {
  return (
    <div className="min-h-screen bg-gray-900">
      <CameraDashboard autoConnect autoSubscribe />
    </div>
  );
}
