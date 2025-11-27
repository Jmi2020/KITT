import { memo, useEffect, useState } from 'react';

interface StreamingIndicatorProps {
  /** Whether streaming is active */
  isStreaming: boolean;
  /** Label text (default: "Generating") */
  label?: string;
  /** Compact mode */
  compact?: boolean;
  /** Show elapsed time */
  showTime?: boolean;
}

/**
 * Animated indicator for LLM streaming/generation.
 * Shows pulsing dots and optional elapsed time.
 */
export const StreamingIndicator = memo(function StreamingIndicator({
  isStreaming,
  label = 'Generating',
  compact = false,
  showTime = true,
}: StreamingIndicatorProps) {
  const [elapsed, setElapsed] = useState(0);
  const [dotCount, setDotCount] = useState(0);

  // Elapsed time counter
  useEffect(() => {
    if (!isStreaming) {
      setElapsed(0);
      return;
    }

    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [isStreaming]);

  // Animated dots
  useEffect(() => {
    if (!isStreaming) {
      setDotCount(0);
      return;
    }

    const interval = setInterval(() => {
      setDotCount((prev) => (prev + 1) % 4);
    }, 400);

    return () => clearInterval(interval);
  }, [isStreaming]);

  if (!isStreaming) return null;

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const dots = '.'.repeat(dotCount);

  return (
    <div
      className={`inline-flex items-center gap-2 ${
        compact ? 'text-xs' : 'text-sm'
      }`}
    >
      {/* Pulsing indicator */}
      <div className="flex items-center gap-1">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
        </span>
      </div>

      {/* Label with animated dots */}
      <span className="text-cyan-400 font-medium">
        {label}
        <span className="inline-block w-6 text-left">{dots}</span>
      </span>

      {/* Elapsed time */}
      {showTime && elapsed > 0 && (
        <span className="text-gray-500 tabular-nums">
          {formatTime(elapsed)}
        </span>
      )}
    </div>
  );
});

/**
 * Typing indicator with bouncing dots.
 */
export const TypingIndicator = memo(function TypingIndicator({
  compact = false,
}: {
  compact?: boolean;
}) {
  return (
    <div className={`flex items-center gap-1 ${compact ? 'py-1' : 'py-2'}`}>
      <span
        className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"
        style={{ animationDelay: '0ms' }}
      />
      <span
        className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"
        style={{ animationDelay: '150ms' }}
      />
      <span
        className="w-2 h-2 bg-cyan-400 rounded-full animate-bounce"
        style={{ animationDelay: '300ms' }}
      />
    </div>
  );
});

export default StreamingIndicator;
