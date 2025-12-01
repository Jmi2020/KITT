import { useCallback, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { VOICE_MODES, VoiceMode, getAllModes } from '../../types/voiceModes';
import { useSettings } from '../../hooks/useSettings';

interface SettingsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  currentMode: string;
  onModeChange: (modeId: string) => void;
  isConnected: boolean;
}

/**
 * Sci-Fi styled settings drawer for voice mode selection.
 * Uses React Portal for proper fixed positioning.
 * Features glassmorphism, animated borders, and mode-specific colors.
 */
export function SettingsDrawer({
  isOpen,
  onClose,
  currentMode,
  onModeChange,
  isConnected,
}: SettingsDrawerProps) {
  const { settings } = useSettings();
  const allModes = getAllModes(settings?.custom_voice_modes || []);

  const handleModeSelect = useCallback((mode: VoiceMode) => {
    onModeChange(mode.id);
    // Close drawer after selection
    setTimeout(onClose, 200);
  }, [onModeChange, onClose]);

  // Handle escape key to close
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Prevent body scroll when drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Use portal to render at document body level
  const content = (
    <>
      {/* Backdrop with blur */}
      <div
        onClick={onClose}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        role="button"
        tabIndex={0}
        aria-label="Close settings"
        style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.6)',
          backdropFilter: 'blur(8px)',
          WebkitBackdropFilter: 'blur(8px)',
          zIndex: 9998,
          opacity: isOpen ? 1 : 0,
          visibility: isOpen ? 'visible' : 'hidden',
          transition: 'opacity 300ms, visibility 300ms',
        }}
      />

      {/* Drawer Panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        style={{
          position: 'fixed',
          right: 0,
          top: 0,
          height: '100vh',
          width: '384px',
          maxWidth: '95vw',
          zIndex: 9999,
          transform: isOpen ? 'translateX(0)' : 'translateX(100%)',
          transition: 'transform 400ms cubic-bezier(0.16, 1, 0.3, 1)', // Smoother spring-like cubic-bezier
        }}
      >
        {/* Glassmorphism background */}
        <div className="absolute inset-0 bg-gradient-to-br from-gray-900/95 via-gray-900/98 to-gray-950/98 backdrop-blur-2xl" />

        {/* Tech Grid Background Pattern */}
        <div
          className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            backgroundImage: `
              linear-gradient(to right, rgba(255,255,255,0.05) 1px, transparent 1px),
              linear-gradient(to bottom, rgba(255,255,255,0.05) 1px, transparent 1px)
            `,
            backgroundSize: '40px 40px',
            maskImage: 'linear-gradient(to bottom, black, transparent)',
            WebkitMaskImage: 'linear-gradient(to bottom, black, transparent)',
          }}
        />

        {/* Animated border gradient */}
        <div className="absolute inset-y-0 left-0 w-[2px] bg-gradient-to-b from-cyan-400 via-purple-500 to-cyan-400 opacity-80"
          style={{
            backgroundSize: '100% 200%',
            animation: 'gradient-shift 3s ease infinite'
          }}
        />

        {/* Content container */}
        <div className="relative h-full flex flex-col">
          {/* Header */}
          <div className="flex-shrink-0 p-5 border-b border-white/10">
            <div className="flex items-center justify-between">
              <div>
                <h2 id="drawer-title" className="text-xl font-bold text-white flex items-center gap-3">
                  <span className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-purple-600 flex items-center justify-center text-sm">
                    ⚙
                  </span>
                  Voice Mode
                </h2>
                <p className="text-gray-400 text-sm mt-1">
                  Select KITTY's operational mode
                </p>
              </div>
              <button
                onClick={onClose}
                className="w-10 h-10 rounded-xl bg-white/5 hover:bg-red-500/20 border border-white/10 hover:border-red-500/50 flex items-center justify-center transition-all duration-200 text-gray-400 hover:text-red-400 hover:scale-105 active:scale-95"
                aria-label="Close drawer"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Mode List - Scrollable */}
          <div className="flex-1 overflow-y-auto p-5 space-y-3">
            {/* System Modes */}
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

            {/* Custom Modes Section */}
            {(settings?.custom_voice_modes || []).length > 0 && (
              <>
                <div className="border-t border-white/10 my-4 pt-4">
                  <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Custom Modes
                  </span>
                </div>
                {(settings?.custom_voice_modes || []).map((mode) => {
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
              </>
            )}
          </div>

          {/* Footer */}
          <div className="flex-shrink-0 p-5 border-t border-white/10 bg-black/20">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">
                {isConnected ? '● Connected' : '○ Disconnected'}
              </span>
              <span className="text-gray-400">
                {isConnected ? 'Changes apply instantly' : 'Connect first'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* CSS for gradient animation */}
      <style>{`
        @keyframes gradient-shift {
          0%, 100% { background-position: 0% 0%; }
          50% { background-position: 0% 100%; }
        }
      `}</style>
    </>
  );

  return createPortal(content, document.body);
}

interface ModeCardProps {
  mode: VoiceMode;
  isSelected: boolean;
  onClick: () => void;
  disabled: boolean;
}

/**
 * Individual mode selection card with clear visual boundaries.
 */
function ModeCard({ mode, isSelected, onClick, disabled }: ModeCardProps) {
  // Color values for mode-specific styling
  const colorValues: Record<string, { bg: string; border: string; accent: string; glow: string }> = {
    cyan: { bg: 'rgba(34, 211, 238, 0.15)', border: 'rgba(34, 211, 238, 0.5)', accent: '#22d3ee', glow: '0 0 20px rgba(34, 211, 238, 0.3)' },
    orange: { bg: 'rgba(249, 115, 22, 0.15)', border: 'rgba(249, 115, 22, 0.5)', accent: '#f97316', glow: '0 0 20px rgba(249, 115, 22, 0.3)' },
    purple: { bg: 'rgba(168, 85, 247, 0.15)', border: 'rgba(168, 85, 247, 0.5)', accent: '#a855f7', glow: '0 0 20px rgba(168, 85, 247, 0.3)' },
    green: { bg: 'rgba(34, 197, 94, 0.15)', border: 'rgba(34, 197, 94, 0.5)', accent: '#22c55e', glow: '0 0 20px rgba(34, 197, 94, 0.3)' },
    pink: { bg: 'rgba(236, 72, 153, 0.15)', border: 'rgba(236, 72, 153, 0.5)', accent: '#ec4899', glow: '0 0 20px rgba(236, 72, 153, 0.3)' },
    blue: { bg: 'rgba(59, 130, 246, 0.15)', border: 'rgba(59, 130, 246, 0.5)', accent: '#3b82f6', glow: '0 0 20px rgba(59, 130, 246, 0.3)' },
    red: { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.5)', accent: '#ef4444', glow: '0 0 20px rgba(239, 68, 68, 0.3)' },
    yellow: { bg: 'rgba(234, 179, 8, 0.15)', border: 'rgba(234, 179, 8, 0.5)', accent: '#eab308', glow: '0 0 20px rgba(234, 179, 8, 0.3)' },
  };

  const colors = colorValues[mode.color] || colorValues.cyan;

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="group"
      style={{
        width: '100%',
        padding: '16px',
        borderRadius: '12px',
        border: isSelected ? `2px solid ${colors.border}` : '2px solid rgba(255, 255, 255, 0.15)',
        backgroundColor: isSelected ? colors.bg : 'rgba(255, 255, 255, 0.05)',
        boxShadow: isSelected ? colors.glow : 'none',
        transition: 'all 200ms ease',
        textAlign: 'left',
        position: 'relative',
        overflow: 'hidden',
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        marginBottom: '12px',
      }}
      onMouseEnter={(e) => {
        if (!disabled && !isSelected) {
          e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
          e.currentTarget.style.transform = 'scale(1.02)';
          e.currentTarget.style.boxShadow = `0 0 15px ${colors.accent}40`;
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled && !isSelected) {
          e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
          e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.15)';
          e.currentTarget.style.transform = 'scale(1)';
          e.currentTarget.style.boxShadow = 'none';
        }
      }}
    >
      {/* Selected indicator bar */}
      {isSelected && (
        <div style={{
          position: 'absolute',
          left: 0,
          top: 0,
          bottom: 0,
          width: '4px',
          background: `linear-gradient(to bottom, ${colors.accent}, ${colors.accent}dd)`,
          borderRadius: '12px 0 0 12px',
        }} />
      )}

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
        {/* Icon with background */}
        <div 
          className="transition-transform duration-300 group-hover:scale-110"
          style={{
          width: '48px',
          height: '48px',
          borderRadius: '12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '24px',
          flexShrink: 0,
          background: isSelected
            ? `linear-gradient(135deg, ${colors.accent}, ${colors.accent}aa)`
            : 'rgba(255, 255, 255, 0.1)',
          boxShadow: isSelected ? '0 4px 12px rgba(0,0,0,0.3)' : 'none',
        }}>
          {mode.icon}
        </div>

        {/* Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{
              fontWeight: 600,
              fontSize: '15px',
              color: isSelected ? '#fff' : '#e5e7eb',
            }}>
              {mode.name}
            </span>
            {mode.allowPaid && (
              <span style={{
                padding: '2px 8px',
                fontSize: '10px',
                fontWeight: 700,
                background: 'linear-gradient(135deg, rgba(251, 191, 36, 0.3), rgba(249, 115, 22, 0.3))',
                color: '#fcd34d',
                borderRadius: '9999px',
                border: '1px solid rgba(251, 191, 36, 0.4)',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}>
                💰 Paid
              </span>
            )}
            {isSelected && (
              <span style={{
                padding: '2px 8px',
                fontSize: '11px',
                fontWeight: 500,
                background: 'rgba(34, 197, 94, 0.2)',
                color: '#4ade80',
                borderRadius: '9999px',
                border: '1px solid rgba(34, 197, 94, 0.3)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}>
                <span style={{
                  width: '6px',
                  height: '6px',
                  background: '#4ade80',
                  borderRadius: '50%',
                  animation: 'pulse 2s infinite',
                }} />
                Active
              </span>
            )}
          </div>

          <p style={{
            fontSize: '13px',
            marginTop: '6px',
            lineHeight: 1.5,
            color: isSelected ? '#d1d5db' : '#9ca3af',
          }}>
            {mode.description}
          </p>

          {/* Enabled tools preview */}
          {mode.enabledTools.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
              {mode.enabledTools.slice(0, 3).map((tool) => (
                <span
                  key={tool}
                  style={{
                    padding: '4px 8px',
                    fontSize: '11px',
                    borderRadius: '6px',
                    background: isSelected ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.05)',
                    color: isSelected ? '#e5e7eb' : '#9ca3af',
                    border: `1px solid ${isSelected ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.08)'}`,
                  }}
                >
                  {tool.replace(/_/g, ' ')}
                </span>
              ))}
              {mode.enabledTools.length > 3 && (
                <span style={{ padding: '4px 8px', fontSize: '11px', color: '#6b7280' }}>
                  +{mode.enabledTools.length - 3} more
                </span>
              )}
            </div>
          )}
        </div>

        {/* Chevron for non-selected */}
        {!isSelected && (
          <div style={{ flexShrink: 0, color: '#6b7280' }}>
            <svg style={{ width: '20px', height: '20px' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        )}
      </div>
    </button>
  );
}

