import { VoiceAssistant } from '../components/VoiceAssistant';

/**
 * Voice assistant page.
 * Provides full-screen voice interaction with KITTY.
 */
export default function Voice() {
  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <VoiceAssistant fullscreen />
    </div>
  );
}
