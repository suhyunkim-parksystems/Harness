import { AlertTriangle, BarChart3, Globe2, Landmark, WalletCards, WifiOff } from "lucide-react";

import { DashboardHeader } from "./DashboardHeader";
import { MarketSection } from "./MarketSection";
import { useMarketSummary } from "../hooks/useMarketSummary";
import type { MarketItem } from "../types/market";

export function DashboardTab() {
  const { data, isLoading, isRefreshing, error, autoRefresh, refresh, toggleAutoRefresh } =
    useMarketSummary();

  const allItems = data ? [...data.indices, ...data.exchangeRates] : [];
  const unavailableCount = allItems.filter((item) => item.status === "unavailable").length;
  const staleCount = allItems.filter((item) => item.status === "stale").length;

  return (
    <section className="dashboard-tab">
      <DashboardHeader
        generatedAt={data?.generatedAt ?? null}
        isRefreshing={isRefreshing}
        autoRefresh={autoRefresh}
        onRefresh={refresh}
        onToggleAutoRefresh={toggleAutoRefresh}
      />

      {error && !data ? (
        <div className="state-panel error-panel" role="alert">
          <WifiOff aria-hidden="true" />
          <strong>시장 데이터를 불러오지 못했습니다.</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {data && (unavailableCount > 0 || staleCount > 0) ? (
        <div className="notice-panel" role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          <span>
            지연 {staleCount}건, 불가 {unavailableCount}건
          </span>
        </div>
      ) : null}

      {isLoading && !data ? (
        <div className="state-panel loading-panel" role="status">
          <BarChart3 aria-hidden="true" />
          <strong>데이터 로딩 중</strong>
        </div>
      ) : null}

      {data ? (
        <div className="dashboard-grid">
          <MarketSection
            title="미국 대표지수"
            icon={Landmark}
            items={filterByCategory(data.indices, "us_index")}
          />
          <MarketSection
            title="한국 대표지수"
            icon={BarChart3}
            items={filterByCategory(data.indices, "korea_index")}
          />
          <MarketSection
            title="기타국 대표지수"
            icon={Globe2}
            items={filterByCategory(data.indices, "global_index")}
          />
          <MarketSection title="환율정보" icon={WalletCards} items={data.exchangeRates} />
        </div>
      ) : null}
    </section>
  );
}

function filterByCategory(items: MarketItem[], category: string): MarketItem[] {
  return items.filter((item) => item.category === category);
}
