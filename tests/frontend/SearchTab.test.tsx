import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { SearchTab } from "../../src/frontend/src/components/SearchTab";
import { StockChart } from "../../src/frontend/src/components/StockChart";
import { StockDetailPanel } from "../../src/frontend/src/components/StockDetailPanel";
import type { ChartResponse, SearchResponse, StockDetail } from "../../src/frontend/src/types/market";

// ── fixtures ─────────────────────────────────────────────────────

const mockCandidate = {
  id: "us:AAPL",
  market: "US",
  assetType: "us_stock",
  symbol: "AAPL",
  name: "Apple Inc.",
  exchange: "NASDAQ",
  currency: "USD",
  matchText: "AAPL Apple Inc.",
  source: "NASDAQ",
  status: "ok" as const,
};

const mockSearchResponse: SearchResponse = {
  candidates: [mockCandidate],
  status: "ok",
  asOf: "2026-06-04T00:00:00Z",
};

const mockDetail: StockDetail = {
  symbol: "AAPL",
  name: "Apple Inc.",
  market: "US",
  assetType: "미국주식",
  exchange: "NASDAQ",
  currency: "USD",
  currentPrice: 150.0,
  openPrice: 148.0,
  highPrice: 152.0,
  lowPrice: 147.0,
  prevClose: 149.0,
  change: 1.0,
  changePercent: 0.67,
  volume: 65000000,
  asOf: "2026-06-04T20:00:00Z",
  source: "Yahoo Finance",
  status: "ok",
  errorMessage: null,
};

const mockChart: ChartResponse = {
  symbol: "AAPL",
  period: "1m",
  bars: [
    { timestamp: "2026-06-04", open: 148.0, high: 152.0, low: 147.0, close: 150.0, volume: 65000000 },
    { timestamp: "2026-06-03", open: 147.0, high: 151.0, low: 146.0, close: 149.0, volume: 60000000 },
  ],
  source: "Yahoo Finance",
  status: "ok",
  errorMessage: null,
};

const flatChart: ChartResponse = {
  symbol: "FLAT",
  period: "1m",
  bars: [
    { timestamp: "2026-06-04", open: 100.0, high: 100.0, low: 100.0, close: 100.0, volume: 0 },
  ],
  source: "Yahoo Finance",
  status: "ok",
  errorMessage: null,
};

// ── helpers ───────────────────────────────────────────────────────

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

function mockFetch(responses: Array<{ url: RegExp | string; payload: unknown }>) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    const match = responses.find((r) =>
      typeof r.url === "string" ? url.includes(r.url) : r.url.test(url),
    );
    const payload = match?.payload ?? {};
    return Promise.resolve({ ok: true, json: async () => payload } as Response);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// ── tests ─────────────────────────────────────────────────────────

describe("SearchTab", () => {
  it("renders category selection buttons", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    render(<SearchTab />);

    expect(screen.getByText("한국주식")).toBeTruthy();
    expect(screen.getByText("한국ETF")).toBeTruthy();
    expect(screen.getByText("미국주식")).toBeTruthy();
    expect(screen.getByText("미국ETF")).toBeTruthy();
  });

  it("shows empty search prompt initially", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    render(<SearchTab />);

    expect(screen.getByText(/종목을 검색해서/)).toBeTruthy();
  });

  it("does not call API for input shorter than 2 chars", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "A" } });

    await new Promise((r) => setTimeout(r, 400));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls autocomplete API after debounce when input >= 2 chars", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockSearchResponse,
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "AA" } });

    // Before debounce fires
    expect(fetchMock).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/search/autocomplete"),
      expect.any(Object),
    );

    vi.useRealTimers();
  });

  it("shows autocomplete candidates in dropdown", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => mockSearchResponse }),
    );
    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "AA" } });
    fireEvent.focus(screen.getByRole("combobox"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
      await flushPromises();
    });

    vi.useRealTimers();

    expect(screen.getByText("Apple Inc.")).toBeTruthy();
  });

  it("loads detail and chart when a candidate is selected", async () => {
    vi.useFakeTimers();
    mockFetch([
      { url: /autocomplete/, payload: mockSearchResponse },
      { url: /\/detail/, payload: mockDetail },
      { url: /\/chart/, payload: mockChart },
    ]);

    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "AA" } });
    fireEvent.focus(screen.getByRole("combobox"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
      await flushPromises();
    });

    // Dropdown candidate is now visible — select it
    const candidate = screen.getByText("Apple Inc.");
    fireEvent.mouseDown(candidate);

    // Flush detail + chart fetch promises
    await act(async () => {
      await flushPromises();
    });

    vi.useRealTimers();

    // Detail panel heading should now be visible
    const headings = screen.getAllByText("Apple Inc.");
    expect(headings.length).toBeGreaterThan(0);
  });

  it("calls korean autocomplete with kr_stock category and shows candidates", async () => {
    vi.useFakeTimers();
    const krCandidate = {
      id: "krx:005930",
      market: "KOSPI",
      assetType: "kr_stock",
      symbol: "005930",
      name: "삼성전자",
      exchange: "KRX",
      currency: "KRW",
      matchText: "005930 삼성전자",
      source: "KRX",
      status: "ok" as const,
    };
    const krResponse: SearchResponse = {
      candidates: [krCandidate],
      status: "ok",
      asOf: "2026-06-04T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => krResponse });
    vi.stubGlobal("fetch", fetchMock);
    render(<SearchTab />);

    // Default category is 한국주식 (kr_stock); type a Korean stock name.
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "삼성" } });
    fireEvent.focus(screen.getByRole("combobox"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
      await flushPromises();
    });

    vi.useRealTimers();

    // Autocomplete called with the kr_stock category.
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/search/autocomplete"),
      expect.any(Object),
    );
    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("category=kr_stock");
    // Candidate dropdown is rendered.
    expect(screen.getByText("삼성전자")).toBeTruthy();
  });

  it("searches korean stocks by 6-digit code", async () => {
    vi.useFakeTimers();
    const krCandidate = {
      id: "krx:005930",
      market: "KOSPI",
      assetType: "kr_stock",
      symbol: "005930",
      name: "삼성전자",
      exchange: "KRX",
      currency: "KRW",
      matchText: "005930 삼성전자",
      source: "KRX",
      status: "ok" as const,
    };
    const krResponse: SearchResponse = {
      candidates: [krCandidate],
      status: "ok",
      asOf: "2026-06-04T00:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => krResponse });
    vi.stubGlobal("fetch", fetchMock);
    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "005930" } });
    fireEvent.focus(screen.getByRole("combobox"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
      await flushPromises();
    });

    vi.useRealTimers();

    const calledUrl = fetchMock.mock.calls[0][0] as string;
    expect(calledUrl).toContain("q=005930");
    expect(calledUrl).toContain("category=kr_stock");
    expect(screen.getByText("삼성전자")).toBeTruthy();
  });

  it("switching category clears the search query and selection", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    render(<SearchTab />);

    const input = screen.getByRole("combobox") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "삼성" } });

    fireEvent.click(screen.getByText("미국주식"));

    expect(input.value).toBe("");
  });
});

