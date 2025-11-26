import { useEffect, useRef, useState } from 'react';

const FFT_BARS = 64;

interface AudioVisualizerProps {
  fftData: number[];
  audioLevel: number;
  status: 'idle' | 'listening' | 'responding' | 'error';
  isProcessing?: boolean;
  progress?: number | null;
}

/**
 * FFT ring visualizer for audio levels.
 * Displays frequency data as bars arranged in a circle.
 */
export function AudioVisualizer({
  fftData,
  audioLevel,
  status,
  isProcessing = false,
  progress = null,
}: AudioVisualizerProps) {
  const [ring1Rotation, setRing1Rotation] = useState(0);
  const [ring2Rotation, setRing2Rotation] = useState(0);
  const rotationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(Date.now());

  // Continuous rotation for rings
  useEffect(() => {
    const rotate = () => {
      const now = Date.now();
      const delta = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      setRing1Rotation((prev) => (prev + 40 * delta) % 360);
      setRing2Rotation((prev) => (prev - 20 * delta) % 360);

      rotationFrameRef.current = requestAnimationFrame(rotate);
    };
    rotate();

    return () => {
      if (rotationFrameRef.current) {
        cancelAnimationFrame(rotationFrameRef.current);
      }
    };
  }, []);

  const ring1Scale = 1 + audioLevel * 0.08;
  const ring2Scale = 1 + audioLevel * 0.05;
  const isActive = status === 'listening' || status === 'responding';

  return (
    <div className="relative flex items-center justify-center w-full max-w-xl aspect-square">
      {/* Ring 2 - Outer */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{
          transform: `rotate(${ring2Rotation}deg) scale(${ring2Scale})`,
          opacity: isActive ? 1 : 0.3,
          transition: 'opacity 300ms',
        }}
      >
        <svg viewBox="0 0 200 200" className="w-full h-full">
          <circle
            cx="100"
            cy="100"
            r="95"
            fill="none"
            stroke="rgba(34, 211, 238, 0.3)"
            strokeWidth="2"
            strokeDasharray="8 4"
          />
          <circle
            cx="100"
            cy="100"
            r="90"
            fill="none"
            stroke="rgba(34, 211, 238, 0.5)"
            strokeWidth="1"
          />
        </svg>
      </div>

      {/* FFT Visualizer Ring */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <svg className="w-2/3 h-2/3" viewBox="0 0 400 400" style={{ overflow: 'visible' }}>
          {fftData.map((value, index) => {
            const angle = (index / FFT_BARS) * Math.PI * 2;
            const radius = 180;
            const centerX = 200;
            const centerY = 200;
            const x = centerX + Math.cos(angle) * radius;
            const y = centerY + Math.sin(angle) * radius;
            const barWidth = 5;
            const baseHeight = 6;

            let barHeight: number;
            let opacity: number;

            // Progress animation (for loading states)
            if (progress !== null) {
              const progressAngle = (progress / 100) * Math.PI * 2;
              const barAngle = (index / FFT_BARS) * Math.PI * 2;
              const isFilled = barAngle <= progressAngle;
              const isEdge = Math.abs(barAngle - progressAngle) < (Math.PI * 2 / FFT_BARS * 2);
              const pulse = isEdge ? Math.sin(Date.now() / 150) * 0.3 + 0.7 : 1;

              barHeight = isFilled ? baseHeight + 20 * pulse : baseHeight;
              opacity = isFilled ? 0.9 * pulse : 0.2;
            }
            // Wave animation when processing
            else if (isProcessing) {
              const waveOffset = Math.sin((Date.now() / 200) + (index * 0.3)) * 15;
              barHeight = baseHeight + Math.abs(waveOffset);
              opacity = 0.6 + (Math.abs(waveOffset) / 15) * 0.4;
            }
            // Normal audio visualization
            else {
              barHeight = baseHeight + value * 25;
              opacity = isActive ? 0.4 + value * 0.6 : 0.1;
            }

            const rotation = (angle * 180) / Math.PI + 90;

            return (
              <g key={index} transform={`translate(${x}, ${y}) rotate(${rotation})`}>
                <rect
                  x={-barWidth / 2}
                  y={-barHeight / 2}
                  width={barWidth}
                  height={barHeight}
                  fill="#22d3ee"
                  opacity={opacity}
                  rx={2.5}
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Ring 1 - Inner */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{
          transform: `rotate(${ring1Rotation}deg) scale(${ring1Scale})`,
          opacity: isActive ? 1 : 0.5,
          transition: 'opacity 200ms',
        }}
      >
        <svg viewBox="0 0 200 200" className="w-4/5 h-4/5">
          <circle
            cx="100"
            cy="100"
            r="75"
            fill="none"
            stroke="rgba(34, 211, 238, 0.6)"
            strokeWidth="2"
            strokeDasharray="4 8"
          />
          <circle
            cx="100"
            cy="100"
            r="70"
            fill="none"
            stroke="rgba(34, 211, 238, 0.8)"
            strokeWidth="1"
          />
        </svg>
      </div>

      {/* Status Ring Glow */}
      {isActive && (
        <div
          className="absolute inset-0 rounded-full transition-opacity duration-300 pointer-events-none"
          style={{
            background: `radial-gradient(circle, rgba(34,211,238,${audioLevel * 0.3}) 0%, transparent 70%)`,
            transform: `scale(${1 + audioLevel * 0.5})`,
          }}
        />
      )}
    </div>
  );
}
