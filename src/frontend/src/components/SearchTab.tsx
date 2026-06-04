import { Search } from "lucide-react";
import { useState } from "react";

import { AutocompleteInput } from "./AutocompleteInput";
import { StockChart } from "./StockChart";
import { StockDetailPanel } from "./StockDetailPanel";
import { useStockDetail } from "../hooks/useStockDetail";
import { useStockSearch } from "../hooks/useStockSearch";
import type { AssetCategory, ChartPeriod, SearchCandidate } from "../types/market";

const CATEGORIES: { id: AssetCategory; label: string }[] = [
  { id: "kr_stock", label: "한국주식" },
  { id: "kr_etf", label: "한국ETF" },
  { id: "us_stock", label: "미국주식" },
  { id: "us_etf", label: "미국ETF" },
];

export function SearchTab() {
  const [category, setCategory] = useState<AssetCategory>("kr_stock");
  const [query, setQuery] = useState("");
  const [selectedCandidate, setSelectedCandidate] = useState<SearchCandidate | null>(null);

  const { candidates, isLoading: isSearchLoading } = useStockSearch(query, category);
  const { state, period, setPeriod } = useStockDetail(
    selectedCandidate?.symbol ?? null,
    selectedCandidate ? (selectedCandidate.assetType as AssetCategory) : category,
  );

  function handleCategoryChange(cat: AssetCategory) {
    setCategory(cat);
    setQuery("");
    setSelectedCandidate(null);
  }

  function handleSelect(candidate: SearchCandidate) {
    setSelectedCandidate(candidate);
    setQuery(`${candidate.symbol} ${candidate.name}`);
  }

  return (
    <section className="search-tab">
      <div className="search-tab-header">
        <div className="search-tab-title">
          <Search size={20} aria-hidden="true" />
          <h2>종목 검색</h2>
        </div>

        <div className="category-selector" role="group" aria-label="검색 범주">
          {CATEGORIES.map((cat) => (
            <button
              key={cat.id}
              type="button"
              className={`category-btn${category === cat.id ? " category-btn--active" : ""}`}
              onClick={() => handleCategoryChange(cat.id)}
              aria-pressed={category === cat.id}
            >
              {cat.label}
            </button>
          ))}
        </div>

        <AutocompleteInput
          value={query}
          onChange={(v) => {
            setQuery(v);
            if (v !== `${selectedCandidate?.symbol ?? ""} ${selectedCandidate?.name ?? ""}`) {
              setSelectedCandidate(null);
            }
          }}
          onSelect={handleSelect}
          candidates={candidates}
          isLoading={isSearchLoading}
          placeholder={
            category === "kr_stock" || category === "kr_etf"
              ? "한글 종목명으로 검색 (예: 삼성전자)"
              : "티커로 검색 (예: AAPL)"
          }
        />
      </div>

      {state.isLoading ? (
        <div className="state-panel loading-panel" role="status">
          <strong>종목 정보 로딩 중...</strong>
        </div>
      ) : state.error ? (
        <div className="state-panel error-panel" role="alert">
          <strong>종목 정보를 불러오지 못했습니다.</strong>
          <span>{state.error}</span>
        </div>
      ) : state.detail ? (
        <div className="stock-content">
          <StockDetailPanel detail={state.detail} />
          <StockChart
            data={state.chart}
            period={period as ChartPeriod}
            onPeriodChange={(p) => setPeriod(p)}
            isLoading={state.isChartLoading}
            category={selectedCandidate ? (selectedCandidate.assetType as AssetCategory) : category}
          />
        </div>
      ) : (
        <div className="search-empty-state">
          <Search size={40} aria-hidden="true" />
          <p>종목을 검색해서 상세 정보와 차트를 확인하세요.</p>
          <p className="search-empty-hint">
            {category === "kr_stock" || category === "kr_etf"
              ? "한글 종목명 2자 이상 입력 시 자동완성이 시작됩니다."
              : "티커 2자 이상 입력 시 자동완성이 시작됩니다."}
          </p>
        </div>
      )}
    </section>
  );
}
