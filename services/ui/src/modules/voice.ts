export type VoiceStatus = 'idle' | 'recording' | 'processing' | 'error';

export interface VoiceResult {
  transcript: string;
  timestamp: number;
}

export type OnTranscript = (result: VoiceResult) => void;

/**
 * Simple wrapper around the Web Speech API with a fallback to server-side transcription.
 */
export const createVoiceController = (onTranscript: OnTranscript, fetchUrl?: string) => {
  let recognition: SpeechRecognition | null = null;

  const supportsSpeechRecognition = typeof window !== 'undefined' && ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window);

  const start = async (): Promise<VoiceStatus> => {
    if (supportsSpeechRecognition) {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';

      return await new Promise<VoiceStatus>((resolve) => {
        recognition!.onresult = (event: SpeechRecognitionEvent) => {
          const transcript = event.results[0][0].transcript;
          onTranscript({ transcript, timestamp: Date.now() });
        };
        recognition!.onend = () => resolve('idle');
        recognition!.onerror = () => resolve('error');
        recognition!.start();
        resolve('recording');
      });
    }

    if (!fetchUrl) {
      throw new Error('SpeechRecognition not supported and no transcription endpoint provided');
    }

    // Fallback: record through MediaRecorder and POST to backend (implementation placeholder)
    // Caller must implement actual recording pipeline.
    return 'processing';
  };

  const stop = () => {
    recognition?.stop();
  };

  return {
    start,
    stop,
  };
};
