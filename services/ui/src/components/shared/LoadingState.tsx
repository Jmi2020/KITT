/**
 * Shared LoadingState Component
 * Loading spinner with optional message
 */

import React from 'react';
import './shared.css';

export type LoadingSize = 'small' | 'medium' | 'large';

export interface LoadingStateProps {
  /** Loading message to display */
  message?: string;
  /** Size of the spinner */
  size?: LoadingSize;
  /** Whether to show as overlay */
  overlay?: boolean;
  /** Optional CSS class */
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = 'Loading...',
  size = 'medium',
  overlay = false,
  className = '',
}) => {
  const content = (
    <div className={`loading-state loading-${size} ${className}`.trim()}>
      <div className="loading-spinner" aria-hidden="true">
        <div className="spinner"></div>
      </div>
      {message && <span className="loading-message">{message}</span>}
    </div>
  );

  if (overlay) {
    return (
      <div className="loading-overlay" role="status" aria-live="polite">
        {content}
      </div>
    );
  }

  return (
    <div role="status" aria-live="polite">
      {content}
    </div>
  );
};

export default LoadingState;
