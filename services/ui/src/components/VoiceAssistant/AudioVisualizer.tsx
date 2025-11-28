import { useEffect, useRef, useState, useMemo } from 'react';

const FFT_BARS = 64;
const PARTICLE_COUNT = 12;

/** Color theme definitions for different voice modes */
const MODE_COLORS = {
  cyan: { hex: '#22d3ee', rgb: '34, 211, 238' },
  orange: { hex: '#f97316', rgb: '249, 115, 22' },
  purple: { hex: '#a855f7', rgb: '168, 85, 247' },
  green: { hex: '#22c55e', rgb: '34, 197, 94' },
  pink: { hex: '#ec4899', rgb: '236, 72, 153' },
  red: { hex: '#ef4444', rgb: '239, 68, 68' },
};

interface AudioVisualizerProps {
  fftData: number[];
  audioLevel: number;
  status: 'idle' | 'listening' | 'responding' | 'error';
  isProcessing?: boolean;
  progress?: number | null;
  /** Size in pixels (default: 280) */
  size?: number;
  /** Color theme based on voice mode (default: cyan) */
  modeColor?: 'cyan' | 'orange' | 'purple' | 'green' | 'pink';
}

/**
 * Jarvis-style FFT ring visualizer for audio levels.
 * Features: rotating rings, FFT bars, scanning effects, and particle system.
 */
