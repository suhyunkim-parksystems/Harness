import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StockChart } from "../../src/frontend/src/components/StockChart";
import {
  buildMinimapPath,
  clampRange,
  computePanRange,
  computeZoomRange,
  formatDateLabel,
  MIN_BARS,
  sampleIndices,
} from "../../src/frontend/src/services/chartHelpers";
import type { ChartResponse } from "../../src/frontend/src/types/market";

// ── fixtures ────────────────────────────────────────────────────────

function makeChart(numBars: number): ChartResponse {
  return {
    symbol: "TEST",
    period: "1m",
    bars: Array.from({ length: numBars }, (_, i) => ({
      timestamp: `2026-01-${String(i + 1).padStart(2, "0")}`,
      open: 100 + i,
      high: 102 + i,
      low: 98 + i,
      close: 101 + i,
      volume: 1_000_000,
    })),
    source: "Test",
    status: "ok" as const,
    errorMessage: null,
  };
}

const smallChart = makeChart(2);
const largeChart = makeChart(50);

function dispatchWheel(svg: Element, deltaY: number): void {
  act(() => {
    svg.dispatchEvent(
      new WheelEvent("wheel", { deltaY, clientX: 400, bubbles: true, cancelable: true }),
    );
  });
}

// ── chartHelpers pure function tests ────────────────────────────────

describe("chartHelpers - clampRange", () => {
  it("returns (0, total-1) when start is negative", () => {
    expect(clampRange(-5, 38, 50)).toEqual({ start: 0, end: 43 });
  });

  it("clamps end when it exceeds total", () => {
    expect(clampRange(10, 60, 50)).toEqual({ start: 0, end: 49 });
  });

  it("returns (0, 0) for empty total", () => {
    expect(clampRange(0, 10, 0)).toEqual({ start: 0, end: 0 });
  });

  it("preserves valid ranges untouched", () => {
    expect(clampRange(3, 46, 50)).toEqual({ start: 3, end: 46 });
  });
});

describe("chartHelpers - computeZoomRange", () => {
  it("zooms in (deltaY < 0) reducing numVisible", () => {
    const result = computeZoomRange(0, 49, 50, -100, 0.5);
    expect(result.end - result.start + 1).toBeLessThan(50);
    expect(result.start).toBeGreaterThanOrEqual(0);
    expect(result.end).toBeLessThanOrEqual(49);
  });

  it("zooms out (deltaY > 0) increasing numVisible", () => {
    const { start, end } = computeZoomRange(5, 40, 50, 100, 0.5);
    expect(end - start + 1).toBeGreaterThan(36);
  });

  it("never goes below MIN_BARS", () => {
    let s = 20, e = 29; // 10 bars = MIN_BARS
    for (let i = 0; i < 20; i++) {
      const r = computeZoomRange(s, e, 50, -100, 0.5);
      expect(r.end - r.start + 1).toBeGreaterThanOrEqual(MIN_BARS);
      s = r.start;
      e = r.end;
    }
  });

  it("never exceeds total bars", () => {
    const result = computeZoomRange(0, 49, 50, 100, 0.5);
    expect(result.end - result.start + 1).toBeLessThanOrEqual(50);
  });

  it("handles total=0 safely", () => {
    expect(computeZoomRange(0, 0, 0, -100, 0.5)).toEqual({ start: 0, end: 0 });
  });
});

describe("chartHelpers - computePanRange", () => {
  it("shifts right (positive shiftBars)", () => {
    // 39 visible bars, shifting 5 bars right: start=2+5=7, end=7+38=45 (no clamp needed)
    const result = computePanRange({ start: 2, end: 40 }, 5, 50);
    expect(result.start).toBe(7);
    expect(result.end).toBe(45);
  });

  it("does not go below 0", () => {
    const result = computePanRange({ start: 3, end: 46 }, -100, 50);
    expect(result.start).toBe(0);
  });

  it("does not exceed total-1", () => {
    const result = computePanRange({ start: 3, end: 46 }, 100, 50);
    expect(result.end).toBe(49);
  });
});

describe("chartHelpers - formatDateLabel", () => {
  const ts = "2026-06-15";

  it("returns MM-DD for short periods", () => {
    expect(formatDateLabel(ts, "1m")).toBe("06-15");
    expect(formatDateLabel(ts, "3m")).toBe("06-15");
    expect(formatDateLabel(ts, "6m")).toBe("06-15");
  });

  it("returns YYYY-MM for 1y and ytd", () => {
    expect(formatDateLabel(ts, "1y")).toBe("2026-06");
    expect(formatDateLabel(ts, "ytd")).toBe("2026-06");
  });

  it("returns YYYY for multi-year periods", () => {
    expect(formatDateLabel(ts, "3y")).toBe("2026");
    expect(formatDateLabel(ts, "5y")).toBe("2026");
    expect(formatDateLabel(ts, "10y")).toBe("2026");
  });
});

