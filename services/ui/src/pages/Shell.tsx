import { useState, useRef, useEffect } from 'react';
import '../styles/Shell.css';
import ProviderSelector from '../components/ProviderSelector';
import ProviderBadge, { ProviderMetadata } from '../components/ProviderBadge';

interface Message {
  id: string;
  type: 'user' | 'assistant' | 'system' | 'artifact' | 'thinking';
  content: string;
  timestamp: Date;
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
  // Multi-provider state
  selectedProvider: string | null;
  selectedModel: string | null;
}

const COMMANDS = [
  { cmd: '/help', desc: 'Show all available commands' },
  { cmd: '/verbosity', desc: 'Set response detail level (1-5)' },
  { cmd: '/provider', desc: 'Select LLM provider (local/openai/anthropic/etc)' },
  { cmd: '/model', desc: 'Select specific model' },
  { cmd: '/providers', desc: 'List all available providers' },
  { cmd: '/cad', desc: 'Generate CAD model from description' },
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

const Shell = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [state, setState] = useState<ShellState>({
    conversationId: crypto.randomUUID(),
    verbosity: 3,
    agentEnabled: true,
    traceEnabled: false,
    selectedProvider: null,
    selectedModel: null,
  });
  const [showCommands, setShowCommands] = useState(false);
  const [filteredCommands, setFilteredCommands] = useState(COMMANDS);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<ConversationSummary[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
      id: crypto.randomUUID(),
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
        const newId = crypto.randomUUID();
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
        if (args.length === 0) {
          const current = state.selectedProvider || 'local';
          addMessage('system', `Current provider: ${current}`);
        } else {
          const providerName = args[0].toLowerCase();
          if (providerName === 'local' || providerName === 'none') {
            setState(prev => ({ ...prev, selectedProvider: null, selectedModel: null }));
            addMessage('system', '✓ Provider set to: local (Q4)');
          } else {
            setState(prev => ({ ...prev, selectedProvider: providerName, selectedModel: null }));
            addMessage('system', `✓ Provider set to: ${providerName}\n💡 Enable in I/O Control if disabled`);
          }
        }
        return true;

      case 'model':
        if (args.length === 0) {
          const current = state.selectedModel || state.selectedProvider || 'local Q4';
          addMessage('system', `Current model: ${current}`);
        } else {
          const modelName = args[0];
          setState(prev => ({ ...prev, selectedModel: modelName }));
          addMessage('system', `✓ Model set to: ${modelName}`);
        }
        return true;

      case 'providers':
        // This will be handled by API, but we could show local status
        return false; // Send to API

      default:
        return false; // Command not handled locally, send to API
    }
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
    const thinkingId = crypto.randomUUID();
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
        prompt: userInput,
        verbosity: state.verbosity,
        useAgent: state.agentEnabled,
        // Multi-provider support
        provider: state.selectedProvider,
        model: state.selectedModel,
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
      }

      // Make API call
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
        // Display collective results
        const proposals = data.proposals.map((p: any, i: number) =>
          `${i + 1}. [${p.role}]\n   ${p.text}`
        ).join('\n\n');

        addMessage('assistant', proposals, { pattern: data.pattern });
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
        id: crypto.randomUUID(),
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
        <div className="shell-input-wrapper">
          <ProviderSelector
            selectedProvider={state.selectedProvider}
            selectedModel={state.selectedModel}
            onProviderChange={(provider, model) => {
              setState(prev => ({
                ...prev,
                selectedProvider: provider,
                selectedModel: model,
              }));
            }}
          />
          <input
            ref={inputRef}
            type="text"
            className="shell-input"
            placeholder="Type a message or / for commands..."
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
