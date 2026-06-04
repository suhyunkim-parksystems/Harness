import { useCallback, useEffect, useRef, useState } from "react";

import type { ChartBar, ChartResponse, ChartPeriod } from "../types/market";
import {
  buildMinimapPath,
  computePanRange,
  computeZoomRange,
  formatDateLabel,
  sampleIndices,
} from "../services/chartHelpers";

const PERIODS: { id: ChartPeriod; label: string }[] = [
  { id: "1m", label: "1M" },
  { id: "3m", label: "3M" },
  { id: "6m", label: "6M" },
  { id: "1y", label: "1Y" },
  { id: "3y", label: "3Y" },
  { id: "5y", label: "5Y" },
  { id: "10y", label: "10Y" },
  { id: "ytd", label: "YTD" },
];

// SVG layout constants (viewBox 800 x 380)
const VB_WIDTH = 800;
const VB_HEIGHT = 380;
const PAD_LEFT = 72;
const PAD_RIGHT = 12;
const PAD_TOP = 14;
const PAD_BOTTOM = 22;
const PRICE_H = 240;
const VOL_H = 72;
const GAP = 16;

const CHART_W = VB_WIDTH - PAD_LEFT - PAD_RIGHT;
const VOL_TOP = PAD_TOP + PRICE_H + GAP;

// Minimap: overlaid on the lower-right of the price chart area
const MM_W = 160;
const MM_H = 48;
const MM_X = VB_WIDTH - PAD_RIGHT - MM_W - 4;
const MM_Y = PAD_TOP + PRICE_H - MM_H - 8;

// Suppress unused constant lint; PAD_BOTTOM is kept for layout documentation
void PAD_BOTTOM;

interface StockChartProps {
  data: ChartResponse | null;
  period: ChartPeriod;
  onPeriodChange: (p: ChartPeriod) => void;
  isLoading?: boolean;
  category?: string;
}

