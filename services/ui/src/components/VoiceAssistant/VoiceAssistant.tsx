import { useEffect, useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useVoiceStream } from '../../hooks/useVoiceStream';
import { useAudioCapture } from '../../hooks/useAudioCapture';
import { useAudioAnalyzer } from '../../hooks/useAudioAnalyzer';
import { useSettings } from '../../hooks/useSettings';
import { useWindowSize } from '../../hooks/useWindowSize';
import { useTypingActivity } from '../../hooks/useTypingActivity';
import { useVoiceStore } from './store/voiceStore';
import { generateId } from '../../utils/user';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Layout
import { VoiceLayout } from './layout/VoiceLayout';

// Components
import { AudioVisualizer } from './AudioVisualizer';
import { SettingsDrawer } from './SettingsDrawer';
import { Button } from '../../design-system/Button';
import { Input } from '../../design-system/Input';
import { ToolExecutionList } from './ToolExecutionCard';
import { ConversationPanel } from './ConversationPanel';
import { ConversationSelector } from './ConversationSelector';
import { ConversationSidebar } from './ConversationSidebar';
import { HUDLabel, HUDDivider } from './HUDFrame';
import { InputLevelMeter } from './InputLevelMeter';
import { useConversations } from '../../hooks/useConversations';
import { useConversationApi } from '../../hooks/useConversationApi';
import { getModeById } from '../../types/voiceModes';

