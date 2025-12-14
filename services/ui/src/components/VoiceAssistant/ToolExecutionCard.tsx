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
  'lights': '💡',
  'thermostat': '🌡️',
  'lock': '🔒',
  'camera': '📷',
  'speaker': '🔊',
  'tv': '📺',
  'print': '🖨️',
  'printer': '🖨️',
  'filament': '🧵',
  'bed': '🛏️',
  'model': '📐',
  'design': '✏️',
  'export': '📤',
  'weather': '🌤️',
  'search': '🔍',
  'timer': '⏱️',
  'reminder': '🔔',
  'calendar': '📅',
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
 * Timeline visualization of tool executions.
 */
const ToolTimeline = memo(function ToolTimeline({ tools }: { tools: ToolExecution[] }) {
  if (tools.length === 0) return null;

  // Find min start and max end to normalize timeline
  const startTimes = tools.map(t => t.startedAt?.getTime() || Date.now());
  const endTimes = tools.map(t => t.completedAt?.getTime() || Date.now());
  const minTime = Math.min(...startTimes);
  const maxTime = Math.max(...endTimes);
  const totalDuration = Math.max(maxTime - minTime, 1000); // Min 1s to avoid divide by zero

  return (
    <div className="space-y-2 mt-2">
      {tools.map((tool) => {
        const start = tool.startedAt?.getTime() || minTime;
        const end = tool.completedAt?.getTime() || Date.now();
        const duration = end - start;
        
        const leftPercent = ((start - minTime) / totalDuration) * 100;
        const widthPercent = Math.max(((duration / totalDuration) * 100), 1); // Min 1% width
        
        const statusColor = tool.status === 'error' ? 'bg-red-500' : 
                           tool.status === 'running' ? 'bg-yellow-400' : 'bg-green-500';

        return (
          <div key={tool.id} className="relative h-6 flex items-center group">
            <div className="w-24 text-[10px] text-gray-400 truncate pr-2 text-right">
              {tool.displayName || tool.name}
            </div>
            <div className="flex-1 h-full relative bg-gray-800/30 rounded overflow-hidden">
              {/* Timeline bar */}
              <div 
                className={`absolute top-1.5 bottom-1.5 rounded-sm ${statusColor} opacity-60 group-hover:opacity-100 transition-opacity`}
                style={{ 
                  left: `${leftPercent}%`, 
                  width: `${widthPercent}%`,
                  minWidth: '4px'
                }}
              />
              {/* Tooltip on hover */}
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 flex items-center justify-center pointer-events-none">
                <span className="text-[9px] bg-black/80 px-1 rounded text-white whitespace-nowrap">
                  {formatDuration(new Date(start), new Date(end))}
                </span>
              </div>
            </div>
          </div>
        );
      })}
      
      {/* Time axis */}
      <div className="flex justify-between text-[9px] text-gray-600 pl-24 pt-1 border-t border-white/5">
        <span>0s</span>
        <span>{(totalDuration / 1000).toFixed(1)}s</span>
      </div>
    </div>
  );
});

/**
 * Card component for displaying tool execution status.
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
 * List of tool executions with status summary and view toggle.
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
  const [viewMode, setViewMode] = useState<'list' | 'timeline'>('list');

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
      {/* Header with view toggle */}
      {tools.length > 1 && (
        <div className="flex items-center justify-between text-xs text-gray-400">
          <div className="flex items-center gap-2">
            <span>Tools: {tools.length}</span>
            {statusCounts.running > 0 && (
              <span className="text-yellow-400">{statusCounts.running} active</span>
            )}
          </div>
          
          {!compact && (
            <div className="flex bg-gray-800/50 rounded p-0.5">
              <button 
                onClick={() => setViewMode('list')}
                className={`px-2 py-0.5 rounded text-[10px] ${viewMode === 'list' ? 'bg-gray-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                List
              </button>
              <button 
                onClick={() => setViewMode('timeline')}
                className={`px-2 py-0.5 rounded text-[10px] ${viewMode === 'timeline' ? 'bg-gray-600 text-white' : 'text-gray-500 hover:text-gray-300'}`}
              >
                Timeline
              </button>
            </div>
          )}
        </div>
      )}

      {/* View Content */}
      {viewMode === 'timeline' ? (
        <ToolTimeline tools={tools} />
      ) : (
        <>
          <div className={compact ? 'space-y-1' : 'space-y-2'}>
            {visibleTools.map((tool) => (
              <ToolExecutionCard key={tool.id} tool={tool} compact={compact} />
            ))}
          </div>

          {hiddenCount > 0 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full py-1 text-xs text-gray-400 hover:text-cyan-400 transition-colors"
            >
              {showAll ? 'Show less' : `Show ${hiddenCount} more`}
            </button>
          )}
        </>
      )}
    </div>
  );
});

export default ToolExecutionCard;
