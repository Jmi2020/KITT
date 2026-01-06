import { useState, useCallback, memo } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Copy, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface CodeBlockProps {
  /** The code content to display */
  code: string;
  /** Programming language for syntax highlighting */
  language?: string;
  /** Optional filename to show in header */
  filename?: string;
  /** Whether to show line numbers (default: true for >3 lines) */
  showLineNumbers?: boolean;
  /** Whether the copy button is enabled (default: true) */
  copyEnabled?: boolean;
  /** Maximum height before scrolling (default: 400px) */
  maxHeight?: number | string;
  /** Optional className */
  className?: string;
}

// Custom theme based on oneDark but matching KITTY's glassmorphism
const kittyTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: 'transparent',
    margin: 0,
    padding: '1rem',
    fontSize: '0.875rem',
    lineHeight: '1.6',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
  },
};

/**
 * CodeBlock component provides syntax-highlighted code display with copy functionality.
 */
export const CodeBlock = memo(function CodeBlock({
  code,
  language = 'text',
  filename,
  showLineNumbers,
  copyEnabled = true,
  maxHeight = 400,
  className,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  // Auto-detect if line numbers should be shown
  const lineCount = code.split('\n').length;
  const shouldShowLineNumbers = showLineNumbers ?? lineCount > 3;

  const handleCopy = useCallback(async () => {
    if (!copyEnabled) return;

    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy code:', err);
    }
  }, [code, copyEnabled]);

  // Normalize language name for display
  const displayLanguage = language.toLowerCase();
  const languageLabel = displayLanguage === 'text' ? '' : displayLanguage;

  return (
    <div
      className={cn(
        'relative group rounded-lg overflow-hidden',
        'border border-white/10',
        'bg-[#0a0e1a]/90 backdrop-blur-md',
        className
      )}
    >
      {/* Header bar */}
      <div
        className={cn(
          'flex items-center justify-between px-4 py-2',
          'bg-gradient-to-r from-primary/10 to-secondary/5',
          'border-b border-white/10'
        )}
      >
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Terminal size={14} className="text-primary/70" />
          <span className="font-mono">
            {filename || languageLabel || 'code'}
          </span>
        </div>

        {copyEnabled && (
          <motion.button
            onClick={handleCopy}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              'hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-ring/50',
              'text-muted-foreground hover:text-foreground'
            )}
            whileTap={{ scale: 0.95 }}
            aria-label={copied ? 'Copied!' : 'Copy code'}
          >
            <AnimatePresence mode="wait">
              {copied ? (
                <motion.div
                  key="check"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <Check size={14} className="text-green-400" />
                </motion.div>
              ) : (
                <motion.div
                  key="copy"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ duration: 0.15 }}
                >
                  <Copy size={14} />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        )}
      </div>

      {/* Code content */}
      <div
        className="overflow-auto"
        style={{ maxHeight: typeof maxHeight === 'number' ? `${maxHeight}px` : maxHeight }}
      >
        <SyntaxHighlighter
          language={displayLanguage}
          style={kittyTheme}
          showLineNumbers={shouldShowLineNumbers}
          lineNumberStyle={{
            minWidth: '2.5em',
            paddingRight: '1em',
            color: 'hsl(var(--muted-foreground))',
            opacity: 0.5,
            userSelect: 'none',
          }}
          customStyle={{
            margin: 0,
            background: 'transparent',
          }}
          codeTagProps={{
            style: {
              fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', monospace",
            },
          }}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  );
});

export default CodeBlock;
