import { useCallback, useEffect, useRef, useState } from 'react';
import { ToolExecution, ToolStatus } from '../components/VoiceAssistant/ToolExecutionCard';
import { getModeById, findModeById, VoiceMode } from '../types/voiceModes';

type VoiceStatus = 'disconnected' | 'connecting' | 'connected' | 'listening' | 'responding' | 'error';

/**
 * Format tool name for display (snake_case → Title Case)
 */
function formatToolName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Map backend status to ToolStatus type
 */
function mapToolStatus(status: string): ToolStatus {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'error':
    case 'blocked':
      return 'error';
    case 'running':
      return 'running';
    default:
      return 'pending';
  }
}

interface VoiceStreamState {
  status: VoiceStatus;
  transcript: string;
  response: string;
  tier: string | null;
  sessionId: string | null;
  error: string | null;
  preferLocal: boolean;
  capabilities: {
    stt: boolean;
    tts: boolean;
    streaming: boolean;
    wakeWord: boolean;
  };
  /** Whether auto-reconnect is active */
  isReconnecting: boolean;
  /** Number of reconnection attempts made */
  reconnectAttempts: number;
  /** Active tool executions for current response */
  toolExecutions: ToolExecution[];
  /** Total tools used in last response */
  toolsUsed: number;
  /** Current voice mode (basic, maker, research, home, creative) */
  mode: string;
  /** Whether paid API calls are allowed */
  allowPaid: boolean;
  /** Whether wake word detection is enabled */
  wakeWordEnabled: boolean;
  /** Activation mode: 'ptt' or 'always_listening' */
  activationMode: 'ptt' | 'always_listening';
  /** TTS provider being used (kokoro, piper, openai) */
  ttsProvider: string | null;
}

interface VoiceStreamConfig {
  conversationId?: string;
  userId?: string;
  voice?: string;
  language?: string;
  sampleRate?: number;
  preferLocal?: boolean;
  /** Voice mode (basic, maker, research, home, creative) */
  mode?: string;
  /** Allow paid API calls */
  allowPaid?: boolean;
  /** Enabled tool names for this mode */
  enabledTools?: string[];
}

interface UseVoiceStreamOptions {
  /** WebSocket endpoint (defaults to current host) */
  endpoint?: string;
  /** Enable auto-reconnect on disconnect (default: true) */
  autoReconnect?: boolean;
  /** Maximum reconnection attempts (default: 5) */
  maxReconnectAttempts?: number;
  /** Base delay in ms for reconnect backoff (default: 1000) */
  reconnectBaseDelay?: number;
  /** Maximum delay in ms for reconnect backoff (default: 30000) */
  reconnectMaxDelay?: number;
  /** Custom voice modes (for lookup when setMode is called) */
  customModes?: VoiceMode[];
}

interface UseVoiceStreamReturn extends VoiceStreamState {
  connect: (config?: VoiceStreamConfig) => void;
  disconnect: () => void;
  sendAudio: (chunk: ArrayBuffer) => void;
  sendText: (text: string) => void;
  endAudio: () => void;
  cancel: () => void;
  setPreferLocal: (prefer: boolean) => void;
  /** Set voice mode (basic, maker, research, home, creative) */
  setMode: (modeId: string) => void;
  /** Toggle wake word detection on/off */
  toggleWakeWord: (enable?: boolean) => void;
}

/**
 * Hook for managing WebSocket voice streaming connection.
 * Handles bidirectional audio/text communication with KITTY voice service.
 * Supports auto-reconnect with exponential backoff.
 */
