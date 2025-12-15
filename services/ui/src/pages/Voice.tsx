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
    <div className="h-full w-full bg-gray-900 relative overflow-hidden">
      {/* Deep Space Background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-gray-800 via-gray-900 to-black" />

      {/* Cyber Grid Overlay */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255,255,255,0.1) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255,255,255,0.1) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
          maskImage: 'radial-gradient(circle at center, black 40%, transparent 100%)',
          WebkitMaskImage: 'radial-gradient(circle at center, black 40%, transparent 100%)',
        }}
      />

      {/* Subtle Scanline */}
      <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] z-[1] bg-[length:100%_2px,3px_100%] opacity-20" />

      {/* Content Wrapper */}
      <div className="relative z-10 w-full h-full">
        <VoiceAssistant fullscreen onStatusChange={handleStatusChange} />
      </div>

      {/* Floating KITTY badge - pauses wandering during active conversation */}
      <KittyBadge size={100} wandering={true} wanderInterval={25000} paused={isActive} />
    </div>
  );
}
