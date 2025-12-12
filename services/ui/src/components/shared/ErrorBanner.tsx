/**
 * Shared ErrorBanner Component
 * Error display with optional retry action
 */

import React from 'react';
import './shared.css';

export type ErrorSeverity = 'error' | 'warning' | 'info';

export interface ErrorBannerProps {
  /** Error message to display */
  message: string;
  /** Error severity level */
  severity?: ErrorSeverity;
  /** Optional retry callback */
  onRetry?: () => void;
  /** Optional dismiss callback */
  onDismiss?: () => void;
  /** Retry button text */
  retryText?: string;
  /** Optional CSS class */
  className?: string;
  /** Optional title */
  title?: string;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({
  message,
  severity = 'error',
  onRetry,
  onDismiss,
  retryText = 'Retry',
  className = '',
  title,
}) => {
  const icon = severity === 'error' ? '❌' : severity === 'warning' ? '⚠️' : 'ℹ️';

  return (
    <div
      className={`error-banner error-${severity} ${className}`.trim()}
      role="alert"
      aria-live="assertive"
    >
      <div className="error-content">
        <span className="error-icon" aria-hidden="true">
          {icon}
        </span>
        <div className="error-text">
          {title && <strong className="error-title">{title}</strong>}
          <span className="error-message">{message}</span>
        </div>
      </div>
      <div className="error-actions">
        {onRetry && (
          <button className="btn-retry" onClick={onRetry}>
            {retryText}
          </button>
        )}
        {onDismiss && (
          <button
            className="btn-dismiss"
            onClick={onDismiss}
            aria-label="Dismiss error"
          >
            ×
          </button>
        )}
      </div>
    </div>
  );
};

export default ErrorBanner;
