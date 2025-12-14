import { useEffect, useRef, useState, useMemo } from 'react';

const CODE_CHARS = '{}[]/<>*#+-=_:;.,?!@$%^&()';
const CODE_SEGMENTS_COUNT = 16;
const DOT_COUNT = 8;

const MODE_COLORS = {
  cyan: { hex: '#22d3ee', rgb: '34, 211, 238' },
  orange: { hex: '#f97316', rgb: '249, 115, 22' },
  purple: { hex: '#a855f7', rgb: '168, 85, 247' },
  green: { hex: '#22c55e', rgb: '34, 197, 94' },
  pink: { hex: '#ec4899', rgb: '236, 72, 153' },
  red: { hex: '#ef4444', rgb: '239, 68, 68' },
};

interface CodeCircleVisualizerProps {
  fftData: number[];
  audioLevel: number;
  typingLevel?: number;
  status: 'idle' | 'listening' | 'responding' | 'error';
  size?: number;
  modeColor?: 'cyan' | 'orange' | 'purple' | 'green' | 'pink';
}

export function CodeCircleVisualizer({
  fftData,
  audioLevel,
  typingLevel = 0,
  status,
  size = 300,
  modeColor = 'cyan',
}: CodeCircleVisualizerProps) {
  const [rotation, setRotation] = useState(0);
  const animationRef = useRef<number>();
  
  const codeRings = useMemo(() => {
    return Array.from({ length: 3 }).map((_, ringIndex) => 
      Array.from({ length: CODE_SEGMENTS_COUNT }).map((_, i) => {
        const segmentLength = 3 + Math.floor(Math.random() * 5);
        let segment = '';
        for(let j=0; j<segmentLength; j++) {
          segment += CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)];
        }
        return {
          text: segment,
          angle: (i / CODE_SEGMENTS_COUNT) * 360,
          opacity: 0.3 + Math.random() * 0.7
        };
      })
    );
  }, []);

  useEffect(() => {
    const animate = () => {
      const speed = status === 'listening' ? 0.5 : status === 'responding' ? 0.2 : 0.05;
      const typingBoost = typingLevel * 0.5;
      
      setRotation(prev => (prev + speed + typingBoost) % 360);
      animationRef.current = requestAnimationFrame(animate);
    };
    animate();
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [status, typingLevel]);

  const colorTheme = MODE_COLORS[modeColor] || MODE_COLORS.cyan;
  const isActive = status === 'listening' || status === 'responding';
  
  const activityLevel = Math.max(audioLevel, typingLevel * 0.8);
  const baseScale = 1 + (activityLevel * 0.2);
  const activeOpacity = isActive || typingLevel > 0;

  const glowStyle = {
    backgroundColor: colorTheme.hex,
    transform: 'scale(' + (baseScale * 0.8) + ')',
    opacity: 0.2 + (activityLevel * 0.3)
  };

  const centerRotation = 'rotate(' + rotation + ', 200, 200)';
  const middleRotation = 'rotate(' + (-rotation * 1.5) + ', 200, 200)';

  return (
    <div 
      className="relative flex items-center justify-center select-none"
      style={{ width: size, height: size }}
    >
      <div 
        className="absolute inset-0 rounded-full blur-3xl transition-all duration-500"
        style={glowStyle}
      />

      <svg 
        viewBox="0 0 400 400" 
        className="w-full h-full overflow-visible transition-all duration-100"
      >
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
            <feMerge>
              <feMergeNode in="coloredBlur"/>
              <feMergeNode in="SourceGraphic"/>
            </feMerge>
          </filter>
        </defs>

        <g transform={centerRotation} style={{ transformOrigin: 'center' }}>
          {codeRings[0].map((segment, i) => {
            const radius = 100 + (fftData[i % fftData.length] || 0) * 50 + (activityLevel * 10 * (i%2===0 ? 1 : -1));
            const x = 200 + radius * Math.cos(segment.angle * Math.PI / 180);
            const y = 200 + radius * Math.sin(segment.angle * Math.PI / 180);
            const textTransform = 'rotate(' + (segment.angle + 90) + ', ' + x + ', ' + y + ')';
            
            return (
              <text
                key={i}
                x={x}
                y={y}
                fill={colorTheme.hex}
                opacity={Math.min(1, segment.opacity + activityLevel)}
                fontSize="10"
                fontFamily="monospace"
                textAnchor="middle"
                dominantBaseline="middle"
                transform={textTransform}
                filter="url(#glow)"
              >
                {segment.text}
              </text>
            );
          })}
        </g>

        <g transform={middleRotation} style={{ transformOrigin: 'center' }}>
          {codeRings[1].map((segment, i) => {
            const radius = 140;
            const x = 200 + radius * Math.cos((segment.angle + 15) * Math.PI / 180);
            const y = 200 + radius * Math.sin((segment.angle + 15) * Math.PI / 180);
            const textTransform = 'rotate(' + (segment.angle + 105) + ', ' + x + ', ' + y + ')';
            
            return (
              <text
                key={i}
                x={x}
                y={y}
                fill={colorTheme.hex}
                opacity={activeOpacity ? 0.8 : 0.2}
                fontSize="12"
                fontWeight="bold"
                fontFamily="monospace"
                textAnchor="middle"
                dominantBaseline="middle"
                transform={textTransform}
              >
                {segment.text}
              </text>
            );
          })}
        </g>

        {Array.from({ length: DOT_COUNT }).map((_, i) => {
          const angle = (i / DOT_COUNT) * 360 + (rotation * (i % 2 === 0 ? 2 : -2));
          const radius = 170 + (activityLevel * 20) + (isActive ? Math.sin(Date.now() / 500 + i) * 10 : 0);
          const x = 200 + radius * Math.cos(angle * Math.PI / 180);
          const y = 200 + radius * Math.sin(angle * Math.PI / 180);
          const dotKey = 'dot-' + i;

          return (
            <circle
              key={dotKey}
              cx={x}
              cy={y}
              r={(isActive || typingLevel > 0) ? 3 : 2}
              fill={colorTheme.hex}
              opacity={0.6 + (activityLevel * 0.4)}
              filter="url(#glow)"
            />
          );
        })}

        {activeOpacity && (
          <g opacity={0.2 + (activityLevel * 0.3)}>
            {Array.from({ length: 8 }).map((_, i) => {
              const angle = (i / 8) * 360 + rotation;
              const x1 = 200 + 100 * Math.cos(angle * Math.PI / 180);
              const y1 = 200 + 100 * Math.sin(angle * Math.PI / 180);
              const x2 = 200 + 170 * Math.cos(angle * Math.PI / 180);
              const y2 = 200 + 170 * Math.sin(angle * Math.PI / 180);
              const lineKey = 'line-' + i;
              
              return (
                <line 
                  key={lineKey}
                  x1={x1} y1={y1} 
                  x2={x2} y2={y2} 
                  stroke={colorTheme.hex} 
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
              );
            })}
          </g>
        )}
      </svg>
    </div>
  );
}