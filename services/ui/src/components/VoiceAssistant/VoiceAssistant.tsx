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

  // Hooks
  const { typingLevel, trigger: triggerTyping } = useTypingActivity(300);

  // Voice Logic
  const voiceStream = useVoiceStream({ customModes: settings?.custom_voice_modes || [] });
  const {
    status, transcript, response, connect, disconnect,
    sendAudio, sendText, endAudio, toolExecutions,
    mode, setMode, capabilities, preferLocal, wakeWordEnabled, toggleWakeWord, tier, ttsProvider
  } = voiceStream;
  
  // Audio Logic
  const audioCapture = useAudioCapture({ sampleRate: 16000, onAudioChunk: sendAudio });
  const { isCapturing, startCapture, stopCapture, stream, inputLevel } = audioCapture;
  const { fftData, audioLevel } = useAudioAnalyzer(stream);

  // Conversation Logic
  const { messages, clearMessages, createConversation, loadMessages, addUserMessage, addAssistantMessage } = useConversations();
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
    connect({ conversationId, userId, voice: 'default' });
    return () => disconnect();
  }, []); 

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
  }, [status, onStatusChange]);

  // Handlers
  const handleNewConversation = useCallback(() => {
    const newId = generateId();
    setConversationId(newId);
    clearMessages();
    createConversation(`Voice Session ${new Date().toLocaleTimeString()}`);
    disconnect();
    setTimeout(() => connect({ conversationId: newId, userId, voice: 'default' }), 100);
  }, [clearMessages, createConversation, connect, disconnect, userId]);

  const handleSelectConversation = useCallback(async (id: string) => {
    if (id === conversationId) return;
    setConversationId(id);
    clearMessages();
    disconnect();
    const loadedMessages = await fetchMessages(id);
    if (loadedMessages && loadedMessages.length > 0) {
      loadMessages(loadedMessages);
    }
    connect({ conversationId: id, userId, voice: 'default' });
  }, [conversationId, clearMessages, connect, disconnect, userId, fetchMessages, loadMessages]);

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
        />
    </div>
  ) : null;

  // 3. Controls (Right Panel - Redesigned)
  const ControlsNode = controlsOpen ? (
    <div className="h-full flex flex-col p-4 gap-4 overflow-y-auto voice-scroll-container">
        {/* Header */}
        <div className="flex flex-col gap-2 pt-2">
            <div className="flex items-center gap-2 px-1">
                <span className="text-lg filter drop-shadow-md">🛸</span>
                <span className="text-xs font-bold tracking-[0.2em] text-gray-400 uppercase">System Status</span>
            </div>
            <div className="h-px w-full bg-gradient-to-r from-white/10 via-white/5 to-transparent" />
        </div>

        {/* 1. Protocol / Mode */}
        <div className="group relative overflow-hidden rounded-xl border border-white/5 bg-white/[0.02] hover:bg-white/[0.04] transition-all p-4">
            <div className="flex justify-between items-start mb-3">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Protocol</span>
                <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={() => setSettingsOpen(true)}
                    className="h-5 px-2 text-[9px] bg-white/5 hover:bg-white/10 border border-white/5"
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
            className={`w-full p-4 rounded-xl border flex items-center justify-between transition-all group relative overflow-hidden ${
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
        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 flex flex-col gap-2">
            <div className="flex justify-between items-center">
                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Audio Input</span>
                <span className={`text-[9px] ${isCapturing ? 'text-red-400 animate-pulse' : 'text-gray-600'}`}>
                    {isCapturing ? 'LIVE' : 'OFF'}
                </span>
            </div>
            <InputLevelMeter level={inputLevel} active={isCapturing} />
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

  // 4. Main Content (Messages + Visualizer)
  const MainNode = (
    <div className="flex flex-col h-full relative">
       {/* Background Ambience */}
       <div className={`absolute inset-0 bg-gradient-to-b from-${currentModeConfig?.color}-500/5 via-transparent to-transparent pointer-events-none transition-colors duration-1000`} />
       
       {/* Messages Area - SCROLLABLE */}
       <div 
          ref={scrollViewportRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto voice-scroll-container p-4 md:p-8 scroll-smooth relative" 
          style={{ scrollBehavior: 'smooth' }}
       >
          <div className="max-w-3xl mx-auto flex flex-col gap-6 pb-8">
              {/* Empty State / Visualizer Placeholder */}
              {messages.length === 0 && (
                <div className="h-[40vh] flex items-center justify-center">
                    <div className={`transition-all duration-700 ${transcript ? 'scale-75 opacity-50' : 'scale-100 opacity-100'}`}>
                        <AudioVisualizer
                            fftData={fftData}
                            audioLevel={audioLevel}
                            typingLevel={typingLevel}
                            status={status === 'listening' ? 'listening' : status === 'responding' ? 'responding' : 'idle'}
                            enable3D={true}
                            size={300}
                            modeColor={currentModeConfig?.color as any}
                        />
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
                    className="self-start max-w-[85%]"
                  >
                      <div className="bg-gray-800/80 border border-white/10 text-gray-100 px-6 py-4 rounded-2xl rounded-tl-sm backdrop-blur-md shadow-xl">
                          <div className="prose prose-invert prose-sm max-w-none">
                            <Markdown>{response}</Markdown>
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
    <div className="bg-gradient-to-t from-black via-black/95 to-transparent pb-6 pt-12 px-4">
        <div className="max-w-2xl mx-auto flex flex-col items-center gap-4">
            {/* Mode Switcher */}
            <div className="flex gap-1 p-1 bg-white/5 rounded-full border border-white/5 backdrop-blur-md">
                <button 
                    onClick={() => setInputType('voice')}
                    className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest transition-all ${inputType === 'voice' ? 'bg-white/10 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
                >
                    Voice
                </button>
                <button 
                    onClick={() => setInputType('text')}
                    className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest transition-all ${inputType === 'text' ? 'bg-white/10 text-white shadow-sm' : 'text-gray-500 hover:text-gray-300'}`}
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
                            className="flex flex-col items-center gap-3"
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
                                    h-16 w-16 rounded-full flex items-center justify-center transition-all duration-300
                                    ${isCapturing ? 'scale-110 shadow-[0_0_40px_rgba(239,68,68,0.5)] bg-red-500 text-white' : 'shadow-[0_0_20px_rgba(6,182,212,0.3)] hover:scale-105 bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'}
                                `}
                                disabled={status === 'disconnected'}
                            >
                                <span className="text-2xl">{isCapturing ? '🎙️' : '🎤'}</span>
                            </Button>
                            <span className="text-[9px] text-gray-500 font-mono uppercase tracking-[0.2em] animate-pulse">
                                {isCapturing ? 'LISTENING...' : 'HOLD TO SPEAK'}
                            </span>
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
                                <div className="absolute inset-0 bg-cyan-500/5 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity" />
                                <div className="relative flex items-center bg-black/40 backdrop-blur-xl rounded-2xl border border-white/10 group-hover:border-white/20 transition-colors p-1">
                                    <Input
                                        value={textInput}
                                        onChange={handleInputChange}
                                        placeholder="Command input..." 
                                        fullWidth 
                                        className="bg-transparent border-none text-lg h-14 focus:ring-0 px-6 font-mono text-cyan-100 placeholder:text-gray-700"
                                        disabled={status === 'disconnected'}
                                        autoFocus
                                    />
                                    <Button type="submit" variant="ghost" className="h-12 w-12 rounded-xl text-cyan-500 hover:bg-cyan-500/10 hover:text-cyan-400">
                                        ↵
                                    </Button>
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
