import { useCallback, useEffect, useState } from 'react';

type LoginState = 'checking' | 'logged_out' | 'needs_verification' | 'logged_in' | 'error';

interface BambuStatus {
  logged_in: boolean;
  mqtt_connected: boolean;
}

interface BambuPrinter {
  device_id: string;
  name: string;
  model: string;
  online: boolean;
}

interface BambuLoginProps {
  onLoginSuccess?: () => void;
  onClose?: () => void;
  showPrinters?: boolean;
}

/**
 * Bambu Labs login component.
 * Handles OAuth login with email verification support.
 */
export function BambuLogin({ onLoginSuccess, onClose, showPrinters = true }: BambuLoginProps) {
  const [state, setState] = useState<LoginState>('checking');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [printers, setPrinters] = useState<BambuPrinter[]>([]);
  const [mqttConnected, setMqttConnected] = useState(false);

  // Check initial status
  const checkStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/bambu/status');
      if (response.ok) {
        const status: BambuStatus = await response.json();
        setMqttConnected(status.mqtt_connected);
        if (status.logged_in) {
          setState('logged_in');
          if (showPrinters) {
            fetchPrinters();
          }
        } else {
          setState('logged_out');
        }
      } else {
        setState('logged_out');
      }
    } catch {
      setState('error');
      setError('Failed to check Bambu status');
    }
  }, [showPrinters]);

  const fetchPrinters = async () => {
    try {
      const response = await fetch('/api/bambu/printers');
      if (response.ok) {
        const data = await response.json();
        setPrinters(data);
      }
    } catch {
      // Ignore printer fetch errors
    }
  };

  useEffect(() => {
    checkStatus();
  }, [checkStatus]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/bambu/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      const result = await response.json();

      if (result.success) {
        setState('logged_in');
        setMqttConnected(true);
        onLoginSuccess?.();
        if (showPrinters) {
          fetchPrinters();
        }
      } else if (result.needs_verification) {
        setState('needs_verification');
        setError('Check your email for a verification code');
      } else {
        setError(result.error || 'Login failed');
      }
    } catch (err) {
      setError('Network error. Is the fabrication service running?');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/bambu/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, code: verificationCode }),
      });

      const result = await response.json();

      if (result.success) {
        setState('logged_in');
        setMqttConnected(true);
        onLoginSuccess?.();
        if (showPrinters) {
          fetchPrinters();
        }
      } else {
        setError(result.error || 'Invalid verification code');
      }
    } catch (err) {
      setError('Network error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLogout = async () => {
    setIsLoading(true);
    try {
      await fetch('/api/bambu/logout', { method: 'POST' });
      setState('logged_out');
      setMqttConnected(false);
      setPrinters([]);
      setEmail('');
      setPassword('');
      setVerificationCode('');
    } catch {
      setError('Logout failed');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReconnect = async () => {
    setIsLoading(true);
    try {
      const response = await fetch('/api/bambu/connect', { method: 'POST' });
      const result = await response.json();
      setMqttConnected(result.connected);
      if (result.connected) {
        fetchPrinters();
      }
    } catch {
      setError('Reconnect failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 p-6 max-w-md w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-green-500/20 rounded-lg flex items-center justify-center">
            <span className="text-2xl">🖨️</span>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Bambu Labs</h2>
            <p className="text-xs text-gray-400">
              {state === 'logged_in' ? (
                <span className="text-green-400">Connected</span>
              ) : state === 'checking' ? (
                'Checking...'
              ) : (
                'Not connected'
              )}
            </p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        )}
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-500/50 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Checking state */}
      {state === 'checking' && (
        <div className="text-center py-8 text-gray-400">
          <div className="animate-spin w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full mx-auto mb-4" />
          Checking connection...
        </div>
      )}

      {/* Login form */}
      {state === 'logged_out' && (
        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="your@email.com"
              required
              className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 bg-green-500/20 text-green-400 border border-green-500/50 rounded-lg hover:bg-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isLoading ? 'Logging in...' : 'Login to Bambu Labs'}
          </button>
          <p className="text-xs text-gray-500 text-center">
            Uses Bambu Labs cloud API for printer access
          </p>
        </form>
      )}

      {/* Verification form */}
      {state === 'needs_verification' && (
        <form onSubmit={handleVerify} className="space-y-4">
          <div className="p-3 bg-yellow-900/30 border border-yellow-500/50 rounded-lg text-yellow-400 text-sm mb-4">
            A verification code has been sent to <strong>{email}</strong>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Verification Code</label>
            <input
              type="text"
              value={verificationCode}
              onChange={(e) => setVerificationCode(e.target.value)}
              placeholder="123456"
              required
              maxLength={6}
              className="w-full px-4 py-2 bg-gray-900 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-cyan-500 text-center text-2xl tracking-widest"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || verificationCode.length < 6}
            className="w-full py-3 bg-green-500/20 text-green-400 border border-green-500/50 rounded-lg hover:bg-green-500/30 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            {isLoading ? 'Verifying...' : 'Verify Code'}
          </button>
          <button
            type="button"
            onClick={() => {
              setState('logged_out');
              setVerificationCode('');
              setError(null);
            }}
            className="w-full py-2 text-gray-400 hover:text-white transition-colors text-sm"
          >
            Back to login
          </button>
        </form>
      )}

      {/* Logged in state */}
      {state === 'logged_in' && (
        <div className="space-y-4">
          {/* Connection status */}
          <div className="flex items-center justify-between p-3 bg-gray-900/50 rounded-lg">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${mqttConnected ? 'bg-green-400' : 'bg-yellow-400'}`} />
              <span className="text-sm text-gray-400">
                MQTT {mqttConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
            {!mqttConnected && (
              <button
                onClick={handleReconnect}
                disabled={isLoading}
                className="text-xs text-cyan-400 hover:text-cyan-300"
              >
                Reconnect
              </button>
            )}
          </div>

          {/* Printers list */}
          {showPrinters && (
            <div>
              <h3 className="text-sm text-gray-400 mb-2">Your Printers</h3>
              {printers.length === 0 ? (
                <div className="p-4 bg-gray-900/50 rounded-lg text-center text-gray-500 text-sm">
                  No printers found
                </div>
              ) : (
                <div className="space-y-2">
                  {printers.map((printer) => (
                    <div
                      key={printer.device_id}
                      className="p-3 bg-gray-900/50 rounded-lg flex items-center justify-between"
                    >
                      <div>
                        <div className="font-medium text-white">{printer.name}</div>
                        <div className="text-xs text-gray-500">{printer.model}</div>
                      </div>
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${
                          printer.online
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-gray-500/20 text-gray-400'
                        }`}
                      >
                        {printer.online ? 'Online' : 'Offline'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Logout button */}
          <button
            onClick={handleLogout}
            disabled={isLoading}
            className="w-full py-2 bg-gray-700/50 text-gray-400 rounded-lg hover:bg-gray-700 hover:text-white transition-colors text-sm"
          >
            {isLoading ? 'Logging out...' : 'Logout'}
          </button>
        </div>
      )}

      {/* Error state */}
      {state === 'error' && (
        <div className="text-center py-8">
          <div className="text-red-400 mb-4">Failed to connect to Bambu service</div>
          <button
            onClick={checkStatus}
            className="px-4 py-2 bg-cyan-500/20 text-cyan-400 rounded-lg hover:bg-cyan-500/30"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
