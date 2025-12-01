import { useState, useCallback } from 'react';
import { BambuLogin } from '../components/BambuLogin';
import { VoiceModeEditor } from '../components/VoiceModeEditor';
import { useSettings } from '../hooks/useSettings';
import type { VoiceMode } from '../types/voiceModes';

type SettingsTab = 'connections' | 'voice' | 'voice_modes' | 'fabrication' | 'ui';

/**
 * Settings page with service connections and preferences.
 */
export default function Settings() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('connections');
  const { settings, updateSection, updateSettings, isLoading } = useSettings();

  const tabs: { id: SettingsTab; label: string; icon: string }[] = [
    { id: 'connections', label: 'Connections', icon: '🔌' },
    { id: 'voice', label: 'Voice', icon: '🎙️' },
    { id: 'voice_modes', label: 'Voice Modes', icon: '🎭' },
    { id: 'fabrication', label: 'Fabrication', icon: '🖨️' },
    { id: 'ui', label: 'Interface', icon: '🎨' },
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
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <h1 className="text-2xl font-bold text-white mb-6">Settings</h1>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 border-b border-gray-700 pb-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-t-lg flex items-center gap-2 transition-colors ${
                activeTab === tab.id
                  ? 'bg-gray-800 text-white border-b-2 border-cyan-500'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Connections Tab */}
        {activeTab === 'connections' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-lg font-semibold text-white mb-4">Service Connections</h2>
              <div className="grid gap-4 md:grid-cols-2">
                {/* Bambu Labs */}
                <BambuLogin showPrinters />

                {/* Placeholder for future connections */}
                <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 bg-blue-500/20 rounded-lg flex items-center justify-center">
                      <span className="text-2xl">🏠</span>
                    </div>
                    <div>
                      <h3 className="font-semibold text-white">Home Assistant</h3>
                      <p className="text-xs text-gray-400">Smart home control</p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-500">
                    Configure in .env file with HOME_ASSISTANT_TOKEN
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Voice Tab */}
        {activeTab === 'voice' && settings && (
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Voice Settings</h2>
              <div className="space-y-4">
                {/* Prefer Local */}
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-white">Prefer Local Processing</div>
                    <div className="text-sm text-gray-400">
                      Use local Whisper/Piper when available
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      updateSection('voice', { prefer_local: !settings.voice.prefer_local })
                    }
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.voice.prefer_local ? 'bg-cyan-500' : 'bg-gray-600'
                    }`}
                  >
                    <span
                      className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                        settings.voice.prefer_local ? 'left-7' : 'left-1'
                      }`}
                    />
                  </button>
                </div>

                {/* TTS Voice */}
                <div>
                  <label className="block text-white mb-2">TTS Voice</label>
                  <select
                    value={settings.voice.voice}
                    onChange={(e) => updateSection('voice', { voice: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="alloy">Alloy (Neutral)</option>
                    <option value="echo">Echo (Male)</option>
                    <option value="fable">Fable (British)</option>
                    <option value="onyx">Onyx (Deep)</option>
                    <option value="nova">Nova (Female)</option>
                    <option value="shimmer">Shimmer (Soft)</option>
                  </select>
                </div>

                {/* Language */}
                <div>
                  <label className="block text-white mb-2">Language</label>
                  <select
                    value={settings.voice.language}
                    onChange={(e) => updateSection('voice', { language: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="en">English</option>
                    <option value="es">Spanish</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="ja">Japanese</option>
                    <option value="zh">Chinese</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Voice Modes Tab */}
        {activeTab === 'voice_modes' && settings && (
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Voice Modes</h2>
              <VoiceModeEditor
                customModes={settings.custom_voice_modes || []}
                onSave={handleSaveVoiceModes}
              />
            </div>
          </div>
        )}

        {/* Fabrication Tab */}
        {activeTab === 'fabrication' && settings && (
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Fabrication Settings</h2>
              <div className="space-y-4">
                {/* Safety Confirmation */}
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-white">Safety Confirmations</div>
                    <div className="text-sm text-gray-400">
                      Require confirmation for hazardous operations
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      updateSection('fabrication', {
                        safety_confirmation: !settings.fabrication.safety_confirmation,
                      })
                    }
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.fabrication.safety_confirmation ? 'bg-cyan-500' : 'bg-gray-600'
                    }`}
                  >
                    <span
                      className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                        settings.fabrication.safety_confirmation ? 'left-7' : 'left-1'
                      }`}
                    />
                  </button>
                </div>

                {/* Default Material */}
                <div>
                  <label className="block text-white mb-2">Default Material</label>
                  <select
                    value={settings.fabrication.default_material}
                    onChange={(e) =>
                      updateSection('fabrication', { default_material: e.target.value })
                    }
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
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
                <div>
                  <label className="block text-white mb-2">Default Print Profile</label>
                  <select
                    value={settings.fabrication.default_profile}
                    onChange={(e) =>
                      updateSection('fabrication', { default_profile: e.target.value })
                    }
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="draft">Draft (0.28mm)</option>
                    <option value="standard">Standard (0.20mm)</option>
                    <option value="quality">Quality (0.12mm)</option>
                    <option value="fine">Fine (0.08mm)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* UI Tab */}
        {activeTab === 'ui' && settings && (
          <div className="space-y-6">
            <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Interface Settings</h2>
              <div className="space-y-4">
                {/* Theme */}
                <div>
                  <label className="block text-white mb-2">Theme</label>
                  <select
                    value={settings.ui.theme}
                    onChange={(e) => updateSection('ui', { theme: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="dark">Dark</option>
                    <option value="light">Light (Coming Soon)</option>
                    <option value="system">System</option>
                  </select>
                </div>

                {/* Default View */}
                <div>
                  <label className="block text-white mb-2">Default View</label>
                  <select
                    value={settings.ui.default_view}
                    onChange={(e) => updateSection('ui', { default_view: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="shell">Shell</option>
                    <option value="dashboard">Dashboard</option>
                    <option value="voice">Voice</option>
                    <option value="projects">Projects</option>
                    <option value="console">Fabrication Console</option>
                  </select>
                </div>

                {/* Show Debug */}
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-white">Show Debug Info</div>
                    <div className="text-sm text-gray-400">Display debug information in UI</div>
                  </div>
                  <button
                    onClick={() => updateSection('ui', { show_debug: !settings.ui.show_debug })}
                    className={`relative w-12 h-6 rounded-full transition-colors ${
                      settings.ui.show_debug ? 'bg-cyan-500' : 'bg-gray-600'
                    }`}
                  >
                    <span
                      className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${
                        settings.ui.show_debug ? 'left-7' : 'left-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="text-center py-8 text-gray-400">Loading settings...</div>
        )}
      </div>
    </div>
  );
}
