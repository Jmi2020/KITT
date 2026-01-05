import { useCallback, useEffect, useRef, useState } from 'react';

const API_BASE = '/api/suggest';

/**
 * Suggestion context types matching backend contexts.
 */
export type SuggestionContext = 'chat' | 'coding' | 'cad' | 'image' | 'research';

/**
 * A single prompt suggestion.
 */
export interface PromptSuggestion {
  text: string;
  reason: string;
}

/**
 * Options for the usePromptSuggestion hook.
 */
export interface UsePromptSuggestionOptions {
  /** The context type for suggestions */
  context: SuggestionContext;
  /** Optional field identifier for analytics */
  fieldId?: string;
  /** Whether suggestions are enabled (default: true) */
  enabled?: boolean;
  /** Debounce delay in ms (default: 300) */
  debounceMs?: number;
  /** Minimum input length before fetching (default: 10) */
  minLength?: number;
  /** Maximum suggestions to return (default: 3) */
  maxSuggestions?: number;
}

/**
 * Return type for the usePromptSuggestion hook.
 */
export interface UsePromptSuggestionResult {
  /** Current suggestions */
  suggestions: PromptSuggestion[];
  /** Whether suggestions are loading */
  isLoading: boolean;
  /** Error message if any */
  error: string | null;
  /** Manually trigger suggestion fetch */
  fetchSuggestions: (input: string) => void;
  /** Clear current suggestions */
  clearSuggestions: () => void;
  /** Accept a suggestion and return its text */
  acceptSuggestion: (index: number) => string;
  /** Whether suggestions are visible/available */
  hasSuggestions: boolean;
}

/**
 * Hook for fetching context-aware prompt suggestions.
 *
 * Provides intelligent prompt enhancement suggestions as users type,
 * with debouncing, streaming support, and context-specific refinement.
 *
 * @example
 * ```tsx
 * const { suggestions, isLoading, fetchSuggestions, acceptSuggestion } = usePromptSuggestion({
 *   context: 'coding',
 *   debounceMs: 300,
 *   minLength: 10,
 * });
 *
 * // In input onChange:
 * fetchSuggestions(inputValue);
 *
 * // To accept:
 * setInputValue(acceptSuggestion(0));
 * ```
 */
export function usePromptSuggestion(
  options: UsePromptSuggestionOptions
): UsePromptSuggestionResult {
  const {
    context,
    fieldId = '',
    enabled = true,
    debounceMs = 300,
    minLength = 10,
    maxSuggestions = 3,
  } = options;

  const [suggestions, setSuggestions] = useState<PromptSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Refs for cleanup and debouncing
  const abortControllerRef = useRef<AbortController | null>(null);
  const debounceTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const lastInputRef = useRef<string>('');

  /**
   * Clear any pending requests and timeouts.
   */
  const cleanup = useCallback(() => {
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
      debounceTimeoutRef.current = null;
    }
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  /**
   * Fetch suggestions from the API (streaming).
   */
  const doFetch = useCallback(async (input: string) => {
    // Cancel any existing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    setSuggestions([]);

    try {
      const response = await fetch(`${API_BASE}/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          input,
          context,
          field_id: fieldId,
          max_suggestions: maxSuggestions,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      const newSuggestions: PromptSuggestion[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'suggestion') {
                const suggestion: PromptSuggestion = {
                  text: event.text || '',
                  reason: event.reason || '',
                };
                newSuggestions.push(suggestion);
                // Update state progressively
                setSuggestions([...newSuggestions]);
              } else if (event.type === 'error') {
                throw new Error(event.error || 'Unknown error');
              }
            } catch (parseErr) {
              // Ignore JSON parse errors for incomplete chunks
              if (parseErr instanceof SyntaxError) continue;
              throw parseErr;
            }
          }
        }
      }

      setIsLoading(false);
    } catch (err) {
      // Don't treat abort as an error
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      setIsLoading(false);
    }
  }, [context, fieldId, maxSuggestions]);

  /**
   * Debounced fetch for suggestions.
   */
  const fetchSuggestions = useCallback((input: string) => {
    // Store the latest input
    lastInputRef.current = input;

    // Clear previous timeout
    if (debounceTimeoutRef.current) {
      clearTimeout(debounceTimeoutRef.current);
    }

    // Check if we should fetch
    if (!enabled) {
      return;
    }

    if (input.length < minLength) {
      setSuggestions([]);
      setIsLoading(false);
      return;
    }

    // Set loading immediately for UX
    setIsLoading(true);

    // Debounce the actual fetch
    debounceTimeoutRef.current = setTimeout(() => {
      // Verify input hasn't changed during debounce
      if (lastInputRef.current === input) {
        doFetch(input);
      }
    }, debounceMs);
  }, [enabled, minLength, debounceMs, doFetch]);

  /**
   * Clear all suggestions.
   */
  const clearSuggestions = useCallback(() => {
    cleanup();
    setSuggestions([]);
    setError(null);
    setIsLoading(false);
  }, [cleanup]);

  /**
   * Accept a suggestion and return its text.
   */
  const acceptSuggestion = useCallback((index: number): string => {
    const suggestion = suggestions[index];
    if (suggestion) {
      clearSuggestions();
      return suggestion.text;
    }
    return '';
  }, [suggestions, clearSuggestions]);

  return {
    suggestions,
    isLoading,
    error,
    fetchSuggestions,
    clearSuggestions,
    acceptSuggestion,
    hasSuggestions: suggestions.length > 0,
  };
}

export default usePromptSuggestion;
