/**
 * StepContainer - Wrapper component for workflow steps
 *
 * Provides consistent styling and disabled/locked states for each step.
 * Supports expanded/collapsed states and status indicators.
 */

import { ReactNode, useState } from 'react';
import './StepContainer.css';

export interface StepContainerProps {
  /** Step number (1-4) */
  stepNumber: number;
  /** Step title */
  title: string;
  /** Optional subtitle or status text */
  subtitle?: string;
  /** Content to render inside the step */
  children: ReactNode;
  /** Whether the step is currently active */
  isActive?: boolean;
  /** Whether the step is completed */
  isCompleted?: boolean;
  /** Whether the step is locked (prerequisites not met) */
  isLocked?: boolean;
  /** Whether the step is loading */
  isLoading?: boolean;
  /** Optional error message to display */
  error?: string | null;
  /** Whether the step is collapsible (default: true when completed) */
  collapsible?: boolean;
  /** Initial collapsed state */
  defaultCollapsed?: boolean;
  /** Optional icon to show next to title */
  icon?: ReactNode;
  /** Optional action button in header */
  headerAction?: ReactNode;
  /** Optional tooltip/help text */
  helpText?: string;
}

export function StepContainer({
  stepNumber,
  title,
  subtitle,
  children,
  isActive = false,
  isCompleted = false,
  isLocked = false,
  isLoading = false,
  error,
  collapsible = false,
  defaultCollapsed = false,
  icon,
  headerAction,
  helpText,
}: StepContainerProps) {
  const [isCollapsed, setIsCollapsed] = useState(defaultCollapsed);

  const shouldCollapse = collapsible && isCollapsed && !isActive;

  const getStatusIcon = () => {
    if (isLoading) {
      return (
        <svg className="step-container__status-icon step-container__spinner" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" fill="none" strokeWidth="3" strokeDasharray="32" strokeLinecap="round" />
        </svg>
      );
    }
    if (error) {
      return (
        <svg className="step-container__status-icon step-container__status-icon--error" viewBox="0 0 16 16">
          <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 3.5a.75.75 0 011.5 0v4a.75.75 0 01-1.5 0v-4zm.75 7.5a1 1 0 100-2 1 1 0 000 2z" />
        </svg>
      );
    }
    if (isCompleted) {
      return (
        <svg className="step-container__status-icon step-container__status-icon--success" viewBox="0 0 16 16">
          <path d="M13.78 4.22a.75.75 0 010 1.06l-7.25 7.25a.75.75 0 01-1.06 0L2.22 9.28a.75.75 0 111.06-1.06L6 10.94l6.72-6.72a.75.75 0 011.06 0z" />
        </svg>
      );
    }
    if (isLocked) {
      return (
        <svg className="step-container__status-icon step-container__status-icon--locked" viewBox="0 0 16 16">
          <path d="M4 5V4a4 4 0 118 0v1h1a1 1 0 011 1v8a1 1 0 01-1 1H3a1 1 0 01-1-1V6a1 1 0 011-1h1zm2-1v1h4V4a2 2 0 10-4 0z" />
        </svg>
      );
    }
    return null;
  };

  return (
    <section
      className={`step-container ${isActive ? 'step-container--active' : ''} ${isCompleted ? 'step-container--completed' : ''} ${isLocked ? 'step-container--locked' : ''} ${isLoading ? 'step-container--loading' : ''} ${error ? 'step-container--error' : ''} ${shouldCollapse ? 'step-container--collapsed' : ''}`}
      aria-labelledby={`step-${stepNumber}-title`}
      aria-disabled={isLocked}
    >
      <header className="step-container__header">
        <div className="step-container__title-row">
          <div className="step-container__title-group">
            <span className="step-container__step-badge">Step {stepNumber}</span>
            {icon && <span className="step-container__icon">{icon}</span>}
            <h2 id={`step-${stepNumber}-title`} className="step-container__title">
              {title}
            </h2>
            {getStatusIcon()}
            {helpText && (
              <span className="step-container__help" title={helpText}>
                <svg viewBox="0 0 16 16" className="step-container__help-icon">
                  <path d="M8 0a8 8 0 100 16A8 8 0 008 0zm1 12H7V7h2v5zM8 6a1 1 0 110-2 1 1 0 010 2z" />
                </svg>
              </span>
            )}
          </div>

          <div className="step-container__actions">
            {headerAction}
            {collapsible && !isLocked && (
              <button
                type="button"
                className="step-container__collapse-btn"
                onClick={() => setIsCollapsed(!isCollapsed)}
                aria-expanded={!isCollapsed}
                aria-label={isCollapsed ? 'Expand step' : 'Collapse step'}
              >
                <svg viewBox="0 0 16 16" className={`step-container__chevron ${isCollapsed ? 'step-container__chevron--collapsed' : ''}`}>
                  <path d="M4.22 6.22a.75.75 0 011.06 0L8 8.94l2.72-2.72a.75.75 0 111.06 1.06l-3.25 3.25a.75.75 0 01-1.06 0L4.22 7.28a.75.75 0 010-1.06z" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {subtitle && (
          <p className="step-container__subtitle">{subtitle}</p>
        )}
      </header>

      {!shouldCollapse && (
        <div className="step-container__content">
          {error && (
            <div className="step-container__error-message" role="alert">
              <svg viewBox="0 0 16 16" className="step-container__error-icon">
                <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 3.5a.75.75 0 011.5 0v4a.75.75 0 01-1.5 0v-4zm.75 7.5a1 1 0 100-2 1 1 0 000 2z" />
              </svg>
              {error}
            </div>
          )}
          {children}
        </div>
      )}

      {isLocked && (
        <div className="step-container__locked-overlay" aria-hidden="true">
          <span>Complete previous steps to unlock</span>
        </div>
      )}
    </section>
  );
}

export default StepContainer;
