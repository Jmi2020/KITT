import { useCallback, useEffect, useRef, useState } from 'react';
import { useAudioCapture } from '../../hooks/useAudioCapture';
import { useAudioAnalyzer } from '../../hooks/useAudioAnalyzer';
import { useVoiceStream } from '../../hooks/useVoiceStream';
import { useConversations } from '../../hooks/useConversations';
import { useConversationApi } from '../../hooks/useConversationApi';
import { AudioVisualizer } from './AudioVisualizer';
import { InputLevelMeter } from './InputLevelMeter';
import { ConversationPanel } from './ConversationPanel';
import { ConversationSelector } from './ConversationSelector';

interface VoiceAssistantProps {
  initialConversationId?: string;
  userId?: string;
  onClose?: () => void;
  fullscreen?: boolean;
  /** Callback when voice status changes */
  onStatusChange?: (status: string) => void;
  /** Show conversation history panel */
  showHistory?: boolean;
}

/**
 * Voice assistant component with real-time audio streaming.
 * Provides voice interaction with KITTY via WebSocket.
 */
export function VoiceAssistant({
  initialConversationId,
  userId = 'anonymous',
  onClose,
  fullscreen = false,
  onStatusChange,
  showHistory = true,
}: VoiceAssistantProps) {
  const [isPushToTalk, setIsPushToTalk] = useState(false);
  const [textInput, setTextInput] = useState('');
  const [showHistoryPanel, setShowHistoryPanel] = useState(showHistory);
  const [conversationId, setConversationId] = useState<string>(
    initialConversationId || `conv-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  );
  const currentMessageIdRef = useRef<string | null>(null);

  // Voice stream hook
  const voiceStream = useVoiceStream();
  const {
    status,
    transcript,
    response,
    tier,
    capabilities,
    error,
    preferLocal,
    isReconnecting,
    reconnectAttempts,
    connect,
    disconnect,
    sendAudio,
    sendText,
    endAudio,
    cancel,
    setPreferLocal,
  } = voiceStream;

  // Audio capture hook
  const audioCapture = useAudioCapture({
    sampleRate: 16000,
    onAudioChunk: sendAudio,
  });
  const { isCapturing, stream, startCapture, stopCapture, error: captureError, inputLevel } = audioCapture;

  // Audio analyzer for visualization
  const { fftData, audioLevel } = useAudioAnalyzer(stream);

  // Conversation management (local state)
  const conversations = useConversations();
  const { messages, addUserMessage, addAssistantMessage, updateMessage, appendToMessage, clearMessages, createConversation } = conversations;

  // Conversation API (remote state)
  const conversationApi = useConversationApi();
  const {
    conversations: savedConversations,
    isLoading: isLoadingConversations,
    fetchConversations,
    fetchMessages,
    renameConversation,
    deleteConversation,
  } = conversationApi;

  // Fetch conversations on mount
  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  // Load conversation history when conversation changes
  useEffect(() => {
    if (conversationId) {
      fetchMessages(conversationId).then((loadedMessages) => {
        if (loadedMessages.length > 0) {
          // Update local conversation state with loaded messages
          createConversation(`Loaded: ${conversationId.slice(0, 8)}`);
          loadedMessages.forEach((msg) => {
            if (msg.role === 'user') {
              addUserMessage(msg.content);
            } else if (msg.role === 'assistant') {
              addAssistantMessage(msg.content, msg.tier);
            }
          });
        } else {
          // New conversation
          createConversation(`Voice Session ${new Date().toLocaleTimeString()}`);
        }
      });
    }
  }, [conversationId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Track when we start responding and add assistant message
  useEffect(() => {
    if (status === 'responding' && transcript && !currentMessageIdRef.current) {
      // Add user message first
      addUserMessage(transcript);
      // Create placeholder for assistant response
      const msg = addAssistantMessage('', tier || undefined);
      currentMessageIdRef.current = msg.id;
    }
  }, [status, transcript, tier, addUserMessage, addAssistantMessage]);

  // Track response changes
  useEffect(() => {
    if (response && currentMessageIdRef.current) {
      updateMessage(currentMessageIdRef.current, { content: response, isStreaming: status === 'responding' });
    }
  }, [response, status, updateMessage]);

  // Clear current message ref when response ends
  useEffect(() => {
    if (status === 'connected' && currentMessageIdRef.current) {
      updateMessage(currentMessageIdRef.current, { isStreaming: false });
      currentMessageIdRef.current = null;
    }
  }, [status, updateMessage]);

  // Connect on mount
  useEffect(() => {
    connect({ conversationId, userId });
    return () => disconnect();
  }, [connect, disconnect, conversationId, userId]);

  // Notify parent of status changes
  useEffect(() => {
    onStatusChange?.(status);
  }, [status, onStatusChange]);

  // Handle push-to-talk
  const handlePushToTalkStart = useCallback(async () => {
    if (status !== 'connected' && status !== 'listening') return;
    setIsPushToTalk(true);
    await startCapture();
  }, [status, startCapture]);

  const handlePushToTalkEnd = useCallback(() => {
    if (!isPushToTalk) return;
    setIsPushToTalk(false);
    stopCapture();
    endAudio();
  }, [isPushToTalk, stopCapture, endAudio]);

  // Handle text input
  const handleTextSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    sendText(textInput.trim());
    setTextInput('');
  }, [textInput, sendText]);

  // Handle new conversation
  const handleNewConversation = useCallback(() => {
    const newId = `conv-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    setConversationId(newId);
    clearMessages();
    createConversation(`Voice Session ${new Date().toLocaleTimeString()}`);
    // Reconnect with new conversation ID
    disconnect();
    setTimeout(() => connect({ conversationId: newId, userId }), 100);
  }, [clearMessages, createConversation, connect, disconnect, userId]);

  // Handle conversation switch
  const handleSelectConversation = useCallback((id: string) => {
    if (id === conversationId) return;
    setConversationId(id);
    clearMessages();
    // Reconnect with new conversation ID
    disconnect();
    setTimeout(() => connect({ conversationId: id, userId }), 100);
  }, [conversationId, clearMessages, connect, disconnect, userId]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space' && !e.repeat && e.target === document.body) {
        e.preventDefault();
        handlePushToTalkStart();
      }
      if (e.code === 'Escape') {
        cancel();
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        handlePushToTalkEnd();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [handlePushToTalkStart, handlePushToTalkEnd, cancel]);

  const visualizerStatus =
    status === 'listening' ? 'listening' :
    status === 'responding' ? 'responding' :
    status === 'error' ? 'error' : 'idle';

  // Responsive: detect mobile
  const isMobile = typeof window !== 'undefined' && window.innerWidth < 768;

  const containerClass = fullscreen
    ? 'fixed inset-0 bg-gray-900 overflow-hidden'
    : 'relative w-full max-w-4xl mx-auto p-4 md:p-6';

  return (
    <div className={containerClass}>
      {/* Top bar with conversation selector and controls */}
      <div className="flex items-center justify-between mb-4 px-2 gap-2">
        <div className="flex items-center gap-2">
          {/* Conversation selector */}
          <ConversationSelector
            conversations={savedConversations}
            currentId={conversationId}
            onSelect={handleSelectConversation}
            onNew={handleNewConversation}
            onRename={renameConversation}
            onDelete={deleteConversation}
            isLoading={isLoadingConversations}
            compact={isMobile}
          />

          {/* History toggle */}
          <button
            onClick={() => setShowHistoryPanel(!showHistoryPanel)}
            className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-gray-800/50 hover:bg-gray-700/50 border border-gray-700 text-gray-400 hover:text-cyan-400 transition-all text-sm"
            title="Toggle history panel"
          >
            <span>{showHistoryPanel ? '◀' : '▶'}</span>
            {!isMobile && <span>History</span>}
            {messages.length > 0 && (
              <span className="px-1.5 py-0.5 bg-cyan-500/20 rounded-full text-xs text-cyan-400">
                {messages.length}
              </span>
            )}
          </button>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="w-9 h-9 rounded-full bg-cyan-500/20 hover:bg-cyan-500/40 border border-cyan-500/50 flex items-center justify-center transition-all"
          >
            <span className="text-cyan-400 text-xl font-bold leading-none">&times;</span>
          </button>
        )}
      </div>

      {/* Main content area - responsive flex layout */}
      <div className={`flex ${fullscreen ? 'h-[calc(100vh-80px)]' : ''} gap-4 ${showHistoryPanel ? 'flex-col md:flex-row' : 'flex-col'}`}>
        {/* Conversation History Panel - collapsible on mobile */}
        {showHistoryPanel && (
          <div className={`${fullscreen ? 'md:w-80 flex-shrink-0' : 'w-full md:w-72'} bg-gray-800/30 rounded-xl border border-gray-700/50 p-4 ${isMobile ? 'max-h-48' : ''} overflow-hidden`}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-cyan-400 text-sm font-semibold uppercase tracking-wider">
                Conversation
              </h3>
              {messages.length > 0 && (
                <button
                  onClick={handleNewConversation}
                  className="text-xs px-2 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 rounded text-cyan-400 transition-all"
                >
                  New
                </button>
              )}
            </div>
            <ConversationPanel
              messages={messages}
              isStreaming={status === 'responding'}
              maxHeight={fullscreen ? 'calc(100vh - 200px)' : isMobile ? '120px' : '300px'}
              compact={isMobile}
              autoScroll
            />
          </div>
        )}

        {/* Main interaction area */}
        <div className={`flex-1 flex flex-col items-center ${fullscreen ? 'overflow-y-auto' : ''} ${showHistoryPanel ? '' : 'max-w-2xl mx-auto w-full'}`}>
          {/* KITTY Logo/Visualizer */}
          <div className="relative flex items-center justify-center mb-6">
            <AudioVisualizer
              fftData={fftData}
              audioLevel={audioLevel}
              status={visualizerStatus}
              isProcessing={status === 'responding'}
              size={isMobile ? 200 : 280}
            />

            {/* Center content */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <div className={`${isMobile ? 'text-4xl' : 'text-5xl'} mb-2`}>
                  {status === 'error' ? '!' : status === 'responding' ? '...' : '🐱'}
                </div>
                <div className="text-cyan-400 text-xs md:text-sm uppercase tracking-wider">
                  {isReconnecting && `Reconnecting (${reconnectAttempts})...`}
                  {!isReconnecting && status === 'connecting' && 'Connecting...'}
                  {!isReconnecting && status === 'connected' && 'Ready'}
                  {!isReconnecting && status === 'listening' && 'Listening...'}
                  {!isReconnecting && status === 'responding' && 'Thinking...'}
                  {!isReconnecting && status === 'error' && 'Error'}
                  {!isReconnecting && status === 'disconnected' && 'Offline'}
                </div>
              </div>
            </div>
          </div>

          {/* Current exchange - only show if not in history view */}
          {!showHistoryPanel && (
            <>
              {/* Transcript Display */}
              {transcript && (
                <div className="w-full mb-3 p-3 bg-gray-800/50 rounded-lg border border-gray-700">
                  <div className="text-gray-400 text-xs uppercase mb-1">You said:</div>
                  <div className="text-white text-sm">{transcript}</div>
                </div>
              )}

              {/* Response Display */}
              {response && (
                <div className="w-full mb-3 p-3 bg-cyan-900/20 rounded-lg border border-cyan-500/30">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-cyan-400 text-xs uppercase">KITTY</span>
                    {tier && (
                      <span className="text-xs px-2 py-0.5 bg-cyan-500/20 rounded-full text-cyan-300">
                        {tier}
                      </span>
                    )}
                  </div>
                  <div className="text-white text-sm whitespace-pre-wrap">{response}</div>
                </div>
              )}
            </>
          )}

          {/* Error Display */}
          {(error || captureError) && (
            <div className="w-full mb-3 p-3 bg-red-900/20 rounded-lg border border-red-500/30">
              <div className="text-red-400 text-sm">{error || captureError}</div>
            </div>
          )}

          {/* Controls */}
          <div className="w-full space-y-3">
            {/* Input Level Meter */}
            <div className="flex justify-center">
              <InputLevelMeter level={inputLevel} active={isCapturing} compact={isMobile} />
            </div>

            {/* Push to Talk Button */}
            <button
              onMouseDown={handlePushToTalkStart}
              onMouseUp={handlePushToTalkEnd}
              onMouseLeave={handlePushToTalkEnd}
              onTouchStart={handlePushToTalkStart}
              onTouchEnd={handlePushToTalkEnd}
              disabled={status === 'disconnected' || status === 'connecting'}
              className={`w-full py-3 md:py-4 rounded-xl font-semibold transition-all text-sm md:text-base ${
                isCapturing
                  ? 'bg-cyan-500 text-gray-900 shadow-[0_0_30px_rgba(34,211,238,0.5)]'
                  : status === 'disconnected' || status === 'connecting'
                  ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
                  : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30'
              }`}
            >
              {isCapturing ? 'Release to Send' : isMobile ? 'Hold to Talk' : 'Hold to Talk (Space)'}
            </button>

            {/* Text Input (fallback) */}
            <form onSubmit={handleTextSubmit} className="flex gap-2">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                placeholder={isMobile ? 'Type message...' : 'Or type your message...'}
                disabled={status === 'disconnected' || status === 'connecting'}
                className="flex-1 px-3 md:px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500 text-sm"
              />
              <button
                type="submit"
                disabled={!textInput.trim() || status === 'disconnected' || status === 'connecting'}
                className="px-4 md:px-6 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 rounded-lg hover:bg-cyan-500/30 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                Send
              </button>
            </form>

            {/* Cancel Button */}
            {status === 'responding' && (
              <button
                onClick={cancel}
                className="w-full py-2 bg-red-500/20 text-red-400 border border-red-500/50 rounded-lg hover:bg-red-500/30 text-sm"
              >
                Cancel
              </button>
            )}

            {/* Connection & Settings Row */}
            <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
              {/* Connection button */}
              {status === 'disconnected' ? (
                <button
                  onClick={() => connect({ conversationId, userId })}
                  className="px-3 py-1.5 bg-green-500/20 text-green-400 border border-green-500/50 rounded-lg hover:bg-green-500/30 text-sm"
                >
                  Connect
                </button>
              ) : (
                <button
                  onClick={disconnect}
                  className="px-3 py-1.5 bg-gray-500/20 text-gray-400 border border-gray-500/50 rounded-lg hover:bg-gray-500/30 text-sm"
                >
                  Disconnect
                </button>
              )}

              {/* Local/Cloud Toggle */}
              {status !== 'disconnected' && (
                <div className="inline-flex rounded-lg border border-gray-600 overflow-hidden">
                  <button
                    type="button"
                    onClick={() => setPreferLocal(true)}
                    className={`px-3 py-1.5 text-xs font-medium transition-all ${
                      preferLocal
                        ? 'bg-cyan-500 text-gray-900'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    Local
                  </button>
                  <button
                    type="button"
                    onClick={() => setPreferLocal(false)}
                    className={`px-3 py-1.5 text-xs font-medium transition-all ${
                      !preferLocal
                        ? 'bg-purple-500 text-white'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    Cloud
                  </button>
                </div>
              )}
            </div>

            {/* Capabilities indicator - compact on mobile */}
            {status !== 'disconnected' && (
              <div className="flex justify-center gap-3 text-xs text-gray-500">
                <span className={capabilities.stt ? 'text-green-400' : 'text-gray-600'}>
                  STT {capabilities.stt ? '✓' : '✗'}
                </span>
                <span className={capabilities.tts ? 'text-green-400' : 'text-gray-600'}>
                  TTS {capabilities.tts ? '✓' : '✗'}
                </span>
                {!isMobile && (
                  <span className={capabilities.streaming ? 'text-green-400' : 'text-gray-600'}>
                    Stream {capabilities.streaming ? '✓' : '✗'}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Instructions - hidden on mobile for space */}
          {!isMobile && (
            <div className="mt-4 text-center text-gray-500 text-xs">
              <p>
                <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs">Space</kbd> to talk
                {' · '}
                <kbd className="px-1.5 py-0.5 bg-gray-800 rounded text-xs">Esc</kbd> to cancel
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
