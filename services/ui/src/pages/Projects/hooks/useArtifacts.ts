/**
 * useArtifacts - Hook for fetching and managing artifact data
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import type {
  LocalArtifact,
  ArtifactStats,
  ProjectModel,
  UnifiedArtifact,
  SortField,
  SortOrder,
  ArtifactTypeFilter,
} from '../types';

interface UseArtifactsOptions {
  typeFilter: ArtifactTypeFilter;
  sortBy: SortField;
  sortOrder: SortOrder;
  pageSize?: number;
}

interface UseArtifactsReturn {
  // Local artifacts from filesystem
  localArtifacts: LocalArtifact[];
  localLoading: boolean;
  localError: string | null;

  // Database projects
  projects: ProjectModel[];
  projectsLoading: boolean;
  projectsError: string | null;

  // Stats
  stats: ArtifactStats | null;
  statsLoading: boolean;

  // Unified view with pagination
  unifiedArtifacts: UnifiedArtifact[];
  displayedArtifacts: UnifiedArtifact[];
  totalCount: number;
  displayedCount: number;
  hasMore: boolean;

  // Actions
  refresh: () => void;
  loadMore: () => void;
  loadMoreProjects: () => void;
  hasMoreProjects: boolean;
}

const DEFAULT_PAGE_SIZE = 24; // 4 rows of 6, or 6 rows of 4, or 8 rows of 3

export function useArtifacts(options: UseArtifactsOptions): UseArtifactsReturn {
  const { typeFilter, sortBy, sortOrder, pageSize = DEFAULT_PAGE_SIZE } = options;

  // Local artifacts state
  const [localArtifacts, setLocalArtifacts] = useState<LocalArtifact[]>([]);
  const [localLoading, setLocalLoading] = useState(true);
  const [localError, setLocalError] = useState<string | null>(null);

  // Stats state
  const [stats, setStats] = useState<ArtifactStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Database projects state
  const [projects, setProjects] = useState<ProjectModel[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState<string | null>(null);
  const [projectsOffset, setProjectsOffset] = useState(0);
  const [hasMoreProjects, setHasMoreProjects] = useState(false);

  // Pagination state for unified view
  const [displayLimit, setDisplayLimit] = useState(pageSize);

  const PAGE_SIZE = 20;

  // Fetch local artifacts
  const fetchLocalArtifacts = useCallback(async () => {
    setLocalLoading(true);
    setLocalError(null);

    try {
      const params = new URLSearchParams({
        sort: sortBy,
        order: sortOrder,
        limit: '500', // Max allowed by backend, paginate on frontend
      });

      if (typeFilter !== 'all') {
        params.set('type', typeFilter);
      }

      const response = await fetch(`/api/projects/artifacts?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`Failed to fetch artifacts (${response.status})`);
      }

      const data = await response.json();
      setLocalArtifacts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Local artifacts fetch error:', err);
      setLocalError((err as Error).message);
      setLocalArtifacts([]);
    } finally {
      setLocalLoading(false);
    }
  }, [typeFilter, sortBy, sortOrder]);

  // Fetch stats
  const fetchStats = useCallback(async () => {
    setStatsLoading(true);

    try {
      const response = await fetch('/api/projects/artifacts/stats');

      if (!response.ok) {
        throw new Error(`Failed to fetch stats (${response.status})`);
      }

      const data = await response.json();
      setStats(data);
    } catch (err) {
      console.error('Stats fetch error:', err);
      setStats(null);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Fetch database projects
  const fetchProjects = useCallback(
    async (reset: boolean = false) => {
      setProjectsLoading(true);
      setProjectsError(null);

      try {
        const offset = reset ? 0 : projectsOffset;
        const params = new URLSearchParams({
          limit: PAGE_SIZE.toString(),
          offset: offset.toString(),
        });

        if (typeFilter !== 'all') {
          params.set('artifactType', typeFilter);
        }

        const response = await fetch(`/api/projects?${params.toString()}`);

        if (!response.ok) {
          if (response.status === 404 || response.status === 502) {
            throw new Error('Projects API is not available');
          }
          throw new Error(`Failed to load projects (${response.status})`);
        }

        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
          throw new Error('Projects API returned invalid response');
        }

        const data = (await response.json()) as ProjectModel[];
        const list = Array.isArray(data) ? data : [];

        setProjects((prev) => (reset ? list : [...prev, ...list]));
        setHasMoreProjects(list.length === PAGE_SIZE);
        setProjectsOffset(offset + list.length);
      } catch (err) {
        console.error('Projects fetch error:', err);
        setProjectsError((err as Error).message);
        setHasMoreProjects(false);
      } finally {
        setProjectsLoading(false);
      }
    },
    [typeFilter, projectsOffset]
  );

  // Create unified view of all artifacts
  const unifiedArtifacts = useMemo(() => {
    const unified: UnifiedArtifact[] = [];

    // Add local artifacts
    localArtifacts.forEach((artifact) => {
      unified.push({
        id: `local-${artifact.artifactType}-${artifact.filename}`,
        source: 'filesystem',
        filename: artifact.filename,
        artifactType: artifact.artifactType,
        category: artifact.category,
        sizeBytes: artifact.sizeBytes,
        modifiedAt: artifact.modifiedAt,
        downloadUrl: artifact.downloadUrl,
        parentDir: artifact.parentDir,
      });
    });

    // Add database project artifacts
    projects.forEach((project) => {
      project.artifacts.forEach((artifact, idx) => {
        // Extract filename from location
        const filename = artifact.location.split('/').pop() || artifact.location;

        unified.push({
          id: `db-${project.projectId}-${idx}`,
          source: 'database',
          filename,
          artifactType: artifact.artifactType,
          category: getCategoryForType(artifact.artifactType),
          modifiedAt: project.updatedAt,
          downloadUrl: artifact.location,
          projectTitle: project.title || undefined,
          conversationId: project.conversationId,
          provider: artifact.provider,
          metadata: artifact.metadata,
        });
      });
    });

    // Sort unified list
    return sortUnifiedArtifacts(unified, sortBy, sortOrder);
  }, [localArtifacts, projects, sortBy, sortOrder]);

  // Paginated display
  const displayedArtifacts = useMemo(() => {
    return unifiedArtifacts.slice(0, displayLimit);
  }, [unifiedArtifacts, displayLimit]);

  const hasMore = displayLimit < unifiedArtifacts.length;
  const totalCount = unifiedArtifacts.length;
  const displayedCount = displayedArtifacts.length;

  // Load data on mount and when filters change
  useEffect(() => {
    fetchLocalArtifacts();
    fetchStats();
  }, [fetchLocalArtifacts, fetchStats]);

  useEffect(() => {
    setProjects([]);
    setProjectsOffset(0);
    fetchProjects(true);
  }, [typeFilter]);

  // Reset display limit when filters change
  useEffect(() => {
    setDisplayLimit(pageSize);
  }, [typeFilter, sortBy, sortOrder, pageSize]);

  const refresh = useCallback(() => {
    setDisplayLimit(pageSize);
    fetchLocalArtifacts();
    fetchStats();
    setProjects([]);
    setProjectsOffset(0);
    fetchProjects(true);
  }, [fetchLocalArtifacts, fetchStats, fetchProjects, pageSize]);

  const loadMore = useCallback(() => {
    setDisplayLimit((prev) => prev + pageSize);
  }, [pageSize]);

  const loadMoreProjects = useCallback(() => {
    fetchProjects(false);
  }, [fetchProjects]);

  return {
    localArtifacts,
    localLoading,
    localError,
    projects,
    projectsLoading,
    projectsError,
    stats,
    statsLoading,
    unifiedArtifacts,
    displayedArtifacts,
    totalCount,
    displayedCount,
    hasMore,
    refresh,
    loadMore,
    loadMoreProjects,
    hasMoreProjects,
  };
}

function getCategoryForType(type: string): string {
  const categoryMap: Record<string, string> = {
    stl: 'mesh',
    glb: 'mesh',
    gltf: 'mesh',
    '3mf': 'printable',
    step: 'cad',
    gcode: 'instruction',
    png: 'image',
    jpg: 'image',
    thumbnail: 'image',
  };
  return categoryMap[type.toLowerCase()] || 'mesh';
}

function sortUnifiedArtifacts(
  artifacts: UnifiedArtifact[],
  sortBy: SortField,
  sortOrder: SortOrder
): UnifiedArtifact[] {
  const sorted = [...artifacts];
  const multiplier = sortOrder === 'desc' ? -1 : 1;

  sorted.sort((a, b) => {
    switch (sortBy) {
      case 'date':
        return multiplier * (new Date(a.modifiedAt).getTime() - new Date(b.modifiedAt).getTime());
      case 'name':
        return multiplier * a.filename.toLowerCase().localeCompare(b.filename.toLowerCase());
      case 'size':
        return multiplier * ((a.sizeBytes || 0) - (b.sizeBytes || 0));
      case 'type':
        return multiplier * a.artifactType.localeCompare(b.artifactType);
      default:
        return 0;
    }
  });

  return sorted;
}

export default useArtifacts;
