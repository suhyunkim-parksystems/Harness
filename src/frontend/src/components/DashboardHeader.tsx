import { Activity, Clock, Pause, Play, RefreshCcw } from "lucide-react";

interface DashboardHeaderProps {
  generatedAt: string | null;
  isRefreshing: boolean;
  autoRefresh: boolean;
  onRefresh: () => void;
  onToggleAutoRefresh: () => void;
}

export function DashboardHeader({
  generatedAt,
  isRefreshing,
  autoRefresh,
  onRefresh,
  onToggleAutoRefresh
}: DashboardHeaderProps) {
  return (
    <header className="dashboard-header">
      <div>
        <div className="eyebrow">
          <Activity size={16} aria-hidden="true" />
          실시간 시장 현황
        </div>
        <h1>주식·환율 대시보드</h1>
        <div className="updated-at">
          <Clock size={15} aria-hidden="true" />
          <span>{generatedAt ? formatGeneratedAt(generatedAt) : "업데이트 대기 중"}</span>
        </div>
      </div>
      <div className="header-actions">
        <button
          className="icon-button"
          type="button"
          onClick={onToggleAutoRefresh}
          title={autoRefresh ? "자동 새로고침 끄기" : "자동 새로고침 켜기"}
          aria-label={autoRefresh ? "자동 새로고침 끄기" : "자동 새로고침 켜기"}
        >
          {autoRefresh ? <Pause size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />}
        </button>
        <button
          className="action-button"
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="새로고침"
        >
          <RefreshCcw size={17} aria-hidden="true" className={isRefreshing ? "spin" : undefined} />
          <span>{isRefreshing ? "갱신 중" : "새로고침"}</span>
        </button>
      </div>
    </header>
  );
}

function formatGeneratedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "업데이트 시각 확인 불가";
  }
  return `업데이트 ${new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(date)}`;
}
