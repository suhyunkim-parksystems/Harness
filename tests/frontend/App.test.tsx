import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import App from "../../src/frontend/src/App";
import type { MarketSummary } from "../../src/frontend/src/types/market";

const summary: MarketSummary = {
  generatedAt: "2026-06-04T00:00:00Z",
  cacheTtlSeconds: 30,
  status: "partial",
  indices: [
    makeItem("sp500", "S&P 500", "us_index", "ok"),
    makeItem("kospi", "KOSPI", "korea_index", "stale"),
    makeItem("dax", "DAX", "global_index", "unavailable")
  ],
  exchangeRates: [makeItem("usd_krw", "USD/KRW", "exchange_rate", "ok")]
};

describe("App", () => {
  it("renders market sections and partial failure badges", async () => {
    mockFetch(summary);

    render(<App />);

    expect(screen.getByText("데이터 로딩 중")).toBeTruthy();
    expect(await screen.findByText("미국 대표지수")).toBeTruthy();
    expect(screen.getByText("S&P 500")).toBeTruthy();
    expect(screen.getByText("KOSPI")).toBeTruthy();
    expect(screen.getByText("DAX")).toBeTruthy();
    expect(screen.getByText("환율정보")).toBeTruthy();
    expect(screen.getByText("지연 1건, 불가 1건")).toBeTruthy();
  });

  it("calls the API again when the refresh button is clicked", async () => {
    const fetchMock = mockFetch(summary);

    render(<App />);

    await screen.findByText("S&P 500");
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });

  it("renders a full failure state when the initial request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    render(<App />);

    expect(await screen.findByText("시장 데이터를 불러오지 못했습니다.")).toBeTruthy();
    expect(screen.getByText("network down")).toBeTruthy();
  });
});

function mockFetch(payload: MarketSummary) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => payload
  } as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function makeItem(
  id: string,
  name: string,
  category: string,
  status: "ok" | "stale" | "unavailable"
) {
  return {
    id,
    name,
    category,
    region: "Test",
    symbol: id,
    value: status === "unavailable" ? null : 100,
    change: status === "unavailable" ? null : 1,
    changePercent: status === "unavailable" ? null : 1,
    currency: "USD",
    asOf: status === "unavailable" ? null : "2026-06-04T00:00:00Z",
    source: "Test",
    status,
    errorMessage: status === "unavailable" ? "missing" : null
  };
}
