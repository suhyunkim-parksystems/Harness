import { StatusBadge } from "./StatusBadge";
import type { StockDetail } from "../types/market";

interface StockDetailPanelProps {
  detail: StockDetail;
}

export function StockDetailPanel({ detail }: StockDetailPanelProps) {
  const changeClass =
    detail.change == null ? "" : detail.change > 0 ? "change-up" : detail.change < 0 ? "change-down" : "change-flat";

  return (
    <div className="stock-detail-panel">
      <div className="stock-detail-header">
        <div className="stock-detail-title-row">
          <h2 className="stock-detail-name">{detail.name}</h2>
          <StatusBadge status={detail.status} />
        </div>
        <div className="stock-detail-meta-row">
          <span className="stock-detail-symbol">{detail.symbol}</span>
          <span className="stock-detail-meta-tag">{detail.market}</span>
          <span className="stock-detail-meta-tag">{detail.assetType}</span>
          <span className="stock-detail-meta-tag">{detail.exchange}</span>
          <span className="stock-detail-meta-tag">{detail.currency}</span>
        </div>
      </div>

      {detail.status === "stale" && (
        <div className="detail-notice detail-notice--stale" role="status">
          캐시된 데이터를 표시합니다. 실시간 조회가 지연될 수 있습니다.
        </div>
      )}
      {detail.status === "unavailable" && detail.errorMessage && (
        <div className="detail-notice detail-notice--error" role="alert">
          {detail.errorMessage}
        </div>
      )}

      <div className="stock-detail-grid">
        <DetailRow label="현재가" value={formatPrice(detail.currentPrice, detail.currency)} className={changeClass} />
        <DetailRow
          label="등락"
          value={
            detail.change != null && detail.changePercent != null
              ? `${formatSign(detail.change)}${formatNum(Math.abs(detail.change))} (${formatSign(detail.changePercent)}${formatNum(Math.abs(detail.changePercent))}%)`
              : "N/A"
          }
          className={changeClass}
        />
        <DetailRow label="시가" value={formatPrice(detail.openPrice, detail.currency)} />
        <DetailRow label="고가" value={formatPrice(detail.highPrice, detail.currency)} />
        <DetailRow label="저가" value={formatPrice(detail.lowPrice, detail.currency)} />
        <DetailRow label="전일 종가" value={formatPrice(detail.prevClose, detail.currency)} />
        <DetailRow label="거래량" value={detail.volume != null ? detail.volume.toLocaleString() : "N/A"} />
        <DetailRow label="기준 시각" value={detail.asOf ? formatDateTime(detail.asOf) : "N/A"} />
        <DetailRow label="데이터 출처" value={detail.source} />
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="detail-row">
      <span className="detail-label">{label}</span>
      <span className={`detail-value numeric-cell${className ? ` ${className}` : ""}`}>{value}</span>
    </div>
  );
}

function formatPrice(value: number | null, currency: string): string {
  if (value == null) return "N/A";
  const symbol = currency === "KRW" ? "₩" : currency === "USD" ? "$" : `${currency} `;
  const decimals = currency === "KRW" ? 0 : 2;
  return `${symbol}${value.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function formatNum(value: number): string {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatSign(value: number): string {
  return value >= 0 ? "+" : "";
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(d);
}
