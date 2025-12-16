import { useState, useEffect, useRef, useCallback } from 'react';
import './GcodeConsole.css';

interface GcodeConsoleProps {
  printerId?: string;
}

interface ConsoleEntry {
  message: string;
  time: number;
  type: 'command' | 'response' | 'error';
  isLocal?: boolean;
}

const QUICK_COMMANDS = [
  { label: 'Home All', command: 'G28', description: 'Home all axes' },
  { label: 'Home XY', command: 'G28 X Y', description: 'Home X and Y only' },
  { label: 'Position', command: 'M114', description: 'Report current position' },
  { label: 'Settings', command: 'M503', description: 'Report firmware settings' },
  { label: 'Fan On', command: 'M106 S255', description: 'Part cooling fan 100%' },
  { label: 'Fan Off', command: 'M107', description: 'Part cooling fan off' },
];

export default function GcodeConsole({ printerId = 'elegoo_giga' }: GcodeConsoleProps) {
  const [history, setHistory] = useState<ConsoleEntry[]>([]);
  const [command, setCommand] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when history changes
  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [history]);

  // Load initial history
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const response = await fetch(`/api/fabrication/elegoo/gcode_history?count=100`);
      if (!response.ok) {
        throw new Error('Failed to load history');
      }
      const data = await response.json();

      // Convert API response to our format (API returns newest first, we want oldest first)
      const entries: ConsoleEntry[] = data.history
        .reverse()
        .map((entry: { message: string; time: number; type: string }) => ({
          message: entry.message,
          time: entry.time,
          type: entry.type === 'response' ? 'response' : 'command',
        }));

      setHistory(entries);
    } catch (err) {
      console.error('Failed to load gcode history:', err);
      // Don't set error - just start with empty history
    } finally {
      setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const sendCommand = useCallback(async (cmd: string) => {
    if (!cmd.trim()) return;

    setSending(true);
    setError(null);

    // Add command to local history immediately
    const localEntry: ConsoleEntry = {
      message: cmd,
      time: Date.now() / 1000,
      type: 'command',
      isLocal: true,
    };
    setHistory(prev => [...prev, localEntry]);

    try {
      const response = await fetch('/api/fabrication/elegoo/gcode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      });

      const data = await response.json();

      if (!data.success) {
        // Add error response
        setHistory(prev => [...prev, {
          message: data.error || 'Command failed',
          time: Date.now() / 1000,
          type: 'error',
          isLocal: true,
        }]);
        setError(data.error);
      } else if (data.response && data.response !== 'ok') {
        // Add response if there's meaningful output
        setHistory(prev => [...prev, {
          message: data.response,
          time: Date.now() / 1000,
          type: 'response',
          isLocal: true,
        }]);
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to send command';
      setHistory(prev => [...prev, {
        message: errorMsg,
        time: Date.now() / 1000,
        type: 'error',
        isLocal: true,
      }]);
      setError(errorMsg);
    } finally {
      setSending(false);
      setCommand('');
      inputRef.current?.focus();
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendCommand(command);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendCommand(command);
    }
  };

  const handleClear = () => {
    setHistory([]);
    setError(null);
  };

  const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  return (
    <div className="gcode-console">
      <div className="console-header">
        <h4>G-code Console</h4>
        <div className="console-actions">
          <button
            className="refresh-btn"
            onClick={loadHistory}
            disabled={loadingHistory}
            title="Reload history"
          >
            &#x21bb;
          </button>
          <button className="clear-btn" onClick={handleClear} title="Clear">
            Clear
          </button>
        </div>
      </div>

      {error && (
        <div className="console-error">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="console-output" ref={outputRef}>
        {loadingHistory && history.length === 0 && (
          <div className="console-loading">Loading history...</div>
        )}
        {history.length === 0 && !loadingHistory && (
          <div className="console-empty">
            No commands yet. Type a G-code command below or use quick actions.
          </div>
        )}
        {history.map((entry, i) => (
          <div key={i} className={`console-entry ${entry.type}`}>
            <span className="entry-time">{formatTime(entry.time)}</span>
            <span className="entry-prompt">
              {entry.type === 'command' ? '>' : entry.type === 'error' ? '!' : '<'}
            </span>
            <span className="entry-message">{entry.message}</span>
          </div>
        ))}
      </div>

      <div className="console-quick-actions">
        {QUICK_COMMANDS.map((qc) => (
          <button
            key={qc.command}
            className="quick-btn"
            onClick={() => sendCommand(qc.command)}
            disabled={sending}
            title={qc.description}
          >
            {qc.label}
          </button>
        ))}
      </div>

      <form className="console-input-row" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value.toUpperCase())}
          onKeyDown={handleKeyDown}
          placeholder="Enter G-code command (e.g., G28, M114)..."
          disabled={sending}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          type="submit"
          className="send-btn"
          disabled={sending || !command.trim()}
        >
          {sending ? 'Sending...' : 'Send'}
        </button>
      </form>
    </div>
  );
}