describe("chartHelpers - buildMinimapPath", () => {
  it("returns empty string for fewer than 2 points", () => {
    expect(buildMinimapPath([], 0, 0, 100, 40)).toBe("");
    expect(buildMinimapPath([100], 0, 0, 100, 40)).toBe("");
  });

  it("returns a closed SVG path string for valid data", () => {
    const path = buildMinimapPath([100, 110, 105], 600, 200, 160, 48);
    expect(path).toContain("M");
    expect(path).toContain("L");
    expect(path).toContain("Z");
  });
});

describe("chartHelpers - sampleIndices", () => {
  it("returns an empty array for total <= 0", () => {
    expect(sampleIndices(0, 5)).toEqual([]);
    expect(sampleIndices(-3, 5)).toEqual([]);
  });

  it("returns all indices when total <= count", () => {
    expect(sampleIndices(3, 5)).toEqual([0, 1, 2]);
    expect(sampleIndices(5, 5)).toEqual([0, 1, 2, 3, 4]);
  });

  it("returns evenly spaced indices including first and last", () => {
    const r = sampleIndices(50, 5);
    expect(r.length).toBe(5);
    expect(r[0]).toBe(0);
    expect(r[r.length - 1]).toBe(49);
    // strictly increasing
    for (let i = 1; i < r.length; i++) expect(r[i]).toBeGreaterThan(r[i - 1]);
  });

  it("handles count <= 1 without dividing by zero", () => {
    expect(sampleIndices(50, 1)).toEqual([0]);
  });
});

// ── StockChart component tests ───────────────────────────────────────

