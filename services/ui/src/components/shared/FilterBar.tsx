/**
 * Shared FilterBar Component
 * Search input with filter controls
 */

import React from 'react';
import './shared.css';

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterConfig {
  /** Unique identifier for the filter */
  id: string;
  /** Display label */
  label: string;
  /** Available options */
  options: FilterOption[];
  /** Current selected value */
  value: string;
  /** Change handler */
  onChange: (value: string) => void;
}

export interface FilterBarProps {
  /** Search input value */
  searchValue?: string;
  /** Search input change handler */
  onSearchChange?: (value: string) => void;
  /** Search input placeholder */
  searchPlaceholder?: string;
  /** Filter configurations */
  filters?: FilterConfig[];
  /** Toggle filters (checkbox style) */
  toggles?: Array<{
    id: string;
    label: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
  }>;
  /** Optional CSS class */
  className?: string;
  /** Children for additional custom controls */
  children?: React.ReactNode;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  filters = [],
  toggles = [],
  className = '',
  children,
}) => {
  return (
    <div className={`filter-bar ${className}`.trim()}>
      {onSearchChange && (
        <div className="filter-search">
          <input
            type="text"
            value={searchValue || ''}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            className="search-input"
          />
        </div>
      )}

      {filters.map((filter) => (
        <div key={filter.id} className="filter-group">
          <label htmlFor={filter.id}>{filter.label}</label>
          <select
            id={filter.id}
            value={filter.value}
            onChange={(e) => filter.onChange(e.target.value)}
            className="filter-select"
          >
            {filter.options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      ))}

      {toggles.map((toggle) => (
        <label key={toggle.id} className="filter-toggle">
          <input
            type="checkbox"
            checked={toggle.checked}
            onChange={(e) => toggle.onChange(e.target.checked)}
          />
          <span>{toggle.label}</span>
        </label>
      ))}

      {children}
    </div>
  );
};

export default FilterBar;
