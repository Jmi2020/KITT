import { memo } from 'react';
import Markdown from 'react-markdown';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  tier?: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
}

export interface ToolCall {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  result?: string;
  status: 'pending' | 'running' | 'completed' | 'error';
}

interface ConversationMessageProps {
  message: Message;
  compact?: boolean;
}

/**
 * Individual conversation message component.
 * Displays user/assistant messages with appropriate styling.
 */
export const ConversationMessage = memo(function ConversationMessage({
  message,
  compact = false,
}: ConversationMessageProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  const containerClass = isUser
    ? 'bg-gray-800/50 border-gray-700'
    : isSystem
    ? 'bg-yellow-900/20 border-yellow-500/30'
    : 'bg-cyan-900/20 border-cyan-500/30';

  const labelClass = isUser
    ? 'text-gray-400'
    : isSystem
    ? 'text-yellow-400'
    : 'text-cyan-400';

  const label = isUser ? 'You' : isSystem ? 'System' : 'KITTY';

  return (
    <div className={`${compact ? 'p-2' : 'p-4'} rounded-lg border ${containerClass}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-xs uppercase ${labelClass}`}>{label}</span>
        {message.tier && (
          <span className="text-xs px-2 py-0.5 bg-cyan-500/20 rounded-full text-cyan-300">
            {message.tier}
          </span>
        )}
        {!compact && (
          <span className="text-xs text-gray-600 ml-auto">
            {message.timestamp.toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className={`markdown-content ${message.isStreaming ? 'streaming' : ''}`}>
        <Markdown>{message.content}</Markdown>
        {message.isStreaming && (
          <span className="typing-cursor" />
        )}
      </div>

      {/* Tool calls display */}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <div className="mt-2 space-y-1">
          {message.toolCalls.map((tool) => (
            <ToolCallDisplay key={tool.id} tool={tool} compact={compact} />
          ))}
        </div>
      )}
    </div>
  );
});

interface ToolCallDisplayProps {
  tool: ToolCall;
  compact?: boolean;
}

function ToolCallDisplay({ tool, compact }: ToolCallDisplayProps) {
  const statusColors = {
    pending: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    running: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    completed: 'bg-green-500/20 text-green-400 border-green-500/30',
    error: 'bg-red-500/20 text-red-400 border-red-500/30',
  };

  const statusIcons = {
    pending: '○',
    running: '◐',
    completed: '●',
    error: '✕',
  };

  return (
    <div className={`${compact ? 'p-1.5' : 'p-2'} rounded border ${statusColors[tool.status]}`}>
      <div className="flex items-center gap-2">
        <span className="text-sm">{statusIcons[tool.status]}</span>
        <span className={`${compact ? 'text-xs' : 'text-sm'} font-mono`}>{tool.name}</span>
        {tool.status === 'running' && (
          <span className="text-xs animate-pulse">Running...</span>
        )}
      </div>
      {!compact && tool.result && (
        <div className="mt-1 text-xs text-gray-400 font-mono truncate">
          {tool.result}
        </div>
      )}
    </div>
  );
}

export default ConversationMessage;
