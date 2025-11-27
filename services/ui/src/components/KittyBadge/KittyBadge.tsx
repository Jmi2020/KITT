import { useCallback, useEffect, useState } from 'react';
import './KittyBadge.css';

interface KittyBadgeProps {
  /** Size in pixels (default: 100) */
  size?: number;
  /** Whether to randomly reposition on interval */
  wandering?: boolean;
  /** Interval in ms for wandering (default: 30000 = 30s) */
  wanderInterval?: number;
  /** Pause wandering (e.g., during active conversation) */
  paused?: boolean;
  /** Click handler */
  onClick?: () => void;
}

type Corner = 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left' | 'mid-right' | 'mid-left';

const CORNERS: Corner[] = ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'mid-right', 'mid-left'];

/**
 * Floating neon KITTY badge with spinning rings and cat face.
 * Randomly repositions on click or on interval.
 */
export function KittyBadge({
  size = 100,
  wandering = true,
  wanderInterval = 30000,
  paused = false,
  onClick,
}: KittyBadgeProps) {
  const [corner, setCorner] = useState<Corner>('bottom-right');
  const [isHovered, setIsHovered] = useState(false);

  // Random corner selection
  const moveToRandomCorner = useCallback(() => {
    const availableCorners = CORNERS.filter(c => c !== corner);
    const randomIndex = Math.floor(Math.random() * availableCorners.length);
    setCorner(availableCorners[randomIndex]);
  }, [corner]);

  // Handle click
  const handleClick = useCallback(() => {
    moveToRandomCorner();
    onClick?.();
  }, [moveToRandomCorner, onClick]);

  // Wandering interval
  useEffect(() => {
    if (!wandering || paused) return;

    const interval = setInterval(() => {
      if (!isHovered && !paused) {
        moveToRandomCorner();
      }
    }, wanderInterval);

    return () => clearInterval(interval);
  }, [wandering, wanderInterval, isHovered, paused, moveToRandomCorner]);

  // Corner position styles
  const getPositionStyle = (): React.CSSProperties => {
    const offset = '20px';
    switch (corner) {
      case 'bottom-right':
        return { bottom: offset, right: offset, top: 'auto', left: 'auto' };
      case 'bottom-left':
        return { bottom: offset, left: offset, top: 'auto', right: 'auto' };
      case 'top-right':
        return { top: offset, right: offset, bottom: 'auto', left: 'auto' };
      case 'top-left':
        return { top: offset, left: offset, bottom: 'auto', right: 'auto' };
      case 'mid-right':
        return { top: '50%', right: offset, bottom: 'auto', left: 'auto', transform: 'translateY(-50%)' };
      case 'mid-left':
        return { top: '50%', left: offset, bottom: 'auto', right: 'auto', transform: 'translateY(-50%)' };
      default:
        return { bottom: offset, right: offset };
    }
  };

  return (
    <div
      className={`kitty-badge-wrapper ${isHovered ? 'hovered' : ''}`}
      style={{ width: size, height: size, ...getPositionStyle() }}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title="Click to move KITTY"
    >
      <svg className="kitty-svg" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="kitty-neon-grad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00f3ff" stopOpacity="1" />
            <stop offset="50%" stopColor="#00d4ff" stopOpacity="1" />
            <stop offset="100%" stopColor="#00f3ff" stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* Rotating outer rings */}
        <g className="rotating-assembly">
          <circle className="neon-ring thick-ring" cx="60" cy="60" r="56" />
          <circle className="neon-ring dashed-ring-1" cx="60" cy="60" r="52" />
          {/* Circuit bits on outer ring */}
          <g className="circuit-bits neon-ring">
            <line x1="60" y1="2" x2="60" y2="8" />
            <line x1="60" y1="112" x2="60" y2="118" />
            <line x1="2" y1="60" x2="8" y2="60" />
            <line x1="112" y1="60" x2="118" y2="60" />
          </g>
        </g>

        {/* Counter-rotating inner ring */}
        <g className="counter-rotate">
          <circle className="neon-ring dashed-ring-2" cx="60" cy="60" r="46" />
        </g>

        {/* Static inner boundary */}
        <circle className="neon-ring inner-boundary" cx="60" cy="60" r="38" />

        {/* Cat face group */}
        <g className="cat-group">
          {/* Cat ears */}
          <path className="cat-path ears" d="M 35 42 L 42 28 L 48 40" />
          <path className="cat-path ears" d="M 85 42 L 78 28 L 72 40" />

          {/* Cat head outline */}
          <ellipse className="cat-path" cx="60" cy="52" rx="22" ry="18" />

          {/* Cat eyes */}
          <ellipse className="cat-path" cx="50" cy="50" rx="4" ry="5" />
          <ellipse className="cat-path" cx="70" cy="50" rx="4" ry="5" />

          {/* Cat nose */}
          <path className="cat-path" d="M 58 56 L 60 59 L 62 56" />

          {/* Cat whiskers */}
          <g className="cat-path whiskers">
            <line x1="38" y1="54" x2="28" y2="52" />
            <line x1="38" y1="58" x2="28" y2="60" />
            <line x1="82" y1="54" x2="92" y2="52" />
            <line x1="82" y1="58" x2="92" y2="60" />
          </g>
        </g>

        {/* KITTY text at bottom */}
        <text className="kitty-text" x="60" y="90">KITTY</text>
      </svg>
    </div>
  );
}

export default KittyBadge;
