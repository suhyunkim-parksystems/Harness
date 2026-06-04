import type { MarketStatus } from "../types/market";

const statusLabels: Record<MarketStatus, string> = {
  ok: "정상",
  stale: "지연",
  unavailable: "불가"
};

interface StatusBadgeProps {
  status: MarketStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${status}`}>{statusLabels[status]}</span>;
}
