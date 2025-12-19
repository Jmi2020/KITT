/**
 * ArtifactFilters - Filter and sort controls for artifacts
 */

import type { ArtifactStats, SortField, SortOrder, ArtifactTypeFilter } from '../types';

interface ArtifactFiltersProps {
  typeFilter: ArtifactTypeFilter;
  sortBy: SortField;
  sortOrder: SortOrder;
  stats: ArtifactStats | null;
  onTypeChange: (type: ArtifactTypeFilter) => void;
  onSortChange: (sort: SortField) => void;
  onOrderToggle: () => void;
  onRefresh: () => void;
  loading?: boolean;
}

export function ArtifactFilters({
  typeFilter,
  sortBy,
  sortOrder,
  stats,
  onTypeChange,
  onSortChange,
  onOrderToggle,
  onRefresh,
  loading = false,
}: ArtifactFiltersProps) {
  const getCount = (type: string): number => {
    if (!stats) return 0;
    return stats.byType[type] || 0;
  };

  return (
    <div className="artifact-filters">
      <div className="filter-group">
        <label htmlFor="type-filter">Type</label>
        <select
          id="type-filter"
          value={typeFilter}
          onChange={(e) => onTypeChange(e.target.value as ArtifactTypeFilter)}
        >
          <option value="all">All Types ({stats?.totalCount || 0})</option>
          <option value="stl">STL ({getCount('stl')})</option>
          <option value="glb">GLB ({getCount('glb')})</option>
          <option value="3mf">3MF ({getCount('3mf')})</option>
          <option value="gcode">G-Code ({getCount('gcode')})</option>
          <option value="step">STEP ({getCount('step')})</option>
          <option value="png">PNG ({getCount('png')})</option>
          <option value="jpg">JPG ({getCount('jpg')})</option>
        </select>
      </div>

      <div className="filter-group">
        <label htmlFor="sort-by">Sort By</label>
        <select
          id="sort-by"
          value={sortBy}
          onChange={(e) => onSortChange(e.target.value as SortField)}
        >
          <option value="date">Date Modified</option>
          <option value="name">Name</option>
          <option value="size">Size</option>
          <option value="type">Type</option>
        </select>
      </div>

      <button
        className="sort-order-toggle"
        onClick={onOrderToggle}
        title={sortOrder === 'desc' ? 'Descending (newest first)' : 'Ascending (oldest first)'}
      >
        {sortOrder === 'desc' ? '↓' : '↑'}
      </button>

      <button className="btn-refresh" onClick={onRefresh} disabled={loading}>
        {loading ? 'Loading...' : 'Refresh'}
      </button>
    </div>
  );
}

export default ArtifactFilters;
