import { useState, useRef, useEffect, useCallback } from 'react';
import '../styles/Shell.css';
import ProviderSelector from '../components/ProviderSelector';
import ProviderBadge, { ProviderMetadata } from '../components/ProviderBadge';
import { generateId } from '../utils/user';

interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system' | 'artifact' | 'thinking';
  content: string;
  timestamp: Date;
  images?: string[];  // Base64 images attached to user messages
  metadata?: {
    tier?: string;
    confidence?: number;
    latency?: number;
    artifacts?: any[];
    pattern?: string;
    // Multi-provider metadata
    provider_used?: string;
    model_used?: string;
    tokens_used?: number;
    cost_usd?: number;
    fallback_occurred?: boolean;
  };
}

interface ConversationSummary {
  conversationId: string;
  title?: string;
  lastMessageAt?: string;
  lastUserMessage?: string;
  lastAssistantMessage?: string;
  messageCount: number;
}

interface ConversationMessageRecord {
  messageId: string;
  role: string;
  content: string;
  createdAt: string;
  metadata?: Record<string, any>;
}

interface ShellState {
  conversationId: string;
  verbosity: number;
  agentEnabled: boolean;
  traceEnabled: boolean;
  // Model selection
  selectedModel: string | null;
  // Vision support
  isVisionModel: boolean;
}

const COMMANDS = [
  { cmd: '/help', desc: 'Show all available commands' },
  { cmd: '/verbosity', desc: 'Set response detail level (1-5)' },
  { cmd: '/provider', desc: 'Select LLM provider (local/openai/anthropic/etc)' },
  { cmd: '/model', desc: 'Select specific model' },
  { cmd: '/providers', desc: 'List all available providers' },
  { cmd: '/cad', desc: 'Generate CAD model (--organic/--parametric --image <ref>)' },
  { cmd: '/generate', desc: 'Generate image with Stable Diffusion' },
  { cmd: '/list', desc: 'Show cached artifacts' },
  { cmd: '/queue', desc: 'Queue artifact to printer' },
  { cmd: '/vision', desc: 'Search & store reference images' },
  { cmd: '/images', desc: 'List stored reference images' },
  { cmd: '/usage', desc: 'Show provider usage dashboard' },
  { cmd: '/trace', desc: 'Toggle agent reasoning trace' },
  { cmd: '/agent', desc: 'Toggle ReAct agent mode' },
  { cmd: '/history', desc: 'Browse & resume conversation sessions' },
  { cmd: '/collective', desc: 'Multi-agent collaboration' },
  { cmd: '/remember', desc: 'Store a long-term memory note' },
  { cmd: '/memories', desc: 'Search saved memories' },
  { cmd: '/reset', desc: 'Start a new conversation session' },
  { cmd: '/clear', desc: 'Clear message history (local only)' },
];

// Artifact path translation for web UI
const ARTIFACTS_BASE_URL = '/api/cad/artifacts';

