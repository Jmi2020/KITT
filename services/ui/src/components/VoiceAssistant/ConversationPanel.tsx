import { useEffect, useRef, memo } from 'react';
import { ConversationMessage, Message } from './ConversationMessage';

interface ConversationPanelProps {
  messages: Message[];
  /** Whether new message is being streamed */
  isStreaming?: boolean;
  /** Maximum height of the panel */
  maxHeight?: string;
  /** Compact mode for mobile */
  compact?: boolean;
  /** Show timestamps */
  showTimestamps?: boolean;
  /** Auto-scroll to bottom on new messages */
  autoScroll?: boolean;
}

/**
 * Scrollable conversation history panel.
 * Displays messages with auto-scroll to latest.
 */
export const ConversationPanel = memo(function ConversationPanel({
  messages,
  isStreaming = false,
  maxHeight = '400px',
  compact = false,
  autoScroll = true,
}: ConversationPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevMessagesLength = useRef(messages.length);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (!autoScroll) return;

    const shouldScroll =
      messages.length > prevMessagesLength.current || isStreaming;

    if (shouldScroll && scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }

    prevMessagesLength.current = messages.length;
  }, [messages, isStreaming, autoScroll]);

  if (messages.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-gray-500 text-sm"
        style={{ minHeight: '100px' }}
      >
        Start a conversation with KITTY
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="overflow-y-auto space-y-3 pr-2 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent"
      style={{ maxHeight }}
    >
      {messages.map((message, index) => (
        <ConversationMessage
          key={message.id || index}
          message={message}
          compact={compact}
        />
      ))}
    </div>
  );
});

export default ConversationPanel;
