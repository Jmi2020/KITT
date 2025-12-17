interface InputLevelMeterProps {
  /** Audio level from 0 to 1 */
  level: number;
  /** Whether the meter is active/visible */
  active?: boolean;
  /** Compact mode for mobile */
  compact?: boolean;
}

/**
 * Visual indicator for microphone input level.
 * Shows a horizontal bar that fills based on audio level.
 */
export function InputLevelMeter({ level, active = true, compact = false }: InputLevelMeterProps) {
  if (!active) return null;

  const bars = compact ? 8 : 12;
  const height = compact ? 'h-3' : 'h-4';

  return (
    <div className="flex items-center gap-2">
      <div className={`flex gap-0.5 ${height}`}>
        {Array.from({ length: bars }).map((_, i) => {
          const threshold = (i + 1) / bars;
          const isActive = level >= threshold;
          const isHigh = threshold > 0.7;
          const isMedium = threshold > 0.4;

          let colorClass = 'bg-gray-700';
          if (isActive) {
            if (isHigh) {
              colorClass = 'bg-red-500';
            } else if (isMedium) {
              colorClass = 'bg-yellow-500';
            } else {
              colorClass = 'bg-cyan-500';
            }
          }

          return (
            <div
              key={i}
              className={`${compact ? 'w-1.5' : 'w-2'} rounded-sm transition-colors duration-75 ${colorClass}`}
            />
          );
        })}
      </div>

      {!compact && (
        <span className="text-xs text-gray-500 w-8 text-right">
          {Math.round(level * 100)}%
        </span>
      )}
    </div>
  );
}

export default InputLevelMeter;
