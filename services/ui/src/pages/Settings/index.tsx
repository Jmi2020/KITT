/**
 * Settings Page - Consolidated settings with System tab
 * Includes: Connections, Voice, Voice Modes, Fabrication, UI, Runtime, System (IOControl)
 */

import { useState, useCallback, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { BambuLogin } from '../../components/BambuLogin';
import { VoiceModeEditor } from '../../components/VoiceModeEditor';
import { useSettings } from '../../hooks/useSettings';
import { useIOControl } from '../../hooks/useIOControl';
import type { VoiceMode } from '../../types/voiceModes';
import SystemTab from './tabs/SystemTab';
import RuntimeTab from './tabs/RuntimeTab';
import ModelTestingTab from './tabs/ModelTestingTab';
import { VoiceTab } from './tabs/VoiceTab';
import './Settings.css';

type SettingsTab = 'connections' | 'voice' | 'voice_modes' | 'fabrication' | 'ui' | 'runtime' | 'model_testing' | 'system';

/**
 * Settings page with service connections, preferences, and system configuration.
 */
export default function Settings() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get('tab') as SettingsTab | null;
  const [activeTab, setActiveTab] = useState<SettingsTab>(tabFromUrl || 'connections');
  const { settings, updateSection, updateSettings, isLoading } = useSettings();
  const ioControlApi = useIOControl();

  // Sync tab with URL
  useEffect(() => {
    if (tabFromUrl && tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
    }
  }, [tabFromUrl, activeTab]);

  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab);
    setSearchParams({ tab });
  };

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'connections', label: 'Connections', icon: '🔌' },
    { id: 'voice', label: 'Voice', icon: '🎙️' },
    { id: 'voice_modes', label: 'Voice Modes', icon: '🎭' },
    { id: 'fabrication', label: 'Fabrication', icon: '🖨️' },
    { id: 'ui', label: 'Interface', icon: '🎨' },
    { id: 'runtime', label: 'Runtime', icon: '🚀' },
    { id: 'model_testing', label: 'Model Testing', icon: '🧪' },
    { id: 'system', label: 'System', icon: '⚙️' },
  ];

  const handleSaveVoiceModes = useCallback(
    async (modes: VoiceMode[]) => {
      // Update the custom_voice_modes in settings using updateSettings for array handling
      if (settings) {
        await updateSettings({ custom_voice_modes: modes });
      }
    },
    [settings, updateSettings]
  );

  return (
    <div className="settings-page">
      <div className="settings-container">
        {/* Header */}
        <div className="settings-header">
          <h1>Settings</h1>
          <p className="settings-subtitle">Configure connections, preferences, and system features</p>
        </div>

        {/* Tabs */}
        <div className="settings-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
            >
              <span className="tab-icon">{tab.icon}</span>
              <span className="tab-label">{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="settings-content">
          {/* Connections Tab */}
          {activeTab === 'connections' && (
            <div className="settings-section">
              <h2>Service Connections</h2>
              <div className="connections-grid">
                {/* Bambu Labs */}
                <BambuLogin showPrinters />

                {/* Placeholder for future connections */}
                <div className="connection-card">
                  <div className="connection-header">
                    <div className="connection-icon">🏠</div>
                    <div>
                      <h3>Home Assistant</h3>
                      <p className="connection-status">Smart home control</p>
                    </div>
                  </div>
                  <p className="connection-hint">
                    Configure in .env file with HOME_ASSISTANT_TOKEN
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Voice Tab */}
          {activeTab === 'voice' && settings && (
            <VoiceTab settings={settings} updateSection={updateSection} />
          )}

          {/* Voice Modes Tab */}
          {activeTab === 'voice_modes' && settings && (
            <div className="settings-section">
              <h2>Voice Modes</h2>
              <div className="settings-card">
                <VoiceModeEditor
                  customModes={settings.custom_voice_modes || []}
                  onSave={handleSaveVoiceModes}
                />
              </div>
            </div>
          )}

          {/* Fabrication Tab */}
          {activeTab === 'fabrication' && settings && (
            <div className="settings-section">
              <h2>Fabrication Settings</h2>
              <div className="settings-card">
                {/* Safety Confirmation */}
                <div className="setting-row">
                  <div className="setting-info">
                    <div className="setting-label">Safety Confirmations</div>
                    <div className="setting-description">
                      Require confirmation for hazardous operations
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      updateSection('fabrication', {
                        safety_confirmation: !settings.fabrication.safety_confirmation,
                      })
                    }
                    className={`toggle-button ${settings.fabrication.safety_confirmation ? 'active' : ''}`}
                    aria-label="Toggle safety confirmation"
                  >
                    <span className="toggle-thumb" />
                  </button>
                </div>

                {/* Default Material */}
                <div className="setting-row">
                  <label className="setting-label" htmlFor="material-select">Default Material</label>
                  <select
                    id="material-select"
                    value={settings.fabrication.default_material}
                    onChange={(e) =>
                      updateSection('fabrication', { default_material: e.target.value })
                    }
                    className="setting-select"
                  >
                    <option value="pla_black_esun">PLA Black (eSUN)</option>
                    <option value="pla_white_esun">PLA White (eSUN)</option>
                    <option value="petg_black">PETG Black</option>
                    <option value="petg_clear">PETG Clear</option>
                    <option value="abs_black">ABS Black</option>
                    <option value="tpu_black">TPU Black</option>
                  </select>
                </div>

                {/* Default Profile */}
                <div className="setting-row">
                  <label className="setting-label" htmlFor="profile-select">Default Print Profile</label>
                  <select
                    id="profile-select"
                    value={settings.fabrication.default_profile}
                    onChange={(e) =>
                      updateSection('fabrication', { default_profile: e.target.value })
                    }
                    className="setting-select"
                  >
                    <option value="draft">Draft (0.28mm)</option>
                    <option value="standard">Standard (0.20mm)</option>
                    <option value="quality">Quality (0.12mm)</option>
                    <option value="fine">Fine (0.08mm)</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* UI Tab */}
          {activeTab === 'ui' && settings && (
            <div className="settings-section">
              <h2>Interface Settings</h2>
              <div className="settings-card">
                {/* Theme */}
                <div className="setting-row">
                  <label className="setting-label" htmlFor="theme-select">Theme</label>
                  <select
                    id="theme-select"
                    value={settings.ui.theme}
                    onChange={(e) => updateSection('ui', { theme: e.target.value })}
                    className="setting-select"
                  >
                    <option value="dark">Dark</option>
                    <option value="light">Light (Coming Soon)</option>
                    <option value="system">System</option>
                  </select>
                </div>

                {/* Default View */}
                <div className="setting-row">
                  <label className="setting-label" htmlFor="default-view-select">Default View</label>
                  <select
                    id="default-view-select"
                    value={settings.ui.default_view}
                    onChange={(e) => updateSection('ui', { default_view: e.target.value })}
                    className="setting-select"
                  >
                    <option value="shell">Shell</option>
                    <option value="dashboard">Dashboard</option>
                    <option value="voice">Voice</option>
                    <option value="projects">Projects</option>
                    <option value="console">Fabrication Console</option>
                  </select>
                </div>

                {/* Show Debug */}
                <div className="setting-row">
                  <div className="setting-info">
                    <div className="setting-label">Show Debug Info</div>
                    <div className="setting-description">Display debug information in UI</div>
                  </div>
                  <button
                    onClick={() => updateSection('ui', { show_debug: !settings.ui.show_debug })}
                    className={`toggle-button ${settings.ui.show_debug ? 'active' : ''}`}
                    aria-label="Toggle show debug"
                  >
                    <span className="toggle-thumb" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Runtime Tab (Service Management) */}
          {activeTab === 'runtime' && <RuntimeTab />}

          {/* Model Testing Tab (LLM Debugging) */}
          {activeTab === 'model_testing' && <ModelTestingTab />}

          {/* System Tab (IOControl) */}
          {activeTab === 'system' && <SystemTab api={ioControlApi} />}
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="settings-loading">Loading settings...</div>
        )}
      </div>
    </div>
  );
}
