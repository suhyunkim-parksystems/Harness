import type { ChartResponse, MarketSummary, SearchResponse, StockDetail } from "../types/market";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchMarketSummary(signal?: AbortSignal): Promise<MarketSummary> {
  const response = await fetch(`${apiBaseUrl}/api/markets/summary`, { signal });
  if (!response.ok) {
    throw new Error(`Market summary request failed with status ${response.status}`);
  }
  return response.json() as Promise<MarketSummary>;
}

export async function fetchAutocomplete(
  query: string,
  category: string,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, category });
  const response = await fetch(`${apiBaseUrl}/api/search/autocomplete?${params}`, { signal });
  if (!response.ok) {
    throw new Error(`Autocomplete request failed with status ${response.status}`);
  }
  return response.json() as Promise<SearchResponse>;
}

export async function fetchStockDetail(
  symbol: string,
  category: string,
  signal?: AbortSignal,
): Promise<StockDetail> {
  const params = new URLSearchParams({ category });
  const response = await fetch(`${apiBaseUrl}/api/stocks/${encodeURIComponent(symbol)}/detail?${params}`, { signal });
  if (!response.ok) {
    throw new Error(`Stock detail request failed with status ${response.status}`);
  }
  return response.json() as Promise<StockDetail>;
}

export async function fetchStockChart(
  symbol: string,
  category: string,
  period: string,
  signal?: AbortSignal,
): Promise<ChartResponse> {
  const params = new URLSearchParams({ category, period });
  const response = await fetch(`${apiBaseUrl}/api/stocks/${encodeURIComponent(symbol)}/chart?${params}`, { signal });
  if (!response.ok) {
    throw new Error(`Stock chart request failed with status ${response.status}`);
  }
  return response.json() as Promise<ChartResponse>;
}
