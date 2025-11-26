import { useCallback, useEffect, useState } from 'react';
import { useAudioCapture } from '../../hooks/useAudioCapture';
import { useAudioAnalyzer } from '../../hooks/useAudioAnalyzer';
import { useVoiceStream } from '../../hooks/useVoiceStream';
import { AudioVisualizer } from './AudioVisualizer';

interface VoiceAssistantProps {
  conversationId?: string;
  userId?: string;
  onClose?: () => void;
  fullscreen?: boolean;
}

/**
 * Voice assistant component with real-time audio streaming.
 * Provides voice interaction with KITTY via WebSocket.
 */
export function VoiceAssistant({
  conversationId = 'default',
  userId = 'anonymous',
  onClose,
  fullscreen = false,
}: VoiceAssistantProps) {
  const [isPushToTalk, setIsPushToTalk] = useState(false);
  const [textInput, setTextInput] = useState('');

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
  const { isCapturing, stream, startCapture, stopCapture, error: captureError } = audioCapture;

  // Audio analyzer for visualization
  const { fftData, audioLevel } = useAudioAnalyzer(stream);

  // Connect on mount
  useEffect(() => {
    connect({ conversationId, userId });
    return () => disconnect();
  }, [connect, disconnect, conversationId, userId]);

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

  const containerClass = fullscreen
    ? 'fixed inset-0 bg-gray-900 overflow-y-auto'
    : 'relative w-full max-w-2xl mx-auto p-6';

  return (
    <div className={containerClass}>
      <div className={fullscreen ? 'min-h-full flex flex-col items-center justify-start py-8 px-4 max-w-2xl mx-auto w-full' : ''}>
      {/* Close button */}
      {onClose && (
        <button
          onClick={onClose}
          className="absolute top-4 right-4 w-10 h-10 rounded-full bg-cyan-500/20 hover:bg-cyan-500/40 border border-cyan-500/50 flex items-center justify-center transition-all z-20"
        >
          <span className="text-cyan-400 text-2xl font-bold leading-none">&times;</span>
        </button>
      )}

      {/* KITTY Logo/Visualizer */}
      <div className="relative flex items-center justify-center mb-8">
        <AudioVisualizer
          fftData={fftData}
          audioLevel={audioLevel}
          status={visualizerStatus}
          isProcessing={status === 'responding'}
        />

        {/* Center content */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center">
            <div className="text-6xl mb-2">
              {status === 'error' ? '!' : status === 'responding' ? '...' : '🐱'}
            </div>
            <div className="text-cyan-400 text-sm uppercase tracking-wider">
              {status === 'connecting' && 'Connecting...'}
              {status === 'connected' && 'Ready'}
              {status === 'listening' && 'Listening...'}
              {status === 'responding' && 'Thinking...'}
              {status === 'error' && 'Error'}
              {status === 'disconnected' && 'Offline'}
            </div>
          </div>
        </div>
      </div>

      {/* Transcript Display */}
      {transcript && (
        <div className="mb-4 p-4 bg-gray-800/50 rounded-lg border border-gray-700">
          <div className="text-gray-400 text-xs uppercase mb-1">You said:</div>
          <div className="text-white">{transcript}</div>
        </div>
      )}

      {/* Response Display */}
      {response && (
        <div className="mb-4 p-4 bg-cyan-900/20 rounded-lg border border-cyan-500/30">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-cyan-400 text-xs uppercase">KITTY</span>
            {tier && (
              <span className="text-xs px-2 py-0.5 bg-cyan-500/20 rounded-full text-cyan-300">
                {tier}
              </span>
            )}
          </div>
          <div className="text-white whitespace-pre-wrap">{response}</div>
        </div>
      )}

      {/* Error Display */}
      {(error || captureError) && (
        <div className="mb-4 p-4 bg-red-900/20 rounded-lg border border-red-500/30">
          <div className="text-red-400">{error || captureError}</div>
        </div>
      )}

      {/* Controls */}
      <div className="space-y-4">
        {/* Push to Talk Button */}
        <button
          onMouseDown={handlePushToTalkStart}
          onMouseUp={handlePushToTalkEnd}
          onMouseLeave={handlePushToTalkEnd}
          onTouchStart={handlePushToTalkStart}
          onTouchEnd={handlePushToTalkEnd}
          disabled={status === 'disconnected' || status === 'connecting'}
          className={`w-full py-4 rounded-xl font-semibold transition-all ${
            isCapturing
              ? 'bg-cyan-500 text-gray-900 shadow-[0_0_30px_rgba(34,211,238,0.5)]'
              : status === 'disconnected' || status === 'connecting'
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-500/30'
          }`}
        >
          {isCapturing ? 'Release to Send' : 'Hold to Talk (Space)'}
        </button>

        {/* Text Input (fallback) */}
        <form onSubmit={handleTextSubmit} className="flex gap-2">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Or type your message..."
            disabled={status === 'disconnected' || status === 'connecting'}
            className="flex-1 px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
          />
          <button
            type="submit"
            disabled={!textInput.trim() || status === 'disconnected' || status === 'connecting'}
            className="px-6 py-2 bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 rounded-lg hover:bg-cyan-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </form>

        {/* Cancel Button */}
        {status === 'responding' && (
          <button
            onClick={cancel}
            className="w-full py-2 bg-red-500/20 text-red-400 border border-red-500/50 rounded-lg hover:bg-red-500/30"
          >
            Cancel Response
          </button>
        )}

        {/* Connection Controls */}
        <div className="flex gap-2 justify-center">
          {status === 'disconnected' ? (
            <button
              onClick={() => connect({ conversationId, userId })}
              className="px-4 py-2 bg-green-500/20 text-green-400 border border-green-500/50 rounded-lg hover:bg-green-500/30"
            >
              Connect
            </button>
          ) : (
            <button
              onClick={disconnect}
              className="px-4 py-2 bg-gray-500/20 text-gray-400 border border-gray-500/50 rounded-lg hover:bg-gray-500/30"
            >
              Disconnect
            </button>
          )}
        </div>

        {/* Local/Cloud Toggle - Segmented Button */}
        {status !== 'disconnected' && (
          <div className="flex items-center justify-center pt-2">
            <div className="inline-flex rounded-lg border border-gray-600 overflow-hidden">
              <button
                type="button"
                onClick={() => setPreferLocal(true)}
                className={`px-4 py-2 text-sm font-medium transition-all ${
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
                className={`px-4 py-2 text-sm font-medium transition-all ${
                  !preferLocal
                    ? 'bg-purple-500 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                Cloud
              </button>
            </div>
          </div>
        )}

        {/* Capabilities indicator */}
        {status !== 'disconnected' && (
          <div className="flex justify-center gap-4 text-xs text-gray-500">
            <span className={capabilities.stt ? 'text-green-400' : 'text-gray-600'}>
              STT {capabilities.stt ? '✓' : '✗'}
            </span>
            <span className={capabilities.tts ? 'text-green-400' : 'text-gray-600'}>
              TTS {capabilities.tts ? '✓' : '✗'}
            </span>
            <span className={capabilities.streaming ? 'text-green-400' : 'text-gray-600'}>
              Streaming {capabilities.streaming ? '✓' : '✗'}
            </span>
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="mt-6 text-center text-gray-500 text-sm">
        <p>Press and hold <kbd className="px-2 py-1 bg-gray-800 rounded">Space</kbd> to talk</p>
        <p>Press <kbd className="px-2 py-1 bg-gray-800 rounded">Esc</kbd> to cancel</p>
      </div>

      {/* Command Examples */}
      <div className="mt-8 p-4 bg-gray-800/30 rounded-lg border border-gray-700/50">
        <h3 className="text-cyan-400 text-sm font-semibold mb-3 uppercase tracking-wider">
          Example Commands
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
          <div className="space-y-2">
            <p className="text-gray-400">
              <span className="text-cyan-300">"Turn on the living room lights"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"Set the thermostat to 72 degrees"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"What's the weather like?"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"Play some music"</span>
            </p>
          </div>
          <div className="space-y-2">
            <p className="text-gray-400">
              <span className="text-cyan-300">"Start a 3D print of a gear"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"Check printer status"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"Show me the camera feed"</span>
            </p>
            <p className="text-gray-400">
              <span className="text-cyan-300">"What can you do?"</span>
            </p>
          </div>
        </div>
        <p className="mt-3 text-xs text-gray-500">
          KITTY understands natural language - just speak normally!
        </p>
      </div>
      </div>
    </div>
  );
}
