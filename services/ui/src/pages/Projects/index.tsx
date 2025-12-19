/**
 * Projects / Artifact Library
 *
 * A comprehensive artifact browser for viewing, downloading, and managing
 * all fabrication assets generated through KITTY workflows.
 *
 * Features:
 * - Multi-type artifact support (STL, GLB, 3MF, STEP, GCODE, images)
 * - Unified view combining local filesystem and database projects
 * - Sorting and filtering
 * - 3D model preview for GLB, STL, 3MF files
 * - Send to Fabrication integration
 * - Infinite scroll with intelligent navigation
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useArtifacts } from './hooks/useArtifacts';
import { PageDescriptor } from './components/PageDescriptor';
import { ArtifactFilters } from './components/ArtifactFilters';
import { ArtifactGrid } from './components/ArtifactGrid';
import { ModelPreview } from './components/ModelPreview';
import type {
  UnifiedArtifact,
  ArtifactTab,
  SortField,
  SortOrder,
  ArtifactTypeFilter,
} from './types';
import { ARTIFACT_TYPE_INFO } from './types';
import './Projects.css';

const DESCRIPTOR_DISMISSED_KEY = 'projects_descriptor_dismissed';

const Projects = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const gridRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Tab state
  const tabParam = searchParams.get('tab') as ArtifactTab | null;
  const [activeTab, setActiveTab] = useState<ArtifactTab>(tabParam || 'all');

  // Filter/sort state
  const [typeFilter, setTypeFilter] = useState<ArtifactTypeFilter>('all');
  const [sortBy, setSortBy] = useState<SortField>('date');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Descriptor state
  const [descriptorDismissed, setDescriptorDismissed] = useState(
    localStorage.getItem(DESCRIPTOR_DISMISSED_KEY) === 'true'
  );

  // Preview modal state
  const [previewArtifact, setPreviewArtifact] = useState<UnifiedArtifact | null>(null);

  // Scroll to top button visibility
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Data fetching
  const {
    localLoading,
    localError,
    projectsLoading,
    projectsError,
    stats,
    unifiedArtifacts,
    displayedArtifacts,
    totalCount,
    displayedCount,
    hasMore,
    refresh,
    loadMore,
    loadMoreProjects,
    hasMoreProjects,
  } = useArtifacts({ typeFilter, sortBy, sortOrder });

  // Filter artifacts by tab
  const getDisplayedArtifacts = (): UnifiedArtifact[] => {
    switch (activeTab) {
      case 'local':
        return displayedArtifacts.filter((a) => a.source === 'filesystem');
      case 'database':
        return displayedArtifacts.filter((a) => a.source === 'database');
      case 'all':
      default:
        return displayedArtifacts;
    }
  };

  const filteredArtifacts = getDisplayedArtifacts();
  const isLoading = localLoading || projectsLoading;
  const error = localError || projectsError;

  // Infinite scroll observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoading) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (loadMoreRef.current) {
      observer.observe(loadMoreRef.current);
    }

    return () => observer.disconnect();
  }, [hasMore, isLoading, loadMore]);

  // Scroll to top visibility
  useEffect(() => {
    const handleScroll = () => {
      setShowScrollTop(window.scrollY > 400);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Tab change handler
  const handleTabChange = (tab: ArtifactTab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  // Dismiss descriptor
  const handleDismissDescriptor = () => {
    setDescriptorDismissed(true);
    localStorage.setItem(DESCRIPTOR_DISMISSED_KEY, 'true');
  };

  // Filter handlers
  const handleTypeChange = (type: ArtifactTypeFilter) => {
    setTypeFilter(type);
  };

  const handleSortChange = (sort: SortField) => {
    setSortBy(sort);
  };

  const handleOrderToggle = () => {
    setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
  };

  // Artifact actions
  const handlePreview = useCallback((artifact: UnifiedArtifact) => {
    setPreviewArtifact(artifact);
  }, []);

  const handleClosePreview = useCallback(() => {
    setPreviewArtifact(null);
  }, []);

  const handleDownload = useCallback((artifact: UnifiedArtifact) => {
    const link = document.createElement('a');
    link.href = artifact.downloadUrl;
    link.download = artifact.filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }, []);

  const handleSendToFabrication = useCallback(
    (artifact: UnifiedArtifact) => {
      navigate('/console', {
        state: {
          selectedArtifact: {
            url: artifact.downloadUrl,
            filename: artifact.filename,
            type: artifact.artifactType,
          },
        },
      });
    },
    [navigate]
  );

  // Scroll to top
  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Quick jump to type
  const handleQuickJump = (type: string) => {
    setTypeFilter(type as ArtifactTypeFilter);
    if (gridRef.current) {
      gridRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Calculate tab counts from full list
  const allCount = unifiedArtifacts.length;
  const localCount = unifiedArtifacts.filter((a) => a.source === 'filesystem').length;
  const dbCount = unifiedArtifacts.filter((a) => a.source === 'database').length;

  const tabs: { id: ArtifactTab; label: string; count: number }[] = [
    { id: 'all', label: 'All Artifacts', count: allCount },
    { id: 'local', label: 'Local Files', count: localCount },
    { id: 'database', label: 'Project Artifacts', count: dbCount },
  ];

  // Get unique types for quick navigation
  const availableTypes = stats?.byType ? Object.keys(stats.byType).filter((t) => stats.byType[t] > 0) : [];

  return (
    <section className="projects-page">
      <header className="projects-header">
        <h1>Artifact Library</h1>
        <p className="subtitle">Manage your fabrication assets</p>
      </header>

      <PageDescriptor
        stats={stats}
        isDismissed={descriptorDismissed}
        onDismiss={handleDismissDescriptor}
      />

      {error && activeTab !== 'local' && (
        <div className="error-banner warning">
          <strong>Note:</strong> {error}
          <span className="error-hint">Local artifacts are still available below.</span>
        </div>
      )}

      {/* Quick Navigation */}
      {availableTypes.length > 1 && (
        <div className="quick-nav">
          <span className="quick-nav-label">Jump to:</span>
          {availableTypes.map((type) => {
            const typeInfo = ARTIFACT_TYPE_INFO[type];
            return (
              <button
                key={type}
                className={`quick-nav-btn ${typeFilter === type ? 'active' : ''}`}
                onClick={() => handleQuickJump(type)}
                title={`Show ${type.toUpperCase()} files (${stats?.byType[type] || 0})`}
              >
                <span className="quick-nav-icon">{typeInfo?.icon || '📄'}</span>
                <span className="quick-nav-type">{type.toUpperCase()}</span>
                <span className="quick-nav-count">{stats?.byType[type] || 0}</span>
              </button>
            );
          })}
          {typeFilter !== 'all' && (
            <button className="quick-nav-btn quick-nav-clear" onClick={() => setTypeFilter('all')}>
              Show All
            </button>
          )}
        </div>
      )}

      <nav className="projects-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabChange(tab.id)}
          >
            <span className="tab-label">{tab.label}</span>
            <span className="tab-count">{tab.count}</span>
          </button>
        ))}
      </nav>

      <ArtifactFilters
        typeFilter={typeFilter}
        sortBy={sortBy}
        sortOrder={sortOrder}
        stats={stats}
        onTypeChange={handleTypeChange}
        onSortChange={handleSortChange}
        onOrderToggle={handleOrderToggle}
        onRefresh={refresh}
        loading={isLoading}
      />

      {/* Progress indicator */}
      {totalCount > 0 && (
        <div className="pagination-info">
          Showing {displayedCount} of {totalCount} artifacts
          {hasMore && <span className="pagination-hint"> (scroll down for more)</span>}
        </div>
      )}

      <div ref={gridRef}>
        <ArtifactGrid
          artifacts={filteredArtifacts}
          loading={isLoading && displayedCount === 0}
          error={activeTab === 'local' ? localError : null}
          onPreview={handlePreview}
          onDownload={handleDownload}
          onSendToFabrication={handleSendToFabrication}
          onRetry={refresh}
        />
      </div>

      {/* Infinite scroll trigger */}
      {hasMore && (
        <div ref={loadMoreRef} className="load-more-trigger">
          {isLoading ? (
            <div className="loading-more">
              <div className="loader-spinner small"></div>
              <span>Loading more...</span>
            </div>
          ) : (
            <button className="btn btn-secondary" onClick={loadMore}>
              Load More ({totalCount - displayedCount} remaining)
            </button>
          )}
        </div>
      )}

      {activeTab === 'database' && hasMoreProjects && !projectsLoading && (
        <div className="load-more-container">
          <button className="btn btn-secondary" onClick={loadMoreProjects}>
            Load More Projects
          </button>
        </div>
      )}

      {/* Scroll to top button */}
      {showScrollTop && (
        <button className="scroll-to-top" onClick={scrollToTop} title="Scroll to top">
          ↑
        </button>
      )}

      <ModelPreview artifact={previewArtifact} onClose={handleClosePreview} />
    </section>
  );
};

export default Projects;
