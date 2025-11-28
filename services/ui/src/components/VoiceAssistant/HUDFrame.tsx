import { ReactNode } from 'react';

interface HUDFrameProps {
  children: ReactNode;
  /** Color theme: cyan, orange, purple, green, pink, red, gray */
  color?: string;
  /** Show corner brackets */
  corners?: boolean;
  /** Show scan line effect */
  scanLine?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Glow intensity: none, subtle, medium, intense */
  glow?: 'none' | 'subtle' | 'medium' | 'intense';
  /** Animation state: idle, active, pulse, alert */
  state?: 'idle' | 'active' | 'pulse' | 'alert';
}

const COLOR_CLASSES = {
  cyan: {
    border: 'border-cyan-500/50',
    bg: 'bg-cyan-500/5',
    corner: 'border-cyan-500/70',
    glow: 'shadow-cyan-500/30',
    text: 'text-cyan-400',
  },
  orange: {
    border: 'border-orange-500/50',
    bg: 'bg-orange-500/5',
    corner: 'border-orange-500/70',
    glow: 'shadow-orange-500/30',
    text: 'text-orange-400',
  },
  purple: {
    border: 'border-purple-500/50',
    bg: 'bg-purple-500/5',
    corner: 'border-purple-500/70',
    glow: 'shadow-purple-500/30',
    text: 'text-purple-400',
  },
  green: {
    border: 'border-green-500/50',
    bg: 'bg-green-500/5',
    corner: 'border-green-500/70',
    glow: 'shadow-green-500/30',
    text: 'text-green-400',
  },
  pink: {
    border: 'border-pink-500/50',
    bg: 'bg-pink-500/5',
    corner: 'border-pink-500/70',
    glow: 'shadow-pink-500/30',
    text: 'text-pink-400',
  },
  red: {
    border: 'border-red-500/50',
    bg: 'bg-red-500/5',
    corner: 'border-red-500/70',
    glow: 'shadow-red-500/30',
    text: 'text-red-400',
  },
  gray: {
    border: 'border-gray-500/50',
    bg: 'bg-gray-500/5',
    corner: 'border-gray-500/70',
    glow: 'shadow-gray-500/30',
    text: 'text-gray-400',
  },
};

const GLOW_CLASSES = {
  none: '',
  subtle: 'shadow-md',
  medium: 'shadow-lg',
  intense: 'shadow-xl',
};

/**
 * Sci-Fi HUD-style frame component with corner brackets and optional effects.
 * Used for consistent cyberpunk/sci-fi dashboard aesthetic.
 */
export function HUDFrame({
  children,
  color = 'cyan',
  corners = true,
  scanLine = false,
  className = '',
  glow = 'none',
  state = 'idle',
}: HUDFrameProps) {
  const colors = COLOR_CLASSES[color as keyof typeof COLOR_CLASSES] || COLOR_CLASSES.cyan;
  const glowClass = glow !== 'none' ? `${GLOW_CLASSES[glow]} ${colors.glow}` : '';

  const stateClasses = {
    idle: '',
    active: 'ring-2 ring-current ring-opacity-30',
    pulse: 'animate-pulse',
    alert: 'animate-[pulse_0.5s_ease-in-out_infinite]',
  };

  return (
    <div
      className={`relative border ${colors.border} ${colors.bg} rounded-lg ${glowClass} ${stateClasses[state]} ${className}`}
    >
      {/* Corner brackets */}
      {corners && (
        <>
          <div className={`absolute -top-px -left-px w-3 h-3 border-l-2 border-t-2 ${colors.corner} rounded-tl-lg`} />
          <div className={`absolute -top-px -right-px w-3 h-3 border-r-2 border-t-2 ${colors.corner} rounded-tr-lg`} />
          <div className={`absolute -bottom-px -left-px w-3 h-3 border-l-2 border-b-2 ${colors.corner} rounded-bl-lg`} />
          <div className={`absolute -bottom-px -right-px w-3 h-3 border-r-2 border-b-2 ${colors.corner} rounded-br-lg`} />
        </>
      )}

      {/* Scan line effect */}
      {scanLine && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-lg">
          <div
            className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-current to-transparent opacity-30 animate-[scanLine_3s_linear_infinite]"
            style={{
              animation: 'scanLine 3s linear infinite',
            }}
          />
        </div>
      )}

      {/* Content */}
      <div className="relative z-10">{children}</div>
    </div>
  );
}

/**
 * Small HUD accent indicator dot.
 */
interface HUDIndicatorProps {
  active?: boolean;
  color?: string;
  pulse?: boolean;
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export function HUDIndicator({
  active = true,
  color = 'cyan',
  pulse = false,
  size = 'sm',
  label,
}: HUDIndicatorProps) {
  const colors = COLOR_CLASSES[color as keyof typeof COLOR_CLASSES] || COLOR_CLASSES.cyan;

  const sizes = {
    sm: 'w-2 h-2',
    md: 'w-3 h-3',
    lg: 'w-4 h-4',
  };

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative">
        <div
          className={`${sizes[size]} rounded-full ${
            active ? `bg-current ${colors.text}` : 'bg-gray-600'
          } ${pulse && active ? 'animate-pulse' : ''}`}
        />
        {active && pulse && (
          <div
            className={`absolute inset-0 ${sizes[size]} rounded-full bg-current ${colors.text} animate-ping opacity-75`}
          />
        )}
      </div>
      {label && (
        <span className={`text-xs ${active ? colors.text : 'text-gray-500'}`}>
          {label}
        </span>
      )}
    </div>
  );
}

/**
 * HUD-style label with decorative elements.
 */
interface HUDLabelProps {
  children: ReactNode;
  color?: string;
  icon?: string;
  uppercase?: boolean;
}

export function HUDLabel({
  children,
  color = 'cyan',
  icon,
  uppercase = true,
}: HUDLabelProps) {
  const colors = COLOR_CLASSES[color as keyof typeof COLOR_CLASSES] || COLOR_CLASSES.cyan;

  return (
    <div className={`flex items-center gap-2 ${colors.text}`}>
      {icon && <span>{icon}</span>}
      <span
        className={`text-xs font-semibold tracking-wider ${
          uppercase ? 'uppercase' : ''
        }`}
      >
        {children}
      </span>
      <div className="flex-1 h-px bg-gradient-to-r from-current to-transparent opacity-30" />
    </div>
  );
}

/**
 * HUD-style divider line.
 */
interface HUDDividerProps {
  color?: string;
  accent?: boolean;
}

export function HUDDivider({ color = 'cyan', accent = false }: HUDDividerProps) {
  const colors = COLOR_CLASSES[color as keyof typeof COLOR_CLASSES] || COLOR_CLASSES.cyan;

  return (
    <div className="relative py-2">
      <div className={`h-px ${accent ? 'bg-current' : 'bg-gray-700'} ${colors.text} opacity-30`} />
      {accent && (
        <>
          <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 h-1 ${colors.text} bg-current rounded-full`} />
          <div className={`absolute right-0 top-1/2 -translate-y-1/2 w-1 h-1 ${colors.text} bg-current rounded-full`} />
        </>
      )}
    </div>
  );
}
