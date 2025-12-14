import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useVoiceStream } from '../../hooks/useVoiceStream';
import { useAudioCapture } from '../../hooks/useAudioCapture';
import { useAudioAnalyzer } from '../../hooks/useAudioAnalyzer';
import { useSettings } from '../../hooks/useSettings';
import { useWindowSize } from '../../hooks/useWindowSize';
import { useTypingActivity } from '../../hooks/useTypingActivity';
import { useVoiceStore } from './store/voiceStore';

// Atomic Components
import { MainLayout } from './templates/MainLayout';
import { AudioVisualizer } from './AudioVisualizer';
import { SettingsDrawer } from './SettingsDrawer';
import { Button } from '../../design-system/Button';
import { Input } from '../../design-system/Input';
import { StatusBadge } from './StatusBadge';
import { ToolExecutionList } from './ToolExecutionCard';
import { ConversationPanel } from './ConversationPanel';
import { ConversationSelector } from './ConversationSelector';
import { HUDFrame, HUDLabel, HUDDivider } from './HUDFrame';
import { InputLevelMeter } from './InputLevelMeter';
import { useConversations } from '../../hooks/useConversations';
import { useConversationApi } from '../../hooks/useConversationApi';
import { getModeById, SYSTEM_MODES } from '../../types/voiceModes';