export function VoiceAssistant({
  initialConversationId,
  userId = 'anonymous',
  onClose,
  fullscreen = false,
  onStatusChange,
}: any) {
  // Global State
  const { isSettingsOpen, setSettingsOpen, isHistoryOpen, setHistoryOpen } = useVoiceStore();
  const { isMobile } = useWindowSize();
  const { settings } = useSettings();

  // Local State
  const [conversationId, setConversationId] = useState<string>(
    initialConversationId || generateId()
  );
  const [inputType, setInputType] = useState<'voice' | 'text'>('voice');
  const [textInput, setTextInput] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [controlsOpen, setControlsOpen] = useState(true); // Collapsible Status Column
  const [pendingMicStart, setPendingMicStart] = useState(false);

  // Hooks
  const { typingLevel, trigger: triggerTyping } = useTypingActivity(300);

  // Voice Logic
  const voiceStream = useVoiceStream({ customModes: settings?.custom_voice_modes || [] });
  const {
    status, transcript, response, connect, disconnect,
    sendAudio, sendText, endAudio, toolExecutions,
    mode, setMode, capabilities, preferLocal, wakeWordEnabled, toggleWakeWord, tier, ttsProvider,
    updateVoiceConfig
  } = voiceStream;
  
  // Audio Logic
  const audioCapture = useAudioCapture({ sampleRate: 16000, onAudioChunk: sendAudio });
  const { isCapturing, startCapture, stopCapture, stream, inputLevel } = audioCapture;
  const { fftData, audioLevel } = useAudioAnalyzer(stream);
  const [captureError, setCaptureError] = useState<string | null>(null);
  const lastSpeechRef = useRef<number>(0);
  const silenceTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoStopEnabled = settings?.voice?.auto_stop_enabled ?? true;
  const autoStopMs = settings?.voice?.auto_stop_silence_ms ?? 1400;
  const autoStopLevel = settings?.voice?.auto_stop_level ?? 0.08;
  const [processingSince, setProcessingSince] = useState<number | null>(null);
  const [processingElapsedMs, setProcessingElapsedMs] = useState<number>(0);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [reconnectError, setReconnectError] = useState<string | null>(null);
  const quickPrompts = [
    'Summarize this URL',
    'What happened in the last 24h on X for <topic>?',
    'Outline steps to fix my build error',
    'Create a 3-bullet daily plan',
  ];

  // Conversation Logic
  const { messages, clearMessages, createConversation, loadMessages, addUserMessage, addAssistantMessage } = useConversations();
  const { 
    conversations: savedConversations, 
    isLoading: isLoadingConversations,
    error: conversationsError,
    fetchConversations, 
    fetchMessages,
    renameConversation,
    deleteConversation 
  } = useConversationApi();

  useEffect(() => {
    fetchConversations();

    // Ensure voice service is running before connecting
    const ensureVoiceServiceAndConnect = async () => {
      try {
        // Try to ensure voice service is running via service manager
        const response = await fetch('/api/services/voice/ensure', { method: 'POST' });
        if (!response.ok) {
          console.warn('Failed to ensure voice service is running:', response.status);
        }
        // Wait a moment for service to be ready
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (err) {
        console.warn('Could not contact service manager to start voice service:', err);
      }

      // Connect regardless - WebSocket will retry if service isn't ready yet
      connect({
        conversationId,
        userId,
        voice: settings?.voice?.voice || 'bf_emma',
        speed: settings?.voice?.speed || 1.1,
      });
    };

    ensureVoiceServiceAndConnect();
    return () => disconnect();
  }, []);

  // Update voice config when settings change (live update without reconnect)
  const prevVoiceRef = useRef(settings?.voice?.voice);
  const prevSpeedRef = useRef(settings?.voice?.speed);
  useEffect(() => {
    const currentVoice = settings?.voice?.voice;
    const currentSpeed = settings?.voice?.speed;

    // Only send update if values actually changed (not on mount)
    if (prevVoiceRef.current !== currentVoice || prevSpeedRef.current !== currentSpeed) {
      updateVoiceConfig({
        voice: currentVoice || 'bf_emma',
        speed: currentSpeed ?? 1.1,
      });
      prevVoiceRef.current = currentVoice;
      prevSpeedRef.current = currentSpeed;
    }
  }, [settings?.voice?.voice, settings?.voice?.speed, updateVoiceConfig]); 

  // Auto-scroll logic
  const scrollViewportRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const handleScroll = useCallback(() => {
    if (!scrollViewportRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollViewportRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
    setUserScrolledUp(!isAtBottom);
    setShowScrollButton(!isAtBottom);
  }, []);

  const scrollToBottom = useCallback((smooth = true) => {
    if (scrollViewportRef.current) {
        scrollViewportRef.current.scrollTo({
            top: scrollViewportRef.current.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
        setUserScrolledUp(false);
        setShowScrollButton(false);
    }
  }, []);

  useEffect(() => {
    if (!userScrolledUp) {
        scrollToBottom();
    }
  }, [messages.length, transcript, response, userScrolledUp, scrollToBottom]);

  useEffect(() => {
    setUserScrolledUp(false);
    setShowScrollButton(false);
    setTimeout(() => scrollToBottom(false), 50);
  }, [conversationId, scrollToBottom]);

  useEffect(() => {
    onStatusChange?.(status);
    // Clear reconnect error when successfully connected
    if (status === 'connected') {
      setReconnectError(null);
      setIsReconnecting(false);
    }
  }, [status, onStatusChange]);

  // Track processing timer when responding
  useEffect(() => {
    const shouldProcess =
      status === 'responding' ||
      (status === 'listening' && !isCapturing);

    if (shouldProcess) {
      setProcessingSince((prev) => prev ?? Date.now());
    } else if (status === 'connected' || status === 'disconnected' || status === 'error') {
      setProcessingSince(null);
      setProcessingElapsedMs(0);
    }
  }, [status, isCapturing]);

  useEffect(() => {
    if (!processingSince) return;
    const interval = setInterval(() => {
      setProcessingElapsedMs(Date.now() - processingSince);
    }, 1000);
    return () => clearInterval(interval);
  }, [processingSince]);

  // Handlers
  const handleNewConversation = useCallback(() => {
    const newId = generateId();
    setConversationId(newId);
    clearMessages();
    createConversation(`Voice Session ${new Date().toLocaleTimeString()}`);
    disconnect();
    setTimeout(() => connect({
      conversationId: newId,
      userId,
      voice: settings?.voice?.voice || 'bf_emma',
      speed: settings?.voice?.speed || 1.1,
    }), 100);
  }, [clearMessages, createConversation, connect, disconnect, userId, settings?.voice?.voice, settings?.voice?.speed]);

  const handleSelectConversation = useCallback(async (id: string) => {
    if (id === conversationId) return;
    setConversationId(id);
    clearMessages();
    disconnect();
    const loadedMessages = await fetchMessages(id);
    if (loadedMessages && loadedMessages.length > 0) {
      loadMessages(loadedMessages);
    }
    connect({
      conversationId: id,
      userId,
      voice: settings?.voice?.voice || 'bf_emma',
      speed: settings?.voice?.speed || 1.1,
    });
  }, [conversationId, clearMessages, connect, disconnect, userId, fetchMessages, loadMessages, settings?.voice?.voice, settings?.voice?.speed]);

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
  const formatDuration = useCallback((ms: number) => {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  }, []);
  const isLongInference = processingElapsedMs > 60000;

  // --- Voice Controls ---
  const startListening = useCallback(async () => {
    lastSpeechRef.current = Date.now();
    try {
      await startCapture();
      setCaptureError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unable to start microphone';
      setCaptureError(message);
      console.error('Unable to start capture', err);
    }
  }, [startCapture]);

  const stopListening = useCallback(() => {
    stopCapture();
    endAudio();
  }, [stopCapture, endAudio]);

  const handleMicToggle = useCallback(() => {
    if (isCapturing) {
      stopListening();
      return;
    }
    // If socket is down, connect first and start after connected
    if (status === 'disconnected' || status === 'error') {
      setPendingMicStart(true);
      connect({
        conversationId,
        userId,
        voice: settings?.voice?.voice || 'bf_emma',
        speed: settings?.voice?.speed || 1.1,
      });
      return;
    }
    startListening();
  }, [isCapturing, startListening, stopListening, status, connect, conversationId, userId, settings?.voice?.voice, settings?.voice?.speed]);

  // If we tried to start while disconnected, start capture once socket connects
  useEffect(() => {
    if (pendingMicStart && status === 'connected' && !isCapturing) {
      setPendingMicStart(false);
      startListening();
    }
    if (status === 'error') {
      setPendingMicStart(false);
    }
  }, [pendingMicStart, status, isCapturing, startListening]);

  // Auto-stop when silence is detected after speech
  useEffect(() => {
    if (!autoStopEnabled || !isCapturing) {
      if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current);
      return;
    }

    // Refresh last speech timestamp on voice energy
    if (inputLevel > autoStopLevel) {
      lastSpeechRef.current = Date.now();
    }

    if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current);
    silenceTimeoutRef.current = setTimeout(() => {
      const silenceDuration = Date.now() - lastSpeechRef.current;
      if (isCapturing && silenceDuration >= autoStopMs) {
        stopListening();
      }
    }, autoStopMs + 100);

    return () => {
      if (silenceTimeoutRef.current) clearTimeout(silenceTimeoutRef.current);
    };
  }, [inputLevel, isCapturing, stopListening, autoStopEnabled, autoStopMs, autoStopLevel]);

  // --- UI SECTIONS ---

  // 1. Header
  const HeaderNode = (
    <div className="flex items-center justify-between px-6 py-3 bg-black/40 backdrop-blur-md border-b border-white/5 h-16">
       <div className="flex items-center gap-4">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-500 ${status === 'listening' ? 'bg-cyan-500 shadow-[0_0_15px_rgba(6,182,212,0.5)]' : 'bg-gray-800/50 border border-white/10'}`}>
            <span className="text-lg">🐱</span>
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-[0.2em] text-white uppercase">KITTY <span className="text-cyan-400">OS</span></h1>
            <div className="flex items-center gap-2 mt-0.5">
                <div className={`w-1.5 h-1.5 rounded-full ${status === 'connected' ? 'bg-emerald-400' : 'bg-red-500'}`} />
                <span className="text-[9px] font-mono text-gray-400 uppercase tracking-wider">{status}</span>
            </div>
          </div>
       </div>

       <div className="flex items-center gap-2">
          {!isMobile && (
            <>
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSidebarOpen(!sidebarOpen)}
                    className={`text-[10px] uppercase tracking-wider h-8 px-3 ${!sidebarOpen ? 'text-gray-500' : 'text-cyan-400 bg-cyan-500/10'}`}
                >
                    History
                </Button>
                <div className="w-px h-4 bg-white/10" />
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setControlsOpen(!controlsOpen)}
                    className={`text-[10px] uppercase tracking-wider h-8 px-3 ${!controlsOpen ? 'text-gray-500' : 'text-cyan-400 bg-cyan-500/10'}`}
                >
                    Status
                </Button>
            </>
          )}
          {onClose && (
            <Button variant="ghost" size="sm" onClick={onClose} color="error" className="w-8 h-8 p-0 rounded-full hover:bg-white/5">
              ✕
            </Button>
          )}
       </div>
    </div>
  );

  // 2. Sidebar (History)
  const SidebarNode = sidebarOpen ? (
    <div className="h-full flex flex-col">
        <ConversationSidebar
          conversations={savedConversations}
          currentId={conversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={deleteConversation}
          onRename={renameConversation}
          onClose={() => setSidebarOpen(false)}
          isLoading={isLoadingConversations}
          error={conversationsError}
          onRetry={fetchConversations}
        />
    </div>
  ) : null;

  // 3. Controls (Right Panel - Redesigned)
  const ControlsNode = controlsOpen ? (
    <div className="h-full flex flex-col p-3 md:p-4 gap-3 overflow-y-auto voice-scroll-container">
        {/* Header */}
        <div className="flex flex-col gap-2 pt-1">
            <div className="flex items-center gap-2 px-1">
                <span className="text-lg filter drop-shadow-md">🛸</span>
                <span className="text-xs font-bold tracking-[0.2em] text-gray-400 uppercase">System Status</span>
            </div>
            <div className="h-px w-full bg-gradient-to-r from-white/10 via-white/5 to-transparent" />
        </div>

        {/* 1. Protocol / Mode */}
        <div className="group relative overflow-hidden rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all p-3.5">
            <div className="flex justify-between items-start mb-3">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Protocol</span>
                <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={() => setSettingsOpen(true)}
                    className="h-6 px-2 text-[10px] bg-white/5 hover:bg-white/10 border border-white/5"
                >
                    EDIT
                </Button>
            </div>
            
            <div className="flex gap-3 items-center">
                <div className="w-10 h-10 rounded-lg bg-black/40 flex items-center justify-center border border-white/5 shadow-inner text-2xl">
                    {currentModeConfig?.icon}
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="font-bold text-gray-200 text-sm truncate">{currentModeConfig?.name}</h3>
                    <span className="text-[10px] text-gray-500 font-mono">{tier?.toUpperCase() || 'LOCAL'} TIER</span>
                </div>
            </div>
        </div>

        {/* 2. Wake Word Toggle (Prominent) */}
        <button 
            onClick={() => toggleWakeWord()}
            className={`w-full p-3.5 rounded-xl border flex items-center justify-between transition-all group relative overflow-hidden ${
                wakeWordEnabled && capabilities.wakeWord
                ? 'bg-emerald-900/10 border-emerald-500/30' 
                : 'bg-white/[0.02] border-white/5'
            }`}
            disabled={!capabilities.wakeWord}
        >
            <div className="flex flex-col items-start z-10">
                <span className={`text-[10px] uppercase font-bold tracking-wider mb-1 ${wakeWordEnabled ? 'text-emerald-400' : 'text-gray-500'}`}>
                    Wake Word
                </span>
                <span className={`text-xs font-mono ${wakeWordEnabled ? 'text-white' : 'text-gray-600'}`}>
                    {capabilities.wakeWord ? (wakeWordEnabled ? 'ACTIVE' : 'DISABLED') : 'N/A'}
                </span>
            </div>
            
            {/* Toggle Switch Visual */}
            <div className={`w-10 h-5 rounded-full p-0.5 transition-colors z-10 ${wakeWordEnabled && capabilities.wakeWord ? 'bg-emerald-500' : 'bg-gray-700'}`}>
                <div className={`w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-300 ${wakeWordEnabled && capabilities.wakeWord ? 'translate-x-5' : 'translate-x-0'}`} />
            </div>

            {/* Subtle Glow */}
            {wakeWordEnabled && <div className="absolute inset-0 bg-emerald-500/5 blur-xl" />}
        </button>

        {/* 3. Audio Input */}
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5 flex flex-col gap-2">
            <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Audio Input</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border ${isCapturing ? 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10' : 'text-gray-500 border-white/10 bg-white/5'}`}>
                    {isCapturing ? 'LIVE' : 'OFF'}
                </span>
            </div>
            <div className="pt-1 flex justify-center">
              <InputLevelMeter level={inputLevel} active={isCapturing} />
            </div>
        </div>

        {/* 4. Runtime Tasks */}
        <div className="flex-1 min-h-[120px] flex flex-col border border-white/5 rounded-xl bg-black/20 overflow-hidden">
            <div className="px-3 py-2 border-b border-white/5 flex justify-between items-center bg-white/[0.02]">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Tasks</span>
                {toolExecutions.length > 0 && (
                    <span className="flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-green-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                    </span>
                )}
            </div>
            <div className="flex-1 overflow-y-auto p-2 voice-scroll-container">
                {toolExecutions.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-gray-600 gap-2 opacity-60">
                        <span className="text-lg">⚡</span>
                        <span className="text-[10px] uppercase tracking-wider font-medium">System Idle</span>
                    </div>
                ) : (
                    <ToolExecutionList tools={toolExecutions} compact />
                )}
            </div>
        </div>
    </div>
  ) : null;

  // Handler to try reconnecting with loading state
  const handleReconnect = useCallback(async () => {
    setIsReconnecting(true);
    setReconnectError(null);

    try {
      // Try to ensure voice service is running
      const response = await fetch('/api/services/voice/ensure', { method: 'POST' });
      const data = await response.json().catch(() => ({}));

      if (!response.ok || data.success === false) {
        // Service couldn't be started automatically - show helpful message
        setReconnectError('Voice service needs to be started manually');
      }

      // Wait a moment for service to be ready
      await new Promise(resolve => setTimeout(resolve, 1500));
    } catch (err) {
      console.warn('Could not start voice service:', err);
      setReconnectError('Voice service needs to be started manually');
    }

    // Try connecting regardless
    connect({
      conversationId,
      userId,
      voice: settings?.voice?.voice || 'bf_emma',
      speed: settings?.voice?.speed || 1.1,
    });

    // Give connection attempt some time, then reset loading state
    setTimeout(() => {
      setIsReconnecting(false);
    }, 2000);
  }, [connect, conversationId, userId, settings?.voice?.voice, settings?.voice?.speed]);

  // 4. Main Content (Messages + Visualizer)
  const MainNode = (
    <div className="flex flex-col h-full relative">
       {/* Background Ambience */}
       <div className={`absolute inset-0 bg-gradient-to-b from-${currentModeConfig?.color}-500/5 via-transparent to-transparent pointer-events-none transition-colors duration-1000`} />

       {/* Disconnected Overlay */}
       {(status === 'disconnected' || status === 'error') && (
         <div className="absolute inset-x-0 top-4 z-30 flex flex-col items-center gap-2 px-4">
           <div className="flex items-center gap-4 px-5 py-3 rounded-2xl border border-red-500/30 bg-red-900/20 backdrop-blur-xl shadow-lg">
             <div className="flex items-center gap-2">
               {isReconnecting ? (
                 <span className="h-2.5 w-2.5 rounded-full border-2 border-yellow-400 border-t-transparent animate-spin" />
               ) : (
                 <span className="h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse" />
               )}
               <span className="text-sm font-medium text-red-200">
                 {isReconnecting ? 'Connecting...' : 'Voice Service Offline'}
               </span>
             </div>
             <button
               onClick={handleReconnect}
               disabled={isReconnecting}
               className={`px-4 py-1.5 text-sm font-medium rounded-lg border transition-all ${
                 isReconnecting
                   ? 'bg-white/5 text-gray-400 border-white/10 cursor-wait'
                   : 'bg-white/10 hover:bg-white/20 text-white border-white/20'
               }`}
             >
               {isReconnecting ? 'Connecting...' : 'Connect'}
             </button>
             <span className="text-xs text-gray-400 hidden md:inline">
               or run: <code className="px-1.5 py-0.5 rounded bg-black/40 text-gray-300 font-mono">./ops/scripts/start-voice-service.sh</code>
             </span>
           </div>
           {/* Error message when auto-start fails */}
           {reconnectError && !isReconnecting && (
             <div className="px-4 py-2 rounded-xl border border-amber-500/30 bg-amber-900/20 backdrop-blur-xl text-xs text-amber-200">
               {reconnectError} — run the script above or check if the service is already running
             </div>
           )}
         </div>
       )}

       {/* Messages Area - SCROLLABLE */}
       <div 
          ref={scrollViewportRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto voice-scroll-container p-4 md:p-8 scroll-smooth relative" 
          style={{ scrollBehavior: 'smooth' }}
       >
          <div className="max-w-3xl mx-auto flex flex-col gap-6 pb-8">
              {processingSince && (
                <div className="sticky top-0 z-20">
                  <div className="flex items-center gap-3 px-4 py-3 rounded-2xl border border-white/10 bg-black/60 backdrop-blur-xl shadow-lg relative overflow-hidden">
                      <span className="h-3 w-3 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_12px_rgba(52,211,153,0.6)]" />
                      <div className="flex-1">
                        <div className="text-sm font-semibold text-white">Inference in progress</div>
                        <div className="text-[11px] uppercase tracking-[0.18em] text-gray-400">
                          {formatDuration(processingElapsedMs)} elapsed • long responses can take up to 20 minutes
                        </div>
                      </div>
                      {isLongInference && (
                        <span className="px-2 py-1 rounded-md text-[11px] border border-amber-400/40 text-amber-200 bg-amber-500/10">
                          Long run
                        </span>
                      )}
                      <div className="absolute inset-x-3 bottom-2 h-0.5 rounded-full bg-gradient-to-r from-cyan-400 via-purple-400 to-emerald-400 opacity-60 blur-[1px] animate-pulse" />
                  </div>
                </div>
              )}

              {/* Empty State / Visualizer Placeholder */}
              {messages.length === 0 && (
                <div className="h-[48vh] flex flex-col items-center justify-center gap-6">
                    <div className={`transition-all duration-700 ${transcript ? 'scale-75 opacity-50' : 'scale-100 opacity-100'}`}>
                        <AudioVisualizer
                            fftData={fftData}
                            audioLevel={audioLevel}
                            typingLevel={typingLevel}
                            status={status === 'listening' ? 'listening' : status === 'responding' ? 'responding' : 'idle'}
                            enable3D={true}
                            size={260}
                            modeColor={currentModeConfig?.color as any}
                        />
                    </div>
                    <div className="max-w-md w-full rounded-2xl border border-white/10 bg-white/5 backdrop-blur-xl p-4 shadow-[0_20px_60px_rgba(0,0,0,0.35)]">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-semibold text-white">Quick starts</span>
                        <span className="px-2 py-0.5 text-[10px] rounded-full border border-white/10 text-cyan-200 bg-cyan-500/10">Tap mic below</span>
                      </div>
                      <ul className="space-y-1 text-sm text-gray-300">
                        {quickPrompts.map((prompt) => (
                          <li key={prompt} className="flex items-start gap-2">
                            <span className="text-cyan-300 text-xs mt-0.5">•</span>
                            <span>{prompt}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                </div>
              )}

              {/* Message List */}
              <ConversationPanel 
                  messages={messages} 
                  maxHeight="none" 
                  autoScroll={false} 
                  disableScroll={true}
              />

              {/* Active Transcript (User) */}
              {transcript && !response && (
                  <motion.div 
                    initial={{ opacity: 0, y: 20 }} 
                    animate={{ opacity: 1, y: 0 }}
                    className="self-end max-w-[80%]"
                  >
                      <div className="bg-cyan-500/20 border border-cyan-500/30 text-cyan-100 px-6 py-4 rounded-2xl rounded-tr-sm backdrop-blur-md">
                          <p className="text-lg font-light leading-relaxed">"{transcript}"</p>
                      </div>
                      <div className="text-right mt-1">
                          <span className="text-[10px] uppercase tracking-widest text-cyan-500/50 font-bold">Listening...</span>
                      </div>
                  </motion.div>
              )}

              {/* Active Response (Assistant) */}
              {response && (
                  <motion.div 
                    initial={{ opacity: 0, y: 20 }} 
                    animate={{ opacity: 1, y: 0 }}
                    className="self-start w-full max-w-4xl"
                  >
                      <div className="bg-gray-800/80 border border-white/10 text-gray-100 px-6 py-5 rounded-2xl rounded-tl-sm backdrop-blur-md shadow-xl voice-response">
                          <div className="prose prose-invert prose-base max-w-none markdown-content">
                            <Markdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                img: ({ node, ...props }) => (
                                  <div className="my-2 rounded-lg overflow-hidden border border-gray-700 bg-black/50">
                                    <img {...props} className="max-w-full h-auto" loading="lazy" />
                                  </div>
                                ),
                                p: ({ node, ...props }) => <p {...props} className="mb-2 last:mb-0" />,
                                a: ({ node, ...props }) => (
                                  <a
                                    {...props}
                                    className="text-cyan-400 hover:text-cyan-300 underline decoration-cyan-500/30"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  />
                                ),
                                code: ({ node, ...props }) => (
                                  <code {...props} className="bg-black/30 px-1 py-0.5 rounded text-xs font-mono text-cyan-200" />
                                ),
                                pre: ({ node, ...props }) => (
                                  <pre
                                    {...props}
                                    className="bg-black/50 p-2 rounded-lg text-xs font-mono overflow-x-auto my-2 border border-gray-800"
                                  />
                                ),
                                table: ({ node, ...props }) => (
                                  <div className="my-3 overflow-x-auto rounded-lg border border-gray-700">
                                    <table {...props} className="min-w-full text-xs" />
                                  </div>
                                ),
                                thead: ({ node, ...props }) => <thead {...props} className="bg-gray-800/80" />,
                                tbody: ({ node, ...props }) => <tbody {...props} className="divide-y divide-gray-700/50" />,
                                tr: ({ node, ...props }) => <tr {...props} className="hover:bg-gray-800/30 transition-colors" />,
                                th: ({ node, ...props }) => (
                                  <th {...props} className="px-3 py-2 text-left font-semibold text-cyan-300 border-b border-gray-600" />
                                ),
                                td: ({ node, ...props }) => <td {...props} className="px-3 py-2 text-gray-300" />,
                              }}
                            >
                              {response}
                            </Markdown>
                          </div>
                      </div>
                      <div className="text-left mt-1 flex items-center gap-2">
                          <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />
                          <span className="text-[10px] uppercase tracking-widest text-cyan-500/50 font-bold">Generative Stream</span>
                      </div>
                  </motion.div>
              )}
          </div>
       </div>

       {/* Scroll to Bottom Button */}
       <AnimatePresence>
          {showScrollButton && (
            <motion.button
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                onClick={() => scrollToBottom(true)}
                className="absolute bottom-4 right-8 z-50 bg-cyan-500/20 hover:bg-cyan-500/40 text-cyan-400 border border-cyan-500/30 rounded-full p-2 shadow-lg backdrop-blur-md transition-colors"
            >
                <span className="text-xl">↓</span>
            </motion.button>
          )}
       </AnimatePresence>
    </div>
  );

  // 5. Footer (Input)
  const FooterNode = (
    <div className="bg-gradient-to-t from-black via-black/95 to-transparent pb-5 pt-6 px-4">
        <div className="max-w-2xl mx-auto flex flex-col items-center gap-4">
            {/* Mode Switcher */}
            <div className="voice-mode-toggle">
                <button 
                    type="button"
                    onClick={() => setInputType('voice')}
                    className={`voice-mode-option ${inputType === 'voice' ? 'active' : ''}`}
                >
                    Voice
                </button>
                <button 
                    type="button"
                    onClick={() => setInputType('text')}
                    className={`voice-mode-option ${inputType === 'text' ? 'active' : ''}`}
                >
                    Terminal
                </button>
            </div>

            {/* Input Controls */}
            <div className="w-full relative min-h-[80px] flex items-center justify-center">
                <AnimatePresence mode="wait">
                    {inputType === 'voice' ? (
                        <motion.div
                            key="voice-input"
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.9 }}
                            transition={{ duration: 0.2 }}
                            className="flex flex-col items-center gap-2"
                        >
                            <div className="voice-mic-wrap">
                                <div className={`voice-mic-ring ${isCapturing ? 'active' : ''}`} />
                                <Button
                                    size="lg"
                                    glow={isCapturing}
                                    color={isCapturing ? 'error' : 'primary'}
                                    onClick={handleMicToggle}
                                    className={`voice-mic-button ${isCapturing ? 'active' : ''}`}
                                >
                                    <span className="icon">{isCapturing ? '🎙️' : '🎤'}</span>
                                </Button>
                            </div>
                            <div className="voice-hint-row">
                                <span className="voice-hint-chip">
                                  {isCapturing ? 'Listening live' : 'Tap to start'}
                                </span>
                                <span className="voice-hint-chip">{currentModeConfig?.name || 'Realtime'}</span>
                                <span className="voice-hint-chip">{preferLocal ? 'Local' : (ttsProvider?.toUpperCase() || 'Cloud')}</span>
                                <span className="voice-hint-chip">Auto-stop</span>
                            </div>
                            {captureError && (
                              <div className="text-xs text-red-400 text-center mt-2 max-w-xs">
                                {captureError}
                              </div>
                            )}
                        </motion.div>
                    ) : (
                        <motion.div
                            key="text-input"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -10 }}
                            className="w-full"
                        >
                            <form onSubmit={handleTextSubmit} className="relative group">
                                <div className="voice-terminal-bar">
                                    <div className="voice-terminal-inner">
                                        <Input
                                            value={textInput}
                                            onChange={handleInputChange}
                                            placeholder="Command input..." 
                                            fullWidth 
                                            className="voice-terminal-input"
                                            disabled={status === 'disconnected'}
                                            autoFocus
                                        />
                                        <Button type="submit" variant="ghost" className="voice-terminal-send">
                                            ↵
                                        </Button>
                                    </div>
                                </div>
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
      <VoiceLayout
        header={HeaderNode}
        sidebar={SidebarNode}
        controls={ControlsNode}
        main={MainNode}
        footer={FooterNode}
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
