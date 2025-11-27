import { memo, useState } from 'react';

export type ToolStatus = 'pending' | 'running' | 'completed' | 'error';

export interface ToolExecution {
  id: string;
  name: string;
  displayName?: string;
  args?: Record<string, unknown>;
  result?: string;
  error?: string;
  status: ToolStatus;
  startedAt?: Date;
  completedAt?: Date;
}

interface ToolExecutionCardProps {
  tool: ToolExecution;
  /** Compact display mode */
  compact?: boolean;
  /** Show arguments */
  showArgs?: boolean;
  /** Show result/error details */
  showDetails?: boolean;
}

const STATUS_CONFIG = {
  pending: {
    icon: '○',
    color: 'text-gray-400',
    bg: 'bg-gray-500/10',
    border: 'border-gray-500/30',
    label: 'Pending',
  },
  running: {
    icon: '◐',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    label: 'Running',
  },
  completed: {
    icon: '●',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    label: 'Complete',
  },
  error: {
    icon: '✕',
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    label: 'Error',
  },
};

const TOOL_ICONS: Record<string, string> = {
  // Home automation
  'lights': '💡',
  'thermostat': '🌡️',
  'lock': '🔒',
  'camera': '📷',
  'speaker': '🔊',
  'tv': '📺',
  // 3D printing
  'print': '🖨️',
  'printer': '🖨️',
  'filament': '🧵',
  'bed': '🛏️',
  // CAD
  'model': '📐',
  'design': '✏️',
  'export': '📤',
  // System
  'weather': '🌤️',
  'search': '🔍',
  'timer': '⏱️',
  'reminder': '🔔',
  'calendar': '📅',
  // Default
  'default': '⚙️',
};

function getToolIcon(toolName: string): string {
  const lowerName = toolName.toLowerCase();
  for (const [key, icon] of Object.entries(TOOL_ICONS)) {
    if (lowerName.includes(key)) {
      return icon;
    }
  }
  return TOOL_ICONS.default;
}

