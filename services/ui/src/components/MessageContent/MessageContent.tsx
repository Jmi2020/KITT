import { memo, useMemo } from 'react';
import { StreamingText } from '@/components/StreamingText';
import { CodeBlock } from '@/components/CodeBlock';
import { cn } from '@/lib/utils';

export interface MessageContentProps {
  /** The message content to parse and render */
  content: string;
  /** Whether the content is still being streamed */
  isStreaming?: boolean;
  /** Optional className for the container */
  className?: string;
}

interface ContentSegment {
  type: 'text' | 'code';
  content: string;
  language?: string;
  filename?: string;
}

/**
 * Parse content into segments of text and code blocks.
 * Handles fenced code blocks with optional language and filename.
 */
function parseContent(content: string): ContentSegment[] {
  const segments: ContentSegment[] = [];

  // Regex to match fenced code blocks: ```language:filename or ```language or ```
  const codeBlockRegex = /```(\w+)?(?::([^\n]+))?\n([\s\S]*?)```/g;

  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before this code block
    if (match.index > lastIndex) {
      const textContent = content.slice(lastIndex, match.index);
      if (textContent.trim()) {
        segments.push({ type: 'text', content: textContent });
      }
    }

    // Add the code block
    segments.push({
      type: 'code',
      content: match[3].trim(),
      language: match[1] || 'text',
      filename: match[2],
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text after last code block
  if (lastIndex < content.length) {
    const textContent = content.slice(lastIndex);
    if (textContent.trim()) {
      segments.push({ type: 'text', content: textContent });
    }
  }

  // If no segments, the entire content is text
  if (segments.length === 0 && content.trim()) {
    segments.push({ type: 'text', content });
  }

  return segments;
}

/**
 * MessageContent component parses message content and renders:
 * - Text segments with StreamingText (when streaming)
 * - Code blocks with syntax highlighting
 */
export const MessageContent = memo(function MessageContent({
  content,
  isStreaming = false,
  className,
}: MessageContentProps) {
  const segments = useMemo(() => parseContent(content), [content]);

  // If streaming with only text (no code blocks yet), use StreamingText
  if (isStreaming && segments.length <= 1 && segments[0]?.type === 'text') {
    return (
      <div className={cn('prose prose-invert max-w-none', className)}>
        <StreamingText
          content={content}
          isStreaming={isStreaming}
          showCursor={true}
        />
      </div>
    );
  }

  return (
    <div className={cn('space-y-4', className)}>
      {segments.map((segment, index) => {
        if (segment.type === 'code') {
          return (
            <CodeBlock
              key={`code-${index}`}
              code={segment.content}
              language={segment.language}
              filename={segment.filename}
            />
          );
        }

        // Text segment
        const isLastSegment = index === segments.length - 1;
        const shouldStream = isStreaming && isLastSegment;

        return (
          <div
            key={`text-${index}`}
            className="prose prose-invert max-w-none whitespace-pre-wrap"
          >
            {shouldStream ? (
              <StreamingText
                content={segment.content}
                isStreaming={isStreaming}
                showCursor={true}
              />
            ) : (
              segment.content
            )}
          </div>
        );
      })}
    </div>
  );
});

export default MessageContent;
