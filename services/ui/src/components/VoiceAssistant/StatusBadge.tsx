import { memo } from 'react';
import { getModeById } from '../../types/voiceModes';

export type VoiceStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'listening'
  | 'responding'
  | 'error';

interface StatusBadgeProps {
  status: VoiceStatus;
  /** Is currently reconnecting */
  isReconnecting?: boolean;
  /** Reconnect attempt count */
  reconnectAttempts?: number;
  /** Compact display */
  compact?: boolean;
}

const STATUS_CONFIG: Record<VoiceStatus, {
  label: string;
  color: string;
  bg: string;
  border: string;
  pulse?: boolean;
  glow?: string;
}> = {
  disconnected: {
    label: 'OFFLINE',
    color: 'text-gray-400',
    bg: 'bg-gray-900/40',
    border: 'border-gray-700/50',
    glow: '',
  },
  connecting: {
    label: 'CONNECTING',
    color: 'text-yellow-400',
    bg: 'bg-yellow-900/20',
    border: 'border-yellow-500/30',
    pulse: true,
    glow: 'shadow-[0_0_10px_rgba(250,204,21,0.2)]',
  },
  connected: {
    label: 'SYSTEM READY',
    color: 'text-green-400',
    bg: 'bg-green-900/20',
    border: 'border-green-500/30',
    glow: 'shadow-[0_0_10px_rgba(74,222,128,0.2)]',
  },
  listening: {
    label: 'LISTENING',
    color: 'text-cyan-400',
    bg: 'bg-cyan-900/20',
    border: 'border-cyan-500/30',
    pulse: true,
    glow: 'shadow-[0_0_15px_rgba(34,211,238,0.3)]',
  },
  responding: {
    label: 'PROCESSING',
    color: 'text-purple-400',
    bg: 'bg-purple-900/20',
    border: 'border-purple-500/30',
    pulse: true,
    glow: 'shadow-[0_0_15px_rgba(168,85,247,0.3)]',
  },
  error: {
    label: 'SYSTEM ERROR',
    color: 'text-red-400',
    bg: 'bg-red-900/20',
    border: 'border-red-500/30',
    glow: 'shadow-[0_0_10px_rgba(248,113,113,0.2)]',
  },
};

/**
 * Visual status badge showing connection/activity state.
 * Features color-coded indicators with optional animations.
 */
export const StatusBadge = memo(function StatusBadge({
  status,
  isReconnecting = false,
  reconnectAttempts = 0,
  compact = false,
}: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];

  // Override for reconnecting state
  const displayLabel = isReconnecting
    ? `RETRYING${reconnectAttempts > 0 ? ` (${reconnectAttempts})` : ''}`
    : config.label;

  const displayConfig = isReconnecting
    ? STATUS_CONFIG.connecting
    : config;

  return (
    <div
      className={`inline-flex items-center gap-2 ${
        compact ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1 text-xs'
      } rounded-full ${displayConfig.bg} ${displayConfig.border} border backdrop-blur-sm transition-all duration-300 ${displayConfig.glow}`}
    >
      {/* Status indicator dot */}
      <span className="relative flex h-2 w-2">
        {displayConfig.pulse && (
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${displayConfig.color} opacity-75 animate-ping`}
          />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${displayConfig.color} bg-current`} />
      </span>

      {/* Label */}
      <span className={`${displayConfig.color} font-bold tracking-wider font-mono`}>
        {displayLabel}
      </span>
    </div>
  );
});

/**
 * Horizontal status bar with multiple indicators.
 */
interface StatusBarProps {
  status: VoiceStatus;
  isReconnecting?: boolean;
  reconnectAttempts?: number;
  tier?: string;
  preferLocal?: boolean;
  compact?: boolean;
  /** Current voice mode ID */
  mode?: string;
}

export const StatusBar = memo(function StatusBar({
  status,
  isReconnecting,
  reconnectAttempts,
  tier,
  preferLocal,
  compact = false,
  mode = 'basic',
}: StatusBarProps) {
  const modeConfig = getModeById(mode);

  return (
    <div className={`flex items-center justify-center gap-3 flex-wrap ${compact ? 'text-xs' : 'text-sm'}`}>
      {/* Main status */}
      <StatusBadge
        status={status}
        isReconnecting={isReconnecting}
        reconnectAttempts={reconnectAttempts}
        compact={compact}
      />

      {/* Mode indicator */}
      {modeConfig && status !== 'disconnected' && (
        <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full ${modeConfig.bgClass} ${modeConfig.borderClass} border backdrop-blur-sm transition-all duration-300`}>
          <span className="text-sm leading-none">{modeConfig.icon}</span>
          {!compact && (
            <span className="font-bold text-white/90 text-xs tracking-wide uppercase">{modeConfig.name}</span>
          )}
        </div>
      )}

      {/* Tier indicator */}
      {tier && status !== 'disconnected' && (
        <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full ${
          preferLocal
            ? 'bg-cyan-900/20 border-cyan-500/30 text-cyan-400'
            : 'bg-purple-900/20 border-purple-500/30 text-purple-400'
        } border backdrop-blur-sm transition-all duration-300`}>
          <span className="text-xs">
            {preferLocal ? '🏠' : '☁️'}
          </span>
          <span className="font-bold text-xs tracking-wide uppercase">{tier}</span>
        </div>
      )}
    </div>
  );
});

export default StatusBadge;