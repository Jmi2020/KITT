import { useCallback, useRef, useState } from 'react';

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
}

/**
 * Hook for capturing audio from the microphone.
 * Uses AudioWorklet for high-quality, low-latency audio processing.
 */
export function useAudioCapture(options: UseAudioCaptureOptions = {}): UseAudioCaptureReturn {
  const { sampleRate = 16000, onAudioChunk } = options;

  const [isCapturing, setIsCapturing] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const startCapture = useCallback(async () => {
    try {
      setError(null);

      // Request microphone access
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = mediaStream;
      setStream(mediaStream);

      // Create audio context
      const audioContext = new AudioContext({ sampleRate });
      audioContextRef.current = audioContext;

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

      // Connect microphone to worklet
      const source = audioContext.createMediaStreamSource(mediaStream);
      source.connect(workletNode);

      setIsCapturing(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to access microphone';
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
    // Stop all media tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setStream(null);
    }

    // Disconnect and close audio context
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setIsCapturing(false);
  }, []);

  return {
    isCapturing,
    stream,
    startCapture,
    stopCapture,
    error,
  };
}
