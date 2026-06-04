export type MarketStatus = "ok" | "stale" | "unavailable";
export type SummaryStatus = "ok" | "partial" | "unavailable";

export interface MarketItem {
  id: string;
  name: string;
  category: "us_index" | "korea_index" | "global_index" | "exchange_rate" | string;
  region: string;
  symbol: string;
  value: number | null;
  change: number | null;
  changePercent: number | null;
  currency: string;
  asOf: string | null;
  source: string;
  status: MarketStatus;
  errorMessage: string | null;
}

export interface MarketSummary {
  generatedAt: string;
  cacheTtlSeconds: number;
  status: SummaryStatus;
  indices: MarketItem[];
  exchangeRates: MarketItem[];
}

export type AssetCategory = "kr_stock" | "kr_etf" | "us_stock" | "us_etf";
export type ChartPeriod = "1m" | "3m" | "6m" | "1y" | "3y" | "5y" | "10y" | "ytd";

export interface SearchCandidate {
  id: string;
  market: string;
  assetType: string;
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  matchText: string;
  source: string;
  status: MarketStatus;
}

export interface SearchResponse {
  candidates: SearchCandidate[];
  status: string;
  asOf: string | null;
}

export interface StockDetail {
  symbol: string;
  name: string;
  market: string;
  assetType: string;
  exchange: string;
  currency: string;
  currentPrice: number | null;
  openPrice: number | null;
  highPrice: number | null;
  lowPrice: number | null;
  prevClose: number | null;
  change: number | null;
  changePercent: number | null;
  volume: number | null;
  asOf: string | null;
  source: string;
  status: MarketStatus;
  errorMessage: string | null;
}

export interface ChartBar {
  timestamp: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface ChartResponse {
  symbol: string;
  period: string;
  bars: ChartBar[];
  source: string;
  status: MarketStatus;
  errorMessage: string | null;
}