const translateArtifactPath = (location: string): string => {
  if (location.startsWith('artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('artifacts/', '')}`;
  }
  if (location.startsWith('storage/artifacts/')) {
    return `${ARTIFACTS_BASE_URL}/${location.replace('storage/artifacts/', '')}`;
  }
  if (location.startsWith('/')) {
    const filename = location.split('/').pop() || location;
    return `${ARTIFACTS_BASE_URL}/${filename}`;
  }
  return location;
};

interface CadArtifact {
  provider: string;
  artifactType: string;
  location: string;
  metadata?: {
    glb_location?: string;
    stl_location?: string;
    thumbnail?: string;
    [key: string]: string | undefined;
  };
}

const formatArtifactMessage = (artifacts: CadArtifact[]): string => {
  if (!artifacts.length) return 'No artifacts generated.';

  return artifacts.map((a, i) => {
    const lines = [`[${i + 1}] ${a.provider} (${a.artifactType})`];
    const glbLoc = a.metadata?.glb_location;
    const stlLoc = a.metadata?.stl_location;

    if (glbLoc) {
      lines.push(`    📦 GLB (preview): ${translateArtifactPath(glbLoc)}`);
    }
    if (stlLoc) {
      lines.push(`    🖨️  STL (slicer):  ${translateArtifactPath(stlLoc)}`);
    }
    if (!glbLoc && !stlLoc) {
      lines.push(`    📥 ${translateArtifactPath(a.location)}`);
    }
    return lines.join('\n');
  }).join('\n\n');
};

const Shell = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [state, setState] = useState<ShellState>({
    conversationId: generateId(),
    verbosity: 3,
    agentEnabled: true,
    traceEnabled: false,
    selectedModel: null,
    isVisionModel: false,
  });
  const [showCommands, setShowCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState(COMMANDS);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Vision model image upload state
  const [conversationImages, setConversationImages] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Image upload handlers
  const handleImageUpload = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) {
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const result = e.target?.result as string;
      if (result) {
        setConversationImages(prev => [...prev, result]);
      }
    };
    reader.readAsDataURL(file);
  }, []);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      Array.from(files).forEach(handleImageUpload);
    }
    // Reset input so same file can be selected again
    e.target.value = '';
  }, [handleImageUpload]);

  const handleRemoveImage = useCallback((index: number) => {
    setConversationImages(prev => prev.filter((_, i) => i !== index));
  }, []);

  const handleClearImages = useCallback(() => {
    setConversationImages([]);
  }, []);

  // Handle drag and drop
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!state.isVisionModel) return;

    const files = Array.from(e.dataTransfer.files);
    files.forEach(handleImageUpload);
  }, [state.isVisionModel, handleImageUpload]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  // Auto-scroll to bottom when new messages appear
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Add welcome message on mount
  useEffect(() => {
    addMessage('system', `Welcome to KITTY Interactive Shell

Type a message to chat, or use commands:
• Type "/" to see available commands
• /help for detailed command list
• /verbosity <1-5> to adjust detail level

Session: ${state.conversationId.slice(0, 8)}...
Verbosity: ${state.verbosity}/5  |  Agent: ${state.agentEnabled ? 'ON' : 'OFF'}  |  Trace: ${state.traceEnabled ? 'ON' : 'OFF'}`);
  }, []);

  const addMessage = (type: Message['type'], content: string, metadata?: any) => {
    const msg: Message = {
      id: generateId(),
      type,
      content,
      timestamp: new Date(),
      metadata,
    };
    setMessages(prev => [...prev, msg]);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInput(value);

    // Show command dropdown if input starts with /
    if (value.startsWith('/')) {
      const query = value.slice(1).toLowerCase();
      const filtered = COMMANDS.filter(cmd =>
        cmd.cmd.slice(1).toLowerCase().includes(query) ||
        cmd.desc.toLowerCase().includes(query)
      );
      setFilteredCommands(filtered);
      setShowCommands(true);
    } else {
      setShowCommands(false);
    }
  };

  const selectCommand = (cmd: string) => {
    setInput(cmd + ' ');
    setShowCommands(false);
    inputRef.current?.focus();
  };

  const historyPreview = (entry: ConversationSummary) => {
    return entry.title?.trim() || entry.lastUserMessage?.trim() || entry.lastAssistantMessage?.trim() || entry.conversationId;
  };

  const formatHistoryTimestamp = (value?: string) => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const loadHistory = async () => {
    setIsHistoryLoading(true);
    setHistoryError(null);
    try {
      const response = await fetch('/api/conversations?limit=25&userId=web-user');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      setHistory(data.conversations || []);
    } catch (error: any) {
      setHistoryError(error.message || 'Failed to load history');
    } finally {
      setIsHistoryLoading(false);
    }
  };

  useEffect(() => {
    if (showHistory) {
      loadHistory();
    }
  }, [showHistory]);

  const handleCommand = async (command: string): Promise<boolean> => {
    const parts = command.slice(1).split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);

    switch (cmd) {
      case 'help':
        addMessage('system', `Available Commands:

${COMMANDS.map(c => `${c.cmd.padEnd(15)} - ${c.desc}`).join('\n')}

Type any message to chat with KITTY.
Commands are executed locally when possible.`);
        return true;

      case 'verbosity':
        if (args.length === 0) {
          addMessage('system', `Current verbosity: ${state.verbosity}/5`);
        } else {
          const level = parseInt(args[0]);
          if (level >= 1 && level <= 5) {
            setState(prev => ({ ...prev, verbosity: level }));
            addMessage('system', `Verbosity set to ${level}/5`);
          } else {
            addMessage('system', '❌ Verbosity must be between 1 and 5');
          }
        }
        return true;

      case 'reset':
        const newId = generateId();
        setState(prev => ({ ...prev, conversationId: newId }));
        addMessage('system', `🔄 Started new session: ${newId.slice(0, 8)}...
(Conversation context cleared)`);
        return true;

      case 'clear':
        setMessages([]);
        addMessage('system', '🗑️  Message history cleared (session continues)');
        return true;

      case 'history':
        setShowHistory(true);
        return true;

      case 'trace':
        if (args.length === 0 || args[0].toLowerCase() === 'toggle') {
          setState(prev => ({ ...prev, traceEnabled: !prev.traceEnabled }));
          addMessage('system', `🔍 Trace mode ${!state.traceEnabled ? 'enabled' : 'disabled'}`);
        } else {
          const enabled = ['on', 'true', '1'].includes(args[0].toLowerCase());
          setState(prev => ({ ...prev, traceEnabled: enabled }));
          addMessage('system', `🔍 Trace mode ${enabled ? 'enabled' : 'disabled'}`);
        }
        return true;

      case 'agent':
        if (args.length === 0 || args[0].toLowerCase() === 'toggle') {
          setState(prev => ({ ...prev, agentEnabled: !prev.agentEnabled }));
          addMessage('system', `🤖 Agent mode ${!state.agentEnabled ? 'enabled' : 'disabled'}`);
        } else {
          const enabled = ['on', 'true', '1'].includes(args[0].toLowerCase());
          setState(prev => ({ ...prev, agentEnabled: enabled }));
          addMessage('system', `🤖 Agent mode ${enabled ? 'enabled' : 'disabled'}`);
        }
        return true;

      case 'provider':
      case 'model':
        if (args.length === 0) {
          const current = state.selectedModel || 'gpt-oss (default)';
          addMessage('system', `Current model: ${current}`);
        } else {
          const modelName = args[0].toLowerCase();
          setState(prev => ({ ...prev, selectedModel: modelName }));
          addMessage('system', `✓ Model set to: ${modelName}`);
        }
        return true;

      case 'providers':
        // This will be handled by API, but we could show local status
        return false; // Send to API

      case 'cad':
        // CAD command is handled specially in sendMessage
        return false;

      default:
        return false; // Command not handled locally, send to API
    }
  };

  // Parse /cad command flags (mirrors CLI main.py logic)
  const parseCadCommand = (args: string[]): { prompt: string; mode: string; imageRefs: string[] } => {
    let organic = false;
    let parametric = false;
    const imageRefs: string[] = [];
    const promptTokens: string[] = [];
    let skipNext = false;

    for (let i = 0; i < args.length; i++) {
      if (skipNext) {
        skipNext = false;
        continue;
      }
      const token = args[i];
      const lower = token.toLowerCase();

      if (lower === '--o' || lower === '--organic') {
        organic = true;
        continue;
      }
      if (lower === '--p' || lower === '--parametric') {
        parametric = true;
        continue;
      }
      if (lower === '--image' || lower === '-i') {
        if (i + 1 < args.length) {
          imageRefs.push(args[i + 1]);
          skipNext = true;
        }
        continue;
      }
      promptTokens.push(token);
    }

    let mode = 'organic'; // default
    if (parametric) mode = 'parametric';
    if (organic) mode = 'organic';

    return {
      prompt: promptTokens.join(' '),
      mode,
      imageRefs,
    };
  };

  const sendMessage = async () => {
    if (!input.trim() || isThinking) return;

    const userInput = input.trim();
    setInput('');

    // Add user message to timeline
    addMessage('user', userInput);

    // Handle commands
    if (userInput.startsWith('/')) {
      const handled = await handleCommand(userInput);
      if (handled) return;
    }

    // Show thinking animation
    setIsThinking(true);
    const thinkingId = generateId();
    setMessages(prev => [...prev, {
      id: thinkingId,
      type: 'thinking',
      content: '',
      timestamp: new Date(),
    }]);

    try {
      // Route based on command vs chat
      let endpoint = '/api/query';
      let payload: any = {
        conversationId: state.conversationId,
        userId: 'web-user',
        intent: 'chat.prompt',
        prompt: userInput,
        verbosity: state.verbosity,
        useAgent: state.agentEnabled,
        // Model selection
        model: state.selectedModel,
        // Include images for vision model
        images: state.isVisionModel && conversationImages.length > 0 ? conversationImages : undefined,
      };

      // Special routing for specific commands
      if (userInput.startsWith('/collective')) {
        endpoint = '/api/collective/run';
        const parts = userInput.split(/\s+/).slice(1);
        const pattern = parts[0] || 'council';
        let k = 3;
        let taskStart = 1;

        if (parts[1]?.startsWith('k=')) {
          k = parseInt(parts[1].slice(2)) || 3;
          taskStart = 2;
        }

        payload = {
          task: parts.slice(taskStart).join(' '),
          pattern,
          k,
          conversationId: state.conversationId,
          userId: 'web-user',
        };
      } else if (userInput.startsWith('/usage')) {
        endpoint = '/api/usage/metrics';
        payload = null;
      } else if (userInput.startsWith('/cad')) {
        // CAD generation with CLI-compatible flag parsing
        endpoint = '/api/cad/generate';
        const parts = userInput.split(/\s+/).slice(1);

        if (parts.length === 0) {
          // Show usage help
          setMessages(prev => prev.filter(m => m.id !== thinkingId));
          addMessage('system', `Usage: /cad <prompt> [--organic|--parametric] [--image <ref>]

Examples:
  /cad design a wall mount bracket
  /cad sculpt a cat figurine --organic
  /cad create a 2U rack faceplate --parametric
  /cad convert to 3D --image 1`);
          setIsThinking(false);
          return;
        }

        const { prompt, mode, imageRefs } = parseCadCommand(parts);
        payload = {
          conversationId: state.conversationId,
          prompt,
          mode,
          imageRefs: imageRefs.length > 0 ? imageRefs : undefined,
        };
      }

      // Handle CAD generation separately (non-streaming, artifact response)
      if (userInput.startsWith('/cad') && endpoint === '/api/cad/generate') {
        const startTime = Date.now();

        // Update thinking with elapsed time
        const elapsedInterval = setInterval(() => {
          const elapsed = Math.floor((Date.now() - startTime) / 1000);
          const timeStr = elapsed > 60 ? `${Math.floor(elapsed / 60)}m ${elapsed % 60}s` : `${elapsed}s`;
          setMessages(prev => prev.map(m =>
            m.id === thinkingId
              ? { ...m, content: `Generating 3D model... (${timeStr})` }
              : m
          ));
        }, 1000);

        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          clearInterval(elapsedInterval);

          if (!response.ok) {
            throw new Error(`CAD generation failed: ${response.status}`);
          }

          const data = await response.json();
          setMessages(prev => prev.filter(m => m.id !== thinkingId));

          const artifacts = data.artifacts || [];
          const artifactMessage = formatArtifactMessage(artifacts);
          addMessage('assistant', `🎨 CAD Generation Complete\n\n${artifactMessage}`, {
            artifacts,
          });
        } catch (error: any) {
          clearInterval(elapsedInterval);
          setMessages(prev => prev.filter(m => m.id !== thinkingId));
          addMessage('system', `❌ CAD Error: ${error.message}`);
        } finally {
          setIsThinking(false);
        }
        return;
      }

      // Use streaming for regular queries (prevents timeout on long-running queries)
      const isRegularQuery = endpoint === '/api/query';
      if (isRegularQuery) {
        const streamEndpoint = '/api/query/stream';
        const startTime = Date.now();
        let streamedContent = '';
        let streamedThinking = '';
        let routingData: any = null;
        const responseId = generateId();

        // Update thinking message with elapsed time
        const elapsedInterval = setInterval(() => {
          const elapsed = Math.floor((Date.now() - startTime) / 1000);
          const minutes = Math.floor(elapsed / 60);
          const seconds = elapsed % 60;
          const timeStr = minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
          setMessages(prev => prev.map(m =>
            m.id === thinkingId
              ? { ...m, content: `Processing... (${timeStr})${streamedThinking ? '\n\n💭 ' + streamedThinking.slice(-200) : ''}` }
              : m
          ));
        }, 1000);

        try {
          const response = await fetch(streamEndpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
          }

          const reader = response.body?.getReader();
          const decoder = new TextDecoder();

          if (!reader) {
            throw new Error('No response body');
          }

          // Create streaming response message
          setMessages(prev => prev.filter(m => m.id !== thinkingId));
          setMessages(prev => [...prev, {
            id: responseId,
            type: 'assistant',
            content: '▌',
            timestamp: new Date(),
          }]);

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const event = JSON.parse(line.slice(6));
                  if (event.type === 'chunk') {
                    if (event.delta) {
                      streamedContent += event.delta;
                      setMessages(prev => prev.map(m =>
                        m.id === responseId ? { ...m, content: streamedContent + '▌' } : m
                      ));
                    }
                    if (event.delta_thinking) {
                      streamedThinking += event.delta_thinking;
                    }
                  } else if (event.type === 'complete') {
                    routingData = event.routing;
                  } else if (event.type === 'error') {
                    throw new Error(event.error);
                  }
                } catch (parseErr) {
                  // Re-throw actual errors, only ignore JSON parse errors
                  if (parseErr instanceof Error && !parseErr.message.includes('JSON')) {
                    throw parseErr;
                  }
                  // Ignore parse errors for incomplete JSON chunks
                }
              }
            }
          }

          // Finalize message
          setMessages(prev => prev.map(m =>
            m.id === responseId
              ? { ...m, content: streamedContent || 'No response', metadata: routingData }
              : m
          ));
          setMessages(prev => prev.filter(m => m.id !== thinkingId));
          setIsThinking(false);
          clearInterval(elapsedInterval);
          return;

        } catch (streamError: any) {
          clearInterval(elapsedInterval);

          // Check if streaming is not supported - fall back to non-streaming
          if (streamError.message?.includes('Streaming not') || streamError.message?.includes('not yet supported')) {
            // Remove the streaming response message
            setMessages(prev => prev.filter(m => m.id !== responseId));

            // Fall back to non-streaming API
            const fallbackResponse = await fetch('/api/query', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });

            if (!fallbackResponse.ok) {
              throw new Error(`HTTP ${fallbackResponse.status}: ${fallbackResponse.statusText}`);
            }

            const data = await fallbackResponse.json();
            setMessages(prev => prev.filter(m => m.id !== thinkingId));
            const output = data.result?.output || data.response || 'No response';
            addMessage('assistant', output, data.routing);
            setIsThinking(false);
            return;
          }

          // For other errors, show error message
          setMessages(prev => prev.filter(m => m.id !== responseId && m.id !== thinkingId));
          addMessage('system', `❌ Error: ${streamError.message}`);
          setIsThinking(false);
          return;
        }
      }

      // Non-streaming path for special commands (/collective, /usage)
      const response = await fetch(endpoint, {
        method: payload ? 'POST' : 'GET',
        headers: payload ? { 'Content-Type': 'application/json' } : undefined,
        body: payload ? JSON.stringify(payload) : undefined,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Remove thinking animation
      setMessages(prev => prev.filter(m => m.id !== thinkingId));

      // Handle different response types
      if (userInput.startsWith('/collective')) {
        // Display collective results with rankings if present
        const proposals = (data.proposals || []).map((p: any, i: number) => {
          const label = p.label || `Response ${String.fromCharCode(65 + i)}`;
          const model = p.model ? ` (${p.model})` : '';
          return `${label} [${p.role}${model}]\n${p.text}`;
        }).join('\n\n');

        let rankingText = '';
        if (data.aggregate_rankings && data.aggregate_rankings.length) {
          rankingText = 'Aggregate ranking:\n' + data.aggregate_rankings.map((r: any) =>
            `- ${r.label} (${r.model || ''}): avg_rank=${r.average_rank}`
          ).join('\n');
        }

        addMessage('assistant', proposals + (rankingText ? `\n\n${rankingText}` : ''), { pattern: data.pattern });
        addMessage('assistant', `⚖️ Judge Verdict\n\n${data.verdict}`, { pattern: data.pattern });
      } else if (userInput.startsWith('/usage')) {
        // Format usage data
        const providers = Object.entries(data).map(([name, info]: [string, any]) =>
          `${name.padEnd(15)} | Calls: ${info.calls?.toString().padStart(4) || '0'} | Cost: $${(info.total_cost || 0).toFixed(4)}`
        ).join('\n');
        addMessage('system', `Provider Usage:\n\n${providers}`);
      } else {
        // Regular chat response
        const output = data.result?.output || data.response || 'No response';
        addMessage('assistant', output, data.routing);
      }

    } catch (error: any) {
      // Remove thinking animation
      setMessages(prev => prev.filter(m => m.id !== thinkingId));
      addMessage('system', `❌ Error: ${error.message}`);
    } finally {
      setIsThinking(false);
    }
  };

  const resumeConversation = async (summary: ConversationSummary) => {
    try {
      setHistoryError(null);
      const response = await fetch(`/api/conversations/${summary.conversationId}/messages?limit=100`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      const transcript: Message[] = (data.messages || []).map((msg: ConversationMessageRecord) => ({
        id: msg.messageId,
        type: msg.role === 'assistant' ? 'assistant' : msg.role === 'system' ? 'system' : 'user',
        content: msg.content,
        timestamp: new Date(msg.createdAt),
        metadata: msg.metadata,
      }));
      const resumeNote: Message = {
        id: generateId(),
        type: 'system',
        content: `Resumed session ${summary.conversationId.slice(0, 8)}...`,
        timestamp: new Date(),
      };
      setMessages([...transcript, resumeNote]);
      setState(prev => ({ ...prev, conversationId: summary.conversationId }));
      setShowHistory(false);
    } catch (error: any) {
      setHistoryError(error.message || 'Failed to resume session');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    } else if (e.key === 'Escape') {
      setShowCommands(false);
    } else if (e.key === 'ArrowDown' && showCommands) {
      e.preventDefault();
      // TODO: Navigate command dropdown
    }
  };

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <div className="shell-container">
      <div className="shell-header">
        <div className="shell-title">
          <span className="shell-icon">💬</span>
          <h2>KITTY Interactive Shell</h2>
        </div>
        <div className="shell-status">
          <span className="status-badge" title="Session ID">
            🔑 {state.conversationId.slice(0, 8)}...
          </span>
          <span className="status-badge" title="Verbosity Level">
            📊 {state.verbosity}/5
          </span>
          <span className={`status-badge ${state.agentEnabled ? 'active' : ''}`} title="Agent Mode">
            🤖 {state.agentEnabled ? 'ON' : 'OFF'}
          </span>
          <span className={`status-badge ${state.traceEnabled ? 'active' : ''}`} title="Trace Mode">
            🔍 {state.traceEnabled ? 'ON' : 'OFF'}
          </span>
          <button className="history-button" onClick={() => setShowHistory(true)}>
            📜 History
          </button>
        </div>
      </div>

      <div className="shell-timeline">
        {messages.map((msg) => (
          <div key={msg.id} className={`message message-${msg.type}`}>
            <div className="message-header">
              <span className="message-sender">
                {msg.type === 'user' && '👤 You'}
                {msg.type === 'assistant' && '🤖 KITTY'}
                {msg.type === 'system' && '⚙️  System'}
                {msg.type === 'thinking' && '💭 Thinking'}
              </span>
              <span className="message-time">{formatTimestamp(msg.timestamp)}</span>
            </div>
            <div className="message-content">
              {msg.type === 'thinking' ? (
                <div className="thinking-animation">
                  <span className="dot"></span>
                  <span className="dot"></span>
                  <span className="dot"></span>
                </div>
              ) : (
                <>
                  <pre className="message-text">{msg.content}</pre>
                  {msg.type === 'assistant' && (
                    <ProviderBadge metadata={msg.metadata as ProviderMetadata} />
                  )}
                </>
              )}
              {msg.metadata && (
                <div className="message-metadata">
                  {msg.metadata.tier && (
                    <span className="meta-badge">tier: {msg.metadata.tier}</span>
                  )}
                  {msg.metadata.confidence !== undefined && (
                    <span className="meta-badge">conf: {(msg.metadata.confidence * 100).toFixed(0)}%</span>
                  )}
                  {msg.metadata.latency && (
                    <span className="meta-badge">{msg.metadata.latency}ms</span>
                  )}
                  {msg.metadata.pattern && (
                    <span className="meta-badge">pattern: {msg.metadata.pattern}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="shell-input-container">
        {showCommands && (
          <div className="command-dropdown">
            {filteredCommands.map((cmd) => (
              <div
                key={cmd.cmd}
                className="command-item"
                onClick={() => selectCommand(cmd.cmd)}
              >
                <span className="command-name">{cmd.cmd}</span>
                <span className="command-desc">{cmd.desc}</span>
              </div>
            ))}
          </div>
        )}
        {/* Vision Model Image Strip */}
        {state.isVisionModel && (
          <div className="image-context-strip">
            {conversationImages.map((img, idx) => (
              <div key={idx} className="image-thumbnail">
                <img src={img} alt={`Context ${idx + 1}`} />
                <button
                  className="image-remove-btn"
                  onClick={() => handleRemoveImage(idx)}
                  title="Remove image"
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="add-image-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Add image"
            >
              📷 Add Image
            </button>
            {conversationImages.length > 0 && (
              <button
                className="clear-images-btn"
                onClick={handleClearImages}
                title="Clear all images"
              >
                Clear All
              </button>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleFileInputChange}
              style={{ display: 'none' }}
            />
          </div>
        )}
        <div
          className={`shell-input-wrapper ${state.isVisionModel ? 'vision-mode' : ''}`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <ProviderSelector
            selectedModel={state.selectedModel}
            onModelChange={(modelId) => {
              setState(prev => ({
                ...prev,
                selectedModel: modelId,
              }));
            }}
            onVisionModelSelected={(isVision) => {
              setState(prev => ({
                ...prev,
                isVisionModel: isVision,
              }));
              // Clear images when switching away from vision model
              if (!isVision) {
                setConversationImages([]);
              }
            }}
          />
          <input
            ref={inputRef}
            type="text"
            className="shell-input"
            placeholder={state.isVisionModel && conversationImages.length > 0
              ? `Ask about ${conversationImages.length} image${conversationImages.length > 1 ? 's' : ''}...`
              : "Type a message or / for commands..."}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={isThinking}
          />
          <button
            className="shell-send-btn"
            onClick={sendMessage}
            disabled={!input.trim() || isThinking}
          >
            {isThinking ? '⏳' : '📤'}
          </button>
        </div>
      <div className="shell-hint">
        Press Enter to send • Type / for commands • ESC to close dropdown
      </div>
    </div>
      {showHistory && (
        <div className="history-overlay">
          <div className="history-panel">
            <div className="history-panel-header">
              <h3>Resume Conversation</h3>
              <button className="history-close" onClick={() => setShowHistory(false)}>✕</button>
            </div>
            {isHistoryLoading ? (
              <p>Loading history…</p>
            ) : historyError ? (
              <p className="history-error">{historyError}</p>
            ) : (
              <div className="history-list">
                {history.length === 0 ? (
                  <p>No saved sessions yet.</p>
                ) : (
                  history.map(entry => (
                    <button
                      key={entry.conversationId}
                      className="history-item"
                      onClick={() => resumeConversation(entry)}
                    >
                      <div className="history-item-title">{historyPreview(entry)}</div>
                      <div className="history-item-meta">
                        <span>{formatHistoryTimestamp(entry.lastMessageAt)}</span>
                        <span>{entry.messageCount} msgs</span>
                        <span>{entry.conversationId.slice(0, 8)}...</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Shell;