describe("StockChart", () => {
  it("renders SVG chart with valid data", () => {
    render(
      <StockChart data={mockChart} period="1m" onPeriodChange={() => {}} />,
    );

    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("renders without throwing when all prices are equal (zero-divide guard)", () => {
    expect(() =>
      render(<StockChart data={flatChart} period="1m" onPeriodChange={() => {}} />),
    ).not.toThrow();

    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("shows empty state when bars are empty", () => {
    const emptyChart: ChartResponse = {
      ...mockChart,
      bars: [],
      status: "unavailable",
      errorMessage: "차트 데이터가 없습니다.",
    };

    render(<StockChart data={emptyChart} period="1m" onPeriodChange={() => {}} />);

    expect(screen.getByText("차트 데이터가 없습니다.")).toBeTruthy();
  });

  it("renders period selector buttons", () => {
    render(<StockChart data={mockChart} period="1m" onPeriodChange={() => {}} />);

    expect(screen.getByText("1M")).toBeTruthy();
    expect(screen.getByText("3M")).toBeTruthy();
    expect(screen.getByText("6M")).toBeTruthy();
    expect(screen.getByText("1Y")).toBeTruthy();
  });

  it("calls onPeriodChange when a period button is clicked", () => {
    const onPeriodChange = vi.fn();
    render(<StockChart data={mockChart} period="1m" onPeriodChange={onPeriodChange} />);

    fireEvent.click(screen.getByText("3M"));

    expect(onPeriodChange).toHaveBeenCalledWith("3m");
  });
});

describe("StockDetailPanel - KRW formatting", () => {
  const krwDetail: StockDetail = {
    symbol: "005930",
    name: "삼성전자",
    market: "KOSPI",
    assetType: "한국주식",
    exchange: "KRX",
    currency: "KRW",
    currentPrice: 70000,
    openPrice: 69500,
    highPrice: 70500,
    lowPrice: 69000,
    prevClose: 69800,
    change: 200,
    changePercent: 0.29,
    volume: 10000000,
    asOf: "2026-06-04T09:00:00Z",
    source: "Yahoo Finance",
    status: "ok",
    errorMessage: null,
  };

  it("renders KRW price without decimal places", () => {
    render(<StockDetailPanel detail={krwDetail} />);
    expect(screen.getByText("₩70,000")).toBeTruthy();
  });

  it("does not show decimals for KRW open/high/low prices", () => {
    render(<StockDetailPanel detail={krwDetail} />);
    expect(screen.getByText("₩69,500")).toBeTruthy();
    expect(screen.getByText("₩70,500")).toBeTruthy();
    expect(screen.getByText("₩69,000")).toBeTruthy();
  });
});

describe("SearchTab - partial failure isolation", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("renders detail panel even when chart fetch fails", async () => {
    let callCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("autocomplete")) {
          return Promise.resolve({ ok: true, json: async () => mockSearchResponse });
        }
        if (url.includes("/detail")) {
          return Promise.resolve({ ok: true, json: async () => mockDetail });
        }
        if (url.includes("/chart")) {
          callCount++;
          return Promise.reject(new Error("chart API unavailable"));
        }
        return Promise.resolve({ ok: true, json: async () => ({}) });
      }),
    );

    render(<SearchTab />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "AA" } });
    fireEvent.focus(screen.getByRole("combobox"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(350);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    const candidate = screen.getByText("Apple Inc.");
    fireEvent.mouseDown(candidate);

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Detail panel should be visible even though chart failed
    const headings = screen.getAllByText("Apple Inc.");
    expect(headings.length).toBeGreaterThan(0);
    // No top-level error panel
    expect(screen.queryByText("종목 정보를 불러오지 못했습니다.")).toBeNull();
  });
});
