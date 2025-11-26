import { useCallback, useEffect, useRef, useState } from 'react';

type VoiceStatus = 'disconnected' | 'connecting' | 'connected' | 'listening' | 'responding' | 'error';

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
  };
}

interface VoiceStreamConfig {
  conversationId?: string;
  userId?: string;
  voice?: string;
  language?: string;
  sampleRate?: number;
  preferLocal?: boolean;
}

interface UseVoiceStreamReturn extends VoiceStreamState {
  connect: (config?: VoiceStreamConfig) => void;
  disconnect: () => void;
  sendAudio: (chunk: ArrayBuffer) => void;
  sendText: (text: string) => void;
  endAudio: () => void;
  cancel: () => void;
  setPreferLocal: (prefer: boolean) => void;
}

/**
 * Hook for managing WebSocket voice streaming connection.
 * Handles bidirectional audio/text communication with KITTY voice service.
 */
export function useVoiceStream(endpoint?: string): UseVoiceStreamReturn {
  const wsEndpoint = endpoint || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/voice/stream`;

  const [state, setState] = useState<VoiceStreamState>({
    status: 'disconnected',
    transcript: '',
    response: '',
    tier: null,
    sessionId: null,
    error: null,
    preferLocal: true,
    capabilities: { stt: false, tts: false, streaming: false },
  });

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioQueueRef = useRef<AudioBuffer[]>([]);
  const isPlayingRef = useRef(false);

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
            capabilities: msg.capabilities || prev.capabilities,
            preferLocal: msg.prefer_local ?? prev.preferLocal,
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
          }));
          break;

        case 'response.text':
          setState((prev) => ({
            ...prev,
            response: prev.response + (msg.delta || ''),
            tier: msg.tier || prev.tier,
          }));
          if (msg.done) {
            setState((prev) => ({ ...prev, status: 'connected' }));
          }
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

  const connect = useCallback((config: VoiceStreamConfig = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setState((prev) => ({ ...prev, status: 'connecting', error: null }));

    const ws = new WebSocket(wsEndpoint);
    wsRef.current = ws;

    ws.onopen = () => {
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
        },
      }));
      setState((prev) => ({ ...prev, preferLocal: config.preferLocal ?? true }));
    };

    ws.onmessage = handleMessage;

    ws.onerror = () => {
      setState((prev) => ({
        ...prev,
        status: 'error',
        error: 'WebSocket connection error',
      }));
    };

    ws.onclose = () => {
      setState((prev) => ({
        ...prev,
        status: 'disconnected',
        sessionId: null,
      }));
      wsRef.current = null;
    };
  }, [wsEndpoint, handleMessage]);

  const disconnect = useCallback(() => {
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
      capabilities: { stt: false, tts: false, streaming: false },
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
  };
}
