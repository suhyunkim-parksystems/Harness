import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMarketSummary } from "../api/markets";
import type { MarketSummary } from "../types/market";

interface UseMarketSummaryOptions {
  refreshIntervalMs?: number;
}

export function useMarketSummary(options: UseMarketSummaryOptions = {}) {
  const refreshIntervalMs = options.refreshIntervalMs ?? 60_000;
  const mountedRef = useRef(true);
  const [data, setData] = useState<MarketSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadSummary = useCallback(async (silent = false) => {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setError(null);

    try {
      const summary = await fetchMarketSummary();
      if (!mountedRef.current) {
        return;
      }
      setData(summary);
    } catch (requestError) {
      if (!mountedRef.current) {
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "데이터를 불러오지 못했습니다.");
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void loadSummary(false);
    return () => {
      mountedRef.current = false;
    };
  }, [loadSummary]);

  useEffect(() => {
    if (!autoRefresh) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void loadSummary(true);
    }, refreshIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [autoRefresh, loadSummary, refreshIntervalMs]);

  return {
    data,
    isLoading,
    isRefreshing,
    error,
    autoRefresh,
    refresh: () => loadSummary(true),
    toggleAutoRefresh: () => setAutoRefresh((current) => !current)
  };
}
