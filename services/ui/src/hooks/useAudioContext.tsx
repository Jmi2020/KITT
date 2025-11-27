import { createContext, useContext, useRef, useCallback, ReactNode, useState } from 'react';

interface AudioContextState {
  audioContext: AudioContext | null;
  analyserNode: AnalyserNode | null;
  inputLevel: number;
  getOrCreateContext: (sampleRate?: number) => AudioContext;
  setupAnalyser: (source: MediaStreamAudioSourceNode) => AnalyserNode;
  closeContext: () => void;
}

const AudioContextContext = createContext<AudioContextState | null>(null);

/**
 * Shared AudioContext provider to prevent multiple context creation.
 * Both useAudioCapture and useAudioAnalyzer should use this.
 */
export function AudioContextProvider({ children }: { children: ReactNode }) {
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const [inputLevel, setInputLevel] = useState(0);

  const getOrCreateContext = useCallback((sampleRate = 16000): AudioContext => {
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      return audioContextRef.current;
    }

    audioContextRef.current = new AudioContext({ sampleRate });
    return audioContextRef.current;
  }, []);

  const setupAnalyser = useCallback((source: MediaStreamAudioSourceNode): AnalyserNode => {
    const ctx = source.context as AudioContext;

    // Create analyser if not exists or context changed
    if (!analyserRef.current || analyserRef.current.context !== ctx) {
      analyserRef.current = ctx.createAnalyser();
      analyserRef.current.fftSize = 512;
      analyserRef.current.smoothingTimeConstant = 0.5;
    }

    // Connect source to analyser
    source.connect(analyserRef.current);

    // Start input level monitoring
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);

    const updateLevel = () => {
      if (!analyserRef.current) return;

      analyserRef.current.getByteFrequencyData(dataArray);

      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const average = sum / dataArray.length;
      const normalized = Math.min(Math.pow(average / 128, 0.6) * 1.5, 1);
      setInputLevel(normalized);

      animationFrameRef.current = requestAnimationFrame(updateLevel);
    };

    // Cancel any existing animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
    }
    updateLevel();

    return analyserRef.current;
  }, []);

  const closeContext = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    if (analyserRef.current) {
      analyserRef.current.disconnect();
      analyserRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setInputLevel(0);
  }, []);

  return (
    <AudioContextContext.Provider
      value={{
        audioContext: audioContextRef.current,
        analyserNode: analyserRef.current,
        inputLevel,
        getOrCreateContext,
        setupAnalyser,
        closeContext,
      }}
    >
      {children}
    </AudioContextContext.Provider>
  );
}

/**
 * Hook to access shared AudioContext.
 * Must be used within AudioContextProvider.
 */
export function useSharedAudioContext(): AudioContextState {
  const context = useContext(AudioContextContext);
  if (!context) {
    throw new Error('useSharedAudioContext must be used within AudioContextProvider');
  }
  return context;
}

export { AudioContextContext };
