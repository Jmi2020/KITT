import { useState, useCallback } from 'react';
import { VoiceAssistant } from '../components/VoiceAssistant';
import { KittyBadge } from '../components/KittyBadge';

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
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <VoiceAssistant fullscreen onStatusChange={handleStatusChange} />
      {/* Floating KITTY badge - pauses wandering during active conversation */}
      <KittyBadge size={100} wandering={true} wanderInterval={25000} paused={isActive} />
    </div>
  );
}
