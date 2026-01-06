import { memo } from 'react';
import { motion } from 'framer-motion';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export interface MessageSkeletonProps {
  /** Number of content lines to show */
  lines?: number;
  /** Whether to show metadata badges */
  showMetadata?: boolean;
  /** Whether to show the avatar/icon placeholder */
  showAvatar?: boolean;
  /** Optional className for the container */
  className?: string;
}

/**
 * MessageSkeleton provides a loading placeholder for chat messages.
 * Matches the KITTY Shell message layout with shimmer animation.
 */
export const MessageSkeleton = memo(function MessageSkeleton({
  lines = 3,
  showMetadata = true,
  showAvatar = false,
  className,
}: MessageSkeletonProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className={cn('flex gap-3 p-4', className)}
    >
      {/* Avatar placeholder */}
      {showAvatar && (
        <Skeleton className="w-8 h-8 rounded-full flex-shrink-0 bg-primary/10" />
      )}

      {/* Content area */}
      <div className="flex-1 space-y-3">
        {/* Header line (shorter) */}
        <Skeleton className="h-4 w-24 bg-primary/10" />

        {/* Content lines with stagger */}
        <div className="space-y-2">
          {Array.from({ length: lines }).map((_, i) => (
            <Skeleton
              key={i}
              className={cn(
                'h-4 bg-primary/10',
                // Last line is shorter for natural appearance
                i === lines - 1 ? 'w-3/4' : 'w-full'
              )}
              style={{
                animationDelay: `${i * 0.1}s`,
              }}
            />
          ))}
        </div>

        {/* Metadata badges */}
        {showMetadata && (
          <div className="flex gap-2 pt-1">
            <Skeleton className="h-5 w-16 rounded-full bg-primary/10" />
            <Skeleton className="h-5 w-20 rounded-full bg-primary/10" />
          </div>
        )}
      </div>
    </motion.div>
  );
});

export interface CodeSkeletonProps {
  /** Number of code lines to show */
  lines?: number;
  /** Whether to show the header bar */
  showHeader?: boolean;
  /** Optional className */
  className?: string;
}

/**
 * CodeSkeleton provides a loading placeholder for code blocks.
 */
export const CodeSkeleton = memo(function CodeSkeleton({
  lines = 5,
  showHeader = true,
  className,
}: CodeSkeletonProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className={cn(
        'rounded-lg overflow-hidden border border-white/10',
        'bg-[#0a0e1a]/90 backdrop-blur-md',
        className
      )}
    >
      {/* Header bar */}
      {showHeader && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Skeleton className="w-4 h-4 rounded bg-primary/20" />
            <Skeleton className="w-16 h-4 rounded bg-primary/10" />
          </div>
          <Skeleton className="w-6 h-6 rounded bg-primary/10" />
        </div>
      )}

      {/* Code lines */}
      <div className="p-4 space-y-2">
        {Array.from({ length: lines }).map((_, i) => {
          // Randomize line widths for code-like appearance
          const widths = ['w-full', 'w-4/5', 'w-3/5', 'w-2/3', 'w-5/6'];
          const width = widths[i % widths.length];

          return (
            <div key={i} className="flex items-center gap-3">
              {/* Line number */}
              <Skeleton className="w-6 h-4 bg-primary/5 flex-shrink-0" />
              {/* Code line */}
              <Skeleton
                className={cn('h-4 bg-primary/10', width)}
                style={{ animationDelay: `${i * 0.05}s` }}
              />
            </div>
          );
        })}
      </div>
    </motion.div>
  );
});

export default MessageSkeleton;
