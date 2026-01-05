import React, { useEffect, useRef, useCallback } from 'react';
import { PromptSuggestion } from '../../hooks/usePromptSuggestion';
import './SuggestionPopup.css';

export interface SuggestionPopupProps {
  /** List of suggestions to display */
  suggestions: PromptSuggestion[];
  /** Whether suggestions are currently loading */
  isLoading: boolean;
  /** Whether the popup should be visible */
  isVisible: boolean;
  /** Currently selected suggestion index */
  selectedIndex: number;
  /** Callback when a suggestion is selected */
  onSelect: (index: number) => void;
  /** Callback when the popup is dismissed */
  onDismiss: () => void;
  /** Callback to update selected index */
  onSelectedIndexChange: (index: number) => void;
  /** Reference to the anchor element for positioning */
  anchorRef: React.RefObject<HTMLElement>;
  /** Position relative to anchor (default: 'below') */
  position?: 'above' | 'below';
  /** Optional className for styling */
  className?: string;
}

/**
 * Floating popup component for displaying prompt suggestions.
 *
 * Features:
 * - Keyboard navigation (arrow keys, Enter, Escape)
 * - Click to select
 * - Loading state
 * - Automatic positioning near anchor element
 */
export function SuggestionPopup({
  suggestions,
  isLoading,
  isVisible,
  selectedIndex,
  onSelect,
  onDismiss,
  onSelectedIndexChange,
  anchorRef,
  position = 'below',
  className = '',
}: SuggestionPopupProps): JSX.Element | null {
  const popupRef = useRef<HTMLDivElement>(null);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (!isVisible) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        onSelectedIndexChange(
          Math.min(selectedIndex + 1, suggestions.length - 1)
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        onSelectedIndexChange(Math.max(selectedIndex - 1, 0));
        break;
      case 'Tab':
        // Tab accepts the suggestion
        if (suggestions.length > 0) {
          e.preventDefault();
          onSelect(selectedIndex);
        }
        break;
      case 'Enter':
        // Ctrl/Cmd+Enter accepts and potentially submits
        if ((e.ctrlKey || e.metaKey) && suggestions.length > 0) {
          e.preventDefault();
          onSelect(selectedIndex);
        }
        break;
      case 'Escape':
        e.preventDefault();
        onDismiss();
        break;
    }
  }, [isVisible, selectedIndex, suggestions.length, onSelect, onDismiss, onSelectedIndexChange]);

  // Add keyboard listener
  useEffect(() => {
    if (isVisible) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isVisible, handleKeyDown]);

  // Handle click outside to dismiss
  useEffect(() => {
    if (!isVisible) return;

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        popupRef.current &&
        !popupRef.current.contains(target) &&
        anchorRef.current &&
        !anchorRef.current.contains(target)
      ) {
        onDismiss();
      }
    };

    // Delay to prevent immediate dismiss on open
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isVisible, onDismiss, anchorRef]);

  // Scroll selected item into view
  useEffect(() => {
    if (popupRef.current && isVisible) {
      const selectedEl = popupRef.current.querySelector('.suggestion-item.selected');
      if (selectedEl) {
        selectedEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedIndex, isVisible]);

  // Don't render if not visible
  if (!isVisible && !isLoading) {
    return null;
  }

  // Show loading state or empty state
  if (isLoading && suggestions.length === 0) {
    return (
      <div
        ref={popupRef}
        className={`suggestion-popup ${position} loading ${className}`}
        role="listbox"
        aria-busy="true"
      >
        <div className="suggestion-loading">
          <span className="suggestion-spinner"></span>
          <span>Generating suggestions...</span>
        </div>
      </div>
    );
  }

  // Don't show empty popup
  if (suggestions.length === 0) {
    return null;
  }

  return (
    <div
      ref={popupRef}
      className={`suggestion-popup ${position} ${className}`}
      role="listbox"
      aria-label="Prompt suggestions"
    >
      {suggestions.map((suggestion, index) => (
        <div
          key={index}
          className={`suggestion-item ${index === selectedIndex ? 'selected' : ''}`}
          role="option"
          aria-selected={index === selectedIndex}
          onClick={() => onSelect(index)}
          onMouseEnter={() => onSelectedIndexChange(index)}
        >
          <div className="suggestion-text">{suggestion.text}</div>
          {suggestion.reason && (
            <div className="suggestion-reason">{suggestion.reason}</div>
          )}
        </div>
      ))}

      <div className="suggestion-footer">
        <span className="suggestion-hint">
          <kbd>Tab</kbd> to accept
          <span className="hint-separator">|</span>
          <kbd>Esc</kbd> to dismiss
        </span>
        {isLoading && (
          <span className="suggestion-more">
            <span className="suggestion-spinner small"></span>
          </span>
        )}
      </div>
    </div>
  );
}

export default SuggestionPopup;
