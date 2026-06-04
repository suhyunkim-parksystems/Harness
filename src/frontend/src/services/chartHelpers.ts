import type { ChartPeriod } from "../types/market";

export const MIN_BARS = 10;

export function clampRange(
  start: number,
  end: number,
  total: number,
): { start: number; end: number } {
  if (total === 0) return { start: 0, end: 0 };
  const numVisible = end - start + 1;
  const safeNumVisible = Math.min(numVisible, total);
  const clampedStart = Math.max(0, Math.min(total - safeNumVisible, start));
  return { start: clampedStart, end: clampedStart + safeNumVisible - 1 };
}

export function computeZoomRange(
  start: number,
  end: number,
  total: number,
  deltaY: number,
  pivotRatio: number,
): { start: number; end: number } {
  if (total === 0) return { start: 0, end: 0 };
  if (deltaY === 0) return { start, end };
  const numVisible = end - start + 1;
  const factor = deltaY > 0 ? 1.15 : 1 / 1.15;
  const minBars = Math.min(MIN_BARS, total);
  const newNumVisible = Math.max(minBars, Math.min(total, Math.round(numVisible * factor)));
  const pivotIdx = start + pivotRatio * (numVisible - 1);
  const newStart = Math.round(pivotIdx - pivotRatio * (newNumVisible - 1));
  return clampRange(newStart, newStart + newNumVisible - 1, total);
}

export function computePanRange(
  dragStartView: { start: number; end: number },
  shiftBars: number,
  total: number,
): { start: number; end: number } {
  const numVisible = dragStartView.end - dragStartView.start + 1;
  const newStart = dragStartView.start + shiftBars;
  return clampRange(newStart, newStart + numVisible - 1, total);
}

export function formatDateLabel(timestamp: string, period: ChartPeriod): string {
  if (period === "3y" || period === "5y" || period === "10y") {
    return timestamp.slice(0, 4);
  }
  if (period === "1y" || period === "ytd") {
    return timestamp.slice(0, 7);
  }
  return timestamp.slice(5);
}

export function sampleIndices(total: number, count: number): number[] {
  if (total <= 0) return [];
  if (count <= 1) return [0];
  if (total <= count) return Array.from({ length: total }, (_, i) => i);
  return Array.from({ length: count }, (_, i) => Math.round((i * (total - 1)) / (count - 1)));
}

export function buildMinimapPath(
  closes: number[],
  mmX: number,
  mmYTop: number,
  mmW: number,
  mmH: number,
): string {
  if (closes.length < 2) return "";
  const minC = closes.reduce((m, v) => (v < m ? v : m), closes[0]);
  const maxC = closes.reduce((m, v) => (v > m ? v : m), closes[0]);
  const range = maxC === minC ? 1 : maxC - minC;
  const padding = range * 0.05;
  const pMin = minC - padding;
  const pRange = range + 2 * padding;

  function scaleY(price: number): number {
    return mmYTop + mmH * (1 - (price - pMin) / pRange);
  }

  const n = closes.length;
  const pts = closes
    .map((c, i) => `${(mmX + (i / (n - 1)) * mmW).toFixed(1)},${scaleY(c).toFixed(1)}`)
    .join(" L ");

  return `M ${mmX.toFixed(1)},${(mmYTop + mmH).toFixed(1)} L ${pts} L ${(mmX + mmW).toFixed(1)},${(mmYTop + mmH).toFixed(1)} Z`;
}
