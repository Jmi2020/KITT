import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface VoiceState {
  // UI State
  isSidebarOpen: boolean;
  isSettingsOpen: boolean;
  isHistoryOpen: boolean;
  controlsVisible: boolean;
  
  // Theme State
  theme: 'dark' | 'light' | 'system';
  primaryColor: string; // Hex or tailwind class prefix
  
  // Actions
  toggleSidebar: () => void;
  setSidebarOpen: (isOpen: boolean) => void;
  toggleSettings: () => void;
  setSettingsOpen: (isOpen: boolean) => void;
  toggleHistory: () => void;
  setHistoryOpen: (isOpen: boolean) => void;
  setControlsVisible: (visible: boolean) => void;
  setTheme: (theme: 'dark' | 'light' | 'system') => void;
}

export const useVoiceStore = create<VoiceState>()(
  persist(
    (set) => ({
      isSidebarOpen: false,
      isSettingsOpen: false,
      isHistoryOpen: true,
      controlsVisible: true,
      theme: 'dark',
      primaryColor: 'cyan',

      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      setSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),
      
      toggleSettings: () => set((state) => ({ isSettingsOpen: !state.isSettingsOpen })),
      setSettingsOpen: (isOpen) => set({ isSettingsOpen: isOpen }),
      
      toggleHistory: () => set((state) => ({ isHistoryOpen: !state.isHistoryOpen })),
      setHistoryOpen: (isOpen) => set({ isHistoryOpen: isOpen }),
      
      setControlsVisible: (visible) => set({ controlsVisible: visible }),
      
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'kitty-voice-storage',
      partialize: (state) => ({ 
        isHistoryOpen: state.isHistoryOpen,
        theme: state.theme 
      }),
    }
  )
);
