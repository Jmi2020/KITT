/**
 * Media Hub - Consolidated media management
 * Combines VisionGallery (search/filter) and ImageGenerator (SD generation)
 */

import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import Gallery from './tabs/Gallery';
import Generate from './tabs/Generate';
import './MediaHub.css';

type MediaTab = 'generate' | 'gallery';

interface TabConfig {
  id: MediaTab;
  label: string;
  icon: string;
}

const tabs: TabConfig[] = [
  { id: 'generate', label: 'Generate', icon: 'M' },
  { id: 'gallery', label: 'Gallery', icon: 'G' },
];

const MediaHub = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as MediaTab | null;
  const [activeTab, setActiveTab] = useState<MediaTab>(
    tabParam && tabs.some(t => t.id === tabParam) ? tabParam : 'generate'
  );

  // Get gallery-specific params
  const queryParam = searchParams.get('query') ?? '';
  const sessionParam = searchParams.get('session') ?? undefined;

  // Update URL when tab changes
  useEffect(() => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('tab', activeTab);
    setSearchParams(newParams, { replace: true });
  }, [activeTab, searchParams, setSearchParams]);

  // Sync from URL on mount or when URL changes externally
  useEffect(() => {
    if (tabParam && tabs.some(t => t.id === tabParam) && tabParam !== activeTab) {
      setActiveTab(tabParam);
    }
  }, [tabParam]);

  const handleTabClick = (tabId: MediaTab) => {
    setActiveTab(tabId);
  };

  return (
    <div className="media-hub">
      <header className="media-hub-header">
        <div className="header-content">
          <h1>Media Hub</h1>
          <p className="subtitle">Generate images with Stable Diffusion or search the visual archive</p>
        </div>
      </header>

      <nav className="media-hub-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <main className="media-hub-content">
        {activeTab === 'generate' && <Generate />}
        {activeTab === 'gallery' && (
          <Gallery
            initialQuery={queryParam}
            initialSession={sessionParam}
          />
        )}
      </main>
    </div>
  );
};

export default MediaHub;
