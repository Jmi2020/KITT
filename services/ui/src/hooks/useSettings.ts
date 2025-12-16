import { useCallback, useEffect, useRef, useState } from 'react';
import type { VoiceMode } from '../types/voiceModes';

export interface VoiceSettings {
  voice: string;
  language: string;
  hotword: string;
  prefer_local: boolean;
  sample_rate: number;
  push_to_talk: boolean;
  speed: number;  // TTS speed multiplier (0.5-2.0)
}

interface FabricationSettings {
  default_material: string;
  default_profile: string;
  safety_confirmation: boolean;
  auto_slice: boolean;
  default_printer: string | null;
}

interface UISettings {
  theme: string;
  compact_mode: boolean;
  show_debug: boolean;
  default_view: string;
  sidebar_collapsed: boolean;
}

interface PrivacySettings {
  store_conversations: boolean;
  telemetry_enabled: boolean;
  local_only: boolean;
}

interface NotificationSettings {
  print_complete: boolean;
  print_failure: boolean;
  low_inventory: boolean;
  sound_enabled: boolean;
}

interface AppSettings {
  voice: VoiceSettings;
  fabrication: FabricationSettings;
  ui: UISettings;
  privacy: PrivacySettings;
  notifications: NotificationSettings;
  custom_voice_modes: VoiceMode[];
}

interface UseSettingsReturn {
  settings: AppSettings | null;
  isLoading: boolean;
  error: string | null;
  version: number;
  updateSettings: (updates: Partial<AppSettings>) => Promise<void>;
  updateSection: <K extends keyof AppSettings>(section: K, updates: Partial<AppSettings[K]>) => Promise<void>;
  reload: () => Promise<void>;
}

const DEFAULT_SETTINGS: AppSettings = {
  voice: {
    voice: 'bf_emma',  // Default Kokoro voice
    language: 'en',
    hotword: 'kitty',
    prefer_local: true,
    sample_rate: 16000,
    push_to_talk: true,
    speed: 1.1,  // Default speech speed
  },
  fabrication: {
    default_material: 'pla_black_esun',
    default_profile: 'standard',
    safety_confirmation: true,
    auto_slice: false,
    default_printer: null,
  },
  ui: {
    theme: 'dark',
    compact_mode: false,
    show_debug: false,
    default_view: 'shell',
    sidebar_collapsed: false,
  },
  privacy: {
    store_conversations: true,
    telemetry_enabled: false,
    local_only: false,
  },
  notifications: {
    print_complete: true,
    print_failure: true,
    low_inventory: true,
    sound_enabled: true,
  },
  custom_voice_modes: [],
};

/**
 * Hook for managing user settings with cross-device sync.
 * Falls back to localStorage if settings service unavailable.
 */
export function useSettings(userId: string = 'default'): UseSettingsReturn {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);

  // Load settings from API or localStorage
  const loadSettings = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`/api/settings?user_id=${userId}`);
      if (response.ok) {
        const data = await response.json();
        setSettings(data.settings);
        setVersion(data.version);
        // Also save to localStorage as backup
        localStorage.setItem('kitty_settings', JSON.stringify(data.settings));
        setIsLoading(false);
        return;
      }
    } catch (err) {
      console.warn('Settings service unavailable, using localStorage');
    }

    // Fall back to localStorage
    const stored = localStorage.getItem('kitty_settings');
    if (stored) {
      try {
        setSettings(JSON.parse(stored));
      } catch {
        setSettings(DEFAULT_SETTINGS);
      }
    } else {
      setSettings(DEFAULT_SETTINGS);
    }
    setIsLoading(false);
  }, [userId]);

  // Update settings
  const updateSettings = useCallback(async (updates: Partial<AppSettings>) => {
    if (!settings) return;

    const newSettings = { ...settings, ...updates };
    setSettings(newSettings);

    // Save to localStorage immediately
    localStorage.setItem('kitty_settings', JSON.stringify(newSettings));

    // Try to sync with server
    try {
      const response = await fetch(`/api/settings?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: updates }),
      });
      if (response.ok) {
        const data = await response.json();
        setVersion(data.version);
      }
    } catch (err) {
      console.warn('Failed to sync settings to server:', err);
    }
  }, [settings, userId]);

  // Update specific section
  const updateSection = useCallback(async <K extends keyof AppSettings>(
    section: K,
    updates: Partial<AppSettings[K]>
  ) => {
    if (!settings) return;

    const newSection = { ...settings[section], ...updates };
    const newSettings = { ...settings, [section]: newSection };
    setSettings(newSettings);

    // Save to localStorage
    localStorage.setItem('kitty_settings', JSON.stringify(newSettings));

    // Try to sync with server
    try {
      const response = await fetch(`/api/settings/${section}?user_id=${userId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSection),
      });
      if (response.ok) {
        // Version is tracked per-record, not per-section
      }
    } catch (err) {
      console.warn('Failed to sync settings section to server:', err);
    }
  }, [settings, userId]);

  // Setup WebSocket sync
  useEffect(() => {
    loadSettings();

    // Try to connect WebSocket for real-time sync
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/settings/sync?user_id=${userId}`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'settings') {
            setSettings(msg.settings);
            setVersion(msg.version);
            localStorage.setItem('kitty_settings', JSON.stringify(msg.settings));
          }
        } catch (err) {
          console.error('Error parsing settings sync message:', err);
        }
      };

      ws.onerror = () => {
        console.warn('Settings sync WebSocket error');
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    } catch (err) {
      console.warn('Could not establish settings sync WebSocket:', err);
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [userId, loadSettings]);

  return {
    settings,
    isLoading,
    error,
    version,
    updateSettings,
    updateSection,
    reload: loadSettings,
  };
}
