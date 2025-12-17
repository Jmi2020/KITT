import { useCallback, useRef, useState, useContext } from 'react';
import { AudioContextContext } from './useAudioContext';

interface UseAudioCaptureOptions {
  sampleRate?: number;
  onAudioChunk?: (chunk: ArrayBuffer) => void;
}

interface UseAudioCaptureReturn {
  isCapturing: boolean;
  stream: MediaStream | null;
  startCapture: () => Promise<void>;
  stopCapture: () => void;
  error: string | null;
  inputLevel: number;
}

/**
 * Hook for capturing audio from the microphone.
 * Uses AudioWorklet for high-quality, low-latency audio processing.
 * Uses shared AudioContext when available, falls back to local context.
 */
export function useAudioCapture(options: UseAudioCaptureOptions = {}): UseAudioCaptureReturn {
  const { sampleRate = 16000, onAudioChunk } = options;

  const [isCapturing, setIsCapturing] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [localInputLevel, setLocalInputLevel] = useState(0);

  // Try to get shared audio context (may be null if not in provider)
  const sharedContext = useContext(AudioContextContext);

  const localAudioContextRef = useRef<AudioContext | null>(null);
  const localAnalyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // Setup local input level monitoring
  const setupLocalAnalyser = useCallback((audioContext: AudioContext, source: MediaStreamAudioSourceNode) => {
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.5;
    localAnalyserRef.current = analyser;
    source.connect(analyser);

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateLevel = () => {
      if (!localAnalyserRef.current) return;
      localAnalyserRef.current.getByteFrequencyData(dataArray);

      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const average = sum / dataArray.length;
      const normalized = Math.min(Math.pow(average / 128, 0.6) * 1.5, 1);
      setLocalInputLevel(normalized);

      animationFrameRef.current = requestAnimationFrame(updateLevel);
    };

    updateLevel();
  }, []);

  const startCapture = useCallback(async () => {
    try {
      setError(null);

      const navAny = navigator as any;
      const mediaDevices = navigator.mediaDevices;

      // Browser support guard
      const legacyGetUserMedia = navAny.getUserMedia || navAny.webkitGetUserMedia || navAny.mozGetUserMedia;
      if (!mediaDevices?.getUserMedia && !legacyGetUserMedia) {
        setError('Microphone not available: getUserMedia is not supported in this browser/context.');
        return;
      }

      const requestUserMedia = async () => {
        if (mediaDevices?.getUserMedia) {
          return mediaDevices.getUserMedia({
            audio: {
              channelCount: 1,
              sampleRate,
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
            },
          });
        }
        return new Promise<MediaStream>((resolve, reject) => {
          legacyGetUserMedia.call(navigator, { audio: true }, resolve, reject);
        });
      };

      // Request microphone access
      const mediaStream = await requestUserMedia();

      streamRef.current = mediaStream;
      setStream(mediaStream);

      // Use shared context if available, otherwise create local
      let audioContext: AudioContext;
      if (sharedContext) {
        audioContext = sharedContext.getOrCreateContext(sampleRate);
      } else {
        audioContext = new AudioContext({ sampleRate });
        localAudioContextRef.current = audioContext;
      }

      // Create source and connect to analyser for input level monitoring
      const source = audioContext.createMediaStreamSource(mediaStream);
      sourceRef.current = source;

      if (sharedContext) {
        sharedContext.setupAnalyser(source);
      } else {
        setupLocalAnalyser(audioContext, source);
      }

      // Load audio worklet
      try {
        await audioContext.audioWorklet.addModule('/audio-processor.js');
      } catch (workletError) {
        console.warn('AudioWorklet not supported, falling back to ScriptProcessor');
        // Fallback for browsers without AudioWorklet support
        setupScriptProcessorFallback(audioContext, mediaStream);
        setIsCapturing(true);
        return;
      }

      // Create worklet node
      const workletNode = new AudioWorkletNode(audioContext, 'audio-capture-processor');
      workletNodeRef.current = workletNode;

      // Handle audio data from worklet
      workletNode.port.onmessage = (event) => {
        if (onAudioChunk) {
          onAudioChunk(event.data);
        }
      };

      // Connect source to worklet (source already created above)
      sourceRef.current?.connect(workletNode);

      setIsCapturing(true);
    } catch (err: any) {
      let message = 'Failed to access microphone';
      if (err?.name === 'NotAllowedError' || err?.name === 'SecurityError') {
        message = 'Microphone permission denied. Please allow mic access in your browser.';
      } else if (err?.name === 'NotFoundError' || err?.name === 'DevicesNotFoundError') {
        message = 'No microphone found. Please plug in a mic and try again.';
      } else if (err instanceof Error && err.message) {
        message = err.message;
      }
      setError(message);
      console.error('Audio capture error:', err);
    }
  }, [sampleRate, onAudioChunk]);

  const setupScriptProcessorFallback = useCallback(
    (audioContext: AudioContext, mediaStream: MediaStream) => {
      // ScriptProcessor fallback for older browsers
      const source = audioContext.createMediaStreamSource(mediaStream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (event) => {
        const inputData = event.inputBuffer.getChannelData(0);

        // Convert to int16 PCM
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
        }

        if (onAudioChunk) {
          onAudioChunk(pcmData.buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);
    },
    [onAudioChunk]
  );

  const stopCapture = useCallback(() => {
    // Stop animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    // Stop all media tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setStream(null);
    }

    // Disconnect worklet node
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    // Disconnect source
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    // Disconnect local analyser
    if (localAnalyserRef.current) {
      localAnalyserRef.current.disconnect();
      localAnalyserRef.current = null;
    }

    // Close context (shared or local)
    if (sharedContext) {
      sharedContext.closeContext();
    } else if (localAudioContextRef.current) {
      localAudioContextRef.current.close();
      localAudioContextRef.current = null;
    }

    setLocalInputLevel(0);
    setIsCapturing(false);
  }, [sharedContext]);

  // Use shared input level if available, otherwise use local
  const inputLevel = sharedContext?.inputLevel ?? localInputLevel;

  return {
    isCapturing,
    stream,
    startCapture,
    stopCapture,
    error,
    inputLevel,
  };
}
