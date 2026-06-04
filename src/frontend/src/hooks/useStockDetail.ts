import { useEffect, useRef, useState } from "react";

import { fetchStockChart, fetchStockDetail } from "../api/markets";
import type { ChartResponse, StockDetail } from "../types/market";

export interface StockDetailState {
  detail: StockDetail | null;
  chart: ChartResponse | null;
  isLoading: boolean;
  isChartLoading: boolean;
  error: string | null;
}

export function useStockDetail(
  symbol: string | null,
  category: string,
): { state: StockDetailState; period: string; setPeriod: (p: string) => void } {
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [chart, setChart] = useState<ChartResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isChartLoading, setIsChartLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState("1m");

  const prevSymbolRef = useRef<string | null>(null);
  const prevCategoryRef = useRef<string>("");

  useEffect(() => {
    if (!symbol) {
      prevSymbolRef.current = null;
      prevCategoryRef.current = category;
      setDetail(null);
      setChart(null);
      setError(null);
      setIsLoading(false);
      setIsChartLoading(false);
      return;
    }

    const symbolOrCategoryChanged =
      symbol !== prevSymbolRef.current || category !== prevCategoryRef.current;
    prevSymbolRef.current = symbol;
    prevCategoryRef.current = category;

    let ignore = false;
    const controller = new AbortController();

    if (symbolOrCategoryChanged) {
      setIsLoading(true);
      setError(null);

      Promise.allSettled([
        fetchStockDetail(symbol, category, controller.signal),
        fetchStockChart(symbol, category, period, controller.signal),
      ]).then(([detailResult, chartResult]) => {
        if (!ignore) {
          if (detailResult.status === "fulfilled") {
            setDetail(detailResult.value);
          } else if (!controller.signal.aborted) {
            setError(
              detailResult.reason instanceof Error
                ? detailResult.reason.message
                : "종목 정보 로딩 실패",
            );
          }
          if (chartResult.status === "fulfilled") {
            setChart(chartResult.value);
          }
          setIsLoading(false);
        }
      });
    } else {
      // Only period changed — fetch chart only
      setIsChartLoading(true);

      fetchStockChart(symbol, category, period, controller.signal)
        .then((c) => {
          if (!ignore) {
            setChart(c);
            setIsChartLoading(false);
          }
        })
        .catch(() => {
          if (!ignore) setIsChartLoading(false);
        });
    }

    return () => {
      ignore = true;
      controller.abort();
    };
  }, [symbol, category, period]);

  return { state: { detail, chart, isLoading, isChartLoading, error }, period, setPeriod };
}
