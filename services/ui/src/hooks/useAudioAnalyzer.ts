import { useEffect, useRef, useState, useContext } from 'react';
import { AudioContextContext } from './useAudioContext';

const FFT_BARS = 64;

interface UseAudioAnalyzerReturn {
  fftData: number[];
  audioLevel: number;
}

/**
 * Hook for real-time FFT audio analysis.
 * Uses the shared AudioContext from AudioContextProvider when available.
 * Falls back to creating its own context if not within provider.
 */
export function useAudioAnalyzer(stream: MediaStream | null): UseAudioAnalyzerReturn {
  const [fftData, setFftData] = useState<number[]>(new Array(FFT_BARS).fill(0));
  const [audioLevel, setAudioLevel] = useState(0);

  // Try to get shared context (may be null if not in provider)
  const sharedContext = useContext(AudioContextContext);

  const localAudioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  useEffect(() => {
    if (!stream) {
      setFftData(new Array(FFT_BARS).fill(0));
      setAudioLevel(0);
      return;
    }

    // Use shared analyser if available, otherwise create local context
    let analyser: AnalyserNode;
    let localContext: AudioContext | null = null;

    if (sharedContext?.analyserNode) {
      // Use existing shared analyser
      analyser = sharedContext.analyserNode;
    } else {
      // Fallback: create local context
      localContext = new AudioContext();
      localAudioContextRef.current = localContext;

      analyser = localContext.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.5;

      // Connect stream to analyser
      const source = localContext.createMediaStreamSource(stream);
      sourceRef.current = source;
      source.connect(analyser);
    }

    analyserRef.current = analyser;
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const updateAnalysis = () => {
      if (!analyserRef.current) return;

      analyserRef.current.getByteFrequencyData(dataArray);

      // Calculate overall audio level
      let sum = 0;
      for (let i = 0; i < dataArray.length; i++) {
        sum += dataArray[i];
      }
      const average = sum / dataArray.length;

      // Normalize and apply curve for better visual response
      let normalizedVolume = Math.min(average / 128, 1);
      normalizedVolume = Math.pow(normalizedVolume, 0.6) * 1.5;
      setAudioLevel(Math.min(normalizedVolume, 1));

      // Calculate FFT bars
      const barData: number[] = [];
      const usefulBins = Math.floor(dataArray.length / 2);
      const samplesPerBar = usefulBins / FFT_BARS;

      for (let i = 0; i < FFT_BARS; i++) {
        let barSum = 0;
        const startIdx = Math.floor(i * samplesPerBar);
        const endIdx = Math.floor((i + 1) * samplesPerBar);

        for (let j = startIdx; j < endIdx; j++) {
          barSum += dataArray[j];
        }

        const normalized = (barSum / (endIdx - startIdx)) / 255;
        const scaled = Math.pow(normalized, 0.5) * 1.8;
        barData.push(Math.min(scaled, 1));
      }

      setFftData(barData);
      animationFrameRef.current = requestAnimationFrame(updateAnalysis);
    };

    updateAnalysis();

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }

      // Only close local context if we created one
      if (localAudioContextRef.current) {
        if (sourceRef.current) {
          sourceRef.current.disconnect();
          sourceRef.current = null;
        }
        localAudioContextRef.current.close();
        localAudioContextRef.current = null;
      }

      analyserRef.current = null;
    };
  }, [stream, sharedContext?.analyserNode]);

  return { fftData, audioLevel };
}
