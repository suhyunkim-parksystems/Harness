import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMarketSummary } from "../../src/frontend/src/hooks/useMarketSummary";
import type { MarketSummary } from "../../src/frontend/src/types/market";

const summary: MarketSummary = {
  generatedAt: "2026-06-04T00:00:00Z",
  cacheTtlSeconds: 30,
  status: "ok",
  indices: [],
  exchangeRates: []
};

afterEach(() => {
  vi.useRealTimers();
});

describe("useMarketSummary", () => {
  it("loads the initial summary", async () => {
    mockFetch(summary);

    const { result } = renderHook(() => useMarketSummary());

    await waitFor(() => {
      expect(result.current.data?.generatedAt).toBe(summary.generatedAt);
    });
    expect(result.current.isLoading).toBe(false);
  });

  it("refreshes on the configured interval while auto refresh is enabled", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch(summary);

    renderHook(() => useMarketSummary({ refreshIntervalMs: 1000 }));

    await act(async () => {
      await flushPromises();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
      await flushPromises();
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("stops interval refresh when auto refresh is toggled off", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch(summary);

    const { result } = renderHook(() => useMarketSummary({ refreshIntervalMs: 1000 }));

    await act(async () => {
      await flushPromises();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.toggleAutoRefresh();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
      await flushPromises();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
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

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}
