import { useState, useCallback } from 'react';
import { VoiceAssistant } from '../components/VoiceAssistant';
import { KittyBadge } from '../components/KittyBadge';
import './Interact.css';

/**
 * Interact page - voice assistant interface.
 * Provides full-screen voice interaction with KITTY.
 */
export default function Interact() {
  const [isActive, setIsActive] = useState(false);

  // Callback to track when voice is active (listening or responding)
  const handleStatusChange = useCallback((status: string) => {
    setIsActive(status === 'listening' || status === 'responding');
  }, []);

  return (
    <div className="interact-page">
      <div className="interact-aurora left" />
      <div className="interact-aurora right" />
      <div className="interact-grid" />
      <div className="interact-scan" />
      <div className="interact-noise" />

      <div className="interact-shell">
        <VoiceAssistant fullscreen onStatusChange={handleStatusChange} />
      </div>

      {/* Floating KITTY badge - pauses wandering during active conversation */}
      <KittyBadge size={100} wandering={true} wanderInterval={25000} paused={isActive} />
    </div>
  );
}
