import { useEffect, useRef, useState } from "react";

import { fetchAutocomplete } from "../api/markets";
import type { SearchCandidate } from "../types/market";

export interface StockSearchState {
  candidates: SearchCandidate[];
  isLoading: boolean;
  error: string | null;
}

export function useStockSearch(query: string, category: string): StockSearchState {
  const [candidates, setCandidates] = useState<SearchCandidate[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setCandidates([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    let ignore = false;

    const timer = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setIsLoading(true);
      setError(null);

      try {
        const result = await fetchAutocomplete(query, category, controller.signal);
        if (!ignore) {
          setCandidates(result.candidates);
          setIsLoading(false);
        }
      } catch (err) {
        if (!ignore && !controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "검색 중 오류가 발생했습니다.");
          setIsLoading(false);
        }
      }
    }, 300);

    return () => {
      ignore = true;
      clearTimeout(timer);
    };
  }, [query, category]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return { candidates, isLoading, error };
}