export function AudioVisualizer({
  fftData,
  audioLevel,
  status,
  isProcessing = false,
  progress = null,
  size = 280,
  modeColor = 'cyan',
}: AudioVisualizerProps) {
  const [ring1Rotation, setRing1Rotation] = useState(0);
  const [ring2Rotation, setRing2Rotation] = useState(0);
  const [ring3Rotation, setRing3Rotation] = useState(0);
  const [scanAngle, setScanAngle] = useState(0);
  const [pulsePhase, setPulsePhase] = useState(0);
  const rotationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(Date.now());

  // Generate stable particle positions
  const particles = useMemo(() => {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
      angle: (i / PARTICLE_COUNT) * Math.PI * 2,
      radius: 0.35 + Math.random() * 0.15,
      speed: 0.5 + Math.random() * 0.5,
      size: 2 + Math.random() * 3,
    }));
  }, []);

  // Continuous rotation for rings
  useEffect(() => {
    const rotate = () => {
      const now = Date.now();
      const delta = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      setRing1Rotation((prev) => (prev + 50 * delta) % 360);
      setRing2Rotation((prev) => (prev - 30 * delta) % 360);
      setRing3Rotation((prev) => (prev + 15 * delta) % 360);
      setScanAngle((prev) => (prev + 120 * delta) % 360);
      setPulsePhase((prev) => prev + delta * 3);

      rotationFrameRef.current = requestAnimationFrame(rotate);
    };
    rotate();

    return () => {
      if (rotationFrameRef.current) {
        cancelAnimationFrame(rotationFrameRef.current);
      }
    };
  }, []);

  const ring1Scale = 1 + audioLevel * 0.1;
  const ring2Scale = 1 + audioLevel * 0.06;
  const ring3Scale = 1 + audioLevel * 0.04;
  const isActive = status === 'listening' || status === 'responding';
  const isError = status === 'error';

  // Color based on status and mode
  const colorTheme = isError ? MODE_COLORS.red : (MODE_COLORS[modeColor] || MODE_COLORS.cyan);
  const primaryColor = colorTheme.hex;
  const primaryRgba = `rgba(${colorTheme.rgb},`;
  const pulseIntensity = Math.sin(pulsePhase) * 0.5 + 0.5;

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: size, height: size }}
    >
      {/* Background glow */}
      <div
        className="absolute inset-0 rounded-full transition-opacity duration-500 pointer-events-none"
        style={{
          background: `radial-gradient(circle, ${primaryRgba}${isActive ? 0.15 + audioLevel * 0.2 : 0.05}) 0%, transparent 70%)`,
          transform: `scale(${1.2 + audioLevel * 0.3})`,
          filter: 'blur(20px)',
        }}
      />

      {/* Ring 3 - Outermost (tech ring) */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{
          transform: `rotate(${ring3Rotation}deg) scale(${ring3Scale})`,
          opacity: isActive ? 0.8 : 0.2,
          transition: 'opacity 300ms',
        }}
      >
        <svg viewBox="0 0 200 200" className="w-full h-full">
          {/* Outer tech ring with segments */}
          <circle
            cx="100"
            cy="100"
            r="98"
            fill="none"
            stroke={`${primaryRgba}0.2)`}
            strokeWidth="1"
          />
          {/* Tech marks */}
          {Array.from({ length: 24 }).map((_, i) => {
            const angle = (i / 24) * Math.PI * 2;
            const x1 = 100 + Math.cos(angle) * 94;
            const y1 = 100 + Math.sin(angle) * 94;
            const x2 = 100 + Math.cos(angle) * (i % 3 === 0 ? 88 : 91);
            const y2 = 100 + Math.sin(angle) * (i % 3 === 0 ? 88 : 91);
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={`${primaryRgba}${i % 3 === 0 ? 0.6 : 0.3})`}
                strokeWidth={i % 3 === 0 ? 2 : 1}
              />
            );
          })}
        </svg>
      </div>

      {/* Ring 2 - Middle */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{
          transform: `rotate(${ring2Rotation}deg) scale(${ring2Scale})`,
          opacity: isActive ? 1 : 0.3,
          transition: 'opacity 300ms',
        }}
      >
        <svg viewBox="0 0 200 200" className="w-[85%] h-[85%]">
          <circle
            cx="100"
            cy="100"
            r="95"
            fill="none"
            stroke={`${primaryRgba}0.3)`}
            strokeWidth="2"
            strokeDasharray="12 6"
          />
          <circle
            cx="100"
            cy="100"
            r="88"
            fill="none"
            stroke={`${primaryRgba}0.5)`}
            strokeWidth="1"
          />
        </svg>
      </div>

      {/* Scanning line effect */}
      {isActive && (
        <div
          className="absolute inset-0 flex items-center justify-center pointer-events-none"
          style={{ transform: `rotate(${scanAngle}deg)` }}
        >
          <svg viewBox="0 0 200 200" className="w-[75%] h-[75%]">
            <defs>
              <linearGradient id="scanGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={primaryColor} stopOpacity="0" />
                <stop offset="50%" stopColor={primaryColor} stopOpacity="0.8" />
                <stop offset="100%" stopColor={primaryColor} stopOpacity="0" />
              </linearGradient>
            </defs>
            <line x1="100" y1="100" x2="100" y2="20" stroke="url(#scanGrad)" strokeWidth="2" />
          </svg>
        </div>
      )}

      {/* FFT Visualizer Ring */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <svg className="w-[65%] h-[65%]" viewBox="0 0 400 400" style={{ overflow: 'visible' }}>
          {fftData.map((value, index) => {
            const angle = (index / FFT_BARS) * Math.PI * 2;
            const radius = 180;
            const centerX = 200;
            const centerY = 200;
            const x = centerX + Math.cos(angle) * radius;
            const y = centerY + Math.sin(angle) * radius;
            const barWidth = 4;
            const baseHeight = 4;

            let barHeight: number;
            let opacity: number;

            // Progress animation
            if (progress !== null) {
              const progressAngle = (progress / 100) * Math.PI * 2;
              const barAngle = (index / FFT_BARS) * Math.PI * 2;
              const isFilled = barAngle <= progressAngle;
              const isEdge = Math.abs(barAngle - progressAngle) < (Math.PI * 2 / FFT_BARS * 2);
              const pulse = isEdge ? pulseIntensity : 1;

              barHeight = isFilled ? baseHeight + 25 * pulse : baseHeight;
              opacity = isFilled ? 0.9 * pulse : 0.15;
            }
            // Wave animation when processing
            else if (isProcessing) {
              const waveOffset = Math.sin(pulsePhase + index * 0.25) * 20;
              barHeight = baseHeight + Math.abs(waveOffset);
              opacity = 0.5 + (Math.abs(waveOffset) / 20) * 0.5;
            }
            // Normal audio visualization
            else {
              barHeight = baseHeight + value * 30;
              opacity = isActive ? 0.3 + value * 0.7 : 0.08;
            }

            const rotation = (angle * 180) / Math.PI + 90;

            return (
              <g key={index} transform={`translate(${x}, ${y}) rotate(${rotation})`}>
                <rect
                  x={-barWidth / 2}
                  y={-barHeight / 2}
                  width={barWidth}
                  height={barHeight}
                  fill={primaryColor}
                  opacity={opacity}
                  rx={2}
                />
              </g>
            );
          })}
        </svg>
      </div>

      {/* Floating particles */}
      {isActive && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <svg className="w-full h-full" viewBox="0 0 200 200">
            {particles.map((particle, i) => {
              const animatedAngle = particle.angle + pulsePhase * particle.speed;
              const animatedRadius = particle.radius * 100 + audioLevel * 15;
              const x = 100 + Math.cos(animatedAngle) * animatedRadius;
              const y = 100 + Math.sin(animatedAngle) * animatedRadius;

              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r={particle.size * (0.5 + audioLevel * 0.5)}
                  fill={primaryColor}
                  opacity={0.4 + audioLevel * 0.4}
                />
              );
            })}
          </svg>
        </div>
      )}

      {/* Ring 1 - Inner */}
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{
          transform: `rotate(${ring1Rotation}deg) scale(${ring1Scale})`,
          opacity: isActive ? 1 : 0.4,
          transition: 'opacity 200ms',
        }}
      >
        <svg viewBox="0 0 200 200" className="w-[50%] h-[50%]">
          <circle
            cx="100"
            cy="100"
            r="90"
            fill="none"
            stroke={`${primaryRgba}0.5)`}
            strokeWidth="2"
            strokeDasharray="6 10"
          />
          <circle
            cx="100"
            cy="100"
            r="80"
            fill="none"
            stroke={`${primaryRgba}0.8)`}
            strokeWidth="1"
          />
        </svg>
      </div>

      {/* Core pulse */}
      <div
        className="absolute rounded-full pointer-events-none"
        style={{
          width: size * 0.25,
          height: size * 0.25,
          background: `radial-gradient(circle, ${primaryRgba}${isActive ? 0.3 + pulseIntensity * 0.2 : 0.1}) 0%, ${primaryRgba}0.05) 60%, transparent 100%)`,
          boxShadow: isActive ? `0 0 ${20 + audioLevel * 30}px ${primaryRgba}0.4)` : 'none',
          transition: 'box-shadow 100ms',
        }}
      />
    </div>
  );
}
