import { useEffect, useRef, useState } from 'react';

const FFT_BARS = 64;

interface UseAudioAnalyzerReturn {
  fftData: number[];
  audioLevel: number;
}

/**
 * Hook for real-time FFT audio analysis.
 * Analyzes audio stream and provides frequency data for visualization.
 */
export function useAudioAnalyzer(stream: MediaStream | null): UseAudioAnalyzerReturn {
  const [fftData, setFftData] = useState<number[]>(new Array(FFT_BARS).fill(0));
  const [audioLevel, setAudioLevel] = useState(0);

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!stream) {
      setFftData(new Array(FFT_BARS).fill(0));
      setAudioLevel(0);
      return;
    }

    // Create audio context and analyser
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;

    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.5;
    analyserRef.current = analyser;

    // Connect stream to analyser
    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

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
      if (audioContextRef.current) {
        audioContextRef.current.close();
        audioContextRef.current = null;
      }
      analyserRef.current = null;
    };
  }, [stream]);

  return { fftData, audioLevel };
}