export function useVoiceStream(options: UseVoiceStreamOptions = {}): UseVoiceStreamReturn {
  const {
    endpoint,
    autoReconnect = true,
    maxReconnectAttempts = 5,
    reconnectBaseDelay = 1000,
    reconnectMaxDelay = 30000,
    customModes = [],
  } = options;

  const wsEndpoint = endpoint || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/voice/stream`;

  const [state, setState] = useState<VoiceStreamState>({
    status: 'disconnected',
    transcript: '',
    response: '',
    tier: null,
    sessionId: null,
    error: null,
    preferLocal: true,
    capabilities: { stt: false, tts: false, streaming: false, wakeWord: false },
    isReconnecting: false,
    reconnectAttempts: 0,
    toolExecutions: [],
    toolsUsed: 0,
    mode: 'basic',
    allowPaid: false,
    wakeWordEnabled: false,
    activationMode: 'ptt',
    ttsProvider: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);
  const lastConfigRef = useRef<VoiceStreamConfig | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intentionalDisconnectRef = useRef(false);
  // Use ref to track state for callbacks without causing re-renders
  const stateRef = useRef(state);
  stateRef.current = state;

  // Play audio chunks from TTS
  const playAudioChunk = useCallback(async (base64Audio: string) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext({ sampleRate: 16000 });
      }

      // Decode base64 to ArrayBuffer
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert PCM16 to Float32 for Web Audio
      const pcm16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768;
      }

      // Create audio buffer
      const audioBuffer = audioContextRef.current.createBuffer(1, float32.length, 16000);
      audioBuffer.getChannelData(0).set(float32);
      audioQueueRef.current.push(audioBuffer);

      // Start playback if not already playing
      if (!isPlayingRef.current) {
        playNextInQueue();
      }
    } catch (err) {
      console.error('Error playing audio:', err);
    }
  }, []);

  const playNextInQueue = useCallback(() => {
    if (audioQueueRef.current.length === 0 || !audioContextRef.current) {
      isPlayingRef.current = false;
      return;
    }

    isPlayingRef.current = true;
    const buffer = audioQueueRef.current.shift()!;
    const source = audioContextRef.current.createBufferSource();
    source.buffer = buffer;
    source.connect(audioContextRef.current.destination);
    source.onended = () => playNextInQueue();
    source.start();
  }, []);

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data);

      switch (msg.type) {
        case 'status':
          setState((prev) => ({
            ...prev,
            sessionId: msg.session_id || prev.sessionId,
            status: msg.status === 'connected' ? 'connected' : prev.status,
            capabilities: msg.capabilities ? {
              stt: msg.capabilities.stt ?? prev.capabilities.stt,
              tts: msg.capabilities.tts ?? prev.capabilities.tts,
              streaming: msg.capabilities.streaming ?? prev.capabilities.streaming,
              wakeWord: msg.capabilities.wake_word ?? prev.capabilities.wakeWord,
            } : prev.capabilities,
            preferLocal: msg.prefer_local ?? prev.preferLocal,
            ttsProvider: msg.tts_provider ?? prev.ttsProvider,
          }));
          break;

        case 'transcript':
          setState((prev) => ({
            ...prev,
            transcript: msg.text,
            status: 'listening',
          }));
          break;

        case 'response.start':
          setState((prev) => ({
            ...prev,
            response: '',
            status: 'responding',
            toolExecutions: [], // Clear previous tools
            toolsUsed: 0,
          }));
          break;

        case 'response.text':
          setState((prev) => ({
            ...prev,
            response: prev.response + (msg.delta || ''),
            tier: msg.tier || prev.tier,
            toolsUsed: msg.tools_used ?? prev.toolsUsed,
          }));
          if (msg.done) {
            setState((prev) => ({ ...prev, status: 'connected' }));
          }
          break;

        case 'function.call':
          // Tool invocation started
          setState((prev) => {
            const newTool: ToolExecution = {
              id: msg.id,
              name: msg.name,
              displayName: formatToolName(msg.name),
              args: msg.args,
              status: 'running',
              startedAt: new Date(),
            };
            return {
              ...prev,
              toolExecutions: [...prev.toolExecutions, newTool],
            };
          });
          break;

        case 'function.result':
          // Tool execution completed
          setState((prev) => {
            const updatedTools = prev.toolExecutions.map((tool) =>
              tool.id === msg.id
                ? {
                    ...tool,
                    result: msg.result,
                    status: mapToolStatus(msg.status),
                    completedAt: new Date(),
                  }
                : tool
            );
            return {
              ...prev,
              toolExecutions: updatedTools,
            };
          });
          break;

        case 'response.audio':
          playAudioChunk(msg.audio);
          break;

        case 'response.end':
          setState((prev) => ({
            ...prev,
            status: 'connected',
          }));
          break;

        case 'wake_word.detected':
          // Wake word was detected - transition to listening mode
          console.log('[VoiceStream] Wake word detected');
          setState((prev) => ({
            ...prev,
            status: 'listening',
          }));
          break;

        case 'wake_word.status':
          // Wake word toggle response
          setState((prev) => ({
            ...prev,
            wakeWordEnabled: msg.enabled ?? prev.wakeWordEnabled,
            activationMode: msg.activation_mode === 'always_listening' ? 'always_listening' : 'ptt',
          }));
          break;

        case 'error':
          setState((prev) => ({
            ...prev,
            error: msg.message,
            status: 'error',
          }));
          break;
      }
    } catch (err) {
      console.error('Error parsing WebSocket message:', err);
    }
  }, [playAudioChunk]);

  // Schedule a reconnection attempt with exponential backoff
  const scheduleReconnect = useCallback((attemptNumber: number) => {
    if (attemptNumber >= maxReconnectAttempts) {
      setState((prev) => ({
        ...prev,
        isReconnecting: false,
        error: 'Failed to reconnect after multiple attempts',
      }));
      return;
    }

    // Calculate delay with exponential backoff and jitter
    const baseDelay = Math.min(
      reconnectBaseDelay * Math.pow(2, attemptNumber),
      reconnectMaxDelay
    );
    const jitter = Math.random() * 0.3 * baseDelay;
    const delay = baseDelay + jitter;

    console.log(`[VoiceStream] Scheduling reconnect attempt ${attemptNumber + 1}/${maxReconnectAttempts} in ${Math.round(delay)}ms`);

    setState((prev) => ({
      ...prev,
      isReconnecting: true,
      reconnectAttempts: attemptNumber + 1,
    }));

    reconnectTimeoutRef.current = setTimeout(() => {
      if (lastConfigRef.current && !intentionalDisconnectRef.current) {
        connect(lastConfigRef.current);
      }
    }, delay);
  }, [maxReconnectAttempts, reconnectBaseDelay, reconnectMaxDelay]);

  const connect = useCallback((config: VoiceStreamConfig = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Store config for reconnection
    lastConfigRef.current = config;
    intentionalDisconnectRef.current = false;

    setState((prev) => ({ ...prev, status: 'connecting', error: null }));

    const ws = new WebSocket(wsEndpoint);
    wsRef.current = ws;

    ws.onopen = () => {
      // Reset reconnect state on successful connection
      setState((prev) => ({
        ...prev,
        isReconnecting: false,
        reconnectAttempts: 0,
      }));

      // Send configuration
      ws.send(JSON.stringify({
        type: 'config',
        config: {
          conversation_id: config.conversationId || 'default',
          user_id: config.userId || 'anonymous',
          voice: config.voice || 'alloy',
          language: config.language || 'en',
          sample_rate: config.sampleRate || 16000,
          prefer_local: config.preferLocal ?? true,
          mode: config.mode || 'basic',
          allow_paid: config.allowPaid ?? false,
          enabled_tools: config.enabledTools || [],
        },
      }));
      setState((prev) => ({
        ...prev,
        preferLocal: config.preferLocal ?? true,
        mode: config.mode || 'basic',
        allowPaid: config.allowPaid ?? false,
      }));
    };

    ws.onmessage = handleMessage;

    ws.onerror = () => {
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: 'WebSocket connection error',
      }));
    };

    ws.onclose = (event) => {
      wsRef.current = null;

      // Check if this was an unexpected close (use ref to avoid dependency issues)
      const currentState = stateRef.current;
      const wasConnected = currentState.status === 'connected' || currentState.status === 'listening' || currentState.status === 'responding';
      const shouldReconnect = autoReconnect && !intentionalDisconnectRef.current && (wasConnected || currentState.isReconnecting);

      setState((prev) => ({
        ...prev,
        status: 'disconnected',
        sessionId: null,
      }));

      // Auto-reconnect if enabled and not intentionally disconnected
      if (shouldReconnect) {
        const attemptNumber = currentState.reconnectAttempts;
        scheduleReconnect(attemptNumber);
      } else {
        setState((prev) => ({
          ...prev,
          isReconnecting: false,
          reconnectAttempts: 0,
        }));
      }
    };
  }, [wsEndpoint, handleMessage, autoReconnect, scheduleReconnect]);

  const disconnect = useCallback(() => {
    // Mark as intentional to prevent auto-reconnect
    intentionalDisconnectRef.current = true;

    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Clear audio queue
    audioQueueRef.current = [];
    isPlayingRef.current = false;

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setState({
      status: 'disconnected',
      transcript: '',
      response: '',
      tier: null,
      sessionId: null,
      error: null,
      preferLocal: true,
      capabilities: { stt: false, tts: false, streaming: false, wakeWord: false },
      isReconnecting: false,
      reconnectAttempts: 0,
      toolExecutions: [],
      toolsUsed: 0,
      mode: 'basic',
      allowPaid: false,
      wakeWordEnabled: false,
      activationMode: 'ptt',
      ttsProvider: null,
    });
  }, []);

  const sendAudio = useCallback((chunk: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Send as binary message
      wsRef.current.send(chunk);
      setState((prev) => ({
        ...prev,
        status: prev.status === 'connected' ? 'listening' : prev.status,
      }));
    }
  }, []);

  const sendText = useCallback((text: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'text',
        content: text,
      }));
      setState((prev) => ({
        ...prev,
        transcript: text,
        status: 'responding',
      }));
    }
  }, []);

  const endAudio = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'audio.end' }));
    }
  }, []);

  const cancel = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'cancel' }));
      // Clear audio queue
      audioQueueRef.current = [];
      setState((prev) => ({
        ...prev,
        status: 'connected',
      }));
    }
  }, []);

  const setPreferLocal = useCallback((prefer: boolean) => {
    setState((prev) => ({ ...prev, preferLocal: prefer }));
    // Send config update to server
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'config',
        config: { prefer_local: prefer },
      }));
    }
  }, []);

  const setMode = useCallback((modeId: string) => {
    // Search both system and custom modes
    const modeConfig = findModeById(modeId, customModes);
    if (!modeConfig) return;

    setState((prev) => ({
      ...prev,
      mode: modeId,
      allowPaid: modeConfig.allowPaid,
      preferLocal: modeConfig.preferLocal,
    }));

    // Send config update to server
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'config',
        config: {
          mode: modeId,
          allow_paid: modeConfig.allowPaid,
          prefer_local: modeConfig.preferLocal,
          enabled_tools: modeConfig.enabledTools,
        },
      }));
    }
  }, [customModes]);

  const toggleWakeWord = useCallback((enable?: boolean) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // If enable is undefined, toggle the current state
      const newState = enable !== undefined ? enable : !stateRef.current.wakeWordEnabled;
      wsRef.current.send(JSON.stringify({
        type: 'wake_word.toggle',
        enable: newState,
      }));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    ...state,
    connect,
    disconnect,
    sendAudio,
    sendText,
    endAudio,
    cancel,
    setPreferLocal,
    setMode,
    toggleWakeWord,
  };
}
