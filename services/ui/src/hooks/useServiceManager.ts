import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import type {
  ServiceStatus,
  ServiceListResponse,
  ServiceActionResponse,
  ServiceCategory,
} from '../types/services';

export interface UseServiceManagerOptions {
  pollInterval?: number;
  autoStart?: boolean;
}

export interface UseServiceManagerReturn {
  // State
  services: Record<string, ServiceStatus>;
  serviceList: ServiceListResponse | null;
  loading: boolean;
  actionLoading: Record<string, boolean>;
  error: string | null;
  lastUpdated: Date | null;
  isPaused: boolean;

  // Computed
  healthyCount: number;
  unhealthyCount: number;
  totalCount: number;
  byCategory: {
    native: ServiceStatus[];
    docker: ServiceStatus[];
    infrastructure: ServiceStatus[];
  };

  // Actions
  refreshAll: () => Promise<void>;
  refreshService: (name: string) => Promise<void>;
  startService: (name: string) => Promise<boolean>;
  stopService: (name: string) => Promise<boolean>;
  restartService: (name: string) => Promise<boolean>;
  clearError: () => void;
  setPollInterval: (ms: number) => void;
  pausePolling: () => void;
  resumePolling: () => void;
  filterByCategory: (category: ServiceCategory) => ServiceStatus[];
  searchServices: (query: string) => ServiceStatus[];
}

export function useServiceManager(
  options: UseServiceManagerOptions = {}
): UseServiceManagerReturn {
  const { pollInterval: initialPollInterval = 5000, autoStart = true } = options;

  // State
  const [services, setServices] = useState<Record<string, ServiceStatus>>({});
  const [serviceList, setServiceList] = useState<ServiceListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [pollInterval, setPollIntervalState] = useState(initialPollInterval);
  const [isPaused, setIsPaused] = useState(!autoStart);

  // Refs
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const retryCount = useRef(0);
  const maxRetries = 3;

  // Fetch service list
  const fetchServiceList = useCallback(async () => {
    try {
      const response = await fetch('/api/services/list');
      if (response.ok) {
        const data: ServiceListResponse = await response.json();
        setServiceList(data);
        return data;
      }
      throw new Error(response.statusText);
    } catch (err) {
      console.warn('Failed to fetch service list:', err);
      return null;
    }
  }, []);

  // Fetch all service statuses
  const fetchAllStatus = useCallback(async () => {
    try {
      const response = await fetch('/api/services/status');
      if (response.ok) {
        const data: Record<string, ServiceStatus> = await response.json();
        setServices(data);
        setLastUpdated(new Date());
        setError(null);
        retryCount.current = 0;
        return data;
      }
      throw new Error(response.statusText);
    } catch (err) {
      if (retryCount.current < maxRetries) {
        retryCount.current++;
        console.warn(
          `Service status API failed, retrying (${retryCount.current}/${maxRetries})...`
        );
      }
      setError('Failed to fetch service status');
      return null;
    }
  }, []);

  // Initial load
  const refreshAll = useCallback(async () => {
    setLoading(true);
    await Promise.all([fetchServiceList(), fetchAllStatus()]);
    setLoading(false);
  }, [fetchServiceList, fetchAllStatus]);

  // Refresh single service
  const refreshService = useCallback(async (name: string) => {
    try {
      const response = await fetch(`/api/services/status/${name}`);
      if (response.ok) {
        const data: ServiceStatus = await response.json();
        setServices((prev) => ({ ...prev, [name]: data }));
        setLastUpdated(new Date());
      }
    } catch (err) {
      console.warn(`Failed to refresh service ${name}:`, err);
    }
  }, []);

  // Service actions
  const performAction = useCallback(
    async (
      name: string,
      action: 'start' | 'stop' | 'restart'
    ): Promise<boolean> => {
      setActionLoading((prev) => ({ ...prev, [name]: true }));
      setError(null);

      try {
        const response = await fetch(`/api/services/${name}/${action}`, {
          method: 'POST',
        });

        if (response.ok) {
          const data: ServiceActionResponse = await response.json();
          // Refresh the service status after action
          setTimeout(() => refreshService(name), 1000);
          return data.success;
        }

        const errorData = await response.json().catch(() => ({}));
        setError(errorData.detail || `Failed to ${action} ${name}`);
        return false;
      } catch (err) {
        setError(`Failed to ${action} ${name}: ${err}`);
        return false;
      } finally {
        setActionLoading((prev) => ({ ...prev, [name]: false }));
      }
    },
    [refreshService]
  );

  const startService = useCallback(
    (name: string) => performAction(name, 'start'),
    [performAction]
  );

  const stopService = useCallback(
    (name: string) => performAction(name, 'stop'),
    [performAction]
  );

  const restartService = useCallback(
    (name: string) => performAction(name, 'restart'),
    [performAction]
  );

  // Polling control
  const pausePolling = useCallback(() => setIsPaused(true), []);
  const resumePolling = useCallback(() => setIsPaused(false), []);
  const setPollInterval = useCallback((ms: number) => setPollIntervalState(ms), []);
  const clearError = useCallback(() => setError(null), []);

  // Computed values
  const serviceArray = useMemo(() => Object.values(services), [services]);

  const healthyCount = useMemo(
    () => serviceArray.filter((s) => s.is_healthy).length,
    [serviceArray]
  );

  const unhealthyCount = useMemo(
    () => serviceArray.filter((s) => !s.is_healthy).length,
    [serviceArray]
  );

  const totalCount = serviceArray.length;

  const byCategory = useMemo(
    () => ({
      native: serviceArray.filter((s) => s.type === 'native_process'),
      docker: serviceArray.filter((s) => s.type === 'docker_service'),
      infrastructure: serviceArray.filter((s) => s.type === 'docker_infra'),
    }),
    [serviceArray]
  );

  // Filter by category
  const filterByCategory = useCallback(
    (category: ServiceCategory): ServiceStatus[] => {
      if (category === 'all') return serviceArray;
      if (category === 'native') return byCategory.native;
      if (category === 'docker') return byCategory.docker;
      if (category === 'infrastructure') return byCategory.infrastructure;
      return serviceArray;
    },
    [serviceArray, byCategory]
  );

  // Search services
  const searchServices = useCallback(
    (query: string): ServiceStatus[] => {
      if (!query.trim()) return serviceArray;
      const lower = query.toLowerCase();
      return serviceArray.filter(
        (s) =>
          s.name.toLowerCase().includes(lower) ||
          s.display_name.toLowerCase().includes(lower)
      );
    },
    [serviceArray]
  );

  // Initial fetch
  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // Polling effect
  useEffect(() => {
    if (isPaused || pollInterval <= 0) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      fetchAllStatus();
    }, pollInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isPaused, pollInterval, fetchAllStatus]);

  return {
    // State
    services,
    serviceList,
    loading,
    actionLoading,
    error,
    lastUpdated,
    isPaused,

    // Computed
    healthyCount,
    unhealthyCount,
    totalCount,
    byCategory,

    // Actions
    refreshAll,
    refreshService,
    startService,
    stopService,
    restartService,
    clearError,
    setPollInterval,
    pausePolling,
    resumePolling,
    filterByCategory,
    searchServices,
  };
}