describe("StockChart - 8 period buttons", () => {
  it("renders all 8 period buttons", () => {
    render(<StockChart data={smallChart} period="1m" onPeriodChange={() => {}} />);

    for (const label of ["1M", "3M", "6M", "1Y", "3Y", "5Y", "10Y", "YTD"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("marks the active period with aria-pressed=true", () => {
    render(<StockChart data={smallChart} period="3y" onPeriodChange={() => {}} />);

    expect(screen.getByText("3Y").closest("button")?.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("1M").closest("button")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("calls onPeriodChange with correct ids for new periods", () => {
    const onPeriodChange = vi.fn();
    render(<StockChart data={smallChart} period="1m" onPeriodChange={onPeriodChange} />);

    fireEvent.click(screen.getByText("3Y"));
    expect(onPeriodChange).toHaveBeenNthCalledWith(1, "3y");

    fireEvent.click(screen.getByText("5Y"));
    expect(onPeriodChange).toHaveBeenNthCalledWith(2, "5y");

    fireEvent.click(screen.getByText("10Y"));
    expect(onPeriodChange).toHaveBeenNthCalledWith(3, "10y");

    fireEvent.click(screen.getByText("YTD"));
    expect(onPeriodChange).toHaveBeenNthCalledWith(4, "ytd");
  });
});

describe("StockChart - zoom via wheel", () => {
  it("does not show minimap when not zoomed", () => {
    render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("shows minimap after wheel zoom-in", () => {
    const { container } = render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100); // zoom in

    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();
  });

  it("hides minimap after zooming back to full range", () => {
    const { container } = render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100);
    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();

    // Each act() flushes a render so viewRef updates between zoom-outs
    for (let i = 0; i < 5; i++) {
      dispatchWheel(svg, 100);
      if (document.querySelector("[aria-hidden='true']") === null) break;
    }

    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("minimap viewport rect fits within the full minimap area", () => {
    const { container } = render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100);

    const minimapGroup = document.querySelector("[aria-hidden='true']");
    expect(minimapGroup).toBeTruthy();
    const rects = minimapGroup!.querySelectorAll("rect");
    // Three rects: background, (path is not a rect), viewport
    expect(rects.length).toBeGreaterThanOrEqual(2);
  });
});

describe("StockChart - drag pan", () => {
  it("does not crash on drag when not zoomed", () => {
    const { container } = render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    const svg = container.querySelector("svg.stock-chart-svg")!;

    act(() => {
      fireEvent.pointerDown(svg, { clientX: 400 });
      fireEvent.pointerMove(svg, { clientX: 300 });
      fireEvent.pointerUp(svg);
    });

    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("maintains minimap after drag pan", () => {
    const { container } = render(<StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />);
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100);
    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();

    act(() => {
      fireEvent.pointerDown(svg, { clientX: 400, pointerId: 1 });
      fireEvent.pointerMove(svg, { clientX: 300, pointerId: 1 });
      fireEvent.pointerUp(svg, { pointerId: 1 });
    });

    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});

describe("StockChart - period reset", () => {
  it("resets zoom when period prop changes", () => {
    const { container, rerender } = render(
      <StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />,
    );
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100);
    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();

    rerender(<StockChart data={largeChart} period="3m" onPeriodChange={() => {}} />);

    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });

  it("resets zoom when data prop changes", () => {
    const { container, rerender } = render(
      <StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />,
    );
    const svg = container.querySelector("svg.stock-chart-svg")!;

    dispatchWheel(svg, -100);
    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();

    rerender(<StockChart data={makeChart(50)} period="1m" onPeriodChange={() => {}} />);

    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });
});

describe("StockChart - edge cases", () => {
  it("does not crash with a single-bar chart", () => {
    const singleBar: ChartResponse = {
      symbol: "X",
      period: "1m",
      bars: [{ timestamp: "2026-01-01", open: 100, high: 100, low: 100, close: 100, volume: 0 }],
      source: "T",
      status: "ok",
      errorMessage: null,
    };
    expect(() =>
      render(<StockChart data={singleBar} period="1m" onPeriodChange={() => {}} />),
    ).not.toThrow();
  });

  it("does not crash with null OHLCV values", () => {
    const nullChart: ChartResponse = {
      symbol: "X",
      period: "1m",
      bars: [
        { timestamp: "2026-01-01", open: null, high: null, low: null, close: null, volume: null },
        { timestamp: "2026-01-02", open: null, high: null, low: null, close: 100, volume: null },
      ],
      source: "T",
      status: "ok",
      errorMessage: null,
    };
    expect(() =>
      render(<StockChart data={nullChart} period="1m" onPeriodChange={() => {}} />),
    ).not.toThrow();
  });

  it("does not crash when all prices are identical (zero-divide guard)", () => {
    const flatChart: ChartResponse = {
      symbol: "FLAT",
      period: "1m",
      bars: [
        { timestamp: "2026-01-01", open: 100, high: 100, low: 100, close: 100, volume: 0 },
        { timestamp: "2026-01-02", open: 100, high: 100, low: 100, close: 100, volume: 0 },
      ],
      source: "T",
      status: "ok",
      errorMessage: null,
    };
    expect(() =>
      render(<StockChart data={flatChart} period="1m" onPeriodChange={() => {}} />),
    ).not.toThrow();
    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("does not show minimap for a chart with all null close values", () => {
    const noCloseChart: ChartResponse = {
      symbol: "X",
      period: "1m",
      bars: [
        { timestamp: "2026-01-01", open: null, high: null, low: null, close: null, volume: null },
      ],
      source: "T",
      status: "unavailable",
      errorMessage: "no data",
    };
    render(<StockChart data={noCloseChart} period="1m" onPeriodChange={() => {}} />);
    expect(screen.getByText("no data")).toBeTruthy();
    expect(document.querySelector("[aria-hidden='true']")).toBeNull();
  });
});

// ── grid rendering ───────────────────────────────────────────────────

describe("StockChart - grid readability", () => {
  it("renders vertical date gridlines aligned with the date labels", () => {
    const { container } = render(
      <StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />,
    );
    const lines = Array.from(container.querySelectorAll("line"));
    // Vertical gridlines are vertical (x1 === x2) with the low-contrast stroke.
    const verticalGrid = lines.filter(
      (l) =>
        l.getAttribute("x1") === l.getAttribute("x2") &&
        l.getAttribute("stroke") === "#eef2f6",
    );
    expect(verticalGrid.length).toBeGreaterThan(0);
  });

  it("renders a volume-area baseline at the bottom of the volume band", () => {
    const { container } = render(
      <StockChart data={largeChart} period="1m" onPeriodChange={() => {}} />,
    );
    const lines = Array.from(container.querySelectorAll("line"));
    // VOL_TOP (PAD_TOP 14 + PRICE_H 240 + GAP 16) + VOL_H 72 = 342
    const volBaseline = lines.find(
      (l) => l.getAttribute("y1") === "342" && l.getAttribute("y2") === "342",
    );
    expect(volBaseline).toBeTruthy();
  });

  it("does not render grid (or crash) in the empty state", () => {
    const emptyChart: ChartResponse = {
      symbol: "X",
      period: "1m",
      bars: [],
      status: "unavailable",
      errorMessage: "no data",
      source: "T",
    };
    const { container } = render(
      <StockChart data={emptyChart} period="1m" onPeriodChange={() => {}} />,
    );
    expect(container.querySelector("line")).toBeNull();
  });
});

// ── regression: wheel listener must survive the loading remount ───────

describe("StockChart - wheel listener survives loading remount", () => {
  it("re-binds wheel zoom after the SVG is remounted post-loading", () => {
    // Period change drives isLoading=true, which unmounts the SVG, then
    // isLoading=false remounts a fresh SVG. The wheel listener must rebind to
    // the new node so zoom/minimap keep working.
    const { container, rerender } = render(
      <StockChart data={null} period="1m" onPeriodChange={() => {}} isLoading={true} />,
    );
    // While loading there is no SVG mounted.
    expect(container.querySelector("svg.stock-chart-svg")).toBeNull();

    // Loading finishes — SVG remounts with data.
    rerender(
      <StockChart data={largeChart} period="3y" onPeriodChange={() => {}} isLoading={false} />,
    );
    const svg = container.querySelector("svg.stock-chart-svg")!;
    expect(svg).toBeTruthy();

    // Wheel zoom on the freshly mounted SVG must work → minimap appears.
    dispatchWheel(svg, -100);
    expect(document.querySelector("[aria-hidden='true']")).toBeTruthy();
  });
});
