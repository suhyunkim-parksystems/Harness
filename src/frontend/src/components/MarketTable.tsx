import type { MarketItem } from "../types/market";
import { StatusBadge } from "./StatusBadge";

interface MarketTableProps {
  items: MarketItem[];
}

export function MarketTable({ items }: MarketTableProps) {
  return (
    <div className="table-shell">
      <table className="market-table">
        <thead>
          <tr>
            <th>종목</th>
            <th>현재가</th>
            <th>변동</th>
            <th>기준 시각</th>
            <th>소스</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id} className={item.status === "unavailable" ? "row-muted" : undefined}>
              <td>
                <div className="instrument-name">{item.name}</div>
                <div className="instrument-meta">
                  {item.region} · {item.symbol.toUpperCase()}
                </div>
                {item.errorMessage ? <div className="row-message">{item.errorMessage}</div> : null}
              </td>
              <td className="numeric-cell">{formatValue(item.value, item.currency)}</td>
              <td className={`numeric-cell ${toChangeClass(item.change)}`}>
                <span>{formatChange(item.change)}</span>
                <span className="percent-value">{formatPercent(item.changePercent)}</span>
              </td>
              <td>{formatDate(item.asOf)}</td>
              <td>{item.source}</td>
              <td>
                <StatusBadge status={item.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatValue(value: number | null, currency: string): string {
  if (value === null) {
    return "N/A";
  }
  const digits = Math.abs(value) < 10 ? 4 : 2;
  return `${new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  }).format(value)} ${currency}`;
}

function formatChange(value: number | null): string {
  if (value === null) {
    return "N/A";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: 2
  }).format(value)}`;
}

function formatPercent(value: number | null): string {
  if (value === null) {
    return "";
  }
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatDate(value: string | null): string {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "N/A";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function toChangeClass(value: number | null): string {
  if (value === null || value === 0) {
    return "change-flat";
  }
  return value > 0 ? "change-up" : "change-down";
}
