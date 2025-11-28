import { useCallback } from 'react';
import { VOICE_MODES, VoiceMode, VoiceModeId } from '../../types/voiceModes';

interface SettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  currentMode: string;
  onModeChange: (modeId: string) => void;
  isConnected: boolean;
}

/**
 * Sci-Fi styled settings drawer for voice mode selection.
 * Features HUD-style corner brackets and mode-specific colors.
 */
export function SettingsDrawer({
  isOpen,
  onClose,
  currentMode,
  onModeChange,
  isConnected,
}: SettingsDrawerProps) {
  const handleModeSelect = useCallback((mode: VoiceMode) => {
    onModeChange(mode.id);
    // Close drawer after selection on mobile
    if (window.innerWidth < 768) {
      setTimeout(onClose, 300);
    }
  }, [onModeChange, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity z-40 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      {/* Drawer */}
      <div
        className={`fixed right-0 top-0 h-full w-80 max-w-[90vw] bg-gray-900/95 border-l border-cyan-500/30 shadow-2xl transform transition-transform duration-300 z-50 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* HUD Corner Brackets */}
        <div className="absolute top-2 left-2 w-4 h-4 border-l-2 border-t-2 border-cyan-500/70" />
        <div className="absolute top-2 right-2 w-4 h-4 border-r-2 border-t-2 border-cyan-500/70" />
        <div className="absolute bottom-2 left-2 w-4 h-4 border-l-2 border-b-2 border-cyan-500/70" />
        <div className="absolute bottom-2 right-2 w-4 h-4 border-r-2 border-b-2 border-cyan-500/70" />

        {/* Header */}
        <div className="p-4 border-b border-cyan-500/20">
          <div className="flex items-center justify-between">
            <h2 className="text-cyan-400 font-bold text-lg tracking-wider uppercase flex items-center gap-2">
              <span className="text-cyan-500">◆</span>
              Voice Mode
            </h2>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg bg-gray-800/50 hover:bg-red-500/20 border border-gray-700 hover:border-red-500/50 flex items-center justify-center transition-all text-gray-400 hover:text-red-400"
            >
              ✕
            </button>
          </div>
          <p className="text-gray-500 text-xs mt-1">
            Select operational mode for KITTY
          </p>
        </div>

        {/* Mode List */}
        <div className="p-4 space-y-3 overflow-y-auto max-h-[calc(100vh-160px)]">
          {VOICE_MODES.map((mode) => {
            const isSelected = mode.id === currentMode;
            return (
              <ModeCard
                key={mode.id}
                mode={mode}
                isSelected={isSelected}
                onClick={() => handleModeSelect(mode)}
                disabled={!isConnected}
              />
            );
          })}
        </div>

        {/* Footer info */}
        <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-gray-900 to-transparent">
          <div className="text-center">
            <p className="text-gray-600 text-xs">
              {isConnected ? 'Mode changes apply immediately' : 'Connect to change modes'}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}

interface ModeCardProps {
  mode: VoiceMode;
  isSelected: boolean;
  onClick: () => void;
  disabled: boolean;
}

/**
 * Individual mode selection card with HUD styling.
 */
function ModeCard({ mode, isSelected, onClick, disabled }: ModeCardProps) {
  const borderColor = isSelected ? mode.borderClass : 'border-gray-700/50';
  const bgColor = isSelected ? mode.bgClass : 'bg-gray-800/30';
  const glowEffect = isSelected ? `shadow-lg ${mode.glowClass}` : '';

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full p-3 rounded-lg border ${borderColor} ${bgColor} ${glowEffect} transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 text-left group relative overflow-hidden`}
    >
      {/* HUD corner accents for selected mode */}
      {isSelected && (
        <>
          <div className="absolute top-1 left-1 w-2 h-2 border-l border-t border-current opacity-50" />
          <div className="absolute top-1 right-1 w-2 h-2 border-r border-t border-current opacity-50" />
          <div className="absolute bottom-1 left-1 w-2 h-2 border-l border-b border-current opacity-50" />
          <div className="absolute bottom-1 right-1 w-2 h-2 border-r border-b border-current opacity-50" />
        </>
      )}

      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className={`text-2xl flex-shrink-0 ${isSelected ? '' : 'grayscale opacity-60 group-hover:grayscale-0 group-hover:opacity-100'} transition-all`}>
          {mode.icon}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className={`font-semibold ${isSelected ? 'text-white' : 'text-gray-300 group-hover:text-white'} transition-colors`}>
              {mode.name}
            </span>
            {mode.allowPaid && (
              <span className="px-1.5 py-0.5 text-[10px] bg-amber-500/20 text-amber-400 rounded border border-amber-500/30 uppercase tracking-wider">
                Paid
              </span>
            )}
            {isSelected && (
              <span className="ml-auto text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">
                Active
              </span>
            )}
          </div>
          <p className={`text-xs mt-1 ${isSelected ? 'text-gray-300' : 'text-gray-500 group-hover:text-gray-400'} transition-colors`}>
            {mode.description}
          </p>

          {/* Enabled tools preview */}
          {mode.enabledTools.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {mode.enabledTools.slice(0, 3).map((tool) => (
                <span
                  key={tool}
                  className={`px-1.5 py-0.5 text-[10px] rounded ${
                    isSelected
                      ? `${mode.bgClass} border ${mode.borderClass}`
                      : 'bg-gray-700/50 border border-gray-600/50'
                  } text-gray-400 transition-colors`}
                >
                  {tool.replace(/_/g, ' ')}
                </span>
              ))}
              {mode.enabledTools.length > 3 && (
                <span className="px-1.5 py-0.5 text-[10px] text-gray-500">
                  +{mode.enabledTools.length - 3} more
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

/**
 * Button to open settings drawer, shows current mode.
 */
interface SettingsButtonProps {
  currentMode: string;
  onClick: () => void;
  compact?: boolean;
}

export function SettingsButton({ currentMode, onClick, compact }: SettingsButtonProps) {
  const mode = VOICE_MODES.find((m) => m.id === currentMode) || VOICE_MODES[0];

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg ${mode.bgClass} border ${mode.borderClass} hover:scale-105 transition-all`}
      title="Voice Mode Settings"
    >
      <span>{mode.icon}</span>
      {!compact && (
        <span className="text-sm font-medium text-white">{mode.name}</span>
      )}
      <span className="text-gray-400">⚙</span>
    </button>
  );
}
