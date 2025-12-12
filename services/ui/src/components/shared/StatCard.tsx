/**
 * Shared StatCard Component
 * Consistent statistic display card with label and value
 */

import React from 'react';
import './shared.css';

export type StatCardVariant = 'default' | 'success' | 'warning' | 'danger' | 'info';

export interface StatCardProps {
  /** Label describing the statistic */
  label: string;
  /** The statistic value to display */
  value: string | number;
  /** Optional icon to display */
  icon?: string;
  /** Visual variant for styling */
  variant?: StatCardVariant;
  /** Optional CSS class for additional styling */
  className?: string;
  /** Optional subtitle or description */
  subtitle?: string;
  /** Optional click handler */
  onClick?: () => void;
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  icon,
  variant = 'default',
  className = '',
  subtitle,
  onClick,
}) => {
  const variantClass = variant !== 'default' ? `stat-${variant}` : '';
  const clickableClass = onClick ? 'stat-clickable' : '';

  return (
    <div
      className={`stat-card ${variantClass} ${clickableClass} ${className}`.trim()}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      {icon && <span className="stat-icon">{icon}</span>}
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {subtitle && <span className="stat-subtitle">{subtitle}</span>}
    </div>
  );
};

export default StatCard;