function formatDuration(start: Date, end?: Date): string {
  const endTime = end || new Date();
  const ms = endTime.getTime() - start.getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

/**
 * Card component for displaying tool execution status.
 * Shows tool name, status, arguments, and results.
 */
export const ToolExecutionCard = memo(function ToolExecutionCard({
  tool,
  compact = false,
  showArgs = false,
  showDetails = true,
}: ToolExecutionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = STATUS_CONFIG[tool.status];
  const icon = getToolIcon(tool.name);

  return (
    <div
      className={`rounded-lg border transition-all ${config.bg} ${config.border} ${
        compact ? 'p-2' : 'p-3'
      } ${showDetails && !compact ? 'cursor-pointer hover:border-opacity-60' : ''}`}
      onClick={() => showDetails && !compact && setIsExpanded(!isExpanded)}
    >
      {/* Header row */}
      <div className="flex items-center gap-2">
        {/* Tool icon */}
        <span className={compact ? 'text-base' : 'text-lg'}>{icon}</span>

        {/* Tool name */}
        <span className={`font-mono ${config.color} ${compact ? 'text-xs' : 'text-sm'} flex-1 truncate`}>
          {tool.displayName || tool.name}
        </span>

        {/* Status indicator */}
        <div className="flex items-center gap-1.5">
          {tool.status === 'running' && (
            <span className={`${config.color} animate-spin text-xs`}>◌</span>
          )}
          <span className={`${config.color} ${compact ? 'text-xs' : 'text-sm'}`}>
            {config.icon}
          </span>
          {!compact && (
            <span className={`text-xs ${config.color}`}>{config.label}</span>
          )}
        </div>
      </div>

      {/* Progress bar for running tools */}
      {tool.status === 'running' && (
        <div className="mt-2 h-1 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-yellow-400 via-cyan-400 to-yellow-400 rounded-full animate-progress"
            style={{
              width: '40%',
              animation: 'progressIndeterminate 1.5s ease-in-out infinite',
            }}
          />
          <style>{`
            @keyframes progressIndeterminate {
              0% { transform: translateX(-100%); }
              100% { transform: translateX(350%); }
            }
          `}</style>
        </div>
      )}

      {/* Duration */}
      {tool.startedAt && (
        <div className={`mt-1 text-xs text-gray-500 ${compact ? 'hidden' : ''}`}>
          {tool.status === 'running' ? (
            <span className="animate-pulse">
              Running for {formatDuration(tool.startedAt)}
            </span>
          ) : tool.completedAt ? (
            <span>Completed in {formatDuration(tool.startedAt, tool.completedAt)}</span>
          ) : null}
        </div>
      )}

      {/* Arguments (when showArgs and expanded) */}
      {showArgs && isExpanded && tool.args && Object.keys(tool.args).length > 0 && (
        <div className="mt-2 p-2 bg-gray-800/50 rounded text-xs font-mono">
          <div className="text-gray-400 mb-1">Arguments:</div>
          <pre className="text-gray-300 whitespace-pre-wrap overflow-x-auto">
            {JSON.stringify(tool.args, null, 2)}
          </pre>
        </div>
      )}

      {/* Result (when expanded and completed) */}
      {showDetails && isExpanded && tool.status === 'completed' && tool.result && (
        <div className="mt-2 p-2 bg-green-900/20 rounded text-xs">
          <div className="text-green-400 mb-1">Result:</div>
          <div className="text-gray-300 whitespace-pre-wrap">{tool.result}</div>
        </div>
      )}

      {/* Error (when expanded and error) */}
      {showDetails && isExpanded && tool.status === 'error' && tool.error && (
        <div className="mt-2 p-2 bg-red-900/20 rounded text-xs">
          <div className="text-red-400 mb-1">Error:</div>
          <div className="text-red-300 whitespace-pre-wrap">{tool.error}</div>
        </div>
      )}

      {/* Expand indicator */}
      {showDetails && !compact && (tool.result || tool.error || (showArgs && tool.args)) && (
        <div className="mt-1 text-xs text-gray-500 text-center">
          {isExpanded ? '▲ Collapse' : '▼ Expand'}
        </div>
      )}
    </div>
  );
});

/**
 * List of tool executions with status summary.
 */
interface ToolExecutionListProps {
  tools: ToolExecution[];
  compact?: boolean;
  maxVisible?: number;
}

export const ToolExecutionList = memo(function ToolExecutionList({
  tools,
  compact = false,
  maxVisible = 5,
}: ToolExecutionListProps) {
  const [showAll, setShowAll] = useState(false);

  if (tools.length === 0) return null;

  const visibleTools = showAll ? tools : tools.slice(0, maxVisible);
  const hiddenCount = tools.length - maxVisible;

  // Status summary
  const statusCounts = tools.reduce(
    (acc, tool) => {
      acc[tool.status]++;
      return acc;
    },
    { pending: 0, running: 0, completed: 0, error: 0 }
  );

  return (
    <div className="space-y-2">
      {/* Status summary */}
      {tools.length > 1 && (
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>Tools: {tools.length}</span>
          {statusCounts.running > 0 && (
            <span className="text-yellow-400">
              {statusCounts.running} running
            </span>
          )}
          {statusCounts.completed > 0 && (
            <span className="text-green-400">
              {statusCounts.completed} done
            </span>
          )}
          {statusCounts.error > 0 && (
            <span className="text-red-400">
              {statusCounts.error} failed
            </span>
          )}
        </div>
      )}

      {/* Tool cards */}
      <div className={compact ? 'space-y-1' : 'space-y-2'}>
        {visibleTools.map((tool) => (
          <ToolExecutionCard key={tool.id} tool={tool} compact={compact} />
        ))}
      </div>

      {/* Show more/less */}
      {hiddenCount > 0 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full py-1 text-xs text-gray-400 hover:text-cyan-400 transition-colors"
        >
          {showAll ? 'Show less' : `Show ${hiddenCount} more`}
        </button>
      )}
    </div>
  );
});

export default ToolExecutionCard;
