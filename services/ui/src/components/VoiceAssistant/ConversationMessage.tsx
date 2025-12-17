import { memo } from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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
  const timestamp =
    message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp);
  const hasValidTime = !Number.isNaN(timestamp?.getTime?.());

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

  // Extract image URLs from content if any (simple regex for basic image detection)
  const imageUrlMatch = message.content.match(/(https?:\/\/.*\.(?:png|jpg|jpeg|gif|webp))/i);
  const imageUrl = imageUrlMatch ? imageUrlMatch[0] : null;
  // Clean content if image is standalone (optional, keeping it simple for now)

  return (
    <div className={`${compact ? 'p-2' : 'p-4'} rounded-lg border ${containerClass} transition-all duration-300 animate-in fade-in slide-in-from-bottom-2`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] font-bold uppercase tracking-wider ${labelClass}`}>{label}</span>
        {message.tier && (
          <span className="text-[9px] px-1.5 py-0.5 bg-cyan-500/20 border border-cyan-500/30 rounded text-cyan-300 font-mono">
            {message.tier}
          </span>
        )}
        {!compact && hasValidTime && (
          <span className="text-[10px] text-gray-600 ml-auto font-mono">
            {timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      <div className={`markdown-content text-sm leading-relaxed ${message.isStreaming ? 'streaming' : ''}`}>
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            img: ({ node, ...props }) => (
              <div className="my-2 rounded-lg overflow-hidden border border-gray-700 bg-black/50">
                <img {...props} className="max-w-full h-auto" loading="lazy" />
              </div>
            ),
            p: ({ node, ...props }) => <p {...props} className="mb-2 last:mb-0" />,
            a: ({ node, ...props }) => <a {...props} className="text-cyan-400 hover:text-cyan-300 underline decoration-cyan-500/30" target="_blank" rel="noopener noreferrer" />,
            code: ({ node, ...props }) => <code {...props} className="bg-black/30 px-1 py-0.5 rounded text-xs font-mono text-cyan-200" />,
            pre: ({ node, ...props }) => <pre {...props} className="bg-black/50 p-2 rounded-lg text-xs font-mono overflow-x-auto my-2 border border-gray-800" />,
            table: ({ node, ...props }) => (
              <div className="my-3 overflow-x-auto rounded-lg border border-gray-700">
                <table {...props} className="min-w-full text-xs" />
              </div>
            ),
            thead: ({ node, ...props }) => <thead {...props} className="bg-gray-800/80" />,
            tbody: ({ node, ...props }) => <tbody {...props} className="divide-y divide-gray-700/50" />,
            tr: ({ node, ...props }) => <tr {...props} className="hover:bg-gray-800/30 transition-colors" />,
            th: ({ node, ...props }) => <th {...props} className="px-3 py-2 text-left font-semibold text-cyan-300 border-b border-gray-600" />,
            td: ({ node, ...props }) => <td {...props} className="px-3 py-2 text-gray-300" />,
          }}
        >
          {message.content}
        </Markdown>
        
        {/* Render standalone detected image if not handled by markdown */}
        {imageUrl && !message.content.includes('![') && (
          <div className="mt-2 rounded-lg overflow-hidden border border-gray-700 bg-black/50">
            <img src={imageUrl} alt="Generated content" className="max-w-full h-auto" loading="lazy" />
          </div>
        )}

        {message.isStreaming && (
          <span className="inline-block w-1.5 h-4 ml-1 align-middle bg-cyan-400 animate-pulse" />
        )}
      </div>

      {/* Tool calls display */}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <div className="mt-3 space-y-1 border-t border-white/5 pt-2">
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
    pending: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
    running: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    completed: 'bg-green-500/10 text-green-400 border-green-500/20',
    error: 'bg-red-500/10 text-red-400 border-red-500/20',
  };

  const statusIcons = {
    pending: '○',
    running: '◌',
    completed: '●',
    error: '✕',
  };

  return (
    <div className={`${compact ? 'p-1.5' : 'p-2'} rounded border ${statusColors[tool.status]} text-xs`}>
      <div className="flex items-center gap-2">
        <span className={`text-[10px] ${tool.status === 'running' ? 'animate-spin' : ''}`}>{statusIcons[tool.status]}</span>
        <span className="font-mono font-bold tracking-tight">{tool.name}</span>
        {tool.status === 'running' && (
          <span className="text-[10px] animate-pulse opacity-70">Processing...</span>
        )}
      </div>
      {!compact && tool.result && (
        <div className="mt-1 pl-4 text-gray-500 font-mono truncate opacity-80 border-l border-white/10">
          {tool.result}
        </div>
      )}
    </div>
  );
}

export default ConversationMessage;