export function StockChart({ data, period, onPeriodChange, isLoading, category }: StockChartProps) {
  const isKorean = category === "kr_stock" || category === "kr_etf";

  // svgRef mirrors the current SVG DOM node for imperative reads (pointer math).
  // svgNode drives the wheel-listener effect so it re-binds whenever the SVG is
  // unmounted/remounted (e.g. the loading branch swaps the SVG out and back in
  // after a period change). A plain ref alone would not re-run the effect.
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [svgNode, setSvgNode] = useState<SVGSVGElement | null>(null);
  const setSvgRef = useCallback((node: SVGSVGElement | null) => {
    svgRef.current = node;
    setSvgNode(node);
  }, []);

  // null = "show full range" sentinel; set when data/period changes
  const [view, setView] = useState<{ start: number; end: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartXRef = useRef(0);
  const dragStartViewRef = useRef({ start: 0, end: 0 });

  // Mutable refs for the wheel handler closure to avoid stale captures
  const viewRef = useRef<{ start: number; end: number }>({ start: 0, end: 0 });
  const totalBarsRef = useRef(0);

  const validBars = (data?.bars ?? []).filter(
    (b): b is ChartBar & { close: number } => b.close != null,
  );
  const totalBars = validBars.length;

  // Compute safe view bounds: clamp view to actual data range
  const safeStart =
    view !== null ? Math.max(0, Math.min(view.start, Math.max(0, totalBars - 1))) : 0;
  const safeEnd =
    view !== null
      ? Math.max(safeStart, Math.min(view.end, Math.max(0, totalBars - 1)))
      : Math.max(0, totalBars - 1);

  const isZoomed = totalBars > 1 && safeEnd - safeStart + 1 < totalBars;

  // Keep refs current for the wheel handler
  viewRef.current = { start: safeStart, end: safeEnd };
  totalBarsRef.current = totalBars;

  // Reset zoom/pan when data or period changes
  useEffect(() => {
    setView(null);
    setIsDragging(false);
  }, [data, period]);

  // Wheel event must be registered imperatively to use { passive: false }.
  // Depends on svgNode so the listener is rebound to each new SVG node — when
  // the SVG is remounted (loading branch after a period change), the old node's
  // listener is cleaned up and the fresh node gets a new one.
  useEffect(() => {
    const svg = svgNode;
    if (!svg) return;

    function onWheel(e: WheelEvent) {
      e.preventDefault();
      const total = totalBarsRef.current;
      if (total === 0) return;

      const { start, end } = viewRef.current;
      const svgRect = svg!.getBoundingClientRect();
      const chartLeftPx = (PAD_LEFT / VB_WIDTH) * svgRect.width;
      const chartRightPx = ((VB_WIDTH - PAD_RIGHT) / VB_WIDTH) * svgRect.width;
      const denominator = chartRightPx - chartLeftPx;
      const raw = denominator !== 0 ? (e.clientX - svgRect.left - chartLeftPx) / denominator : 0.5;
      const pivotRatio = Number.isFinite(raw) ? Math.max(0, Math.min(1, raw)) : 0.5;

      setView(computeZoomRange(start, end, total, e.deltaY, pivotRatio));
    }

    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [svgNode]);

  function handlePointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (!isZoomed) return;
    setIsDragging(true);
    dragStartXRef.current = e.clientX;
    dragStartViewRef.current = { start: safeStart, end: safeEnd };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Ignore in environments that do not support pointer capture
    }
  }

  function handlePointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!isDragging) return;
    const svgRect = svgRef.current?.getBoundingClientRect();
    if (!svgRect) return;
    const numVisible = dragStartViewRef.current.end - dragStartViewRef.current.start + 1;
    const chartWidthPx = ((VB_WIDTH - PAD_LEFT - PAD_RIGHT) / VB_WIDTH) * svgRect.width;
    const pxPerBar = chartWidthPx > 0 ? chartWidthPx / numVisible : 1;
    const shiftBars = Math.round(-(e.clientX - dragStartXRef.current) / pxPerBar);
    setView(computePanRange(dragStartViewRef.current, shiftBars, totalBars));
  }

  function handlePointerUp() {
    setIsDragging(false);
  }

  const periodButtons = (
    <div className="chart-period-selector" role="group" aria-label="차트 기간 선택">
      {PERIODS.map((p) => (
        <button
          key={p.id}
          type="button"
          className={`period-btn${period === p.id ? " period-btn--active" : ""}`}
          onClick={() => onPeriodChange(p.id)}
          aria-pressed={period === p.id}
        >
          {p.label}
        </button>
      ))}
    </div>
  );

  if (isLoading) {
    return (
      <div className="chart-panel">
        {periodButtons}
        <div className="chart-empty chart-empty--loading">차트 로딩 중...</div>
      </div>
    );
  }

  if (!validBars.length) {
    return (
      <div className="chart-panel">
        {periodButtons}
        <div className="chart-empty">
          {data?.status === "unavailable"
            ? (data.errorMessage ?? "차트 데이터를 불러올 수 없습니다.")
            : "차트 데이터가 없습니다."}
        </div>
      </div>
    );
  }

  const visibleBars = validBars.slice(safeStart, safeEnd + 1);
  const n = visibleBars.length || 1;
  const barWidth = CHART_W / n;
  const bodyW = Math.max(barWidth * 0.65, 1);

  // Price scale — based on visible bars (dynamic on zoom)
  const highs = visibleBars.map((b) => b.high ?? b.close);
  const lows = visibleBars.map((b) => b.low ?? b.close);
  const maxP = highs.reduce((m, v) => (v > m ? v : m), highs[0]);
  const minP = lows.reduce((m, v) => (v < m ? v : m), lows[0]);
  const rawRange = maxP - minP;
  const pricePad = rawRange === 0 ? Math.max(maxP * 0.05, 1) : rawRange * 0.05;
  const pMax = maxP + pricePad;
  const pMin = minP - pricePad;
  const pRange = pMax - pMin;

  function toY(price: number): number {
    return PAD_TOP + PRICE_H * (1 - (price - pMin) / pRange);
  }

  // Volume scale — based on visible bars
  const vols = visibleBars.map((b) => b.volume ?? 0);
  const maxVol = Math.max(vols.reduce((m, v) => (v > m ? v : m), 0), 1);

  function toVolY(vol: number): number {
    return VOL_TOP + VOL_H * (1 - vol / maxVol);
  }

  // Y-axis price labels (5 ticks)
  const tickCount = 5;
  const priceTicks: number[] = Array.from({ length: tickCount }, (_, i) =>
    pMin + (pRange * i) / (tickCount - 1),
  );

  // Shared sample positions: vertical grid lines and date labels use the same
  // indices so the gridlines line up exactly under the date labels.
  const labelIndices = sampleIndices(visibleBars.length, 5);

  // Minimap calculations (based on full validBars, not just visible)
  const mmCloses = validBars.map((b) => b.close);
  const minimapPath = buildMinimapPath(mmCloses, MM_X, MM_Y, MM_W, MM_H);
  const mmBarW = totalBars > 1 ? MM_W / totalBars : MM_W;
  const mmViewX = MM_X + safeStart * mmBarW;
  const mmViewW = Math.max((safeEnd - safeStart + 1) * mmBarW, 2);

  const cursorClass = isZoomed ? (isDragging ? "stock-chart-svg--grabbing" : "stock-chart-svg--grab") : "";

  return (
    <div className="chart-panel">
      {periodButtons}
      <svg
        ref={setSvgRef}
        viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
        width="100%"
        height={VB_HEIGHT}
        role="img"
        aria-label={`${data?.symbol ?? ""} 가격 차트`}
        className={`stock-chart-svg${cursorClass ? ` ${cursorClass}` : ""}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        {/* Grid lines */}
        {priceTicks.map((tick) => {
          const y = toY(tick);
          return (
            <g key={tick}>
              <line
                x1={PAD_LEFT}
                y1={y}
                x2={VB_WIDTH - PAD_RIGHT}
                y2={y}
                stroke="#e4ebf1"
                strokeWidth={1}
              />
              <text x={PAD_LEFT - 4} y={y + 4} textAnchor="end" fontSize={10} fill="#8896a4">
                {tick >= 1000 ? tick.toFixed(0) : tick.toFixed(2)}
              </text>
            </g>
          );
        })}

        {/* Vertical date gridlines — aligned with the date labels below */}
        {labelIndices.map((i) => {
          const x = PAD_LEFT + i * barWidth + barWidth / 2;
          return (
            <line
              key={`vgrid-${i}`}
              x1={x}
              y1={PAD_TOP}
              x2={x}
              y2={PAD_TOP + PRICE_H}
              stroke="#eef2f6"
              strokeWidth={1}
            />
          );
        })}

        {/* Volume area baseline + auxiliary gridline (kept lighter than the price
            grid so it frames the volume bars without competing with them) */}
        <line
          x1={PAD_LEFT}
          y1={VOL_TOP}
          x2={VB_WIDTH - PAD_RIGHT}
          y2={VOL_TOP}
          stroke="#eef2f6"
          strokeWidth={1}
        />
        <line
          x1={PAD_LEFT}
          y1={VOL_TOP + VOL_H / 2}
          x2={VB_WIDTH - PAD_RIGHT}
          y2={VOL_TOP + VOL_H / 2}
          stroke="#f1f5f9"
          strokeWidth={1}
        />
        <line
          x1={PAD_LEFT}
          y1={VOL_TOP + VOL_H}
          x2={VB_WIDTH - PAD_RIGHT}
          y2={VOL_TOP + VOL_H}
          stroke="#e4ebf1"
          strokeWidth={1}
        />

        {/* Volume area label */}
        <text
          x={PAD_LEFT - 4}
          y={VOL_TOP + VOL_H / 2 + 4}
          textAnchor="end"
          fontSize={9}
          fill="#8896a4"
        >
          거래량
        </text>

        {/* Candlesticks + Volume bars */}
        {visibleBars.map((bar, i) => {
          const xCenter = PAD_LEFT + i * barWidth + barWidth / 2;
          const xBody = xCenter - bodyW / 2;

          const open = bar.open ?? bar.close;
          const high = bar.high ?? bar.close;
          const low = bar.low ?? bar.close;
          const close = bar.close;
          const isUp = close >= open;
          const color = isKorean
            ? isUp
              ? "#dc2626"
              : "#1d4ed8"
            : isUp
              ? "#16a34a"
              : "#dc2626";

          const bodyTop = toY(Math.max(open, close));
          const bodyBot = toY(Math.min(open, close));
          const bodyHeight = Math.max(bodyBot - bodyTop, 1);
          const wickTop = toY(high);
          const wickBot = toY(low);

          const vol = bar.volume ?? 0;
          const volTop = toVolY(vol);
          const volHeight = Math.max(VOL_TOP + VOL_H - volTop, 1);
          const volColor = isKorean
            ? isUp
              ? "#fecaca"
              : "#bfdbfe"
            : isUp
              ? "#bbf7d0"
              : "#fecaca";

          return (
            <g key={bar.timestamp}>
              {/* Wick */}
              <line
                x1={xCenter}
                y1={wickTop}
                x2={xCenter}
                y2={wickBot}
                stroke={color}
                strokeWidth={1}
              />
              {/* Body */}
              <rect x={xBody} y={bodyTop} width={bodyW} height={bodyHeight} fill={color} />
              {/* Volume bar */}
              <rect x={xBody} y={volTop} width={bodyW} height={volHeight} fill={volColor} />
            </g>
          );
        })}

        {/* Date labels — show ~5 evenly spaced (shares labelIndices with gridlines) */}
        {labelIndices.map((i) => {
          const bar = visibleBars[i];
          const x = PAD_LEFT + i * barWidth + barWidth / 2;
          return (
            <text
              key={bar.timestamp}
              x={x}
              y={VB_HEIGHT - 4}
              textAnchor="middle"
              fontSize={10}
              fill="#8896a4"
            >
              {formatDateLabel(bar.timestamp, period)}
            </text>
          );
        })}

        {/* Minimap — shown only when zoomed in */}
        {isZoomed && minimapPath && (
          <g aria-hidden="true">
            {/* Background */}
            <rect
              x={MM_X - 1}
              y={MM_Y - 1}
              width={MM_W + 2}
              height={MM_H + 2}
              fill="rgba(255,255,255,0.92)"
              stroke="#d1d5db"
              strokeWidth={0.5}
              rx={3}
            />
            {/* Full-range area path */}
            <path
              d={minimapPath}
              fill="rgba(99,102,241,0.15)"
              stroke="#6366f1"
              strokeWidth={0.5}
            />
            {/* Viewport highlight rect */}
            <rect
              x={mmViewX}
              y={MM_Y}
              width={mmViewW}
              height={MM_H}
              fill="rgba(99,102,241,0.2)"
              stroke="#4f46e5"
              strokeWidth={1}
            />
          </g>
        )}
      </svg>
    </div>
  );
}
