import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useVoiceStream } from '../../hooks/useVoiceStream';
import { useAudioCapture } from '../../hooks/useAudioCapture';
import { useAudioAnalyzer } from '../../hooks/useAudioAnalyzer';
import { useSettings } from '../../hooks/useSettings';
import { useWindowSize } from '../../hooks/useWindowSize';
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
  const [showDebug, setShowDebug] = useState(false);

  // Voice Logic
  const voiceStream = useVoiceStream({ customModes: settings?.custom_voice_modes || [] });
  const { 
    status, transcript, response, connect, disconnect, 
    sendAudio, sendText, endAudio, toolExecutions, 
    mode, setMode, capabilities, preferLocal, setPreferLocal,
    wakeWordEnabled, toggleWakeWord, tier
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
    const input = (e.target as HTMLFormElement).querySelector('input') as HTMLInputElement;
    if (input.value.trim()) {
        sendText(input.value.trim());
        input.value = '';
    }
  };

  const currentModeConfig = getModeById(mode);

  // --- Layout Components ---

  const Header = (
    <div className="flex items-center justify-between w-full px-8 py-4">
      <div className="flex items-center gap-8">
        {/* Minimal Logo */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-teal-500/10 rounded-lg flex items-center justify-center border border-teal-500/20">
            <span className="text-sm">◉</span>
          </div>
          <h1 className="text-sm font-semibold tracking-wide text-zinc-300">KITTY</h1>
        </div>

        {/* Conversation Context (Desktop) */}
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
      <div className="flex items-center gap-4">
        <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setHistoryOpen(!isHistoryOpen)}
            color={isHistoryOpen ? 'primary' : 'surface'}
        >
            History
        </Button>
        <Button 
            variant="ghost" 
            size="sm" 
            onClick={() => setSettingsOpen(true)}
            color="surface"
        >
            Settings
        </Button>
        {onClose && (
          <Button variant="ghost" size="sm" onClick={onClose} color="error" className="w-8 h-8 p-0 rounded-full">
            ✕
          </Button>
        )}
      </div>
    </div>
  );

  const Sidebar = isHistoryOpen ? (
    <div className="h-full flex flex-col min-w-[300px] bg-zinc-900/50">
      <div className="p-6 border-b border-white/5">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Recent Activity</h3>
      </div>
      <div className="flex-1 overflow-hidden p-4">
        <ConversationPanel messages={messages} compact />
      </div>
    </div>
  ) : null;

  const RightPanel = (
    <div className="h-full flex flex-col p-6 gap-8 min-w-[320px] overflow-y-auto">
        {/* Mission Control Header */}
        <div>
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-4">Control Center</h3>
            
            {/* Status Cards */}
            <div className="grid grid-cols-2 gap-3 mb-6">
                <div className="bg-zinc-800/50 rounded-xl p-3 border border-white/5">
                    <div className="text-[10px] text-zinc-500 mb-1 font-medium">STATUS</div>
                    <StatusBadge status={status as any} compact />
                </div>
                <div className="bg-zinc-800/50 rounded-xl p-3 border border-white/5">
                    <div className="text-[10px] text-zinc-500 mb-1 font-medium">COMPUTE</div>
                    <div className="text-xs font-medium text-teal-400">{tier || 'LOCAL'}</div>
                </div>
            </div>
        </div>

        {/* Current Mode */}
        <div className="space-y-3">
            <div className="flex justify-between items-center">
                <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">Active Mode</span>
                <button onClick={() => setSettingsOpen(true)} className="text-[10px] text-teal-400 hover:text-teal-300 font-medium transition-colors">CHANGE</button>
            </div>
            
            <div className="bg-zinc-800/30 rounded-xl border border-white/5 p-4 flex items-start gap-4">
                <span className="text-2xl">{currentModeConfig?.icon}</span>
                <div>
                    <h3 className="text-sm font-medium text-zinc-200">{currentModeConfig?.name}</h3>
                    <p className="text-xs text-zinc-500 mt-1">{currentModeConfig?.description}</p>
                </div>
            </div>
        </div>

        {/* Active Processes */}
        <div className="flex-1 min-h-[200px] flex flex-col">
            <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest mb-4">Running Tasks</h3>
            
            <div className="flex-1 rounded-2xl bg-zinc-900/30 border border-white/5 overflow-hidden">
                {toolExecutions.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-zinc-700 gap-2">
                        <span className="text-xl opacity-20">⚡</span>
                        <span className="text-xs font-medium">System Idle</span>
                    </div>
                ) : (
                    <div className="p-2 h-full overflow-y-auto">
                        <ToolExecutionList tools={toolExecutions} compact />
                    </div>
                )}
            </div>
        </div>

        {/* System Details Toggle */}
        <div className="mt-auto">
            <button 
                onClick={() => setShowDebug(!showDebug)}
                className="flex items-center justify-between w-full py-3 text-xs font-medium text-zinc-600 hover:text-zinc-400 transition-colors border-t border-white/5"
            >
                <span>Technical Telemetry</span>
                <span>{showDebug ? '−' : '+'}</span>
            </button>
            
            <AnimatePresence>
                {showDebug && (
                    <motion.div 
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden"
                    >
                        <div className="pt-2 pb-4 grid grid-cols-2 gap-4">
                            <div>
                                <span className="text-[9px] text-zinc-600 block mb-1">LATENCY</span>
                                <span className="text-xs font-mono text-zinc-400">24ms</span>
                            </div>
                            <div>
                                <span className="text-[9px] text-zinc-600 block mb-1">AUDIO IN</span>
                                <InputLevelMeter level={inputLevel} active={isCapturing} compact />
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    </div>
  );

  const MainContent = (
    <div className="flex flex-col h-full w-full max-w-3xl mx-auto relative px-6">
      
      {/* Center Stage */}
      <div className="flex-1 flex flex-col items-center justify-center relative min-h-[400px]">
        
        {/* Transcript / Content */}
        <AnimatePresence mode="wait">
            {(transcript || response) ? (
                <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    className="w-full z-10 flex flex-col gap-8 mb-12"
                >
                    {transcript && (
                        <div className="text-center">
                            <h2 className="text-2xl md:text-3xl font-light text-zinc-300 leading-tight">
                                "{transcript}"
                            </h2>
                        </div>
                    )}
                    
                    {response && (
                        <div className="w-full bg-zinc-900/50 backdrop-blur-xl border border-white/5 rounded-2xl p-8 shadow-2xl">
                            <div className="flex items-center gap-2 mb-4">
                                <div className="w-6 h-6 rounded-full bg-teal-500/10 flex items-center justify-center">
                                    <span className="text-[10px]">🤖</span>
                                </div>
                                <span className="text-xs font-semibold text-teal-500 uppercase tracking-widest">Assistant</span>
                            </div>
                            <p className="text-lg text-zinc-200 font-light leading-relaxed whitespace-pre-wrap">
                                {response}
                            </p>
                        </div>
                    )}
                </motion.div>
            ) : (
                // Idle State - Large Visualizer
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 flex items-center justify-center"
                >
                    <AudioVisualizer 
                        fftData={fftData} 
                        audioLevel={audioLevel} 
                        status={status === 'listening' ? 'listening' : status === 'responding' ? 'responding' : 'idle'} 
                        enable3D={true}
                        size={isDesktop ? 400 : 300}
                        modeColor={currentModeConfig?.color as any}
                    />
                </motion.div>
            )}
        </AnimatePresence>

        {/* Minimized Visualizer (When content is present) */}
        {(transcript || response) && (
            <div className="absolute bottom-32 opacity-30 blur-[2px] pointer-events-none transform scale-75">
                <AudioVisualizer 
                    fftData={fftData} 
                    audioLevel={audioLevel} 
                    status={status === 'listening' ? 'listening' : status === 'responding' ? 'responding' : 'idle'} 
                    enable3D={false}
                    size={200}
                    modeColor={currentModeConfig?.color as any}
                />
            </div>
        )}
      </div>

      {/* Input Deck */}
      <div className="shrink-0 pb-12 w-full z-20">
        <div className="flex flex-col items-center gap-6">
            
            {/* Input Type Toggle */}
            <div className="flex p-1 bg-zinc-900/50 rounded-full border border-white/5">
                <button 
                    onClick={() => setInputType('voice')}
                    className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all ${
                        inputType === 'voice' ? 'bg-zinc-800 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                >
                    Voice
                </button>
                <button 
                    onClick={() => setInputType('text')}
                    className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all ${
                        inputType === 'text' ? 'bg-zinc-800 text-white shadow-sm' : 'text-zinc-500 hover:text-zinc-300'
                    }`}
                >
                    Keyboard
                </button>
            </div>

            {/* Controls */}
            <div className="w-full relative h-20 flex items-center justify-center">
                <AnimatePresence mode="wait">
                    {inputType === 'voice' ? (
                        <motion.div
                            key="voice"
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            className="absolute inset-0 flex items-center justify-center"
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
                                    h-16 px-8 rounded-full font-bold tracking-widest text-sm shadow-xl
                                    ${isCapturing ? 'scale-110 bg-red-500' : 'bg-teal-500 hover:bg-teal-400'}
                                `}
                                disabled={status === 'disconnected'}
                            >
                                {isCapturing ? 'LISTENING...' : 'PUSH TO TALK'}
                            </Button>
                        </motion.div>
                    ) : (
                        <motion.div
                            key="text"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: 10 }}
                            className="w-full max-w-xl"
                        >
                            <form onSubmit={handleTextSubmit} className="relative">
                                <Input
                                    placeholder="Type a command..." 
                                    fullWidth 
                                    className="h-14 pl-6 pr-12 rounded-2xl bg-zinc-900/80 border-white/10 text-lg focus:border-teal-500/50"
                                    disabled={status === 'disconnected'}
                                    autoFocus
                                />
                                <button
                                    type="submit"
                                    className="absolute right-3 top-1/2 -translate-y-1/2 p-2 text-zinc-500 hover:text-teal-400 transition-colors"
                                >
                                    ↵
                                </button>
                            </form>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Micro Controls */}
            <div className="flex gap-6 text-[10px] font-medium tracking-widest text-zinc-500">
                <button onClick={() => toggleWakeWord()} className={`hover:text-zinc-300 transition-colors ${wakeWordEnabled ? 'text-teal-500' : ''}`}>
                    WAKE WORD: {wakeWordEnabled ? 'ON' : 'OFF'}
                </button>
                <button onClick={() => setPreferLocal(!preferLocal)} className="hover:text-zinc-300 transition-colors">
                    MODE: {preferLocal ? 'LOCAL' : 'CLOUD'}
                </button>
            </div>
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
        className="font-sans antialiased selection:bg-teal-500/30 text-zinc-100"
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