/**
 * Button to open settings drawer, shows current mode.
 * Features mode-specific colors and subtle animations.
 */
interface SettingsButtonProps {
  currentMode: string;
  onClick: () => void;
  compact?: boolean;
}

export function SettingsButton({ currentMode, onClick, compact }: SettingsButtonProps) {
  const { settings } = useSettings();
  const allModes = getAllModes(settings?.custom_voice_modes || []);
  const mode = allModes.find((m) => m.id === currentMode) || VOICE_MODES[0];

  // Color classes per mode
  const colorClasses: Record<string, { bg: string; border: string; text: string }> = {
    cyan: { bg: 'bg-cyan-500/15', border: 'border-cyan-500/40', text: 'text-cyan-400' },
    orange: { bg: 'bg-orange-500/15', border: 'border-orange-500/40', text: 'text-orange-400' },
    purple: { bg: 'bg-purple-500/15', border: 'border-purple-500/40', text: 'text-purple-400' },
    green: { bg: 'bg-green-500/15', border: 'border-green-500/40', text: 'text-green-400' },
    pink: { bg: 'bg-pink-500/15', border: 'border-pink-500/40', text: 'text-pink-400' },
    blue: { bg: 'bg-blue-500/15', border: 'border-blue-500/40', text: 'text-blue-400' },
    red: { bg: 'bg-red-500/15', border: 'border-red-500/40', text: 'text-red-400' },
    yellow: { bg: 'bg-yellow-500/15', border: 'border-yellow-500/40', text: 'text-yellow-400' },
  };

  const colors = colorClasses[mode.color] || colorClasses.cyan;

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-2 rounded-xl ${colors.bg} border ${colors.border} hover:scale-105 active:scale-95 transition-all duration-200 group`}
      title="Voice Mode Settings"
    >
      <span className="text-lg">{mode.icon}</span>
      {!compact && (
        <span className={`text-sm font-medium ${colors.text}`}>{mode.name}</span>
      )}
      <svg
        className="w-4 h-4 text-gray-400 group-hover:text-white group-hover:rotate-90 transition-all duration-300"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    </button>
  );
}
