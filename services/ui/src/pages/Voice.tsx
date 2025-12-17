import { useState, useCallback } from 'react';
import { VoiceAssistant } from '../components/VoiceAssistant';
import { KittyBadge } from '../components/KittyBadge';
import './Voice.css';

/**
 * Voice assistant page.
 * Provides full-screen voice interaction with KITTY.
 */
export default function Voice() {
  const [isActive, setIsActive] = useState(false);

  // Callback to track when voice is active (listening or responding)
  const handleStatusChange = useCallback((status: string) => {
    setIsActive(status === 'listening' || status === 'responding');
  }, []);

  return (
    <div className="voice-page">
      <div className="voice-aurora left" />
      <div className="voice-aurora right" />
      <div className="voice-grid" />
      <div className="voice-scan" />
      <div className="voice-noise" />

      <div className="voice-shell">
        <VoiceAssistant fullscreen onStatusChange={handleStatusChange} />
      </div>

      {/* Floating KITTY badge - pauses wandering during active conversation */}
      <KittyBadge size={100} wandering={true} wanderInterval={25000} paused={isActive} />
    </div>
  );
}
