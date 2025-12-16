import { useCallback, useEffect, useRef, useState } from 'react';
import type { VoiceSettings } from '../../../hooks/useSettings';
import './VoiceTab.css';

interface Voice {
  id: string;
  name: string;
  gender: string;
  accent: string;
  curated: boolean;
}

interface VoiceTabProps {
  settings: { voice: VoiceSettings };
  updateSection: (section: 'voice', updates: Partial<VoiceSettings>) => void;
}

export function VoiceTab({ settings, updateSection }: VoiceTabProps) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [curatedVoices, setCuratedVoices] = useState<Voice[]>([]);
  const [showAllVoices, setShowAllVoices] = useState(false);
  const [activeProvider, setActiveProvider] = useState<string>('unknown');
  const [isLoading, setIsLoading] = useState(true);
  const [previewState, setPreviewState] = useState<'idle' | 'generating' | 'playing'>('idle');
  const [savedBadge, setSavedBadge] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const savedTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Pending voice selection (not yet applied)
  const [pendingVoice, setPendingVoice] = useState<string | null>(null);

  // The voice to display/preview: pending if set, otherwise current saved
  const displayedVoice = pendingVoice ?? settings.voice.voice;
  const hasUnappliedChanges = pendingVoice !== null && pendingVoice !== settings.voice.voice;

  // Show saved badge with auto-dismiss
  const showSaved = useCallback((message: string) => {
    if (savedTimeoutRef.current) {
      clearTimeout(savedTimeoutRef.current);
    }
    setSavedBadge(message);
    savedTimeoutRef.current = setTimeout(() => setSavedBadge(null), 2000);
  }, []);

  // Handle voice selection (sets pending, doesn't save)
  const handleVoiceSelect = useCallback((newVoice: string) => {
    setPendingVoice(newVoice);
  }, []);

  // Apply the pending voice permanently
  const handleApplyVoice = useCallback(() => {
    if (pendingVoice && pendingVoice !== settings.voice.voice) {
      updateSection('voice', { voice: pendingVoice });
      setPendingVoice(null);
      showSaved('Voice applied');
    }
  }, [pendingVoice, settings.voice.voice, updateSection, showSaved]);

  // Cancel pending changes
  const handleCancelVoice = useCallback(() => {
    setPendingVoice(null);
  }, []);

  // Handle speed change with save feedback
  const handleSpeedChange = useCallback((newSpeed: number) => {
    updateSection('voice', { speed: newSpeed });
    showSaved('Speed saved');
  }, [updateSection, showSaved]);

  // Handle other setting changes with save feedback
  const handleSettingChange = useCallback((updates: Partial<typeof settings.voice>, message: string) => {
    updateSection('voice', updates);
    showSaved(message);
  }, [updateSection, showSaved]);

  // Fetch available voices from backend
  useEffect(() => {
    async function fetchVoices() {
      try {
        const response = await fetch('/api/voice/voices');
        if (response.ok) {
          const data = await response.json();
          setVoices(data.voices || []);
          setCuratedVoices(data.curated || []);
          setActiveProvider(data.provider || 'unknown');
        }
      } catch (err) {
        console.warn('Failed to fetch voices:', err);
        // Use fallback voices
        setCuratedVoices([
          { id: 'bf_emma', name: 'Emma', gender: 'female', accent: 'British', curated: true },
          { id: 'am_michael', name: 'Michael', gender: 'male', accent: 'American', curated: true },
        ]);
      } finally {
        setIsLoading(false);
      }
    }
    fetchVoices();
  }, []);

  // Preview voice (uses pending/displayed voice)
  const handlePreview = useCallback(async () => {
    if (previewState !== 'idle') return;
    setPreviewState('generating');

    try {
      const response = await fetch('/api/voice/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          voice: displayedVoice,
          text: "Hello! I'm your voice assistant. How can I help you today?",
        }),
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        if (audioRef.current) {
          audioRef.current.pause();
          URL.revokeObjectURL(audioRef.current.src);
        }

        const audio = new Audio(url);
        audioRef.current = audio;
        setPreviewState('playing');
        audio.onended = () => {
          setPreviewState('idle');
          URL.revokeObjectURL(url);
        };
        audio.onerror = () => {
          setPreviewState('idle');
          URL.revokeObjectURL(url);
        };
        await audio.play();
      } else {
        setPreviewState('idle');
      }
    } catch (err) {
      console.error('Preview failed:', err);
      setPreviewState('idle');
    }
  }, [displayedVoice, previewState]);

  // Get display voices based on showAllVoices toggle
  const displayVoices = showAllVoices ? voices : curatedVoices;

  // Group voices by accent
  const groupedVoices = displayVoices.reduce((acc, voice) => {
    const key = `${voice.accent} ${voice.gender === 'female' ? 'Female' : 'Male'}`;
    if (!acc[key]) acc[key] = [];
    acc[key].push(voice);
    return acc;
  }, {} as Record<string, Voice[]>);

  // Format voice display label
  const getVoiceLabel = (voice: Voice) => {
    return `${voice.name} (${voice.accent} ${voice.gender === 'female' ? 'Female' : 'Male'})`;
  };

  // Get currently displayed voice info
  const selectedVoiceInfo = voices.find(v => v.id === displayedVoice) ||
    curatedVoices.find(v => v.id === displayedVoice);

  return (
    <div className="settings-section">
      <div className="voice-settings-header">
        <h2>Voice Settings</h2>
        {savedBadge && (
          <span className="saved-badge">
            <span className="saved-checkmark">✓</span> {savedBadge}
          </span>
        )}
      </div>
      <div className="settings-card">
        {/* Provider Status */}
        <div className="setting-row provider-status-row">
          <div className="setting-info">
            <div className="setting-label">TTS Provider</div>
            <div className="setting-description">
              Active text-to-speech engine
            </div>
          </div>
          <span className={`provider-badge provider-${activeProvider}`}>
            {activeProvider === 'kokoro' ? 'Kokoro' :
             activeProvider === 'piper' ? 'Piper' :
             activeProvider === 'openai' ? 'OpenAI' : 'Unknown'}
          </span>
        </div>

        {/* Voice Selection */}
        <div className="setting-row voice-select-row">
          <div className="setting-info">
            <div className="setting-label">Voice</div>
            <div className="setting-description">
              {selectedVoiceInfo ? getVoiceLabel(selectedVoiceInfo) : 'Select a voice'}
              {hasUnappliedChanges && <span className="pending-indicator"> (not saved)</span>}
            </div>
          </div>
          <div className="voice-controls">
            <select
              value={displayedVoice}
              onChange={(e) => handleVoiceSelect(e.target.value)}
              className={`setting-select ${hasUnappliedChanges ? 'has-changes' : ''}`}
              disabled={isLoading}
            >
              {Object.entries(groupedVoices).map(([group, voiceList]) => (
                <optgroup key={group} label={group}>
                  {voiceList.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <button
              className={`preview-button ${previewState !== 'idle' ? 'active' : ''}`}
              onClick={handlePreview}
              disabled={previewState !== 'idle' || isLoading}
              title={previewState === 'generating' ? 'Generating...' : previewState === 'playing' ? 'Playing...' : 'Preview voice'}
            >
              {previewState === 'generating' ? '◌' : previewState === 'playing' ? '⏹' : '▶'}
            </button>
          </div>
        </div>

        {/* Preview Loading Bar */}
        {previewState !== 'idle' && (
          <div className="preview-status">
            <div className={`preview-loading-bar ${previewState}`} />
            <span className="preview-status-text">
              {previewState === 'generating' ? 'Generating preview...' : 'Playing...'}
            </span>
          </div>
        )}

        {/* Apply/Cancel Voice Buttons */}
        {hasUnappliedChanges && (
          <div className="voice-apply-row">
            <button className="apply-voice-button" onClick={handleApplyVoice}>
              Apply Voice
            </button>
            <button className="cancel-voice-button" onClick={handleCancelVoice}>
              Cancel
            </button>
          </div>
        )}

        {/* Show All Voices Toggle */}
        <div className="show-all-voices">
          <button
            className="expand-voices-button"
            onClick={() => setShowAllVoices(!showAllVoices)}
          >
            {showAllVoices ? '▼' : '▶'} {showAllVoices ? 'Show fewer voices' : `Show all ${voices.length} voices`}
          </button>
        </div>

        {/* Speed Slider */}
        <div className="setting-row speed-row">
          <div className="setting-info">
            <div className="setting-label">Speech Speed</div>
            <div className="setting-description">
              Adjust how fast the voice speaks
            </div>
          </div>
          <div className="speed-control">
            <span className="speed-value">{(settings.voice.speed ?? 1.1).toFixed(1)}x</span>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              value={settings.voice.speed ?? 1.1}
              onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
              className="speed-slider"
            />
          </div>
        </div>

        {/* Language Selection */}
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">Language</div>
            <div className="setting-description">
              Primary language for speech
            </div>
          </div>
          <select
            value={settings.voice.language}
            onChange={(e) => handleSettingChange({ language: e.target.value }, 'Language saved')}
            className="setting-select"
          >
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="ja">Japanese</option>
            <option value="zh">Chinese</option>
          </select>
        </div>

        {/* Prefer Local */}
        <div className="setting-row">
          <div className="setting-info">
            <div className="setting-label">Prefer Local Processing</div>
            <div className="setting-description">
              Use local Kokoro/Piper TTS when available
            </div>
          </div>
          <button
            onClick={() => handleSettingChange({ prefer_local: !settings.voice.prefer_local }, 'Preference saved')}
            className={`toggle-button ${settings.voice.prefer_local ? 'active' : ''}`}
            aria-label="Toggle prefer local"
          >
            <span className="toggle-thumb" />
          </button>
        </div>
      </div>
    </div>
  );
}
