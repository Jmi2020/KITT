import { useState, useEffect, useRef } from 'react';

export interface SystemStats {
  cpu: { usage: number; temp: number };
  memory: { used: number; total: number; percent: number };
  disk: { read: number; write: number }; // MB/s
  network: { up: number; down: number }; // KB/s
  isSimulated?: boolean;
}

/**
 * Hook to provide system resource statistics.
 * Fetches real-time data from the backend API.
 * Falls back to simulation if the backend is unreachable.
 */
export function useSystemStats(updateInterval = 2000) {
  const [stats, setStats] = useState<SystemStats>({
    cpu: { usage: 0, temp: 0 },
    memory: { used: 0, total: 32, percent: 0 },
    disk: { read: 0, write: 0 },
    network: { up: 0, down: 0 },
    isSimulated: false,
  });

  const retryCount = useRef(0);
  const maxRetries = 3;

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await fetch('/api/system/stats');
        if (response.ok) {
          const data = await response.json();
          setStats({ ...data, isSimulated: false });
          retryCount.current = 0; // Reset retries on success
        } else {
          throw new Error(response.statusText);
        }
      } catch (error) {
        // Fallback to simulation if API fails (e.g., service not restarted yet)
        if (retryCount.current < maxRetries) {
          retryCount.current++;
          console.warn(`System stats API failed, retrying (${retryCount.current}/${maxRetries})...`);
        }
        
        // Simulate data so the UI doesn't look broken
        setStats(prev => ({
          cpu: {
            usage: Math.min(100, Math.max(5, prev.cpu.usage + (Math.random() * 20 - 10))),
            temp: 45 + Math.random() * 5,
          },
          memory: {
            used: 16 + Math.random() * 1,
            total: 32,
            percent: ((16 + Math.random() * 1) / 32) * 100,
          },
          disk: { read: 0, write: 0 },
          network: {
            up: Math.random() * 50,
            down: Math.random() * 200,
          },
          isSimulated: true
        }));
      }
    };

    // Fetch immediately
    fetchStats();

    const interval = setInterval(fetchStats, updateInterval);

    return () => clearInterval(interval);
  }, [updateInterval]);

  return stats;
}
