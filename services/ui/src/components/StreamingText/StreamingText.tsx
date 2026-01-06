import { memo, useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

export interface StreamingTextProps {
  /** The full content to display (can grow during streaming) */
  content: string;
  /** Whether content is still being streamed */
  isStreaming: boolean;
  /** Characters to reveal per animation frame (default: 3) */
  charsPerFrame?: number;
  /** Whether to show the blinking cursor */
  showCursor?: boolean;
  /** Custom cursor character (default: '▌') */
  cursorChar?: string;
  /** Callback when streaming animation catches up to content */
  onCatchUp?: () => void;
  /** Optional className for the container */
  className?: string;
}

/**
 * StreamingText component provides smooth, buffered text streaming animation.
 * Uses requestAnimationFrame for 60fps rendering with variable speed pacing.
 */
export const StreamingText = memo(function StreamingText({
  content,
  isStreaming,
  charsPerFrame = 3,
  showCursor = true,
  cursorChar = '▌',
  onCatchUp,
  className,
}: StreamingTextProps) {
  const [displayedLength, setDisplayedLength] = useState(0);
  const animationRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(0);
  const contentRef = useRef(content);

  // Track content changes
  useEffect(() => {
    contentRef.current = content;
  }, [content]);

  // Animation loop using requestAnimationFrame
  const animate = useCallback((timestamp: number) => {
    // Throttle to ~60fps (16ms between frames)
    if (timestamp - lastTimeRef.current < 16) {
      animationRef.current = requestAnimationFrame(animate);
      return;
    }
    lastTimeRef.current = timestamp;

    setDisplayedLength((prev) => {
      const currentContent = contentRef.current;
      if (prev >= currentContent.length) {
        // Caught up with content
        if (onCatchUp) onCatchUp();
        return prev;
      }

      // Variable speed: pause slightly at punctuation for natural pacing
      const nextChar = currentContent[prev];
      const isPunctuation = /[.!?,;:\n]/.test(nextChar);
      const step = isPunctuation ? 1 : charsPerFrame;

      return Math.min(prev + step, currentContent.length);
    });

    animationRef.current = requestAnimationFrame(animate);
  }, [charsPerFrame, onCatchUp]);

  // Start/stop animation based on streaming state
  useEffect(() => {
    if (isStreaming || displayedLength < content.length) {
      animationRef.current = requestAnimationFrame(animate);
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, [isStreaming, animate, displayedLength, content.length]);

  // When not streaming and content is complete, show full content immediately
  useEffect(() => {
    if (!isStreaming && displayedLength === 0 && content.length > 0) {
      // If we just got content and we're not streaming, show it all
      setDisplayedLength(content.length);
    }
  }, [isStreaming, content.length, displayedLength]);

  // Reset displayed length when content is cleared
  useEffect(() => {
    if (content.length === 0) {
      setDisplayedLength(0);
    }
  }, [content.length]);

  const displayedContent = content.slice(0, displayedLength);
  const isCaughtUp = displayedLength >= content.length;
  const shouldShowCursor = showCursor && isStreaming;

  return (
    <div className={cn('relative whitespace-pre-wrap', className)}>
      {displayedContent}
      <AnimatePresence>
        {shouldShowCursor && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="inline-block ml-0.5"
            style={{
              animation: isCaughtUp ? 'cursorBlink 1s ease-in-out infinite' : 'none',
            }}
          >
            {cursorChar}
          </motion.span>
        )}
      </AnimatePresence>
    </div>
  );
});

export default StreamingText;
