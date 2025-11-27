import { memo } from 'react';

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
  icon: string;
  color: string;
  bg: string;
  border: string;
  pulse?: boolean;
}> = {
  disconnected: {
    label: 'Offline',
    icon: '○',
    color: 'text-gray-400',
    bg: 'bg-gray-500/10',
    border: 'border-gray-500/30',
  },
  connecting: {
    label: 'Connecting',
    icon: '◐',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    pulse: true,
  },
  connected: {
    label: 'Ready',
    icon: '●',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
  },
  listening: {
    label: 'Listening',
    icon: '◉',
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
    pulse: true,
  },
  responding: {
    label: 'Thinking',
    icon: '◎',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
    pulse: true,
  },
  error: {
    label: 'Error',
    icon: '✕',
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
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
    ? `Reconnecting${reconnectAttempts > 0 ? ` (${reconnectAttempts})` : ''}`
    : config.label;

  const displayConfig = isReconnecting
    ? STATUS_CONFIG.connecting
    : config;

  return (
    <div
      className={`inline-flex items-center gap-1.5 ${
        compact ? 'px-2 py-0.5 text-xs' : 'px-3 py-1 text-sm'
      } rounded-full ${displayConfig.bg} ${displayConfig.border} border transition-all`}
    >
      {/* Status indicator */}
      <span className="relative flex items-center justify-center">
        {displayConfig.pulse && (
          <span
            className={`absolute inline-flex h-full w-full rounded-full ${displayConfig.color} opacity-50 animate-ping`}
            style={{ animationDuration: '1.5s' }}
          />
        )}
        <span className={`${displayConfig.color} ${compact ? 'text-xs' : 'text-sm'}`}>
          {displayConfig.icon}
        </span>
      </span>

      {/* Label */}
      <span className={`${displayConfig.color} font-medium`}>
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
}

export const StatusBar = memo(function StatusBar({
  status,
  isReconnecting,
  reconnectAttempts,
  tier,
  preferLocal,
  compact = false,
}: StatusBarProps) {
  return (
    <div className={`flex items-center justify-center gap-2 flex-wrap ${compact ? 'text-xs' : 'text-sm'}`}>
      {/* Main status */}
      <StatusBadge
        status={status}
        isReconnecting={isReconnecting}
        reconnectAttempts={reconnectAttempts}
        compact={compact}
      />

      {/* Tier indicator */}
      {tier && status !== 'disconnected' && (
        <div className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${
          preferLocal
            ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400'
            : 'bg-purple-500/10 border-purple-500/30 text-purple-400'
        } border`}>
          <span className="text-xs">
            {preferLocal ? '🏠' : '☁️'}
          </span>
          <span className="font-medium capitalize">{tier}</span>
        </div>
      )}
    </div>
  );
});

export default StatusBadge;