export function VoiceAssistant({
  initialConversationId,
  userId = 'anonymous',
  onClose,
  fullscreen = false,
}: any) {
  // Global State
  const { isSettingsOpen, setSettingsOpen, isHistoryOpen, setHistoryOpen } = useVoiceStore();
  const { isMobile, isDesktop } = useWindowSize();
  const { settings } = useSettings();

  // Local State
  const [conversationId, setConversationId] = useState<string>(
    initialConversationId || crypto.randomUUID()
  );
  const [inputType, setInputType] = useState<'voice' | 'text'>('voice');
  const [textInput, setTextInput] = useState('');
  const [showDebug, setShowDebug] = useState(false);

  // Typing Activity Hook
  const { typingLevel, trigger: triggerTyping } = useTypingActivity(300);

  // Voice Logic
  const voiceStream = useVoiceStream({ customModes: settings?.custom_voice_modes || [] });
  const {
    status, transcript, response, connect, disconnect,
    sendAudio, sendText, endAudio, toolExecutions,
    mode, setMode, capabilities, preferLocal, setPreferLocal,
    wakeWordEnabled, toggleWakeWord, tier, ttsProvider
  } = voiceStream;
  
  // Audio Logic
  const audioCapture = useAudioCapture({ sampleRate: 16000, onAudioChunk: sendAudio });
  const { isCapturing, startCapture, stopCapture, stream, inputLevel } = audioCapture;
  const { fftData, audioLevel } = useAudioAnalyzer(stream);

  // Conversation Logic
  const { messages, clearMessages, createConversation } = useConversations();
  const { 
    conversations: savedConversations, 
    isLoading: isLoadingConversations,
    fetchConversations, 
    fetchMessages,
    renameConversation,
    deleteConversation 
  } = useConversationApi();

  useEffect(() => {
    fetchConversations();
    connect({ conversationId, userId });
    return () => disconnect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    const newId = crypto.randomUUID();
    setConversationId(newId);
    clearMessages();
    createConversation(`Voice Session ${new Date().toLocaleTimeString()}`);
    disconnect();
    setTimeout(() => connect({ conversationId: newId, userId }), 100);
  }, [clearMessages, createConversation, connect, disconnect, userId]);

  // Handle conversation switch
  const handleSelectConversation = useCallback((id: string) => {
    if (id === conversationId) return;
    setConversationId(id);
    clearMessages();
    disconnect();
    fetchMessages(id).then(() => {
        connect({ conversationId: id, userId });
    });
  }, [conversationId, clearMessages, connect, disconnect, userId, fetchMessages]);

  const handleTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (textInput.trim()) {
        sendText(textInput.trim());
        setTextInput('');
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTextInput(e.target.value);
    triggerTyping();
  };

  const currentModeConfig = getModeById(mode);

  // --- Layout Components ---

  const Header = (
    <div className="flex items-center justify-between w-full px-6 py-2">
      <div className="flex items-center gap-6">
        {/* Logo & Status */}
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-500 ${status === 'listening' ? 'bg-cyan-500 shadow-lg shadow-cyan-500/50 scale-110' : 'bg-gray-800'}`}>
            <span className="text-lg">🐱</span>
          </div>
          <div>
            <h1 className="text-xs font-bold tracking-widest text-white uppercase">KITTY <span className="text-cyan-400">OS</span></h1>
            <div className="flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full ${status === 'connected' ? 'bg-green-400' : 'bg-red-500'}`} />
                <span className="text-[9px] font-mono text-gray-500 uppercase">{status}</span>
            </div>
          </div>
        </div>

        {/* Conversation Context */}
        {!isMobile && (
          <div className="w-64 opacity-50 hover:opacity-100 transition-opacity">
            <ConversationSelector
                conversations={savedConversations}
                currentId={conversationId}
                onSelect={handleSelectConversation}
                onNew={handleNewConversation}
                onRename={renameConversation}
                onDelete={deleteConversation}
                isLoading={isLoadingConversations}
            />
          </div>
        )}
      </div>

      {/* Global Actions */}
      <div className="flex items-center gap-2">
        <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setHistoryOpen(!isHistoryOpen)}
            color={isHistoryOpen ? 'primary' : 'surface'}
            className="text-xs uppercase tracking-wider"
        >
            Logs
        </Button>
        <div className="h-4 w-px bg-white/10 mx-1" />
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose} color="error" className="w-8 h-8 p-0 rounded-full">
            ✕
          </Button>
        )}
      </div>
    </div>
  );

  const Sidebar = isHistoryOpen ? (
    <div className="h-full flex flex-col min-w-[300px] bg-black/40">
      <div className="p-4 border-b border-white/5">
        <HUDLabel icon="📜">SESSION LOGS</HUDLabel>
      </div>
      <div className="flex-1 overflow-hidden p-2">
        <ConversationPanel messages={messages} compact />
      </div>
    </div>
  ) : null;

  const RightPanel = (
    <div className="h-full flex flex-col p-6 gap-6 min-w-[320px] overflow-y-auto">
        {/* Mission Control Header */}
        <div>
            <HUDLabel icon="🛸">MISSION CONTROL</HUDLabel>
            <HUDDivider accent />
        </div>

        {/* Current Mode Card */}
        <div className="space-y-2">
            <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Active Protocol</span>
            <div className={`
                relative overflow-hidden rounded-xl border p-4 transition-all duration-300
                ${currentModeConfig?.bgClass} ${currentModeConfig?.borderClass}
            `}>
                <div className="flex justify-between items-start">
                    <div className="flex gap-3">
                        <span className="text-2xl">{currentModeConfig?.icon}</span>
                        <div>
                            <h3 className="font-bold text-white">{currentModeConfig?.name}</h3>
                            <p className="text-xs text-gray-400 mt-1 leading-relaxed">{currentModeConfig?.description}</p>
                        </div>
                    </div>
                    <Button 
                        variant="ghost" 
                        size="sm" 
                        onClick={() => setSettingsOpen(true)}
                        className="h-6 px-2 text-[10px] bg-black/20 hover:bg-black/40"
                    >
                        CHANGE
                    </Button>
                </div>
                
                {/* Active Tools List in Mode Card */}
                {currentModeConfig?.enabledTools && currentModeConfig.enabledTools.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                        {currentModeConfig.enabledTools.slice(0, 3).map(tool => (
                            <span key={tool} className="text-[9px] px-1.5 py-0.5 rounded bg-black/20 text-white/70 border border-white/5">
                                {tool.replace(/_/g, ' ')}
                            </span>
                        ))}
                        {currentModeConfig.enabledTools.length > 3 && (
                            <span className="text-[9px] px-1.5 py-0.5 text-white/50">+{currentModeConfig.enabledTools.length - 3}</span>
                        )}
                    </div>
                )}
            </div>
        </div>

        {/* Active Processes */}
        <div className="flex-1 min-h-[200px] flex flex-col">
            <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Runtime Tasks</span>
                {toolExecutions.length > 0 && <span className="text-[9px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded animate-pulse">ACTIVE</span>}
            </div>
            
            <div className="flex-1 rounded-xl bg-gray-900/30 border border-white/5 overflow-hidden">
                {toolExecutions.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-gray-600 gap-2">
                        <span className="text-xl opacity-20">⚡</span>
                        <span className="text-xs">System Idle</span>
                    </div>
                ) : (
                    <div className="p-2 h-full overflow-y-auto">
                        <ToolExecutionList tools={toolExecutions} compact />
                    </div>
                )}
            </div>
        </div>

        {/* System Vitals (Collapsible) */}
        <div className="space-y-2">
            <button 
                onClick={() => setShowDebug(!showDebug)}
                className="flex items-center justify-between w-full text-[10px] font-bold text-gray-500 uppercase tracking-widest hover:text-cyan-400 transition-colors"
            >
                <span>System Vitals</span>
                <span>{showDebug ? '▼' : '▶'}</span>
            </button>
            
            <AnimatePresence>
                {showDebug && (
                    <motion.div 
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="space-y-2 overflow-hidden"
                    >
                        <HUDFrame color="gray" className="p-3 bg-black/40">
                            <div className="grid grid-cols-2 gap-y-3 gap-x-4">
                                {/* Row 1: Processing */}
                                <div className="flex flex-col">
                                    <span className="text-[9px] text-gray-500">TIER</span>
                                    <span className="text-xs font-mono text-purple-400">{tier?.toUpperCase() || 'LOCAL'}</span>
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-[9px] text-gray-500">STT</span>
                                    <span className={`text-xs font-mono ${capabilities.stt ? 'text-green-400' : 'text-gray-600'}`}>
                                        {capabilities.stt ? 'WHISPER' : 'OFFLINE'}
                                    </span>
                                </div>

                                {/* Row 2: Audio I/O */}
                                <div className="flex flex-col">
                                    <span className="text-[9px] text-gray-500">AUDIO IN</span>
                                    <InputLevelMeter level={inputLevel} active={isCapturing} compact />
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-[9px] text-gray-500">AUDIO OUT</span>
                                    <span className={`text-xs font-mono ${capabilities.tts ? 'text-cyan-400' : 'text-gray-600'}`}>
                                        {ttsProvider?.toUpperCase() || (capabilities.tts ? 'TTS' : 'MUTED')}
                                    </span>
                                </div>

                                {/* Row 3: Wake Word with Toggle */}
                                <div className="col-span-2">
                                    <div className="flex items-center justify-between">
                                        <span className="text-[9px] text-gray-500">WAKE WORD</span>
                                        <button
                                            onClick={() => toggleWakeWord()}
                                            disabled={!capabilities.wakeWord}
                                            className={`
                                                text-[9px] px-2 py-0.5 rounded transition-all
                                                ${!capabilities.wakeWord
                                                    ? 'bg-gray-800 text-gray-600 cursor-not-allowed'
                                                    : wakeWordEnabled
                                                        ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                                                        : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                                                }
                                            `}
                                        >
                                            {!capabilities.wakeWord ? 'UNAVAILABLE' : wakeWordEnabled ? 'ON' : 'OFF'}
                                        </button>
                                    </div>
                                    {capabilities.wakeWord && (
                                        <span className="text-[8px] text-gray-600 mt-1 block">
                                            Say "Hey Kitty" to activate
                                        </span>
                                    )}
                                    {!capabilities.wakeWord && (
                                        <span className="text-[8px] text-gray-600 mt-1 block">
                                            Enable in .env: WAKE_WORD_ENABLED=true
                                        </span>
                                    )}
                                </div>
                            </div>
                        </HUDFrame>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    </div>
  );

  const MainContent = (
    <div className="flex flex-col h-full w-full max-w-4xl mx-auto relative">
      
      {/* Visualizer Stage */}
      <div className="flex-1 flex flex-col items-center justify-center relative min-h-[300px]">
        
        {/* Ambient Glow */}
        <div className={`absolute inset-0 bg-gradient-to-b from-${currentModeConfig?.color}-500/5 via-transparent to-transparent pointer-events-none transition-colors duration-1000`} />

        {/* Teleprompter Transcript */}
        <AnimatePresence mode="wait">
            {(transcript || response) && (
                <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    className="absolute top-[15%] w-full px-8 z-10 flex flex-col items-center gap-8"
                >
                    {transcript && (
                        <h2 className="text-3xl md:text-4xl font-light text-white/90 text-center leading-tight tracking-tight max-w-2xl drop-shadow-2xl">
                            "{transcript}"
                        </h2>
                    )}
                    {response && (
                        <div className="w-full max-w-2xl bg-gray-900/60 backdrop-blur-xl border border-white/10 rounded-2xl p-6 shadow-2xl">
                            <div className="flex items-center gap-2 mb-3 border-b border-white/5 pb-2">
                                <span className="text-cyan-400 text-xs font-bold uppercase tracking-widest">KITTY AI</span>
                                {status === 'responding' && <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />}
                            </div>
                            <p className="text-lg text-gray-100 font-light leading-relaxed whitespace-pre-wrap">
                                {response}
                            </p>
                        </div>
                    )}
                </motion.div>
            )}
        </AnimatePresence>

        {/* Visualizer */}
        <div className={`transition-all duration-1000 ease-[cubic-bezier(0.23,1,0.32,1)] ${transcript || response ? 'translate-y-40 scale-75 opacity-40 blur-sm' : 'translate-y-0 scale-110 opacity-100'}`}>
            <AudioVisualizer 
                fftData={fftData} 
                audioLevel={audioLevel} 
                // Pass typingLevel as an override/addition to audioLevel
                typingLevel={typingLevel}
                status={status === 'listening' ? 'listening' : status === 'responding' ? 'responding' : 'idle'} 
                enable3D={true}
                size={isDesktop ? 420 : 300}
                modeColor={currentModeConfig?.color as any}
            />
        </div>
      </div>

      {/* Input / Command Deck */}
      <div className="shrink-0 pb-12 w-full max-w-xl mx-auto z-20 px-4">
        
        {/* Toggle Bar */}
        <div className="flex justify-center mb-4 gap-4">
            <button 
                onClick={() => setInputType('voice')}
                className={`text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-full transition-all ${inputType === 'voice' ? 'bg-white/10 text-white' : 'text-gray-600 hover:text-gray-400'}`}
            >
                Voice
            </button>
            <button 
                onClick={() => setInputType('text')}
                className={`text-xs font-bold uppercase tracking-widest px-4 py-2 rounded-full transition-all ${inputType === 'text' ? 'bg-white/10 text-white' : 'text-gray-600 hover:text-gray-400'}`}
            >
                Terminal
            </button>
        </div>

        <div className="relative">
            <AnimatePresence mode="wait">
                {inputType === 'voice' ? (
                    <motion.div
                        key="voice-input"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.2 }}
                        className="flex flex-col items-center gap-4"
                    >
                        <Button
                            size="lg"
                            glow={isCapturing}
                            color={isCapturing ? 'error' : 'primary'}
                            onMouseDown={startCapture}
                            onMouseUp={() => { stopCapture(); endAudio(); }}
                            onTouchStart={startCapture}
                            onTouchEnd={() => { stopCapture(); endAudio(); }}
                            className={`
                                h-20 w-20 rounded-full flex items-center justify-center transition-all duration-300
                                ${isCapturing ? 'scale-110 shadow-[0_0_50px_rgba(239,68,68,0.4)]' : 'shadow-[0_0_30px_rgba(6,182,212,0.2)] hover:scale-105'}
                            `}
                            disabled={status === 'disconnected'}
                        >
                            <span className="text-3xl">{isCapturing ? '🎙️' : '🎤'}</span>
                        </Button>
                        <span className="text-[10px] text-gray-500 font-mono uppercase tracking-[0.2em] animate-pulse">
                            {isCapturing ? 'Transmitting Audio Data...' : 'Hold to Speak'}
                        </span>
                    </motion.div>
                ) : (
                    <motion.div
                        key="text-input"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        transition={{ duration: 0.2 }}
                        className="bg-black/60 backdrop-blur-xl rounded-2xl border border-white/10 p-2 shadow-2xl"
                    >
                        <form onSubmit={handleTextSubmit} className="flex gap-2">
                            <Input
                                value={textInput}
                                onChange={handleInputChange}
                                placeholder="Type a command..." 
                                fullWidth 
                                className="bg-transparent border-none text-lg h-12 focus:ring-0 px-4 font-mono text-cyan-300"
                                disabled={status === 'disconnected'}
                                autoFocus
                            />
                            <Button type="submit" variant="ghost" className="text-cyan-400">
                                ↵
                            </Button>
                        </form>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <MainLayout
        header={Header}
        sidebar={isHistoryOpen ? Sidebar : undefined}
        rightPanel={RightPanel}
        content={MainContent}
        className="font-sans antialiased selection:bg-cyan-500/30"
      />
      
      <SettingsDrawer
        isOpen={isSettingsOpen}
        onClose={() => setSettingsOpen(false)}
        currentMode={voiceStream.mode}
        onModeChange={voiceStream.setMode}
        isConnected={status === 'connected'}
      />
    </>
  );
}